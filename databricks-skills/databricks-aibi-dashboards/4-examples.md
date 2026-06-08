# Complete Dashboard Example

A working dashboard JSON that exercises the new feature set:

- **`dataset.columns[]` + `MEASURE()`** — reusable named measures across widgets.
- **`forecast-line`** with `AI_FORECAST` SQL and a **vertical-line annotation** for a known event.
- **`pivot`** with conditional cell coloring.
- **`symbol-map`** (lat/lon) with a continuous color ramp.
- **`range-slider`** filter on a numeric column.
- **Counter sparkline** via the `period` encoding.

**Adapt this to the user's actual data and story** — the structure and feature mix is what to copy, not the column names.

## Key Patterns (read first)

### Page types
- `PAGE_TYPE_CANVAS` — content page with widgets.
- `PAGE_TYPE_GLOBAL_FILTERS` — dedicated filter page, applies to all canvas pages whose datasets contain the filter field.

### Widget versions used in this example

| Widget | Version |
|---|---|
| `counter`, `table`, `filter-*`, `range-slider`, `symbol-map` | **2** |
| `bar`, `line`, `area`, `pie`, `pivot`, `histogram`, `heatmap` | **3** |
| `combo`, `choropleth-map`, `forecast-line`, `sankey`, `funnel`, `box`, `waterfall` | **1** |

See [SKILL.md](SKILL.md#widget-index-version--where-documented) for the full version table.

### Layout (12-col grid)

```
y=0:  Header (w=12, h=2)
y=2:  KPI (w=3) | KPI w/ sparkline (w=3) | KPI (w=3) | KPI (w=3)  ← fills 12
y=5:  Forecast (w=8, h=4)            | Pivot summary (w=4, h=4)
y=9:  Symbol map (w=8, h=5)          | Histogram (w=4, h=5)
y=14: Detail table (w=12, h=6)
```

---

## Full Dashboard: Support Operations

```json
{
  "datasets": [
    {
      "name": "ds_support",
      "displayName": "Support cases",
      "queryLines": [
        "SELECT case_id, opened_at, closed_at, priority, channel, region_name,",
        "       customer_id, reopened_flag, satisfaction_score,",
        "       customer_latitude, customer_longitude,",
        "       (unix_timestamp(closed_at) - unix_timestamp(opened_at)) / 3600.0 AS time_to_resolution_hours",
        "FROM support_cases"
      ],
      "columns": [
        {"displayName": "Total Cases",       "description": "Count of support cases",
         "expression": "COUNT(`case_id`)"},
        {"displayName": "Avg Resolution Hours",
         "description": "Mean resolution time across closed cases",
         "expression": "AVG(`time_to_resolution_hours`)"},
        {"displayName": "Reopen Rate %",
         "description": "Percent of cases reopened after closure",
         "expression": "SUM(CASE WHEN `reopened_flag`=true THEN 1 ELSE 0 END) * 100.0 / COUNT(`case_id`)"},
        {"displayName": "Avg Satisfaction",
         "description": "Average customer satisfaction (1-10)",
         "expression": "AVG(`satisfaction_score`)"},
        {"displayName": "Priority Level",
         "description": "Sortable priority label",
         "expression": "CASE WHEN `priority`='Critical' THEN '1-Critical' WHEN `priority`='High' THEN '2-High' WHEN `priority`='Medium' THEN '3-Medium' ELSE '4-Low' END"}
      ]
    },
    {
      "name": "ds_forecast",
      "displayName": "Cases forecast",
      "queryLines": [
        "WITH original AS (\n",
        "  -- Cutoff grain MUST match the DATE_TRUNC grain to drop the partial week\n",
        "  SELECT DATE_TRUNC('WEEK', opened_at) AS opened_at, COUNT(*) AS count\n",
        "  FROM support_cases\n",
        "  WHERE DATE_TRUNC('WEEK', opened_at) < DATE_TRUNC('WEEK', current_date())\n",
        "  GROUP BY 1\n",
        "),\n",
        "dates AS (SELECT MAX(opened_at) AS max_d, MIN(opened_at) AS min_d FROM original),\n",
        "forecast AS (\n",
        "  SELECT opened_at, count_forecast, count_upper, count_lower, NULL AS count\n",
        "  FROM AI_FORECAST(TABLE(original),\n",
        "    horizon  => (SELECT max_d + MAKE_DT_INTERVAL(CAST(FLOOR(DATEDIFF(max_d, min_d) * 0.5) AS INT), 0, 0, 0) FROM dates),\n",
        "    time_col => 'opened_at', value_col => 'count')\n",
        ")\n",
        "SELECT * FROM forecast UNION ALL SELECT opened_at, NULL, NULL, NULL, count FROM original"
      ]
    }
  ],

  "pages": [
    {
      "name": "overview",
      "displayName": "Overview",
      "pageType": "PAGE_TYPE_CANVAS",
      "layoutVersion": "GRID_V1",
      "layout": [

        {
          "widget": {
            "name": "header",
            "multilineTextboxSpec": {"lines": ["# Support Operations\n\nWeekly volume, resolution speed, and forecast."]}
          },
          "position": {"x": 0, "y": 0, "width": 12, "height": 2}
        },

        {
          "widget": {
            "name": "kpi-total-cases",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [{"name": "measure(Total Cases)", "expression": "MEASURE(`Total Cases`)"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "counter",
              "encodings": {
                "value": {"fieldName": "measure(Total Cases)", "displayName": "Total Cases",
                          "format": {"type": "number", "abbreviation": "compact"}}
              },
              "frame": {"title": "Total Cases", "showTitle": true}
            }
          },
          "position": {"x": 0, "y": 2, "width": 3, "height": 3}
        },

        {
          "widget": {
            "name": "kpi-volume-trend",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [
                  {"name": "weekly(opened_at)", "expression": "DATE_TRUNC(\"WEEK\", `opened_at`)"},
                  {"name": "measure(Total Cases)", "expression": "MEASURE(`Total Cases`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "counter",
              "encodings": {
                "value":  {"fieldName": "measure(Total Cases)", "displayName": "This Week"},
                "period": {"fieldName": "weekly(opened_at)"}
              },
              "frame": {"title": "Volume (with trend)", "showTitle": true}
            }
          },
          "position": {"x": 3, "y": 2, "width": 3, "height": 3}
        },

        {
          "widget": {
            "name": "kpi-resolution",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [{"name": "measure(Avg Resolution Hours)", "expression": "MEASURE(`Avg Resolution Hours`)"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "counter",
              "encodings": {
                "value": {"fieldName": "measure(Avg Resolution Hours)", "displayName": "Avg Hours",
                          "format": {"type": "number", "decimalPlaces": {"type": "max", "places": 1}}}
              },
              "frame": {"title": "Avg Resolution Time", "showTitle": true}
            }
          },
          "position": {"x": 6, "y": 2, "width": 3, "height": 3}
        },

        {
          "widget": {
            "name": "kpi-reopen",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [{"name": "measure(Reopen Rate %)", "expression": "MEASURE(`Reopen Rate %`)"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "counter",
              "encodings": {
                "value": {"fieldName": "measure(Reopen Rate %)", "displayName": "Reopen Rate",
                          "format": {"type": "number", "decimalPlaces": {"type": "max", "places": 1}}}
              },
              "frame": {"title": "Reopen Rate (%)", "showTitle": true}
            }
          },
          "position": {"x": 9, "y": 2, "width": 3, "height": 3}
        },

        {
          "widget": {
            "name": "case-forecast",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_forecast",
                "fields": [
                  {"name": "opened_at",       "expression": "`opened_at`"},
                  {"name": "count",           "expression": "`count`"},
                  {"name": "count_forecast",  "expression": "`count_forecast`"},
                  {"name": "count_upper",     "expression": "`count_upper`"},
                  {"name": "count_lower",     "expression": "`count_lower`"}
                ],
                "disaggregated": true
              }
            }],
            "spec": {
              "version": 1, "widgetType": "forecast-line",
              "encodings": {
                "x": {"fieldName": "opened_at", "scale": {"type": "temporal"}},
                "y": {
                  "scale":           {"type": "quantitative"},
                  "original":        {"fieldName": "count",          "displayName": "Cases"},
                  "prediction":      {"fieldName": "count_forecast", "displayName": "Forecast"},
                  "predictionUpper": {"fieldName": "count_upper"},
                  "predictionLower": {"fieldName": "count_lower"}
                }
              },
              "annotations": [
                {
                  "type": "vertical-line",
                  "encodings": {
                    "x":     {"dataValue": "2024-11-28T12:00:00.000", "dataType": "DATETIME"},
                    "label": {"value": "Thanksgiving"},
                    "color": {"value": {"themeColorType": "visualizationColors", "position": 3}}
                  }
                }
              ],
              "frame": {"showTitle": true, "title": "Case Volume — actuals + forecast"}
            }
          },
          "position": {"x": 0, "y": 5, "width": 8, "height": 4}
        },

        {
          "widget": {
            "name": "priority-by-channel",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [
                  {"name": "channel",        "expression": "`channel`"},
                  {"name": "Priority Level", "expression": "`Priority Level`"},
                  {"name": "count(case_id)", "expression": "COUNT(`case_id`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 3,
              "widgetType": "pivot",
              "encodings": {
                "rows":    [{"fieldName": "channel"}],
                "columns": [{"fieldName": "Priority Level"}],
                "cell": {
                  "type": "multi-cell",
                  "fields": [{
                    "fieldName": "count(case_id)", "cellType": "text",
                    "style": {
                      "type": "basic",
                      "rules": [
                        {"condition": {"operand": {"type": "data-value", "value": "30"}, "operator": ">="},
                         "backgroundColor": {"themeColorType": "visualizationColors", "position": 6}},
                        {"condition": {"operand": {"type": "data-value", "value": "10"}, "operator": ">="},
                         "backgroundColor": {"themeColorType": "visualizationColors", "position": 3}}
                      ]
                    }
                  }]
                }
              },
              "frame": {"showTitle": true, "title": "Cases by channel × priority"}
            }
          },
          "position": {"x": 8, "y": 5, "width": 4, "height": 4}
        },

        {
          "widget": {
            "name": "customer-map",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [
                  {"name": "customer_latitude",  "expression": "`customer_latitude`"},
                  {"name": "customer_longitude", "expression": "`customer_longitude`"},
                  {"name": "measure(Avg Satisfaction)", "expression": "MEASURE(`Avg Satisfaction`)"},
                  {"name": "count(*)", "expression": "COUNT(`*`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "symbol-map",
              "encodings": {
                "coordinates": {
                  "latitude":  {"fieldName": "customer_latitude"},
                  "longitude": {"fieldName": "customer_longitude"}
                },
                "color": {
                  "fieldName": "measure(Avg Satisfaction)",
                  "scale":  {"type": "quantitative", "colorRamp": {"mode": "scheme", "scheme": "RdYlBu"}}
                },
                "size":  {"fieldName": "count(*)", "scale": {"type": "quantitative"}}
              },
              "mark": {"opacity": 0.7},
              "frame": {"showTitle": true, "title": "Customer Satisfaction Map"}
            }
          },
          "position": {"x": 0, "y": 9, "width": 8, "height": 5}
        },

        {
          "widget": {
            "name": "resolution-distribution",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [
                  {"name": "bin(time_to_resolution_hours, binWidth=2)",
                   "expression": "BIN_FLOOR(`time_to_resolution_hours`, 2)"},
                  {"name": "count(*)", "expression": "COUNT(`*`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 3, "widgetType": "histogram",
              "encodings": {
                "x": {"fieldName": "bin(time_to_resolution_hours, binWidth=2)",
                      "scale": {"type": "quantitative"}},
                "y": {"fieldName": "count(*)", "scale": {"type": "quantitative"}}
              },
              "frame": {"showTitle": true, "title": "Resolution time (hours)"}
            }
          },
          "position": {"x": 8, "y": 9, "width": 4, "height": 5}
        },

        {
          "widget": {
            "name": "case-detail",
            "queries": [{
              "name": "main_query",
              "query": {
                "datasetName": "ds_support",
                "fields": [
                  {"name": "case_id",                  "expression": "`case_id`"},
                  {"name": "opened_at",                "expression": "`opened_at`"},
                  {"name": "channel",                  "expression": "`channel`"},
                  {"name": "Priority Level",           "expression": "`Priority Level`"},
                  {"name": "time_to_resolution_hours", "expression": "`time_to_resolution_hours`"},
                  {"name": "satisfaction_score",       "expression": "`satisfaction_score`"}
                ],
                "disaggregated": true
              }
            }],
            "spec": {
              "version": 2, "widgetType": "table",
              "encodings": {
                "columns": [
                  {"fieldName": "case_id",                  "displayName": "Case"},
                  {"fieldName": "opened_at",                "displayName": "Opened"},
                  {"fieldName": "channel",                  "displayName": "Channel"},
                  {"fieldName": "Priority Level",           "displayName": "Priority"},
                  {"fieldName": "time_to_resolution_hours", "displayName": "Hours to resolve",
                   "format": {"type": "number", "decimalPlaces": {"type": "max", "places": 1}},
                   "style": {
                     "type": "basic",
                     "rules": [
                       {"condition": {"operand": {"type": "data-value", "value": "24"}, "operator": ">"},
                        "backgroundColor": {"themeColorType": "visualizationColors", "position": 6}}
                     ]
                   }},
                  {"fieldName": "satisfaction_score",       "displayName": "CSAT"}
                ]
              },
              "frame": {"showTitle": true, "title": "Case Detail"}
            }
          },
          "position": {"x": 0, "y": 14, "width": 12, "height": 6}
        }
      ]
    },

    {
      "name": "filters",
      "displayName": "Filters",
      "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
      "layoutVersion": "GRID_V1",
      "layout": [
        {
          "widget": {
            "name": "filter-date",
            "queries": [{
              "name": "ds_date",
              "query": {
                "datasetName": "ds_support",
                "fields": [{"name": "opened_at", "expression": "`opened_at`"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "filter-date-range-picker",
              "encodings": {"fields": [{"fieldName": "opened_at", "queryName": "ds_date"}]},
              "frame": {"showTitle": true, "title": "Date"}
            }
          },
          "position": {"x": 0, "y": 0, "width": 4, "height": 2}
        },
        {
          "widget": {
            "name": "filter-region",
            "queries": [{
              "name": "ds_region",
              "query": {
                "datasetName": "ds_support",
                "fields": [{"name": "region_name", "expression": "`region_name`"}],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "filter-multi-select",
              "encodings": {"fields": [{"fieldName": "region_name", "queryName": "ds_region", "displayName": "Region"}]},
              "frame": {"showTitle": true, "title": "Region"}
            }
          },
          "position": {"x": 4, "y": 0, "width": 4, "height": 2}
        },
        {
          "widget": {
            "name": "filter-resolution-time",
            "queries": [{
              "name": "ds_resolution",
              "query": {
                "datasetName": "ds_support",
                "fields": [
                  {"name": "min(time_to_resolution_hours)", "expression": "MIN(`time_to_resolution_hours`)"},
                  {"name": "max(time_to_resolution_hours)", "expression": "MAX(`time_to_resolution_hours`)"}
                ],
                "disaggregated": false
              }
            }],
            "spec": {
              "version": 2, "widgetType": "range-slider",
              "encodings": {"fields": [{"fieldName": "time_to_resolution_hours", "queryName": "ds_resolution"}]},
              "frame": {"showTitle": true, "title": "Resolution time (hrs)"}
            }
          },
          "position": {"x": 8, "y": 0, "width": 4, "height": 2}
        }
      ]
    }
  ],

  "uiSettings": {
    "theme": {
      "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
      "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
      "widgetBorderColor":     {"light": "#FFFFFF", "dark": "#11171C"},
      "fontColor":             {"light": "#11171C", "dark": "#E8ECF0"},
      "selectionColor":        {"light": "#2272B4", "dark": "#8ACAFF"},
      "visualizationColors": [
        "#3B82F6",
        "#10B981",
        "#F59E0B",
        "#8B5CF6",
        "#14B8A6",
        "#EF4444",
        "#6B7280"
      ],
      "widgetHeaderAlignment": "LEFT"
    }
  }
}
```

The palette puts the Critical-red at `position: 6` (`#EF4444`) and the warning-amber at `position: 3` (`#F59E0B`) — that's what the pivot conditional rules and the forecast annotation reference. Position 1 (blue) is the default for chart series that don't pin a value.

## What each widget demonstrates

| Widget | Feature shown |
|---|---|
| 4 KPI counters | `MEASURE()` referencing dataset-level `columns[]` |
| `kpi-volume-trend` counter | `period` encoding (sparkline behind the value) |
| `case-forecast` | `forecast-line` with `AI_FORECAST` SQL + `vertical-line` annotation |
| `priority-by-channel` | `pivot` with conditional cell-color rules |
| `customer-map` | `symbol-map` with continuous `colorRamp` |
| `resolution-distribution` | `histogram` with `bin(col, binWidth=N)` |
| `case-detail` table | per-column `format` + conditional `style.rules` for high-hour cells |
| `filter-resolution-time` | `range-slider` filter on a numeric column |
| Global filters page | Filters bound to one source dataset cascade to every widget that uses it |

Adapt the table names, columns, story, and palette to your domain — the structure stays the same.
