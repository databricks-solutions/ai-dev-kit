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
| Create dashboard | `databricks lakeview create --display-name "X" --warehouse-id "WH" --dataset-catalog CATALOG --dataset-schema SCHEMA --serialized-dashboard "$(cat file.json)" --json '{"parent_path": "/Workspace/Users/<you>/path"}'` — `--dataset-catalog` / `--dataset-schema` are **flag-only** (REQUIRED; CLI silently drops them if put in `--json`); `parent_path` is JSON-only (no flag). Queries must use bare table names. |
| Update dashboard | `databricks lakeview update DASHBOARD_ID --serialized-dashboard "$(cat file.json)"` |
| Publish | `databricks lakeview publish DASHBOARD_ID --warehouse-id WH` |
| Delete | `databricks lakeview trash DASHBOARD_ID` |

> **`--warehouse` flag**: if `databricks experimental aitools tools query --warehouse WH "..."` fails with `unknown flag: --warehouse` on your CLI version, set `DATABRICKS_WAREHOUSE_ID=WH` in the environment instead and drop the flag — the command auto-picks it from there.

---

## Widget Index (Version + Where Documented)

> **Wrong version = broken widget!** This is the #1 cause of dashboard errors.

| Widget Type | Version | Documented in |
|-------------|---------|---------------|
| `counter` (KPI + sparkline + comparison) | **2** | [1-widget-specifications.md#counter-kpi](1-widget-specifications.md#counter-kpi) (L71) |
| `table` | **2** | [1-widget-specifications.md#table](1-widget-specifications.md#table) (L235) |
| `bar`, `line` | **3** | [1-widget-specifications.md#line--bar-charts](1-widget-specifications.md#line--bar-charts) (L310) |
| `pie` | **3** | [1-widget-specifications.md#pie-chart](1-widget-specifications.md#pie-chart) (L422) |
| text (markdown, no spec block) | N/A | [1-widget-specifications.md#text-headersdescriptions](1-widget-specifications.md#text-headersdescriptions) (L33) |
| `area` | **3** | [2-advanced-widget-specifications.md#area-chart](2-advanced-widget-specifications.md#area-chart) (L7) |
| `scatter` | **3** | [2-advanced-widget-specifications.md#scatter-plot--bubble-chart](2-advanced-widget-specifications.md#scatter-plot--bubble-chart) (L34) |
| `combo` (bar+line, dual-axis) | **1** | [2-advanced-widget-specifications.md#combo-chart-bar--line](2-advanced-widget-specifications.md#combo-chart-bar--line) (L57) |
| `forecast-line` (with `AI_FORECAST` SQL) | **1** | [2-advanced-widget-specifications.md#forecast-line-with-ai_forecast](2-advanced-widget-specifications.md#forecast-line-with-ai_forecast) (L166) |
| `pivot` (with conditional cell rules) | **3** | [2-advanced-widget-specifications.md#pivot](2-advanced-widget-specifications.md#pivot) (L241) |
| `histogram` (with `bin(col, binWidth=N)`) | **3** | [2-advanced-widget-specifications.md#histogram](2-advanced-widget-specifications.md#histogram) (L302) |
| `heatmap` | **3** | [2-advanced-widget-specifications.md#heatmap](2-advanced-widget-specifications.md#heatmap) (L398) |
| `funnel` | **1** | [2-advanced-widget-specifications.md#funnel](2-advanced-widget-specifications.md#funnel) (L424) |
| `sankey` | **1** | [2-advanced-widget-specifications.md#sankey](2-advanced-widget-specifications.md#sankey) (L338) |
| `box` | **1** | [2-advanced-widget-specifications.md#box](2-advanced-widget-specifications.md#box) (L448) |
| `waterfall` | **1** | [2-advanced-widget-specifications.md#waterfall](2-advanced-widget-specifications.md#waterfall) (L470) |
| `choropleth-map` (regions colored by value) | **1** | [2-advanced-widget-specifications.md#choropleth-map](2-advanced-widget-specifications.md#choropleth-map) (L109) |
| `symbol-map` (lat/lon point map) | **2** | [2-advanced-widget-specifications.md#symbol-map-point-map](2-advanced-widget-specifications.md#symbol-map-point-map) (L364) |
| `filter-single-select`, `filter-multi-select`, `filter-date-range-picker` | **2** | [3-filters.md#filter-widget-structure](3-filters.md#filter-widget-structure) (L32) |
| `range-slider` | **2** | [3-filters.md#range-slider-numeric-range-filter](3-filters.md#range-slider-numeric-range-filter) (L239) |

> Cohort retention charts are built as a `pivot` with a color-scale cell style — there is no `cohort` widget type. See pivot in [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md).

---

## NEW DASHBOARD CREATION WORKFLOW

**You MUST test ALL SQL queries via CLI BEFORE deploying. Follow the overall logic in these steps for new dashboard - Skipping validation causes broken dashboards.**

### Step 1: Get Warehouse ID if not already known

```bash
# List warehouses to find one for SQL execution
databricks warehouses list
```

### Step 2: Discover Table Schemas and existing data pattern

A good dashboard comes from knowing the data first. Spend time here — the exploration drives design decisions in Step 4 (which widgets, which filters, which groupings).

Use `discover-schema` as the default — one call returns columns, types, sample rows, null counts, and row count. If you only know the schema, list tables first with `query "SHOW TABLES IN ..."`.

`databricks experimental aitools tools discover-schema catalog.schema.orders catalog.schema.customers`

Sample rows alone don't tell you what to build. you can write aggregate SQL through `databricks experimental aitools tools query --warehouse <WH> "..."` to probe typically:

- **Cardinality** of candidate grouping columns → decides chart color-group vs. table (≤8 distinct values for charts, see Cardinality & Readability below).
- **Top categorical values** → populates filter options and chart legends meaningfully.
- **Numeric distribution** (min/max/avg/percentiles) → decides KPI with delta vs. trend chart (flat metrics shouldn't be line charts, see Data Variance Considerations below).
- **Trend viability** at daily/weekly/monthly grain → picks the right trend granularity.
- **Story confirmation** — run the aggregations you plan to put in the dashboard and check they're not flat, empty, or uninteresting. Fix the query or adjust the story before moving on.

Fan out independent probes (state ∈ `PENDING|RUNNING|SUCCEEDED|FAILED|CANCELED|CLOSED`):

```bash
submit() { databricks api post /api/2.0/sql/statements --json "$(jq -nc --arg w "$1" --arg s "$2" '{warehouse_id:$w,statement:$s,wait_timeout:"0s",on_wait_timeout:"CONTINUE"}')" | jq -r .statement_id; }
SIDS=(); for q in "$@"; do SIDS+=( "$(submit "$WH" "$q")" ); done
for s in "${SIDS[@]}"; do databricks api get "/api/2.0/sql/statements/$s" | jq '{state:.status.state, rows:.result.data_array}'; done
# cancel: databricks api post "/api/2.0/sql/statements/$SID/cancel"
```

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

4. **Build the dashboard JSON** as a local working file (intermediate step, not the deliverable).

### Step 5: Deploy

**Now deploy the JSON to the workspace.** Run `databricks lakeview create` (below). Your task is not complete until this command succeeds and returns a dashboard ID — the JSON file alone is an intermediate working artifact.

After deploying, the same `lakeview` subcommands manage the dashboard's lifecycle (list, get, update, publish, trash).

```bash
# Deploy: creates the dashboard in the workspace and returns a dashboard ID.
# Canonical form — MIX flags + --json. Each field has exactly ONE valid place:
#   --dataset-catalog / --dataset-schema : FLAG-ONLY (REQUIRED — no JSON field).
#       The CLI silently warns "unknown field" and drops them if put in --json,
#       leaving every dataset query unable to resolve its catalog.schema.
#   parent_path : JSON-ONLY (no flag). Without it, dashboard lands at
#       /Users/<you>/<display-name>.
#   display_name / warehouse_id / serialized_dashboard : either form works;
#       prefer flags for readability.
# Queries inside dashboard.json MUST use bare table names ("FROM trips", never
# "FROM schema.trips" or "FROM catalog.schema.trips") — --dataset-catalog and
# --dataset-schema only fill in missing parts, they do NOT rewrite hardcoded
# prefixes.
databricks lakeview create \
  --display-name "My Dashboard" \
  --warehouse-id "abc123def456" \
  --dataset-catalog "my_catalog" \
  --dataset-schema "my_schema" \
  --serialized-dashboard "$(cat dashboard.json)" \
  --json '{"parent_path": "/Workspace/Users/me@co.com/dashboards"}'

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

### Dashboard Theme (Optional)

Top-level `uiSettings.theme` controls colors, fonts, and widget chrome across every widget on the dashboard. Without it, the dashboard inherits the workspace default. With it, you get a consistent palette across all charts, plus the index that `{"themeColorType": "visualizationColors", "position": N}` in per-widget specs resolves against.

```json
{
  "datasets": [...],
  "pages": [...],
  "uiSettings": {
    "theme": {
      "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
      "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
      "fontColor":             {"light": "#11171C", "dark": "#E8ECF0"},
      "selectionColor":        {"light": "#2272B4", "dark": "#8ACAFF"},
      "visualizationColors": [
        "#FFA600", "#FF7054", "#DE5582", "#995495",
        "#4E5185", "#1D425C", "#99DDB4"
      ],
      "widgetHeaderAlignment": "LEFT"
    }
  }
}
```

- `visualizationColors` is the **ordered palette** chart series and category mappings cycle through. `position: 1` is the first color (`#FFA600` above), `position: 6` is the 6th (`#1D425C`). Length is whatever you want — 5-8 colors is typical.
- Background / font / selection colors take `light` + `dark` pairs; the dashboard automatically applies the right pair based on the viewer's mode.
- `widgetHeaderAlignment`: `"LEFT"` (default), `"CENTER"`, or `"RIGHT"`.
- Per-widget color references use `{"themeColorType": "visualizationColors", "position": N}` to pin a value to a specific slot in this palette (e.g., Critical → position 6 → always red, regardless of how the chart sorts). For an exact hex outside the palette, use `{"hex": "#FF0000"}` instead.

### Linking a Genie Space (Optional)

To add an "Ask Genie" button to the dashboard, or to link a genie space/room with an ID, add `uiSettings.genieSpace` to the JSON (alongside `theme` if you have one):

```json
"uiSettings": {
  "theme": { /* ... */ },
  "genieSpace": {
    "isEnabled": true,
    "overrideId": "your-genie-space-id-here",
    "enablementMode": "ENABLED"
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
- **Chart selection**: Match cardinality to chart type. Few distinct values → bar with color grouping (or pie if you really want a snapshot); many values → table.

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
- **Two ways to define a dataset**:
  - **SQL query**: `{"name": "ds_x", "displayName": "...", "queryLines": ["SELECT ...", "FROM table"]}` — full control, can include `WITH` / `JOIN` / `AI_FORECAST` / etc.
  - **UC asset shorthand**: `{"name": "ds_x", "displayName": "...", "asset_name": "catalog.schema.table_or_view"}` — no SQL needed. Works for regular tables, views, and metric views.
- **Exactly ONE valid SQL query per dataset** when using `queryLines` (no multiple queries separated by `;`)
- **Queries must use bare table names only** — no catalog, no schema prefix. Example: `FROM orders`, never `FROM gold.orders` or `FROM main.gold.orders`. The catalog and schema come from the `--dataset-catalog` and `--dataset-schema` flags at creation time. These flags only fill in missing parts — they do NOT override any catalog/schema written in the query.
- SELECT must include all dimensions needed by widgets and all derived columns via `AS` aliases
- Put ALL business logic (CASE/WHEN, COALESCE, ratios) into the dataset SELECT with explicit aliases
- **Contract rule**: Every widget `fieldName` must exactly match a dataset column or alias
- **Add ORDER BY** when visualization depends on data order:
  - Time series: `ORDER BY date` for chronological display
  - Rankings/Top-N: `ORDER BY metric DESC LIMIT 10` for "Top 10" charts
  - Categorical charts: `ORDER BY metric DESC` to show largest values first

#### Dataset-level measures + `MEASURE()`

Widget expressions are usually inline aggregations (`{"name": "sum(x)", "expression": "SUM(\`x\`)"}`). But you can also **declare reusable measures on the dataset itself** and reference them by name — every widget that consumes the dataset can use the same metric without redefining it.

Two ways to define measures:

1. **Dashboard-level `columns`** (works on any dataset — SQL query or `asset_name`):
   ```json
   {
     "name": "ds_support",
     "queryLines": ["SELECT * FROM support_cases"],
     "columns": [
       {"displayName": "Total Cases",     "description": "Count of cases",
        "expression": "COUNT(`case_id`)"},
       {"displayName": "Reopen Rate %",   "description": "% of reopened cases",
        "expression": "SUM(CASE WHEN `reopened_flag` THEN 1 ELSE 0 END) * 100.0 / COUNT(`case_id`)"},
       {"displayName": "Priority Level",  "description": "Sorted priority label",
        "expression": "CASE WHEN `priority`='Critical' THEN '1-Critical' ELSE '4-Low' END"}
     ]
   }
   ```

2. **Metric-view source** — if the dataset's `asset_name` (or `FROM` clause) is a UC metric view, its YAML-defined measures are already queryable. **Do not redeclare them** in `columns`. See [databricks-metric-views](../databricks-metric-views/SKILL.md).

Either way, widgets reference the measure by name:

```json
"fields": [{"name": "measure(Total Cases)", "expression": "MEASURE(`Total Cases`)"}],
"encodings": {"value": {"fieldName": "measure(Total Cases)", "displayName": "Total Cases"}}
```

`MEASURE(\`...\`)` works in counter, table, bar, line, pie, pivot — any widget that takes a field expression. Mix it with inline aggregations freely.

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

### 4) LAYOUT (12-Column Grid, NO GAPS)

**Every page must include `"layoutVersion": "GRID_V1"`** alongside `pageType`.

```json
{
  "name": "overview",
  "displayName": "Overview",
  "pageType": "PAGE_TYPE_CANVAS",
  "layoutVersion": "GRID_V1",
  "layout": [...]
}
```

Each widget has a position: `{"x": 0, "y": 0, "width": 4, "height": 4}`

**CRITICAL**: Each row must fill width=12 exactly. No gaps allowed.

```
CORRECT:                            WRONG:
y=0: [w=12]                         y=0: [w=8]____  ← gap!
y=1: [w=4][w=4][w=4]  ← fills 12    y=1: [w=2][w=2][w=2][w=2]__  ← gap!
y=4: [w=6][w=6]       ← fills 12
```

**Recommended widget sizes:**

| Widget Type | Width | Height | Notes |
|-------------|-------|--------|-------|
| Text header | 12 | 1 | Full width; use SEPARATE widgets for title and subtitle |
| Counter/KPI | 4 | **3-4** | **NEVER height=2** - too cramped! |
| Line/Bar/Area chart | 6 | **5-6** | Pair side-by-side to fill row |
| Pie chart | 6 | **5-6** | Needs space for legend |
| Full-width chart | 12 | 5-7 | For detailed time series |
| Table | 12 | 5-8 | Full width for readability |

**Standard dashboard structure:**
```text
y=0:  Title (w=12, h=1) - Dashboard title (use separate widget!)
y=1:  Subtitle (w=12, h=1) - Description (use separate widget!)
y=2:  KPIs (w=4 each, h=3) - 3 key metrics side-by-side
y=5:  Section header (w=12, h=1) - "Trends" or similar
y=6:  Charts (w=6 each, h=5) - Two charts side-by-side
y=11: Section header (w=12, h=1) - "Details"
y=12: Table (w=12, h=6) - Detailed data
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
2. **Every page has `"layoutVersion": "GRID_V1"`**
3. All rows sum to width=12 with no gaps
4. KPIs use height 3-4, charts use height 5-6
5. Chart dimensions have reasonable cardinality (≤8 for colors/groups)
6. All widget fieldNames match dataset columns exactly
7. **Field `name` in query.fields matches `fieldName` in encodings exactly** (e.g., both `"sum(spend)"`)
8. Counter datasets: use `disaggregated: true` for 1-row datasets, `disaggregated: false` with aggregation for multi-row
9. **Percent values must be 0-1 for `number-percent` format** (0.865 displays as "86.5%", don't forget to set the format). If data is 0-100, either divide by 100 in SQL or use `number` format instead.
10. SQL uses Spark syntax (date_sub, not INTERVAL)
11. **All SQL queries tested via CLI and return expected data**
12. **Every dataset you want filtered MUST contain the filter field** — filters only affect datasets with that column in their query

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
