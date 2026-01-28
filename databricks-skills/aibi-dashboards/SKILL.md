---
name: aibi-dashboards
description: "Create AI/BI dashboards. CRITICAL: You MUST test ALL SQL queries via execute_sql BEFORE deploying. Follow guidelines strictly."
---

# AI/BI Dashboard Skill

Create Databricks AI/BI dashboards (formerly Lakeview dashboards). **Follow these guidelines strictly.**

## CRITICAL: MANDATORY VALIDATION WORKFLOW

**You MUST follow this workflow exactly. Skipping validation causes broken dashboards.**

```
┌─────────────────────────────────────────────────────────────────────┐
│  STEP 1: Get table schemas via get_table_details(catalog, schema)  │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 2: Write SQL queries for each dataset                        │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 3: TEST EVERY QUERY via execute_sql() ← DO NOT SKIP!         │
│          - If query fails, FIX IT before proceeding                │
│          - Verify column names match what widgets will reference   │
│          - Verify data types are correct (dates, numbers, strings) │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 4: Build dashboard JSON using ONLY verified queries          │
├─────────────────────────────────────────────────────────────────────┤
│  STEP 5: Deploy via create_or_update_dashboard()                   │
└─────────────────────────────────────────────────────────────────────┘
```

**WARNING: If you deploy without testing queries, widgets WILL show "Invalid widget definition" errors!**

## Available MCP Tools

| Tool | Description |
|------|-------------|
| `get_table_details` | **STEP 1**: Get table schemas for designing queries |
| `execute_sql` | **STEP 3**: Test SQL queries - MANDATORY before deployment! |
| `get_best_warehouse` | Get available warehouse ID |
| `create_or_update_dashboard` | **STEP 5**: Deploy dashboard JSON (only after validation!) |
| `get_dashboard` | Get dashboard details by ID |
| `list_dashboards` | List dashboards in workspace |
| `trash_dashboard` | Move dashboard to trash |
| `publish_dashboard` | Publish dashboard for viewers |
| `unpublish_dashboard` | Unpublish a dashboard |

---

## Implementation Guidelines

### 1) DATASET ARCHITECTURE (STRICT)

- **One dataset per domain** (e.g., orders, customers, products)
- **Exactly ONE valid SQL query per dataset** (no multiple queries separated by `;`)
- Always use **fully-qualified table names**: `catalog.schema.table_name`
- SELECT must include all dimensions needed by widgets and all derived columns via `AS` aliases
- Put ALL business logic (CASE/WHEN, COALESCE, ratios) into the dataset SELECT with explicit aliases
- **Contract rule**: Every widget `fieldName` must exactly match a dataset column or alias

### 2) WIDGET FIELD EXPRESSIONS

Allowed expressions in widget queries (you CANNOT use CAST or other SQL in expressions):

**For numbers:**
```json
{"fieldName": "sum(revenue)", "expression": "SUM(`revenue`)"}
{"fieldName": "avg(price)", "expression": "AVG(`price`)"}
{"fieldName": "count(orders)", "expression": "COUNT(`order_id`)"}
{"fieldName": "countdistinct(customers)", "expression": "COUNT(DISTINCT `customer_id`)"}
{"fieldName": "min(date)", "expression": "MIN(`order_date`)"}
{"fieldName": "max(date)", "expression": "MAX(`order_date`)"}
```

**For dates** (use daily for timeseries, weekly/monthly for grouped comparisons):
```json
{"fieldName": "daily(date)", "expression": "DATE_TRUNC(\"DAY\", `date`)"}
{"fieldName": "weekly(date)", "expression": "DATE_TRUNC(\"WEEK\", `date`)"}
{"fieldName": "monthly(date)", "expression": "DATE_TRUNC(\"MONTH\", `date`)"}
```

**Simple field reference** (for pre-aggregated data):
```json
{"fieldName": "category", "expression": "`category`"}
```

If you need conditional logic or multi-field formulas, compute a derived column in the dataset SQL first.

### 3) SPARK SQL PATTERNS

- Date math: `date_sub(current_date(), N)` for days, `add_months(current_date(), -N)` for months
- Date truncation: `DATE_TRUNC('DAY'|'WEEK'|'MONTH'|'QUARTER'|'YEAR', column)`
- **AVOID** `INTERVAL` syntax - use functions instead

### 4) LAYOUT (6-Column Grid, NO GAPS)

Each widget has a position: `{"x": 0, "y": 0, "width": 2, "height": 4}`

**CRITICAL**: Each row must fill width=6 exactly. No gaps allowed.

**Recommended widget sizes:**

| Widget Type | Width | Height | Notes |
|-------------|-------|--------|-------|
| Text header | 6 | 1-2 | Full width; h=1 title only, h=2 with description |
| Counter/KPI | 2 | **3-4** | **NEVER height=2** - too cramped! |
| Line/Bar chart | 3 | **5-6** | Pair side-by-side to fill row |
| Pie chart | 3 | **5-6** | Needs space for legend |
| Full-width chart | 6 | 5-7 | For detailed time series |
| Table | 6 | 5-8 | Full width for readability |

**Standard dashboard structure:**
```text
y=0:  Text header (w=6, h=2) - Dashboard title + description
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
| Filters | 4-10 | 8 countries, 5 channels |
| High cardinality | **Table only** | customer_id, order_id, SKU |

**Before creating any chart with color/grouping:**
1. Check column cardinality (use `get_table_details` to see distinct values)
2. If >10 distinct values, aggregate to higher level OR use TOP-N + "Other" bucket
3. For high-cardinality dimensions, use a table widget instead of a chart

### 6) WIDGET SPECIFICATIONS

**Widget Naming Convention (CRITICAL):**
- `widget.name`: alphanumeric + hyphens + underscores ONLY (no spaces, parentheses, colons)
- `frame.title`: human-readable name (any characters allowed)
- `widget.queries[0].name`: always use `"main_query"`

**Counter (KPI):**
- `widgetType`: "counter"
- Dataset should return exactly 1 row (pre-aggregated)
- Use `"disaggregated": true` in widget query
- Format types: `"number-currency"`, `"number-percent"`, `"number"`
- **Percent values must be 0-1** in the data (not 0-100)

```json
"format": {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 2}}
"format": {"type": "number-percent", "decimalPlaces": {"type": "max", "places": 1}}
```

**Line / Bar Charts:**
- `widgetType`: "line" or "bar"
- Use `x`, `y`, optional `color` encodings
- `scale.type`: `"temporal"` (dates), `"quantitative"` (numbers), `"categorical"` (strings)
- Use `"disaggregated": true` with pre-aggregated dataset data

**Multiple Lines - Two Approaches:**

1. **Multi-Y Fields** (different metrics on same chart):
```json
"y": {
  "scale": {"type": "quantitative"},
  "fields": [
    {"fieldName": "sum(orders)", "displayName": "Orders"},
    {"fieldName": "sum(returns)", "displayName": "Returns"}
  ]
}
```

2. **Color Grouping** (same metric split by dimension):
```json
"y": {"fieldName": "sum(revenue)", "scale": {"type": "quantitative"}},
"color": {"fieldName": "region", "scale": {"type": "categorical"}, "displayName": "Region"}
```

**Bar Chart Modes:**
- **Stacked** (default): No `mark` field - bars stack on top of each other
- **Grouped**: Add `"mark": {"layout": "group"}` - bars side-by-side for comparison

**Combo Chart:**
- `widgetType`: "combo"
- Primary fields show as bars, secondary as line
- Both must use same scale type

```json
"y": {
  "primary": {"fields": [{"fieldName": "sum(orders)", "displayName": "Orders"}]},
  "secondary": {"fields": [{"fieldName": "avg(aov)", "displayName": "AOV"}]},
  "scale": {"type": "quantitative"}
}
```

**Pie Chart:**
- `widgetType`: "pie"
- `angle`: quantitative aggregate
- `color`: categorical dimension
- Limit to 3-8 categories for readability

**Table:**
- `widgetType`: "table"
- Use `"disaggregated": true` for raw rows
- Set column `type`: `"string"`, `"number"`, `"datetime"`
- Add `numberFormat` or `dateTimeFormat` as needed

**Text:**
- Use for headers and section breaks
- Supports markdown: `# H1`, `## H2`, `**bold**`, `*italic*`
- Add `\n` at end of each line in the array

```json
"textboxSpec": {
  "lines": ["# Dashboard Title\n", "Description of what this dashboard shows.\n"]
}
```

### 7) GLOBAL FILTERS

Create a second page with `"pageType": "PAGE_TYPE_GLOBAL_FILTERS"`:

**Filter widget types:**
- `filter-date-range-picker`: for DATE/TIMESTAMP fields
- `filter-single-select`: categorical with single selection
- `filter-multi-select`: categorical with multiple selections

**Filter structure:**
```json
{
  "widget": {
    "name": "filter_region",
    "queries": [
      {"name": "ds_orders_region", "query": {"datasetName": "ds_orders", "fields": [{"name": "region", "expression": "`region`"}], "disaggregated": false}}
    ],
    "spec": {
      "version": 2,
      "widgetType": "filter-multi-select",
      "encodings": {
        "fields": [{"fieldName": "region", "displayName": "Region", "queryName": "ds_orders_region"}]
      }
    }
  },
  "position": {"x": 0, "y": 0, "width": 2, "height": 2}
}
```

**Important:** All datasets must include filter fields for filtering to work across the dashboard.

### 8) QUALITY CHECKLIST

Before deploying, verify:
1. All widget names use only alphanumeric + hyphens + underscores
2. All rows sum to width=6 with no gaps
3. KPIs use height 3-4, charts use height 5-6
4. Chart dimensions have ≤8 distinct values
5. All widget fieldNames match dataset columns exactly
6. Counter datasets return exactly 1 row
7. Percent values are 0-1 (not 0-100)
8. SQL uses Spark syntax (date_sub, not INTERVAL)
9. **All SQL queries tested via `execute_sql` and return expected data**

---

## Complete Example

```python
import json

# Step 1: Check table schema
table_info = get_table_details(catalog="samples", schema="nyctaxi")

# Step 2: Test queries
execute_sql("SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare FROM samples.nyctaxi.trips")
execute_sql("""
    SELECT pickup_zip, COUNT(*) as trip_count
    FROM samples.nyctaxi.trips
    GROUP BY pickup_zip
    ORDER BY trip_count DESC
    LIMIT 10
""")

# Step 3: Build dashboard JSON
dashboard = {
    "pages": [{
        "name": "overview",
        "displayName": "NYC Taxi Overview",
        "layout": [
            {
                "widget": {
                    "name": "total-trips",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "trips", "expression": "`trips`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 3,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "trips", "displayName": "Total Trips"}
                        },
                        "frame": {"title": "Total Trips", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 0, "width": 3, "height": 3}
            },
            {
                "widget": {
                    "name": "avg-fare",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "avg_fare", "expression": "`avg_fare`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 3,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "avg_fare", "displayName": "Avg Fare"}
                        },
                        "format": {
                            "type": "number-currency",
                            "currencyCode": "USD",
                            "decimalPlaces": {"type": "max", "places": 2}
                        },
                        "frame": {"title": "Average Fare", "showTitle": True}
                    }
                },
                "position": {"x": 3, "y": 0, "width": 3, "height": 3}
            },
            {
                "widget": {
                    "name": "trips-by-zip",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "by_zip",
                            "fields": [
                                {"name": "pickup_zip", "expression": "`pickup_zip`"},
                                {"name": "trip_count", "expression": "`trip_count`"}
                            ],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 3,
                        "widgetType": "bar",
                        "encodings": {
                            "x": {"fieldName": "pickup_zip", "scale": {"type": "categorical"}, "displayName": "ZIP"},
                            "y": {"fieldName": "trip_count", "scale": {"type": "quantitative"}, "displayName": "Trips"}
                        },
                        "frame": {"title": "Trips by Pickup ZIP", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 3, "width": 6, "height": 5}
            }
        ]
    }],
    "datasets": [
        {
            "name": "summary",
            "displayName": "Summary Stats",
            "queryLines": [
                "SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare ",
                "FROM samples.nyctaxi.trips "
            ]
        },
        {
            "name": "by_zip",
            "displayName": "Trips by ZIP",
            "queryLines": [
                "SELECT pickup_zip, COUNT(*) as trip_count ",
                "FROM samples.nyctaxi.trips ",
                "GROUP BY pickup_zip ",
                "ORDER BY trip_count DESC ",
                "LIMIT 10 "
            ]
        }
    ]
}

# Step 4: Deploy
result = create_or_update_dashboard(
    display_name="NYC Taxi Dashboard",
    parent_path="/Workspace/Users/me/dashboards",
    serialized_dashboard=json.dumps(dashboard),
    warehouse_id=get_best_warehouse(),
)
print(result["url"])
```

## Troubleshooting

### Widget shows "Invalid widget definition"
- Verify SQL query works via `execute_sql`
- Check `disaggregated` flag (should be `true` for pre-aggregated data)
- Ensure field names match dataset columns exactly

### Dashboard shows empty widgets
- Run the dataset SQL query directly to check data exists
- Verify column aliases match widget field expressions

### Layout has gaps
- Ensure each row sums to width=6
- Check that y positions don't skip values
