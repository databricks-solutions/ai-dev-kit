# Advanced Widget Specifications

Advanced visualization types for AI/BI dashboards. For core widgets (text, counter, table, bar, line, pie), see [1-widget-specifications.md](1-widget-specifications.md).

---

## Area Chart

- `version`: **3**
- `widgetType`: "area"
- Same structure as line chart - useful for showing cumulative values or emphasizing volume

```json
"spec": {
  "version": 3,
  "widgetType": "area",
  "encodings": {
    "x": {"fieldName": "week_start", "scale": {"type": "temporal"}},
    "y": {
      "scale": {"type": "quantitative"},
      "fields": [
        {"fieldName": "revenue_usd", "displayName": "Revenue"},
        {"fieldName": "returns_usd", "displayName": "Returns"}
      ]
    }
  }
}
```

---

## Scatter Plot / Bubble Chart

- `version`: **3**
- `widgetType`: "scatter"
- `x`, `y`: quantitative or temporal
- `size`: optional quantitative field for bubble size
- `color`: optional categorical or quantitative for grouping

```json
"spec": {
  "version": 3,
  "widgetType": "scatter",
  "encodings": {
    "x": {"fieldName": "return_date", "scale": {"type": "temporal"}},
    "y": {"fieldName": "daily_returns", "scale": {"type": "quantitative"}},
    "size": {"fieldName": "count(*)", "scale": {"type": "quantitative"}},
    "color": {"fieldName": "category", "scale": {"type": "categorical"}}
  }
}
```

---

## Combo Chart (Bar + Line)

Combines bar and line visualizations on the same chart - useful for showing related metrics with different scales.

- `version`: **1**
- `widgetType`: "combo"
- `y.primary`: bar chart fields
- `y.secondary`: line chart fields

```json
{
  "widget": {
    "name": "revenue-and-growth",
    "queries": [{
      "name": "main_query",
      "query": {
        "datasetName": "metrics_ds",
        "fields": [
          {"name": "daily(date)", "expression": "DATE_TRUNC(\"DAY\", `date`)"},
          {"name": "sum(revenue)", "expression": "SUM(`revenue`)"},
          {"name": "avg(growth_rate)", "expression": "AVG(`growth_rate`)"}
        ],
        "disaggregated": false
      }
    }],
    "spec": {
      "version": 1,
      "widgetType": "combo",
      "encodings": {
        "x": {"fieldName": "daily(date)", "scale": {"type": "temporal"}},
        "y": {
          "scale": {"type": "quantitative"},
          "primary": {
            "fields": [{"fieldName": "sum(revenue)", "displayName": "Revenue ($)"}]
          },
          "secondary": {
            "fields": [{"fieldName": "avg(growth_rate)", "displayName": "Growth Rate"}]
          }
        },
        "label": {"show": false}
      },
      "frame": {"title": "Revenue & Growth Rate", "showTitle": true}
    }
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 5}
}
```

---

## Choropleth Map

Displays geographic regions colored by aggregate values. Requires a field with geographic names (state names, country names, etc.).

- `version`: **1**
- `widgetType`: "choropleth-map"
- `region`: defines the geographic area mapping
- `color`: quantitative field for coloring regions

```json
"spec": {
  "version": 1,
  "widgetType": "choropleth-map",
  "encodings": {
    "region": {
      "regionType": "mapbox-v4-admin",
      "admin0": {
        "type": "value",
        "value": "United States",
        "geographicRole": "admin0-name"
      },
      "admin1": {
        "fieldName": "state_name",
        "type": "field",
        "geographicRole": "admin1-name"
      }
    },
    "color": {
      "fieldName": "sum(revenue)",
      "scale": {"type": "quantitative"}
    }
  }
}
```

### Region Configuration

**Region levels:**
- `admin0`: Country level - use `"type": "value"` with fixed country name
- `admin1`: State/Province level - use `"type": "field"` with your data column
- `admin2`: County/District level

**Geographic roles:**
- `admin0-name`, `admin1-name`, `admin2-name` - match by name
- `admin0-iso`, `admin1-iso` - match by ISO code

**Supported countries for admin1:** United States, Japan (prefectures), and others.

### Color Scale for Maps

> **Note**: Unlike other charts, choropleth-map supports additional color scale properties:
> - `scheme`: color scheme name (e.g., "YIGnBu")
> - `colorRamp`: custom color gradient
> - `mappings`: explicit value-to-color mappings

---

## Other Visualization Types

The following visualization types are available in Databricks AI/BI dashboards but are less commonly used. Refer to [Databricks documentation](https://docs.databricks.com/aws/en/visualizations/visualization-types) for details:

| Widget Type | Description |
|-------------|-------------|
| heatmap | Color intensity grid for numerical data |
| histogram | Frequency distribution with configurable bins |
| funnel | Stage-based metric analysis |
| sankey | Flow visualization between value sets |
| box | Distribution summary with quartiles |
| marker-map | Latitude/longitude point markers |
| pivot | Drag-and-drop aggregation table |
| word-cloud | Word frequency visualization |
| sunburst | Hierarchical data in concentric circles |
| cohort | Group outcome analysis over time |
