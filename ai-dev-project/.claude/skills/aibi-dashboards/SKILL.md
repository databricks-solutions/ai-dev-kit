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

**Recommended widget sizes:**

| Widget Type | Width | Height | Notes |
|-------------|-------|--------|-------|
| Text header | 6 | 1 | Full width; use SEPARATE widgets for title and subtitle |
| Counter/KPI | 2 | **3-4** | **NEVER height=2** - too cramped! |
| Line/Bar chart | 3 | **5-6** | Pair side-by-side to fill row |
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

**CRITICAL VERSION REQUIREMENTS:**

| Widget Type | Version |
|-------------|---------|
| counter | 2 |
| table | 2 |
| filter-multi-select | 2 |
| filter-single-select | 2 |
| filter-date-range-picker | 2 |
| bar | 3 |
| line | 3 |
| pie | 3 |
| text | N/A (no spec block) |

---

**Text (Headers/Descriptions):**
- **CRITICAL: Text widgets do NOT use a spec block!**
- Use `multilineTextboxSpec` directly on the widget
- Supports markdown: `#`, `##`, `###`, `**bold**`, `*italic*`
- **CRITICAL: Multiple items in the `lines` array are concatenated on a single line, NOT displayed as separate lines!**
- For title + subtitle, use **separate text widgets** at different y positions

```json
// CORRECT: Separate widgets for title and subtitle
{
  "widget": {
    "name": "title",
    "multilineTextboxSpec": {
      "lines": ["## Dashboard Title"]
    }
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 1}
},
{
  "widget": {
    "name": "subtitle",
    "multilineTextboxSpec": {
      "lines": ["Description text here"]
    }
  },
  "position": {"x": 0, "y": 1, "width": 6, "height": 1}
}

// WRONG: Multiple lines concatenate into one line!
{
  "widget": {
    "name": "title-widget",
    "multilineTextboxSpec": {
      "lines": ["## Dashboard Title", "Description text here"]  // Becomes "## Dashboard TitleDescription text here"
    }
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 2}
}
```

---

**Counter (KPI):**
- `version`: **2** (NOT 3!)
- `widgetType`: "counter"
- **Percent values must be 0-1** in the data (not 0-100)

**Two patterns for counters:**

**Pattern 1: Pre-aggregated dataset (1 row, no filters)**
- Dataset returns exactly 1 row
- Use `"disaggregated": true` and simple field reference
- Field `name` matches dataset column directly

```json
{
  "widget": {
    "name": "total-revenue",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "summary_ds",
        "fields": [{"name": "revenue", "expression": "`revenue`"}],
        "disaggregated": true
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "counter",
      "encodings": {
        "value": {"fieldName": "revenue", "displayName": "Total Revenue"}
      },
      "frame": {"showTitle": true, "title": "Total Revenue"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 2, "height": 3}
}
```

**Pattern 2: Aggregating widget (multi-row dataset, supports filters)**
- Dataset returns multiple rows (e.g., grouped by a filter dimension)
- Use `"disaggregated": false` and aggregation expression
- **CRITICAL**: Field `name` MUST match `fieldName` exactly (e.g., `"sum(spend)"`)

```json
{
  "widget": {
    "name": "total-spend",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "by_category",
        "fields": [{"name": "sum(spend)", "expression": "SUM(`spend`)"}],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "counter",
      "encodings": {
        "value": {"fieldName": "sum(spend)", "displayName": "Total Spend"}
      },
      "frame": {"showTitle": true, "title": "Total Spend"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 2, "height": 3}
}
```

---

**Table:**
- `version`: **2** (NOT 1 or 3!)
- `widgetType`: "table"
- **Columns only need `fieldName` and `displayName`** - no other properties!
- Use `"disaggregated": true` for raw rows

```json
{
  "widget": {
    "name": "details-table",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "details_ds",
        "fields": [
          {"name": "name", "expression": "`name`"},
          {"name": "value", "expression": "`value`"}
        ],
        "disaggregated": true
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "table",
      "encodings": {
        "columns": [
          {"fieldName": "name", "displayName": "Name"},
          {"fieldName": "value", "displayName": "Value"}
        ]
      },
      "frame": {"showTitle": true, "title": "Details"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 6}
}
```

---

**Line / Bar Charts:**
- `version`: **3**
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

**Pie Chart:**
- `version`: **3**
- `widgetType`: "pie"
- `angle`: quantitative aggregate
- `color`: categorical dimension
- Limit to 3-8 categories for readability

### 7) FILTERS (Global vs Page-Level)

> **CRITICAL**: Filter widgets use DIFFERENT widget types than charts!
> - Valid types: `filter-multi-select`, `filter-single-select`, `filter-date-range-picker`
> - **DO NOT** use `widgetType: "filter"` - this does not exist and will cause errors
> - Filters use `spec.version: 2`
> - **ALWAYS include `frame` with `showTitle: true`** for filter widgets

**Filter widget types:**
- `filter-date-range-picker`: for DATE/TIMESTAMP fields
- `filter-single-select`: categorical with single selection
- `filter-multi-select`: categorical with multiple selections

---

#### Global Filters vs Page-Level Filters

| Type | Placement | Scope | Use Case |
|------|-----------|-------|----------|
| **Global Filter** | Dedicated page with `"pageType": "PAGE_TYPE_GLOBAL_FILTERS"` | Affects ALL pages that have datasets with the filter field | Cross-dashboard filtering (e.g., date range, campaign) |
| **Page-Level Filter** | Regular page with `"pageType": "PAGE_TYPE_CANVAS"` | Affects ONLY widgets on that same page | Page-specific filtering (e.g., platform filter on breakdown page only) |

**Key Insight**: A filter only affects datasets that contain the filter field. To have a filter affect only specific pages:
1. Include the filter dimension in datasets for pages that should be filtered
2. Exclude the filter dimension from datasets for pages that should NOT be filtered

---

#### Filter Widget Structure

> **CRITICAL**: Do NOT use `associative_filter_predicate_group` - it causes SQL errors!
> Use a simple field expression instead.

```json
{
  "widget": {
    "name": "filter_region",
    "queries": [{
      "name": "ds_data_region",
      "query": {
        "datasetName": "ds_data",
        "fields": [
          {"name": "region", "expression": "`region`"}
        ],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "filter-multi-select",
      "encodings": {
        "fields": [{
          "fieldName": "region",
          "displayName": "Region",
          "queryName": "ds_data_region"
        }]
      },
      "frame": {"showTitle": true, "title": "Region"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 2, "height": 2}
}
```

---

#### Global Filter Example

Place on a dedicated filter page:

```json
{
  "name": "filters",
  "displayName": "Filters",
  "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
  "layout": [
    {
      "widget": {
        "name": "filter_campaign",
        "queries": [{
          "name": "ds_campaign",
          "query": {
            "datasetName": "overview",
            "fields": [{"name": "campaign_name", "expression": "`campaign_name`"}],
            "disaggregated": false
          }
        }],
        "spec": {
          "version": 2,
          "widgetType": "filter-multi-select",
          "encodings": {
            "fields": [{
              "fieldName": "campaign_name",
              "displayName": "Campaign",
              "queryName": "ds_campaign"
            }]
          },
          "frame": {"showTitle": true, "title": "Campaign"}
        }
      },
      "position": {"x": 0, "y": 0, "width": 2, "height": 2}
    }
  ]
}
```

---

#### Page-Level Filter Example

Place directly on a canvas page (affects only that page):

```json
{
  "name": "platform_breakdown",
  "displayName": "Platform Breakdown",
  "pageType": "PAGE_TYPE_CANVAS",
  "layout": [
    {
      "widget": {
        "name": "page-title",
        "multilineTextboxSpec": {"lines": ["## Platform Breakdown"]}
      },
      "position": {"x": 0, "y": 0, "width": 4, "height": 1}
    },
    {
      "widget": {
        "name": "filter_platform",
        "queries": [{
          "name": "ds_platform",
          "query": {
            "datasetName": "platform_data",
            "fields": [{"name": "platform", "expression": "`platform`"}],
            "disaggregated": false
          }
        }],
        "spec": {
          "version": 2,
          "widgetType": "filter-multi-select",
          "encodings": {
            "fields": [{
              "fieldName": "platform",
              "displayName": "Platform",
              "queryName": "ds_platform"
            }]
          },
          "frame": {"showTitle": true, "title": "Platform"}
        }
      },
      "position": {"x": 4, "y": 0, "width": 2, "height": 2}
    }
    // ... other widgets on this page
  ]
}
```

---

**Filter Layout Guidelines:**
- Global filters: Position on dedicated filter page, stack vertically at `x=0`
- Page-level filters: Position in header area of page (e.g., top-right corner)
- Typical sizing: `width: 2, height: 2`

### 8) QUALITY CHECKLIST

Before deploying, verify:
1. All widget names use only alphanumeric + hyphens + underscores
2. All rows sum to width=6 with no gaps
3. KPIs use height 3-4, charts use height 5-6
4. Chart dimensions have ≤8 distinct values
5. All widget fieldNames match dataset columns exactly
6. **Field `name` in query.fields matches `fieldName` in encodings exactly** (e.g., both `"sum(spend)"`)
7. Counter datasets: use `disaggregated: true` for 1-row datasets, `disaggregated: false` with aggregation for multi-row
8. Percent values are 0-1 (not 0-100)
9. SQL uses Spark syntax (date_sub, not INTERVAL)
10. **All SQL queries tested via `execute_sql` and return expected data**

---

## Complete Example

```python
import json

# Step 1: Check table schema
table_info = get_table_details(catalog="samples", schema="nyctaxi")

# Step 2: Test queries
execute_sql("SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare, AVG(trip_distance) as avg_distance FROM samples.nyctaxi.trips")
execute_sql("""
    SELECT pickup_zip, COUNT(*) as trip_count
    FROM samples.nyctaxi.trips
    GROUP BY pickup_zip
    ORDER BY trip_count DESC
    LIMIT 10
""")

# Step 3: Build dashboard JSON
dashboard = {
    "datasets": [
        {
            "name": "summary",
            "displayName": "Summary Stats",
            "queryLines": [
                "SELECT COUNT(*) as trips, AVG(fare_amount) as avg_fare, ",
                "AVG(trip_distance) as avg_distance ",
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
    ],
    "pages": [{
        "name": "overview",
        "displayName": "NYC Taxi Overview",
        "pageType": "PAGE_TYPE_CANVAS",
        "layout": [
            # Text header - NO spec block! Use SEPARATE widgets for title and subtitle!
            {
                "widget": {
                    "name": "title",
                    "multilineTextboxSpec": {
                        "lines": ["## NYC Taxi Dashboard"]
                    }
                },
                "position": {"x": 0, "y": 0, "width": 6, "height": 1}
            },
            {
                "widget": {
                    "name": "subtitle",
                    "multilineTextboxSpec": {
                        "lines": ["Trip statistics and analysis"]
                    }
                },
                "position": {"x": 0, "y": 1, "width": 6, "height": 1}
            },
            # Counter - version 2, width 2!
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
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "trips", "displayName": "Total Trips"}
                        },
                        "frame": {"title": "Total Trips", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 2, "width": 2, "height": 3}
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
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "avg_fare", "displayName": "Avg Fare"}
                        },
                        "frame": {"title": "Average Fare", "showTitle": True}
                    }
                },
                "position": {"x": 2, "y": 2, "width": 2, "height": 3}
            },
            {
                "widget": {
                    "name": "total-distance",
                    "queries": [{
                        "name": "main_query",
                        "query": {
                            "datasetName": "summary",
                            "fields": [{"name": "avg_distance", "expression": "`avg_distance`"}],
                            "disaggregated": True
                        }
                    }],
                    "spec": {
                        "version": 2,
                        "widgetType": "counter",
                        "encodings": {
                            "value": {"fieldName": "avg_distance", "displayName": "Avg Distance"}
                        },
                        "frame": {"title": "Average Distance", "showTitle": True}
                    }
                },
                "position": {"x": 4, "y": 2, "width": 2, "height": 3}
            },
            # Bar chart - version 3
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
                "position": {"x": 0, "y": 5, "width": 6, "height": 5}
            },
            # Table - version 2, minimal column props!
            {
                "widget": {
                    "name": "zip-table",
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
                        "version": 2,
                        "widgetType": "table",
                        "encodings": {
                            "columns": [
                                {"fieldName": "pickup_zip", "displayName": "ZIP Code"},
                                {"fieldName": "trip_count", "displayName": "Trip Count"}
                            ]
                        },
                        "frame": {"title": "Top ZIP Codes", "showTitle": True}
                    }
                },
                "position": {"x": 0, "y": 10, "width": 6, "height": 5}
            }
        ]
    }]
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

## Complete Example with Filters

```python
import json

# Dashboard with a global filter for region
dashboard_with_filters = {
    "datasets": [
        {
            "name": "sales",
            "displayName": "Sales Data",
            "queryLines": [
                "SELECT region, SUM(revenue) as total_revenue ",
                "FROM catalog.schema.sales ",
                "GROUP BY region"
            ]
        }
    ],
    "pages": [
        {
            "name": "overview",
            "displayName": "Sales Overview",
            "pageType": "PAGE_TYPE_CANVAS",
            "layout": [
                {
                    "widget": {
                        "name": "total-revenue",
                        "queries": [{
                            "name": "main_query",
                            "query": {
                                "datasetName": "sales",
                                "fields": [{"name": "total_revenue", "expression": "`total_revenue`"}],
                                "disaggregated": True
                            }
                        }],
                        "spec": {
                            "version": 2,  # Version 2 for counters!
                            "widgetType": "counter",
                            "encodings": {
                                "value": {"fieldName": "total_revenue", "displayName": "Total Revenue"}
                            },
                            "frame": {"title": "Total Revenue", "showTitle": True}
                        }
                    },
                    "position": {"x": 0, "y": 0, "width": 6, "height": 3}
                }
            ]
        },
        {
            "name": "filters",
            "displayName": "Filters",
            "pageType": "PAGE_TYPE_GLOBAL_FILTERS",  # Required for global filter page!
            "layout": [
                {
                    "widget": {
                        "name": "filter_region",
                        "queries": [{
                            "name": "ds_sales_region",
                            "query": {
                                "datasetName": "sales",
                                "fields": [
                                    {"name": "region", "expression": "`region`"}
                                    # DO NOT use associative_filter_predicate_group - causes SQL errors!
                                ],
                                "disaggregated": False  # False for filters!
                            }
                        }],
                        "spec": {
                            "version": 2,  # Version 2 for filters!
                            "widgetType": "filter-multi-select",  # NOT "filter"!
                            "encodings": {
                                "fields": [{
                                    "fieldName": "region",
                                    "displayName": "Region",
                                    "queryName": "ds_sales_region"  # Must match query name!
                                }]
                            },
                            "frame": {"showTitle": True, "title": "Region"}  # Always show title!
                        }
                    },
                    "position": {"x": 0, "y": 0, "width": 2, "height": 2}
                }
            ]
        }
    ]
}

# Deploy with filters
result = create_or_update_dashboard(
    display_name="Sales Dashboard with Filters",
    parent_path="/Workspace/Users/me/dashboards",
    serialized_dashboard=json.dumps(dashboard_with_filters),
    warehouse_id=get_best_warehouse(),
)
print(result["url"])
```

## Troubleshooting

### Widget shows "no selected fields to visualize"

**This is a field name mismatch error.** The `name` in `query.fields` must exactly match the `fieldName` in `encodings`.

**Fix:** Ensure names match exactly:
```json
// WRONG - names don't match
"fields": [{"name": "spend", "expression": "SUM(`spend`)"}]
"encodings": {"value": {"fieldName": "sum(spend)", ...}}  // ERROR!

// CORRECT - names match
"fields": [{"name": "sum(spend)", "expression": "SUM(`spend`)"}]
"encodings": {"value": {"fieldName": "sum(spend)", ...}}  // OK!
```

### Widget shows "Invalid widget definition"

**Check version numbers:**
- Counters: `version: 2`
- Tables: `version: 2`
- Filters: `version: 2`
- Bar/Line/Pie charts: `version: 3`

**Text widget errors:**
- Text widgets must NOT have a `spec` block
- Use `multilineTextboxSpec` directly on the widget object
- Do NOT use `widgetType: "text"` - this is invalid

**Table widget errors:**
- Use `version: 2` (NOT 1 or 3)
- Column objects only need `fieldName` and `displayName`
- Do NOT add `type`, `numberFormat`, or other column properties

**Counter widget errors:**
- Use `version: 2` (NOT 3)
- Ensure dataset returns exactly 1 row

### Dashboard shows empty widgets
- Run the dataset SQL query directly to check data exists
- Verify column aliases match widget field expressions
- Check `disaggregated` flag (should be `true` for pre-aggregated data)

### Layout has gaps
- Ensure each row sums to width=6
- Check that y positions don't skip values

### Filter shows "Invalid widget definition"
- Check `widgetType` is one of: `filter-multi-select`, `filter-single-select`, `filter-date-range-picker`
- **DO NOT** use `widgetType: "filter"` - this is invalid
- Verify `spec.version` is `2`
- Ensure `queryName` in encodings matches the query `name`
- Confirm `disaggregated: false` in filter queries
- Ensure `frame` with `showTitle: true` is included

### Filter not affecting expected pages
- **Global filters** (on `PAGE_TYPE_GLOBAL_FILTERS` page) affect all datasets containing the filter field
- **Page-level filters** (on `PAGE_TYPE_CANVAS` page) only affect widgets on that same page
- A filter only works on datasets that include the filter dimension column

### Filter shows "UNRESOLVED_COLUMN" error for `associative_filter_predicate_group`
- **DO NOT** use `COUNT_IF(\`associative_filter_predicate_group\`)` in filter queries
- This internal expression causes SQL errors when the dashboard executes queries
- Use a simple field expression instead: `{"name": "field", "expression": "\`field\`"}`

### Text widget shows title and description on same line
- Multiple items in the `lines` array are **concatenated**, not displayed on separate lines
- Use **separate text widgets** for title and subtitle at different y positions
- Example: title at y=0 with height=1, subtitle at y=1 with height=1
