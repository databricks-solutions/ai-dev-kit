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
  "position": {"x": 0, "y": 0, "width": 2, "height": 2}
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

## Page-Level Filter Example

Place filter widget directly on a `PAGE_TYPE_CANVAS` page (same widget structure as global filter, but only affects that page):

```json
{
  "name": "platform_breakdown",
  "displayName": "Platform Breakdown",
  "pageType": "PAGE_TYPE_CANVAS",
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
      "position": {"x": 4, "y": 0, "width": 2, "height": 2}
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
    "SELECT category, SUM(revenue) as revenue FROM catalog.schema.orders ",
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
  "position": {"x": 0, "y": 0, "width": 2, "height": 2}
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
  "position": {"x": 0, "y": 0, "width": 2, "height": 2}
}
```

Each `queryName` in `encodings.fields` binds the filter to that specific dataset. Datasets not bound will not be filtered.

---

## Filter Layout Guidelines

- Global filters: Position on dedicated filter page, stack vertically at `x=0`
- Page-level filters: Position in header area of page (e.g., top-right corner)
- Typical sizing: `width: 2, height: 2`
