# Widget Specifications

Core widget types for AI/BI dashboards. For advanced visualizations (area, scatter, choropleth map, combo), see [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md).

## Widget Naming and Display

- `widget.name`: alphanumeric + hyphens + underscores ONLY (max 60 characters)
- `frame.title`: human-readable title (any characters allowed)
- `frame.showTitle`: always set to `true` so users understand the widget
- `displayName`: use in encodings to label axes/values clearly (e.g., "Revenue ($)", "Growth Rate (%)")
- `widget.queries[].name`: use `"main_query"` for chart/counter/table widgets. Filter widgets with multiple queries can use descriptive names (see [3-filters.md](3-filters.md))

**Always format values appropriately** - use `format` for currency, percentages, and large numbers (see [Axis Formatting](#axis-formatting)).

## Version Requirements

| Widget Type | Version | File |
|-------------|---------|------|
| text | N/A | this file |
| counter | 2 | this file |
| table | 2 | this file |
| bar | 3 | this file |
| line | 3 | this file |
| pie | 3 | this file |
| area | 3 | [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md) |
| scatter | 3 | [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md) |
| combo | 1 | [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md) |
| choropleth-map | 1 | [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md) |
| filter-* | 2 | [3-filters.md](3-filters.md) |

---

## Text (Headers/Descriptions)

- **CRITICAL: Text widgets do NOT use a spec block** - use `multilineTextboxSpec` directly
- Supports markdown: `#`, `##`, `###`, `**bold**`, `*italic*`
- **CRITICAL: Multiple items in the `lines` array are concatenated on a single line, NOT displayed as separate lines!**
- For title + subtitle, use **separate text widgets** at different y positions

```json
// CORRECT: Separate widgets for title and subtitle
{
  "widget": {
    "name": "title",
    "multilineTextboxSpec": {"lines": ["## Dashboard Title"]}
  },
  "position": {"x": 0, "y": 0, "width": 6, "height": 1}
},
{
  "widget": {
    "name": "subtitle",
    "multilineTextboxSpec": {"lines": ["Description text here"]}
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

## Counter (KPI)

- `version`: **2** (NOT 3!)
- `widgetType`: "counter"
- Percent values must be 0-1 in the data (not 0-100)

### Number Formatting

```json
"encodings": {
  "value": {
    "fieldName": "revenue",
    "displayName": "Total Revenue",
    "format": {
      "type": "number-currency",
      "currencyCode": "USD",
      "abbreviation": "compact",
      "decimalPlaces": {"type": "max", "places": 2}
    }
  }
}
```

Format types: `number`, `number-currency`, `number-percent`

### Counter Patterns

**Pre-aggregated dataset (1 row)** - use `disaggregated: true`:
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

**Multi-row dataset with aggregation (supports filters)** - use `disaggregated: false`:
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

## Table

- `version`: **2** (NOT 1 or 3!)
- `widgetType`: "table"
- **Columns only need `fieldName` and `displayName`** - no other properties required
- Use `"disaggregated": true` for raw rows
- Default sort: use `ORDER BY` in dataset SQL

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

## Line / Bar Charts

- `version`: **3**
- `widgetType`: "line" or "bar"
- Use `x`, `y`, optional `color` encodings
- `scale.type`: `"temporal"` (dates), `"quantitative"` (numbers), `"categorical"` (strings)
- Use `"disaggregated": true` with pre-aggregated dataset data

**Multiple series - two approaches:**

1. **Multi-Y Fields** (different metrics):
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
"color": {"fieldName": "region", "scale": {"type": "categorical"}}
```

### Bar Chart Modes

| Mode | Configuration |
|------|---------------|
| Stacked (default) | No `mark` field |
| Grouped | `"mark": {"layout": "group"}` |

### Horizontal Bar Chart

Swap `x` and `y` - put quantitative on `x`, categorical/temporal on `y`:
```json
"encodings": {
  "x": {"scale": {"type": "quantitative"}, "fields": [...]},
  "y": {"fieldName": "category", "scale": {"type": "categorical"}}
}
```

### Color Scale

> **CRITICAL**: For bar/line/pie, color scale ONLY supports `type` and `sort`.
> Do NOT use `scheme`, `colorRamp`, or `mappings` (only for choropleth-map).

---

## Pie Chart

- `version`: **3**
- `widgetType`: "pie"
- `angle`: quantitative field
- `color`: categorical dimension
- **Limit to 3-8 categories for readability**

```json
"spec": {
  "version": 3,
  "widgetType": "pie",
  "encodings": {
    "angle": {"fieldName": "revenue", "scale": {"type": "quantitative"}},
    "color": {"fieldName": "category", "scale": {"type": "categorical"}}
  }
}
```

---

## Axis Formatting

Add `format` to any encoding to display values appropriately:

| Data Type | Format Type | Example |
|-----------|-------------|---------|
| Currency | `number-currency` | $1.2M |
| Percentage | `number-percent` | 45.2% (data must be 0-1, not 0-100) |
| Large numbers | `number` with `abbreviation` | 1.5K, 2.3M |

```json
"value": {
  "fieldName": "revenue",
  "displayName": "Revenue",
  "format": {
    "type": "number-currency",
    "currencyCode": "USD",
    "abbreviation": "compact",
    "decimalPlaces": {"type": "max", "places": 2}
  }
}
```

**Options:**
- `abbreviation`: `"compact"` (K/M/B) or omit for full numbers
- `decimalPlaces`: `{"type": "max", "places": N}` or `{"type": "fixed", "places": N}`

---

## Dataset Parameters

Use `:param` syntax in SQL for dynamic filtering:

```json
{
  "name": "revenue_by_category",
  "queryLines": ["SELECT ... WHERE returns_usd > :threshold GROUP BY category"],
  "parameters": [{
    "keyword": "threshold",
    "dataType": "INTEGER",
    "defaultSelection": {}
  }]
}
```

**Parameter types:**
- Single value: `"dataType": "INTEGER"` / `"DECIMAL"` / `"STRING"`
- Multi-select: Add `"complexType": "MULTI"`
- Range: `"dataType": "DATE", "complexType": "RANGE"` - use `:param.min` / `:param.max`

---

## Widget Field Expressions

Allowed in `query.fields` (no CAST or complex SQL):

```json
// Aggregations
{"name": "sum(revenue)", "expression": "SUM(`revenue`)"}
{"name": "avg(price)", "expression": "AVG(`price`)"}
{"name": "count(id)", "expression": "COUNT(`id`)"}
{"name": "countdistinct(id)", "expression": "COUNT(DISTINCT `id`)"}

// Date truncation
{"name": "daily(date)", "expression": "DATE_TRUNC(\"DAY\", `date`)"}
{"name": "weekly(date)", "expression": "DATE_TRUNC(\"WEEK\", `date`)"}
{"name": "monthly(date)", "expression": "DATE_TRUNC(\"MONTH\", `date`)"}

// Simple reference
{"name": "category", "expression": "`category`"}
```

For conditional logic, compute in dataset SQL instead.
