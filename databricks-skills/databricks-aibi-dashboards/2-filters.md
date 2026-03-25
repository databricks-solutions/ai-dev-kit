# Filters (Global vs Page-Level)

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

## Filter Layout Guidelines

- Global filters: Position on dedicated filter page, stack vertically at `x=0`
- Page-level filters: Position in header area of page (e.g., top-right corner)
- Typical sizing: `width: 2, height: 2`
