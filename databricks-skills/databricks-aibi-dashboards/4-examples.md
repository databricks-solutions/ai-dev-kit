# Complete Dashboard Example

This is a **reference example** to understand the JSON structure and layout patterns. **Always adapt to what the user requests** - use their tables, metrics, and visualizations. This example demonstrates the correct syntax; your dashboard should reflect the user's actual requirements.

## Key Patterns (Read First)

### 1. Page Types (Required)
- `PAGE_TYPE_CANVAS` - Main content page with widgets
- `PAGE_TYPE_GLOBAL_FILTERS` - Dedicated filter page that affects all canvas pages

### 2. Widget Versions (Critical!)
| Widget Type | Version |
|-------------|---------|
| `counter`, `table` | **2** |
| `bar`, `line`, `area`, `pie` | **3** |
| `filter-*` | **2** |

### 3. KPI Counter with Currency Formatting
```json
"format": {
  "type": "number-currency",
  "currencyCode": "USD",
  "abbreviation": "compact",
  "decimalPlaces": {"type": "max", "places": 1}
}
```

### 4. Filter Binding to Multiple Datasets
Each filter query binds the filter to one dataset. Add multiple queries to filter multiple datasets:
```json
"queries": [
  {"name": "ds1_region", "query": {"datasetName": "dataset1", ...}},
  {"name": "ds2_region", "query": {"datasetName": "dataset2", ...}}
]
```

### 5. Layout Grid (6 columns)
```
y=0:  Header with title + description (w=6, h=2)
y=2:  KPI(w=2,h=3) | KPI(w=2,h=3) | KPI(w=2,h=3)  ← fills 6
y=5:  Section header (w=6, h=1)
y=6:  Area chart (w=6, h=5)
y=11: Section header (w=6, h=1)
y=12: Pie(w=2,h=5) | Bar chart(w=4,h=5)           ← fills 6
```

Use `\n\n` in text widget lines array to create line breaks within a single widget.

---

## Full Dashboard: Sales Analytics

This example shows a complete dashboard with:
- Title and subtitle text widgets
- 3 KPI counters with currency/number formatting
- Area chart for time series trends
- Pie chart for category breakdown
- Bar chart with color grouping by region
- Data table for detailed records
- Global filters (date range, region, category)

```json
{
  "datasets": [
    {
      "name": "ds_daily_sales",
      "displayName": "Daily Sales",
      "queryLines": [
        "SELECT sale_date, region, department, total_orders, total_units, total_revenue, total_cost, profit_margin ",
        "FROM catalog.schema.gold_daily_sales ",
        "ORDER BY sale_date"
      ]
    },
    {
      "name": "ds_products",
      "displayName": "Product Performance",
      "queryLines": [
        "SELECT product_id, product_name, department, region, units_sold, revenue, cost, profit ",
        "FROM catalog.schema.gold_product_performance"
      ]
    }
  ],
  "pages": [
    {
      "name": "sales_overview",
      "displayName": "Sales Overview",
      "pageType": "PAGE_TYPE_CANVAS",
      "layout": [
        {
          "widget": {
            "name": "header",
            "multilineTextboxSpec": {
              "lines": ["# Sales Dashboard\n\nMonitor daily sales, revenue, and profit margins across regions and departments."]
            }
          },
          "position": {"x": 0, "y": 0, "width": 6, "height": 2}
        },
        {
          "widget": {
            "name": "kpi_revenue",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_daily_sales",
                "fields": [{"name": "sum(total_revenue)", "expression": "SUM(`total_revenue`)"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2,
              "widgetType": "counter",
              "encodings": {
                "value": {
                  "fieldName": "sum(total_revenue)",
                  "displayName": "Total Revenue",
                  "format": {
                    "type": "number-currency",
                    "currencyCode": "USD",
                    "abbreviation": "compact",
                    "decimalPlaces": {"type": "max", "places": 1}
                  }
                }
              },
              "frame": {"title": "Total Revenue", "showTitle": true, "description": "For the selected period", "showDescription": true}
            }
          },
          "position": {"x": 0, "y": 2, "width": 2, "height": 3}
        },
        {
          "widget": {
            "name": "kpi_orders",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_daily_sales",
                "fields": [{"name": "sum(total_orders)", "expression": "SUM(`total_orders`)"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2,
              "widgetType": "counter",
              "encodings": {
                "value": {
                  "fieldName": "sum(total_orders)",
                  "displayName": "Total Orders",
                  "format": {
                    "type": "number",
                    "abbreviation": "compact",
                    "decimalPlaces": {"type": "max", "places": 0}
                  }
                }
              },
              "frame": {"title": "Total Orders", "showTitle": true, "description": "For the selected period", "showDescription": true}
            }
          },
          "position": {"x": 2, "y": 2, "width": 2, "height": 3}
        },
        {
          "widget": {
            "name": "kpi_profit",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_daily_sales",
                "fields": [{"name": "avg(profit_margin)", "expression": "AVG(`profit_margin`)"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2,
              "widgetType": "counter",
              "encodings": {
                "value": {
                  "fieldName": "avg(profit_margin)",
                  "displayName": "Avg Profit Margin",
                  "format": {
                    "type": "number-percent",
                    "decimalPlaces": {"type": "max", "places": 1}
                  }
                }
              },
              "frame": {"title": "Profit Margin", "showTitle": true, "description": "Average for period", "showDescription": true}
            }
          },
          "position": {"x": 4, "y": 2, "width": 2, "height": 3}
        },
        {
          "widget": {
            "name": "section_trends",
            "multilineTextboxSpec": {
              "lines": ["## Revenue Trend"]
            }
          },
          "position": {"x": 0, "y": 5, "width": 6, "height": 1}
        },
        {
          "widget": {
            "name": "chart_revenue_trend",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_daily_sales",
                "fields": [
                  {"name": "sale_date", "expression": "`sale_date`"},
                  {"name": "sum(total_revenue)", "expression": "SUM(`total_revenue`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 3,
              "widgetType": "area",
              "encodings": {
                "x": {
                  "fieldName": "sale_date",
                  "scale": {"type": "temporal"},
                  "axis": {"title": "Date"},
                  "displayName": "Date"
                },
                "y": {
                  "fieldName": "sum(total_revenue)",
                  "scale": {"type": "quantitative"},
                  "format": {
                    "type": "number-currency",
                    "currencyCode": "USD",
                    "abbreviation": "compact"
                  },
                  "axis": {"title": "Revenue ($)"},
                  "displayName": "Revenue ($)"
                }
              },
              "frame": {
                "title": "Daily Revenue",
                "showTitle": true,
                "description": "Track daily revenue trends"
              }
            }
          },
          "position": {"x": 0, "y": 6, "width": 6, "height": 5}
        },
        {
          "widget": {
            "name": "section_breakdown",
            "multilineTextboxSpec": {
              "lines": ["## Breakdown"]
            }
          },
          "position": {"x": 0, "y": 11, "width": 6, "height": 1}
        },
        {
          "widget": {
            "name": "chart_by_department",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_daily_sales",
                "fields": [
                  {"name": "department", "expression": "`department`"},
                  {"name": "sum(total_revenue)", "expression": "SUM(`total_revenue`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 3,
              "widgetType": "pie",
              "encodings": {
                "angle": {
                  "fieldName": "sum(total_revenue)",
                  "scale": {"type": "quantitative"},
                  "displayName": "Revenue"
                },
                "color": {
                  "fieldName": "department",
                  "scale": {"type": "categorical"},
                  "displayName": "Department"
                },
                "label": {"show": true}
              },
              "frame": {"title": "Revenue by Department", "showTitle": true}
            }
          },
          "position": {"x": 0, "y": 12, "width": 2, "height": 5}
        },
        {
          "widget": {
            "name": "chart_by_region",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_daily_sales",
                "fields": [
                  {"name": "sale_date", "expression": "`sale_date`"},
                  {"name": "region", "expression": "`region`"},
                  {"name": "sum(total_revenue)", "expression": "SUM(`total_revenue`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 3,
              "widgetType": "bar",
              "encodings": {
                "x": {
                  "fieldName": "sale_date",
                  "scale": {"type": "temporal"},
                  "axis": {"title": "Date"},
                  "displayName": "Date"
                },
                "y": {
                  "fieldName": "sum(total_revenue)",
                  "scale": {"type": "quantitative"},
                  "format": {
                    "type": "number-currency",
                    "currencyCode": "USD",
                    "abbreviation": "compact"
                  },
                  "axis": {"title": "Revenue ($)"},
                  "displayName": "Revenue ($)"
                },
                "color": {
                  "fieldName": "region",
                  "scale": {"type": "categorical"},
                  "displayName": "Region"
                }
              },
              "frame": {"title": "Revenue by Region", "showTitle": true}
            }
          },
          "position": {"x": 2, "y": 12, "width": 4, "height": 5}
        },
        {
          "widget": {
            "name": "section_products",
            "multilineTextboxSpec": {
              "lines": ["## Top Products"]
            }
          },
          "position": {"x": 0, "y": 17, "width": 6, "height": 1}
        },
        {
          "widget": {
            "name": "table_products",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_products",
                "fields": [
                  {"name": "product_name", "expression": "`product_name`"},
                  {"name": "department", "expression": "`department`"},
                  {"name": "units_sold", "expression": "`units_sold`"},
                  {"name": "revenue", "expression": "`revenue`"},
                  {"name": "profit", "expression": "`profit`"}
                ],
                "disaggregated": true
              }
            }],
            "spec": {
              "version": 2,
              "widgetType": "table",
              "encodings": {
                "columns": [
                  {"fieldName": "product_name", "displayName": "Product"},
                  {"fieldName": "department", "displayName": "Department"},
                  {"fieldName": "units_sold", "displayName": "Units Sold"},
                  {"fieldName": "revenue", "displayName": "Revenue ($)"},
                  {"fieldName": "profit", "displayName": "Profit ($)"}
                ]
              },
              "frame": {
                "title": "Product Performance",
                "showTitle": true,
                "description": "Top products by revenue"
              }
            }
          },
          "position": {"x": 0, "y": 18, "width": 6, "height": 6}
        }
      ]
    },
    {
      "name": "global_filters",
      "displayName": "Filters",
      "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
      "layout": [
        {
          "widget": {
            "name": "filter_date_range",
            "queries": [
              {
                "name": "ds_sales_date",
                "query": {
                  "datasetName": "ds_daily_sales",
                  "fields": [{"name": "sale_date", "expression": "`sale_date`"}],
                  "disaggregated": false
                }
              }
            ],
            "spec": {
              "version": 2,
              "widgetType": "filter-date-range-picker",
              "encodings": {
                "fields": [
                  {"fieldName": "sale_date", "displayName": "Date", "queryName": "ds_sales_date"}
                ]
              },
              "selection": {
                "defaultSelection": {
                  "range": {
                    "dataType": "DATE",
                    "min": {"value": "now/y"},
                    "max": {"value": "now/y"}
                  }
                }
              },
              "frame": {"showTitle": true, "title": "Date Range"}
            }
          },
          "position": {"x": 0, "y": 0, "width": 2, "height": 2}
        },
        {
          "widget": {
            "name": "filter_region",
            "queries": [
              {
                "name": "ds_sales_region",
                "query": {
                  "datasetName": "ds_daily_sales",
                  "fields": [{"name": "region", "expression": "`region`"}],
                  "disaggregated": false
                }
              },
              {
                "name": "ds_products_region",
                "query": {
                  "datasetName": "ds_products",
                  "fields": [{"name": "region", "expression": "`region`"}],
                  "disaggregated": false
                }
              }
            ],
            "spec": {
              "version": 2,
              "widgetType": "filter-multi-select",
              "encodings": {
                "fields": [
                  {"fieldName": "region", "displayName": "Region", "queryName": "ds_sales_region"},
                  {"fieldName": "region", "displayName": "Region", "queryName": "ds_products_region"}
                ]
              },
              "frame": {"showTitle": true, "title": "Region"}
            }
          },
          "position": {"x": 2, "y": 0, "width": 2, "height": 2}
        },
        {
          "widget": {
            "name": "filter_department",
            "queries": [
              {
                "name": "ds_sales_dept",
                "query": {
                  "datasetName": "ds_daily_sales",
                  "fields": [{"name": "department", "expression": "`department`"}],
                  "disaggregated": false
                }
              },
              {
                "name": "ds_products_dept",
                "query": {
                  "datasetName": "ds_products",
                  "fields": [{"name": "department", "expression": "`department`"}],
                  "disaggregated": false
                }
              }
            ],
            "spec": {
              "version": 2,
              "widgetType": "filter-multi-select",
              "encodings": {
                "fields": [
                  {"fieldName": "department", "displayName": "Department", "queryName": "ds_sales_dept"},
                  {"fieldName": "department", "displayName": "Department", "queryName": "ds_products_dept"}
                ]
              },
              "frame": {"showTitle": true, "title": "Department"}
            }
          },
          "position": {"x": 4, "y": 0, "width": 2, "height": 2}
        }
      ]
    }
  ]
}
```
