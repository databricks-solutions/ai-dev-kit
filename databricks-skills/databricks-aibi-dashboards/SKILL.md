---
name: databricks-aibi-dashboards
description: "Create Databricks AI/BI dashboards. Must use when creating, updating, or deploying Lakeview dashboards as Databricks Dashboard have a unique json structure. CRITICAL: You MUST test ALL SQL queries via CLI BEFORE deploying. Follow guidelines strictly."
---

# AI/BI Dashboard Skill

Create Databricks AI/BI dashboards (formerly Lakeview dashboards).
A dashboard should be showing something relevant for a human, typically some KPI on the top, and based on the story, some graph (often temporal), and we see "something happens".
**Follow these guidelines strictly.**

## Quick Reference

| Task | Command |
|------|---------|
| List warehouses | `databricks warehouses list` |
| List tables | `databricks experimental aitools tools query --warehouse WH "SHOW TABLES IN catalog.schema"` |
| Get schema | `databricks experimental aitools tools discover-schema catalog.schema.table1 catalog.schema.table2` |
| Test query | `databricks experimental aitools tools query --warehouse WH "SELECT..."` |
| Create dashboard | `databricks lakeview create --display-name "X" --warehouse-id "Y" --dataset-catalog "catalog" --dataset-schema "schema" --serialized-dashboard "$(cat file.json)"` (always set `--dataset-catalog` and `--dataset-schema` — queries MUST use bare table names only) |
| Update dashboard | `databricks lakeview update DASHBOARD_ID --serialized-dashboard "$(cat file.json)"` |
| Publish | `databricks lakeview publish DASHBOARD_ID --warehouse-id WH` |
| Delete | `databricks lakeview trash DASHBOARD_ID` |

---

## CRITICAL: Widget Version Requirements

> **Wrong version = broken widget!** This is the #1 cause of dashboard errors.

| Widget Type | Version | Notes |
|-------------|---------|-------|
| `counter` | **2** | KPI cards |
| `table` | **2** | Data tables |
| `bar`, `line`, `area`, `pie`, `scatter` | **3** | Charts |
| `combo`, `choropleth-map` | **1** | Advanced charts |
| `filter-*` | **2** | All filter types |

---

## NEW DASHBOARD CREATION WORKFLOW

**You MUST test ALL SQL queries via CLI BEFORE deploying. Follow the overall logic in these steps for new dashboard - Skipping validation causes broken dashboards.**

### Step 1: Get Warehouse ID if not already known

```bash
# List warehouses to find one for SQL execution
databricks warehouses list
```

### Step 2: Discover Table Schemas and existing data pattern

```bash
# Get table schemas for designing queries
databricks experimental aitools tools query --warehouse WAREHOUSE_ID "SHOW TABLES IN catalog.schema" 2>&1
# Use CATALOG.SCHEMA.TABLE format for discover-schema (this is for exploration only)
databricks experimental aitools tools discover-schema catalog.schema.table1 catalog.schema.table2

# Example:
databricks experimental aitools tools discover-schema samples.nyctaxi.trips main.default.customers

# Explore data patterns if needed to confirm the data tells the intended story (to understand what/how to visualize):
databricks experimental aitools tools query --warehouse WAREHOUSE_ID "<YOUR DATA EXPLORATION QUERY>"
```

> **Note**: The `discover-schema` command needs the full `catalog.schema.table` path (it's a separate exploration tool).
>
> **Dashboard queries are different** — inside the dashboard JSON, the `FROM` clause must reference ONLY the table name, with no catalog or schema prefix:
> - ✅ Correct: `FROM trips`
> - ❌ Wrong: `FROM nyctaxi.trips`
> - ❌ Wrong: `FROM samples.nyctaxi.trips`
>
> The catalog and schema are supplied separately via the `--dataset-catalog` and `--dataset-schema` flags when you run `databricks lakeview create`. These flags do NOT rewrite the query — they only fill in the catalog/schema when the query omits them. If you hardcode a catalog or schema in the `FROM` clause, the flags are ignored for that query and the dashboard won't be portable across environments.


### Step 3: Verify Data Matches Story
The datasets.querylines in the dashboard json (see example below) must be tested to ensure 

Before finalizing, run the SQL Queries you intend to add in each dataset to confirm that they run properly and that the result are valid.
This is crucial, as the widget defined in the json will use the query field output to render the visualization. The value should also make sense at a business level.
Remember that for the filter to work, the query should have the field available (so typically group by the filter field)

If values don't match expectations, ensure the query is correct, fix the data if you can, or adjust the story before creating the dashboard.

### Step 4: Plan Dashboard Structure

Before writing JSON, plan your dashboard:

1. You must know the expected specific JSON structure. For this, **Read reference files**: [1-widget-specifications.md](1-widget-specifications.md), [3-filters.md](3-filters.md), [4-examples.md](4-examples.md)

2. Think: **What widgets?** Map each visualization to a dataset:
   | Widget | Type | Dataset | Has filter field? |
   |--------|------|---------|-------------------|
   | Revenue KPI | counter | ds_sales | ✓ date, region |
   | Trend Chart | line | ds_sales | ✓ date, region |
   | Top Products | table | ds_products | ✗ no date | 
   ...

3. **What filters?** For each filter, verify ALL datasets you want filtered contain the filter field.
   > **Filters only affect datasets that have the filter field.** A pre-aggregated table without dates WON'T be date-filtered.

4. **Write JSON locally** as a file.

### Step 5: Dashboard Lifecycle
Once created, you can edit the file as following:
```bash
# Create a dashboard
# IMPORTANT: Use --dataset-catalog and --dataset-schema to set the catalog/schema for all queries
# Queries in the JSON MUST use bare table names only (e.g., "FROM trips"),
# NOT "FROM schema.trips" and NOT "FROM catalog.schema.trips".
# The CLI flags only provide a default — they do NOT override hardcoded catalog/schema in queries.
databricks lakeview create \
  --display-name "My Dashboard" \
  --warehouse-id "abc123def456" \
  --dataset-catalog "my_catalog" \
  --dataset-schema "my_schema" \
  --serialized-dashboard "$(cat dashboard.json)"

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

# By default, after creation, tag dashboards to track resources created with this skill
databricks workspace-entity-tag-assignments create-tag-assignment \
  dashboards DASHBOARD_ID aidevkit_project --tag-value ai-dev-kit
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
      "queryLines": ["SELECT col1, col2 ", "FROM my_table"]
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

To add an "Ask Genie" button to the dashboard, or to link a genie space/room with an ID, add `uiSettings.genieSpace` to the JSON:

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
| Advanced charts (area, scatter/Bubble, combo (Line+Bar), Choropleth map) | [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md) |
| Dashboard with filters (global or page-level) | [3-filters.md](3-filters.md) |
| Need a complete working template to adapt | [4-examples.md](4-examples.md) |
| Debugging a broken dashboard | [5-troubleshooting.md](5-troubleshooting.md) |

---

## Implementation Guidelines

### 1) DATASET ARCHITECTURE

- **One dataset per domain** (e.g., orders, customers, products). Datasets shared across widgets benefit from the same filters.
- **Exactly ONE valid SQL query per dataset** (no multiple queries separated by `;`)
- **Queries must use bare table names only** — no catalog, no schema prefix. Example: `FROM orders`, never `FROM gold.orders` or `FROM main.gold.orders`. The catalog and schema come from the `--dataset-catalog` and `--dataset-schema` flags at creation time. These flags only fill in missing parts — they do NOT override any catalog/schema written in the query.
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

```json
{"name": "[sum|avg|count|countdistinct|min|max](col)", "expression": "[SUM|AVG|COUNT|COUNT(DISTINCT)|MIN|MAX](`col`)"}
{"name": "[daily|weekly|monthly](date)", "expression": "DATE_TRUNC(\"[DAY|WEEK|MONTH]\", `date`)"}
{"name": "field", "expression": "`field`"}
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
8. **Percent values must be 0-1 for `number-percent` format** (0.865 displays as "86.5%", don't forget to set the format). If data is 0-100, either divide by 100 in SQL or use `number` format instead.
9. SQL uses Spark syntax (date_sub, not INTERVAL)
10. **All SQL queries tested via CLI and return expected data**
11. **Every dataset you want filtered MUST contain the filter field** — filters only affect datasets with that column in their query

---

## Data Variance Considerations

Before creating trend charts, check if the metric has enough variance to visualize meaningfully:

```sql
SELECT MIN(metric), MAX(metric), MAX(metric) - MIN(metric) as range FROM dataset
```

If the range is very small relative to the scale (e.g., 83-89% on a 0-100 scale), the chart will appear nearly flat. Consider:
- Showing as KPI with delta/comparison instead of chart
- Using a table to display exact values
- Adjusting the visualization to focus on the variance

---

## Related Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - for querying the underlying data and system tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - for building the data pipelines that feed dashboards
- **[databricks-jobs](../databricks-jobs/SKILL.md)** - for scheduling dashboard data refreshes
