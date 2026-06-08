# Filters (Global vs Page-Level)

> **CRITICAL**: Filter widgets use DIFFERENT widget types than charts!
> - Valid types: `filter-multi-select`, `filter-single-select`, `filter-date-range-picker`
> - **DO NOT** use `widgetType: "filter"` - this does not exist and will cause errors
> - Filters use `spec.version: 2`
> - **ALWAYS include `frame` with `showTitle: true`** for filter widgets

**Filter widget types:**
- `filter-date-range-picker`: for DATE/TIMESTAMP fields (date range selection)
- `filter-single-select`: categorical with single selection
- `filter-multi-select`: categorical with multiple selections (preferred for drill-down)
- `range-slider`: numeric range filter on a quantitative column (e.g., "resolution time hours", "order amount")

> **Performance note**: Global filters automatically apply `WHERE` clauses to dataset queries at runtime. You don't need to pre-filter data in your SQL - the dashboard engine handles this efficiently.

---

## Global Filters vs Page-Level Filters

| Type | Placement | Scope | Use Case |
|------|-----------|-------|----------|
| **Global Filter** | Dedicated page with `"pageType": "PAGE_TYPE_GLOBAL_FILTERS"` | Affects ALL pages that have datasets with the filter field | Cross-dashboard filtering (e.g., date range, campaign) |
| **Page-Level Filter** | Regular page with `"pageType": "PAGE_TYPE_CANVAS"` | Affects ONLY widgets on that same page | Page-specific filtering (e.g., platform filter on breakdown page only) |

**Key Insight**: A filter only affects datasets that contain the filter field. To have a filter affect only specific pages:
1. Include the filter dimension in datasets for pages that should be filtered
2. Exclude the filter dimension from datasets for pages that should NOT be filtered

---

## Filter Widget Structure

> **CRITICAL**: Do NOT use `associative_filter_predicate_group` - it causes SQL errors!
> Use a simple field expression instead.

```json
{
  "widget": {
    "name": "filter_region",
    "queries": [{
      "name": "ds_data_region",  // Query name - must match queryName in encodings!
      "query": {
        "datasetName": "ds_data",
        "fields": [
          {"name": "region", "expression": "`region`"}
        ],
        "disaggregated": false  // CRITICAL: Always false for filters!
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "filter-multi-select",
      "encodings": {
        "fields": [{
          "fieldName": "region",
          "displayName": "Region",
          "queryName": "ds_data_region"  // Must match queries[].name above!
        }]
      },
      "frame": {"showTitle": true, "title": "Region"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 4, "height": 2}
}
```

---

## Global Filter Example

Place on a dedicated filter page:

```json
{
  "name": "filters",
  "displayName": "Filters",
  "pageType": "PAGE_TYPE_GLOBAL_FILTERS",
  "layoutVersion": "GRID_V1",
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
      "position": {"x": 0, "y": 0, "width": 4, "height": 2}
    }
  ]
}
```

---

## Page-Level Filter Example

Place filter widget directly on a `PAGE_TYPE_CANVAS` page (same widget structure as global filter, but only affects that page):

```json
{
  "name": "platform_breakdown",
  "displayName": "Platform Breakdown",
  "pageType": "PAGE_TYPE_CANVAS",
  "layoutVersion": "GRID_V1",
  "layout": [
    {"widget": {...}, "position": {...}},
    {
      "widget": {
        "name": "filter_platform",
        "queries": [{"name": "ds_platform", "query": {"datasetName": "platform_data", "fields": [{"name": "platform", "expression": "`platform`"}], "disaggregated": false}}],
        "spec": {
          "version": 2,
          "widgetType": "filter-multi-select",
          "encodings": {"fields": [{"fieldName": "platform", "displayName": "Platform", "queryName": "ds_platform"}]},
          "frame": {"showTitle": true, "title": "Platform"}
        }
      },
      "position": {"x": 8, "y": 0, "width": 4, "height": 2}
    }
  ]
}
```

---

## Date Range Filtering

> **Best Practice**: Most dashboards should include a date range filter. However, metrics that are not based on a time range (like "MRR" or "All-Time Total") should NOT be date-filtered - omit them from the filter's queries.

**Two binding approaches** (can be combined in one filter):
- **Field-based**: Bind to a date column in SELECT → filter auto-applies `IN_RANGE()`
- **Parameter-based**: Use `:param.min`/`:param.max` in WHERE clause for pre-aggregation filtering

```json
// Dataset with parameter (for aggregated queries)
{
  "name": "revenue_by_category",
  "queryLines": [
    "SELECT category, SUM(revenue) as revenue FROM orders ",
    "WHERE order_date BETWEEN :date_range.min AND :date_range.max ",
    "GROUP BY category"
  ],
  "parameters": [{
    "keyword": "date_range", "dataType": "DATE", "complexType": "RANGE",
    "defaultSelection": {"range": {"dataType": "DATE", "min": {"value": "now-12M/M"}, "max": {"value": "now/M"}}}
  }]
}

// Filter widget binding to both field and parameter
{
  "widget": {
    "name": "date_range_filter",
    "queries": [
      {"name": "q_trend", "query": {"datasetName": "weekly_trend", "fields": [{"name": "week_start", "expression": "`week_start`"}], "disaggregated": false}},
      {"name": "q_category", "query": {"datasetName": "revenue_by_category", "parameters": [{"name": "date_range", "keyword": "date_range"}], "disaggregated": false}}
    ],
    "spec": {
      "version": 2,
      "widgetType": "filter-date-range-picker",
      "encodings": {
        "fields": [
          {"fieldName": "week_start", "queryName": "q_trend"},
          {"parameterName": "date_range", "queryName": "q_category"}
        ]
      },
      "frame": {"showTitle": true, "title": "Date Range"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 4, "height": 2}
}
```

---

## Multi-Dataset Filters

When a filter should affect multiple datasets (e.g., "Region" filter for both sales and customers data), add multiple queries - one per dataset:

```json
{
  "widget": {
    "name": "filter_region",
    "queries": [
      {
        "name": "sales_region",
        "query": {
          "datasetName": "sales",
          "fields": [{"name": "region", "expression": "`region`"}],
          "disaggregated": false
        }
      },
      {
        "name": "customers_region",
        "query": {
          "datasetName": "customers",
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
          {"fieldName": "region", "displayName": "Region (Sales)", "queryName": "sales_region"},
          {"fieldName": "region", "displayName": "Region (Customers)", "queryName": "customers_region"}
        ]
      },
      "frame": {"showTitle": true, "title": "Region"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 4, "height": 2}
}
```

Each `queryName` in `encodings.fields` binds the filter to that specific dataset. Datasets not bound will not be filtered.

---

## Multi-Select Parameters (`MULTI`)

When the dataset **pre-aggregates** (`GROUP BY` in the SQL), uses a CTE, or wraps a table function (e.g. `AI_FORECAST`), a field-based filter can't auto-inject a `WHERE` — you must filter explicitly with a parameter. Same goes when you want the filter expressed in SQL for traceability.

A `MULTI` parameter binds as a **SQL `ARRAY`**, not an `IN`-list. Two rules to filter correctly:

```sql
-- ❌ WRONG: a MULTI param is an ARRAY → DATATYPE_MISMATCH (STRING vs ARRAY<STRING>)
WHERE category IN (:category_filter)

-- ✅ RIGHT: array_contains, with size()=0 guard so an empty selection means "all"
WHERE (size(:category_filter) = 0 OR array_contains(:category_filter, category))
```

The empty-selection default is an **empty array, not NULL** — without the `size()=0` guard, the dashboard loads showing zero rows.

```json
{
  "name": "metric_by_category",
  "queryLines": [
    "SELECT category, SUM(revenue) AS total FROM orders ",
    "WHERE (size(:category_filter) = 0 OR array_contains(:category_filter, category)) ",
    "GROUP BY category"
  ],
  "parameters": [{
    "keyword": "category_filter",
    "dataType": "STRING",
    "complexType": "MULTI",
    "defaultSelection": {"values": {"dataType": "STRING", "values": []}}
  }]
}
```

The filter widget binds the parameter via `parameterName` (NOT `fieldName`), same shape as the date-range parameter example above:

```json
"encodings": {"fields": [{"parameterName": "category_filter", "queryName": "q_param"}]}
```

> **Parameters live on the dataset + the filter widget only.** Don't add `parameters` to a chart/counter widget's own query — the chart reads the dataset, which the filter has already parameterized. Adding parameters to the consuming widget makes it render blank with no error.

---

## Range Slider (numeric range filter)

For filtering on a numeric column where the user wants to drag a min/max slider — e.g., resolution-time hours, amount, age. The query exposes `MIN(col)` and `MAX(col)` so the dashboard knows the slider bounds; `encodings.fields[].fieldName` is the underlying column name.

```json
{
  "widget": {
    "name": "time-to-resolution",
    "queries": [{
      "name": "ds_resolution",
      "query": {
        "datasetName": "ds_cases",
        "fields": [
          {"name": "min(time_to_resolution_hours)", "expression": "MIN(`time_to_resolution_hours`)"},
          {"name": "max(time_to_resolution_hours)", "expression": "MAX(`time_to_resolution_hours`)"}
        ],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 2,
      "widgetType": "range-slider",
      "encodings": {
        "fields": [
          {"fieldName": "time_to_resolution_hours", "queryName": "ds_resolution"}
        ]
      },
      "frame": {"showTitle": true, "title": "Resolution time (hours)"}
    }
  },
  "position": {"x": 0, "y": 0, "width": 4, "height": 2}
}
```

`range-slider` only works on numeric / temporal columns. On a categorical field it will fail at render. To filter a numeric field by an explicit min/max in SQL (rather than a UI-only WHERE), bind to a `:param.min`/`:param.max` parameter — same pattern as date-range, see "Date Range Filtering" above.

---

## Filter Layout Guidelines

- Global filters: Position on dedicated filter page, stack vertically at `x=0`
- Page-level filters: Position in header area of page (e.g., top-right corner)
- Typical sizing: `width: 4, height: 2`
