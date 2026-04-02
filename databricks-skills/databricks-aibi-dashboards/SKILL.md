---
name: databricks-aibi-dashboards
description: "Create Databricks AI/BI dashboards. Use when creating, updating, or deploying Lakeview dashboards. CRITICAL: You MUST test ALL SQL queries via execute_sql BEFORE deploying. Follow guidelines strictly."
---

# AI/BI Dashboard Skill

Create Databricks AI/BI dashboards (formerly Lakeview dashboards). **Follow these guidelines strictly.**

## CRITICAL: Widget Version Requirements

> **Wrong version = broken widget!** This is the #1 cause of dashboard errors.

| Widget Type | Version | Notes |
|-------------|---------|-------|
| `counter` | **2** | KPI cards |
| `table` | **2** | Data tables |
| `bar`, `line`, `area`, `pie` | **3** | Charts |
| `filter-*` | **2** | All filter types |

---

## CRITICAL: MANDATORY VALIDATION WORKFLOW

**You MUST follow this workflow exactly. Skipping validation causes broken dashboards.**

```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Get table schemas via get_table_stats_and_schema(catalog, schema)  │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 2: Write SQL queries for each dataset                        │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 3: TEST EVERY QUERY via execute_sql() ← DO NOT SKIP!         │
│          - If query fails, FIX IT before proceeding                │
│          - Verify column names match what widgets will reference   │
│          - Verify data types are correct (dates, numbers, strings) │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 4: Write dashboard JSON to LOCAL FILE (e.g., ./dashboard.json)        │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 5: Deploy via manage_dashboard(dashboard_file_path="./dashboard.json") │
│          - To update: edit the local file, then call manage_dashboard again │
└─────────────────────────────────────────────────────────────────────┘
```

**WARNING: If you deploy without testing queries, widgets WILL show "Invalid widget definition" errors!**

## CRITICAL: Verify Data Matches Story

Before finalizing, run validation queries to confirm the data tells the intended story:
```sql
-- Example: Verify spike is visible
SELECT
  CASE WHEN date < '2025-02-17' THEN 'Before' ELSE 'After' END as period,
  AVG(total_returns_usd) as avg_daily_returns
FROM gold_daily_summary
GROUP BY 1;
-- Should show significant difference between periods
```

If values don't match expectations (e.g., "spike should be 3x normal" but data shows 1.5x), fix the data generation before creating the dashboard.

---

## Design Best Practices

Apply unless user specifies otherwise (adapt to the use-case/project):

- **Global date filter**: When data has temporal columns, add a date range filter. Most dashboards need time-based filtering.
- **KPI time bounds**: Use time-bounded metrics that enable period comparison (MoM, YoY). Unbounded "all-time" totals are less actionable.
- **Value formatting**: Format values based on their meaning — currency with symbol, percentages with %, large numbers compacted (K/M/B).
- **Chart selection**: Match cardinality to chart type. Few distinct values → pie/bar with color grouping; many values → table.

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `get_table_stats_and_schema` | **STEP 1**: Get table schemas for designing queries |
| `execute_sql` | **STEP 3**: Test SQL queries - MANDATORY before deployment! |
| `manage_warehouse` (action="get_best") | Get available warehouse ID |
| `manage_dashboard` | **STEP 5**: Dashboard lifecycle management (see actions below) |

### manage_dashboard Actions

| Action | Description | Required Params |
|--------|-------------|-----------------|
| `create_or_update` | Deploy dashboard from local JSON file (only after validation!) | display_name, parent_path, dashboard_file_path, warehouse_id |
| `get` | Get dashboard details by ID | dashboard_id |
| `list` | List all dashboards | (none) |
| `delete` | Move dashboard to trash | dashboard_id |
| `publish` | Publish a dashboard | dashboard_id, warehouse_id |
| `unpublish` | Unpublish a dashboard | dashboard_id |

**Optional create_or_update params:**
| Param | Description |
|-------|-------------|
| `publish` | Auto-publish after create (default: True) |
| `genie_space_id` | Link a Genie space to enable "Ask Genie" button on the dashboard |
| `catalog` | Default catalog for unqualified table names in dataset SQL |
| `schema` | Default schema for unqualified table names in dataset SQL |

> **Note:** `catalog`/`schema` only affect unqualified table names. Fully-qualified names (`catalog.schema.table`) are unaffected.

**File-based workflow (recommended):**
1. Write dashboard JSON to a local file (e.g., `./sales_dashboard.json`)
2. Deploy using `manage_dashboard(dashboard_file_path="./sales_dashboard.json", ...)`
3. To update: edit the local file, then call `manage_dashboard` again

**Example usage:**
```python
# Deploy dashboard from local file
manage_dashboard(
    action="create_or_update",
    display_name="Sales Dashboard",
    parent_path="/Workspace/Users/{user_email}/my_project/dashboards",
    dashboard_file_path="./sales_dashboard.json",
    warehouse_id="abc123",
    genie_space_id="genie_space_id_123"  # optional: link Genie for Q&A
)

# To update: edit ./sales_dashboard.json, then call manage_dashboard again

# Get dashboard details
manage_dashboard(action="get", dashboard_id="dashboard_123")

# List all dashboards
manage_dashboard(action="list")
```

## CRITICAL: Check JSON Structure Before Writing

> **If you're unsure about the exact JSON structure for any widget, ALWAYS read these files first:**
> - [1-widget-specifications.md](1-widget-specifications.md) - Widget definitions and encoding patterns
> - [4-examples.md](4-examples.md) - Complete working dashboard template

**Do NOT guess the JSON structure.** Wrong field names or missing properties cause broken widgets.

## Reference Files

| What are you building? | Reference |
|------------------------|-----------|
| Any widget | [1-widget-specifications.md](1-widget-specifications.md) (version table lists all widgets) |
| Dashboard with filters | [3-filters.md](3-filters.md) |
| Complete working template | [4-examples.md](4-examples.md) |
| Debugging errors | [5-troubleshooting.md](5-troubleshooting.md) |

---

## Implementation Guidelines

### 1) DATASET ARCHITECTURE

- **One dataset per domain whenever possible** (e.g., orders, customers, products). Dataset shared on widget will benefit the same filter, reuse the same base dataset as much as possible (adding group by at the widget level for example)
- **Exactly ONE valid SQL query per dataset** (no multiple queries separated by `;`)
- Always use **fully-qualified table names**: `catalog.schema.table_name`
- SELECT must include all dimensions needed by widgets and all derived columns via `AS` aliases
- Put ALL business logic (CASE/WHEN, COALESCE, ratios) into the dataset SELECT with explicit aliases
- **Contract rule**: Every widget `fieldName` must exactly match a dataset column or alias

### 2) WIDGET FIELD EXPRESSIONS

> **CRITICAL**: The `name` in `query.fields` MUST exactly match `fieldName` in `encodings`.
> Mismatch = "no selected fields to visualize" error.

```json
// CORRECT: names match
"fields": [{"name": "sum(spend)", "expression": "SUM(`spend`)"}]
"encodings": {"value": {"fieldName": "sum(spend)", ...}}

// WRONG: "spend" ≠ "sum(spend)"
"fields": [{"name": "spend", "expression": "SUM(`spend`)"}]
```

See [1-widget-specifications.md](1-widget-specifications.md) for full expression reference.

### 3) SPARK SQL PATTERNS

- Date math: `date_sub(current_date(), N)` for days, `add_months(current_date(), -N)` for months
- Date truncation: `DATE_TRUNC('DAY'|'WEEK'|'MONTH'|'QUARTER'|'YEAR', column)`
- **AVOID** `INTERVAL` syntax - use functions instead
- **Add ORDER BY** when visualization depends on data order:
  - Time series: `ORDER BY date` for chronological display
  - Rankings/Top-N: `ORDER BY metric DESC LIMIT 10` for "Top 10" charts
  - Categorical charts: `ORDER BY metric DESC` to show largest values first

### 4) LAYOUT (6-Column Grid, NO GAPS)

Each widget has a position: `{"x": 0, "y": 0, "width": 2, "height": 4}`

**CRITICAL**: Each row must fill width=6 exactly. No gaps allowed.

```
CORRECT:                          WRONG:
y=0: [w=6]                        y=0: [w=4]____  ← gap!
y=1: [w=2][w=2][w=2]  ← fills 6   y=1: [w=1][w=1][w=1][w=1]__  ← gap!
y=4: [w=3][w=3]       ← fills 6
```

| Widget Type | Width | Height | Notes |
|-------------|-------|--------|-------|
| Text header | 6 | 1 | Full width; use SEPARATE widgets for title and subtitle |
| Counter/KPI | 2 | **3-4** | **NEVER height=2** - too cramped! |
| Line/Bar/Area chart | 3 | **5-6** | Pair side-by-side to fill row |
| Pie chart | 3 | **5-6** | Needs space for legend |
| Full-width chart | 6 | 5-7 | For detailed time series |
| Table | 6 | 5-8 | Full width for readability |

**Standard dashboard structure:**
```text
y=0:  Title (w=6, h=1) - Dashboard title (use separate widget!)
y=1:  Subtitle (w=6, h=1) - Description (use separate widget!)
y=2:  KPIs (w=2 each, h=3) - 3 key metrics side-by-side
y=5:  Section header (w=6, h=1) - "Trends" or similar
y=6:  Charts (w=3 each, h=5) - Two charts side-by-side
y=11: Section header (w=6, h=1) - "Details"
y=12: Table (w=6, h=6) - Detailed data
```

### 5) CARDINALITY & READABILITY (CRITICAL)

**Dashboard readability depends on limiting distinct values.** These are guidelines - adjust based on your use case:

| Dimension Type | Suggested Max | Examples |
|----------------|---------------|----------|
| Chart color/groups | ~3-8 values | 4 regions, 5 product lines, 3 tiers |
| Filter dropdowns | ~4-15 values | 8 countries, 5 channels |
| High cardinality | Use table widget | customer_id, order_id, SKU |

**Before creating any chart with color/grouping:**
1. Check column cardinality (use `get_table_stats_and_schema` to see distinct values)
2. If too many distinct values, aggregate to higher level OR use TOP-N + "Other" bucket
3. For high-cardinality dimensions, use a table widget instead of a chart

### 6) QUALITY CHECKLIST

Before deploying, verify:
1. All widget names use only alphanumeric + hyphens + underscores
2. All rows sum to width=6 with no gaps
3. KPIs use height 3-4, charts use height 5-6
4. Chart dimensions have reasonable cardinality (see guidance above)
5. All widget fieldNames match dataset columns exactly
6. **Field `name` in query.fields matches `fieldName` in encodings exactly** (e.g., both `"sum(spend)"`)
7. Counter datasets: use `disaggregated: true` for 1-row datasets, `disaggregated: false` with aggregation for multi-row
8. Percent values are 0-1 (not 0-100)
9. SQL uses Spark syntax (date_sub, not INTERVAL)
10. **All SQL queries tested via `execute_sql` and return expected data**

---

## Related Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - for querying the underlying data and system tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - for building the data pipelines that feed dashboards
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - for scheduling dashboard data refreshes
