---
name: databricks-aibi-dashboards
description: "Create Databricks AI/BI dashboards. Must use when creating, updating, or deploying Lakeview dashboards as Databricks Dashboard have a unique json structure. CRITICAL: You MUST test ALL SQL queries via CLI BEFORE deploying. Follow guidelines strictly."
---

# AI/BI Dashboard Skill

Create Databricks AI/BI dashboards (formerly Lakeview dashboards).
A dashboard should be showing something relevant for a human, typically some KPI on the top, and based on the story, some graph (often temporal), and we see "something happens".
**Follow these guidelines strictly.**

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
│  STEP 1: Get table schemas via discover-schema                      │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 2: Write SQL queries for each dataset                        │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 3: TEST EVERY QUERY via CLI ← DO NOT SKIP!                   │
│          - If query fails, FIX IT before proceeding                │
│          - Verify column names match what widgets will reference   │
│          - Verify data types are correct (dates, numbers, strings) │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 4: Build dashboard JSON (serialized_dashboard content)       │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 5: Deploy via databricks lakeview create                     │
└─────────────────────────────────────────────────────────────────────┘
```

**WARNING: If you deploy without testing queries, widgets WILL show "Invalid widget definition" errors!**

## CLI Commands

### Step 1: Discover Table Schemas

```bash
# Get table schemas for designing queries
# IMPORTANT: Use CATALOG.SCHEMA.TABLE format (full 3-part name required)
databricks experimental aitools tools discover-schema catalog.schema.table1 catalog.schema.table2

# Example:
databricks experimental aitools tools discover-schema samples.nyctaxi.trips main.default.customers

# Explore data patterns if needed (to understand what to visualize):
databricks experimental aitools tools query --warehouse WAREHOUSE_ID "SELECT DISTINCT status FROM catalog.schema.orders"
```

### Step 2: Get Warehouse ID

```bash
# List warehouses to find one for SQL execution
databricks warehouses list
```

### Step 3: Test SQL Queries

```bash
# Test SQL queries - MANDATORY before deployment!
databricks experimental aitools tools query --warehouse WAREHOUSE_ID "SELECT COUNT(*) FROM catalog.schema.table"

# Test aggregations that will be used in widgets:
databricks experimental aitools tools query --warehouse WAREHOUSE_ID "SELECT region, SUM(revenue) FROM catalog.schema.sales GROUP BY region"
```

### Step 4: Verify Data Matches Story

Before finalizing, run validation queries to confirm the data tells the intended story:
```bash
# Example: Verify a spike/trend is visible in the data
databricks experimental aitools tools query --warehouse WAREHOUSE_ID "
SELECT
  CASE WHEN date < '2025-02-17' THEN 'Before' ELSE 'After' END as period,
  AVG(metric) as avg_value
FROM catalog.schema.table
GROUP BY 1"
# Should show significant difference between periods if that's the story
```

If values don't match expectations, fix the data or adjust the story before creating the dashboard.

### Step 5: Dashboard Lifecycle

```bash
# Create a dashboard
# IMPORTANT: Use --display-name, --warehouse-id, and --serialized-dashboard (NOT --json @file.json with displayName in it)
databricks lakeview create \
  --display-name "My Dashboard" \
  --warehouse-id "abc123def456" \
  --serialized-dashboard "$(cat dashboard.json)"

# Alternative: Use --json with the correct structure
databricks lakeview create --json '{
  "display_name": "My Dashboard",
  "warehouse_id": "abc123def456",
  "serialized_dashboard": "{\"datasets\":[...],\"pages\":[...]}"
}'

# List all dashboards
databricks lakeview list

# Get dashboard details
databricks lakeview get DASHBOARD_ID

# Update a dashboard
databricks lakeview update DASHBOARD_ID --serialized-dashboard "$(cat dashboard.json)"

# Publish a dashboard
databricks lakeview publish DASHBOARD_ID --warehouse-id WAREHOUSE_ID

# Unpublish a dashboard
databricks lakeview unpublish DASHBOARD_ID

# Delete (trash) a dashboard
databricks lakeview trash DASHBOARD_ID
```

---

## JSON Structure (Required Skeleton)

Every dashboard's `serialized_dashboard` content must follow this exact structure:

```json
{
  "datasets": [
    {
      "name": "ds_x",
      "displayName": "Dataset X",
      "queryLines": ["SELECT col1, col2 ", "FROM catalog.schema.table"]
    }
  ],
  "pages": [
    {
      "name": "main",
      "displayName": "Main",
      "pageType": "PAGE_TYPE_CANVAS",
      "layout": [
        {"widget": {/* INLINE widget definition */}, "position": {"x":0,"y":0,"width":2,"height":3}}
      ]
    }
  ]
}
```

**Structural rules (violations cause "failed to parse serialized dashboard"):**
- `queryLines`: Array of strings, NOT `"query": "string"`
- Widgets: INLINE in `layout[].widget`, NOT a separate `"widgets"` array
- `pageType`: Required on every page (`PAGE_TYPE_CANVAS` or `PAGE_TYPE_GLOBAL_FILTERS`)
- Query binding: `query.fields[].name` must exactly match `encodings.*.fieldName`

### Linking a Genie Space (Optional)

To add an "Ask Genie" button to the dashboard, add `uiSettings.genieSpace` to the JSON:

```json
{
  "datasets": [...],
  "pages": [...],
  "uiSettings": {
    "genieSpace": {
      "isEnabled": true,
      "overrideId": "your-genie-space-id-here",
      "enablementMode": "ENABLED"
    }
  }
}
```

> **Genie is NOT a widget.** Link via `uiSettings.genieSpace` only. There is no `"widgetType": "assistant"`.

---

## Design Best Practices

Apply unless user specifies otherwise:

- **Global date filter**: When data has temporal columns, add a date range filter. Most dashboards need time-based filtering.
- **KPI time bounds**: Use time-bounded metrics that enable period comparison (MoM, YoY). Unbounded "all-time" totals are less actionable.
- **Value formatting**: Format values based on their meaning — currency with symbol, percentages with %, large numbers compacted (K/M/B).
- **Chart selection**: Match cardinality to chart type. Few distinct values → pie/bar with color grouping; many values → table.

## Reference Files

| What are you building? | Reference |
|------------------------|-----------|
| Any widget (text, counter, table, chart) | [1-widget-specifications.md](1-widget-specifications.md) |
| Advanced charts (area, scatter, combo, map) | [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md) |
| Dashboard with filters (global or page-level) | [3-filters.md](3-filters.md) |
| Need a complete working template to adapt | [4-examples.md](4-examples.md) |
| Debugging a broken dashboard | [5-troubleshooting.md](5-troubleshooting.md) |

---

## Implementation Guidelines

### 1) DATASET ARCHITECTURE

- **One dataset per domain** (e.g., orders, customers, products). Datasets shared across widgets benefit from the same filters.
- **Exactly ONE valid SQL query per dataset** (no multiple queries separated by `;`)
- Always use **fully-qualified table names**: `catalog.schema.table_name`
- SELECT must include all dimensions needed by widgets and all derived columns via `AS` aliases
- Put ALL business logic (CASE/WHEN, COALESCE, ratios) into the dataset SELECT with explicit aliases
- **Contract rule**: Every widget `fieldName` must exactly match a dataset column or alias
- **Add ORDER BY** when visualization depends on data order:
  - Time series: `ORDER BY date` for chronological display
  - Rankings/Top-N: `ORDER BY metric DESC LIMIT 10` for "Top 10" charts
  - Categorical charts: `ORDER BY metric DESC` to show largest values first

### 2) WIDGET FIELD EXPRESSIONS

> **CRITICAL: Field Name Matching Rule**
> The `name` in `query.fields` MUST exactly match the `fieldName` in `encodings`.
> If they don't match, the widget shows "no selected fields to visualize" error!

**Correct pattern for aggregations:**
```json
// In query.fields:
{"name": "sum(spend)", "expression": "SUM(`spend`)"}

// In encodings (must match!):
{"fieldName": "sum(spend)", "displayName": "Total Spend"}
```

**WRONG - names don't match:**
```json
// In query.fields:
{"name": "spend", "expression": "SUM(`spend`)"}  // name is "spend"

// In encodings:
{"fieldName": "sum(spend)", ...}  // ERROR: "sum(spend)" ≠ "spend"
```

Allowed expressions in widget queries (you CANNOT use CAST or other SQL in expressions):

**For numbers:**
```json
{"name": "sum(revenue)", "expression": "SUM(`revenue`)"}
{"name": "avg(price)", "expression": "AVG(`price`)"}
{"name": "count(orders)", "expression": "COUNT(`order_id`)"}
{"name": "countdistinct(customers)", "expression": "COUNT(DISTINCT `customer_id`)"}
{"name": "min(date)", "expression": "MIN(`order_date`)"}
{"name": "max(date)", "expression": "MAX(`order_date`)"}
```

**For dates** (use daily for timeseries, weekly/monthly for grouped comparisons):
```json
{"name": "daily(date)", "expression": "DATE_TRUNC(\"DAY\", `date`)"}
{"name": "weekly(date)", "expression": "DATE_TRUNC(\"WEEK\", `date`)"}
{"name": "monthly(date)", "expression": "DATE_TRUNC(\"MONTH\", `date`)"}
```

**Simple field reference** (for pre-aggregated data):
```json
{"name": "category", "expression": "`category`"}
```

If you need conditional logic or multi-field formulas, compute a derived column in the dataset SQL first.

### 3) SPARK SQL PATTERNS

- Date math: `date_sub(current_date(), N)` for days, `add_months(current_date(), -N)` for months
- Date truncation: `DATE_TRUNC('DAY'|'WEEK'|'MONTH'|'QUARTER'|'YEAR', column)`
- **AVOID** `INTERVAL` syntax - use functions instead

### 4) LAYOUT (6-Column Grid, NO GAPS)

Each widget has a position: `{"x": 0, "y": 0, "width": 2, "height": 4}`

**CRITICAL**: Each row must fill width=6 exactly. No gaps allowed.

```
CORRECT:                          WRONG:
y=0: [w=6]                        y=0: [w=4]____  ← gap!
y=1: [w=2][w=2][w=2]  ← fills 6   y=1: [w=1][w=1][w=1][w=1]__  ← gap!
y=4: [w=3][w=3]       ← fills 6
```

**Recommended widget sizes:**

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

**Dashboard readability depends on limiting distinct values:**

| Dimension Type | Max Values | Examples |
|----------------|------------|----------|
| Chart color/groups | **3-8** | 4 regions, 5 product lines, 3 tiers |
| Filters | 4-15 | 8 countries, 5 channels |
| High cardinality | **Table only** | customer_id, order_id, SKU |

**Before creating any chart with color/grouping:**
1. Check column cardinality via discover-schema or a COUNT DISTINCT query
2. If >10 distinct values, aggregate to higher level OR use TOP-N + "Other" bucket
3. For high-cardinality dimensions, use a table widget instead of a chart

### 6) QUALITY CHECKLIST

Before deploying, verify:
1. All widget names use only alphanumeric + hyphens + underscores
2. All rows sum to width=6 with no gaps
3. KPIs use height 3-4, charts use height 5-6
4. Chart dimensions have reasonable cardinality (≤8 for colors/groups)
5. All widget fieldNames match dataset columns exactly
6. **Field `name` in query.fields matches `fieldName` in encodings exactly** (e.g., both `"sum(spend)"`)
7. Counter datasets: use `disaggregated: true` for 1-row datasets, `disaggregated: false` with aggregation for multi-row
8. Percent values are 0-1 (not 0-100)
9. SQL uses Spark syntax (date_sub, not INTERVAL)
10. **All SQL queries tested via CLI and return expected data**

---

## Related Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - for querying the underlying data and system tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - for building the data pipelines that feed dashboards
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - for scheduling dashboard data refreshes
