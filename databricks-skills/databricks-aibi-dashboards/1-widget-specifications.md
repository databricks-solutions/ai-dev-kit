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
  "position": {"x": 0, "y": 0, "width": 12, "height": 1}
},
{
  "widget": {
    "name": "subtitle",
    "multilineTextboxSpec": {"lines": ["Description text here"]}
  },
  "position": {"x": 0, "y": 1, "width": 12, "height": 1}
}

// WRONG: Multiple lines concatenate into one line!
{
  "widget": {
    "name": "title-widget",
    "multilineTextboxSpec": {
      "lines": ["## Dashboard Title", "Description text here"]  // Becomes "## Dashboard TitleDescription text here"
    }
  },
  "position": {"x": 0, "y": 0, "width": 12, "height": 2}
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
  "position": {"x": 0, "y": 0, "width": 4, "height": 3}
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
  "position": {"x": 0, "y": 0, "width": 4, "height": 3}
}
```

> **`MEASURE()` works here too.** If the dataset defines measures via `dataset.columns[]` or is sourced from a metric view, use `{"expression": "MEASURE(\`Total Cases\`)"}` as the field expression — same pattern, no duplication. See SKILL.md "Dataset-level measures + MEASURE()".

### Counter sparkline (background trend)

Add a `period` encoding to draw a small time-series line behind the KPI value — gives context for whether the metric is rising or falling.

```json
"encodings": {
  "value":  {"fieldName": "measure(Cases Open)", "displayName": "Total Cases"},
  "period": {"fieldName": "weekly(opened_at)"}
}
```

The `period` field must be a temporal expression also present in `query.fields` (e.g., `{"name": "weekly(opened_at)", "expression": "DATE_TRUNC(\"WEEK\", \`opened_at\`)"}`). Common granularities: `DATE_TRUNC("DAY"|"WEEK"|"MONTH", ...)`.

### Counter comparison (delta vs previous period)

Show the current value AND the change vs a previous period. Use a second field in `query.fields` whose expression filters/aggregates the comparison value, and reference it via the `target` encoding:

```json
"fields": [
  {"name": "current",  "expression": "SUM(CASE WHEN week=:this_week THEN amount END)"},
  {"name": "previous", "expression": "SUM(CASE WHEN week=:last_week THEN amount END)"}
],
"encodings": {
  "value":  {"fieldName": "current",  "displayName": "This Week"},
  "target": {"fieldName": "previous", "displayName": "vs Last Week"}
}
```

### Counter format template (custom prefix/suffix text)

Wrap the value with surrounding text. Use `{{@}}` for the raw value and `{{@formatted}}` for the formatted one. Reference other dataset fields with `{{FieldName}}`.

```json
"value": {
  "fieldName": "sum(revenue)",
  "format": {"type": "number-currency", "currencyCode": "USD", "abbreviation": "compact"},
  "formatTemplate": "{{@formatted}} (in {{Region}})"
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
  "position": {"x": 0, "y": 0, "width": 12, "height": 6}
}
```

### Column-level options

Each column object supports format, conditional styling, links, and tooltips. Common patterns:

```json
{
  "fieldName": "amount",
  "displayName": "Amount",
  "format": {"type": "number-currency", "currencyCode": "USD",
             "abbreviation": "compact", "decimalPlaces": {"type": "max", "places": 2}},

  // Conditional background color (heat-map style)
  "style": {
    "type": "basic",
    "rules": [
      {"condition": {"operand": {"type": "data-value", "value": "10000"}, "operator": ">="},
       "backgroundColor": {"themeColorType": "visualizationColors", "position": 4}},
      {"condition": {"operand": {"type": "data-value", "value": "5000"},  "operator": ">="},
       "backgroundColor": {"themeColorType": "visualizationColors", "position": 3}}
    ]
  },

  // Make the cell a clickable link. {{@}} is the cell value, {{Field}} pulls another column.
  "link": {"templatedURL": "/sql/dashboardsv3/{{@}}"},

  // Hover tooltip
  "tooltip": {"templatedText": "Customer ID: {{customer_id}}"}
}
```

Other display types: `"image"` (renders base64 strings as images), `"html"` (sanitized HTML), `"json"` (collapsible JSON tree), `"color-scale"` (continuous color gradient on numeric values without explicit thresholds).

> Same `style.rules` and `link`/`tooltip` patterns work on **pivot** cells — see pivot in [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md).

---

## Line / Bar Charts

- `version`: **3**
- `widgetType`: "line" or "bar"
- **`x` and `y` are both REQUIRED** (one categorical/temporal dimension + one quantitative measure). `color` is optional for splitting into series.
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
| 100% stacked | `"mark": {"layout": "stack-100"}` |

### Horizontal Bar Chart

Swap `x` and `y` - put quantitative on `x`, categorical/temporal on `y`:
```json
"encodings": {
  "x": {"scale": {"type": "quantitative"}, "fields": [...]},
  "y": {"fieldName": "category", "scale": {"type": "categorical"}}
}
```

### Categorical sort with a custom order

When the dimension has natural ordering that ASC/DESC won't capture (priority levels, weekdays, named tiers), pin the order explicitly:

```json
"x": {
  "fieldName": "channel",
  "scale": {
    "type": "categorical",
    "sort": {"by": "custom-order", "orderedValues": ["Chat", "Email", "In-App", "Phone"]}
  }
}
```

Other `sort.by` values: `"alphabetical"`, `"value"` (sort by the y measure), `"cell"` / `"cell-reversed"` (pivot only).

### Color Scale + per-value mappings

Default behaviour: theme colors are assigned to categories in order. To pin specific values (e.g., "Critical" must always be red), use `mappings`:

```json
"color": {
  "fieldName": "Priority Level",
  "scale": {
    "type": "categorical",
    "mappings": [
      {"value": "1-Critical", "color": {"themeColorType": "visualizationColors", "position": 6}},
      {"value": "4-Low",      "color": {"themeColorType": "visualizationColors", "position": 1}}
    ]
  }
}
```

`themeColorType: "visualizationColors"` + `position: 1..N` selects from the dashboard's theme palette. For an exact hex, use `{"hex": "#FF0000"}` instead of `themeColorType`.

> For continuous color ramps on quantitative encodings (e.g., choropleth, symbol-map, heatmap), use `colorRamp` — see [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md).

### Annotations (event markers)

Mark an event on a time-series chart — release, holiday, incident — with a vertical line. Works on `line`, `area`, `bar`, `combo`, and `forecast-line`.

```json
"spec": {
  "version": 3,
  "widgetType": "line",
  "encodings": { /* ... x, y, color ... */ },
  "annotations": [
    {
      "type": "vertical-line",
      "encodings": {
        "x":     {"dataValue": "2024-11-28T12:00:00.000", "dataType": "DATETIME"},
        "label": {"value": "Thanksgiving"},
        "color": {"value": {"themeColorType": "visualizationColors", "position": 3}}
      }
    }
  ]
}
```

Multiple annotations are allowed — add more objects to the array. For non-datetime axes, use `"dataType": "STRING"` or `"NUMBER"` and set `dataValue` accordingly.

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

Use `:param` syntax in SQL for dynamic filtering. Parameters can be bound to filter widgets (see [3-filters.md](3-filters.md)):

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
{"name": "[sum|avg|count|countdistinct|min|max](col)", "expression": "[SUM|AVG|COUNT|COUNT(DISTINCT)|MIN|MAX](`col`)"}
{"name": "[daily|weekly|monthly](date)", "expression": "DATE_TRUNC(\"[DAY|WEEK|MONTH]\", `date`)"}
{"name": "field", "expression": "`field`"}
```

For conditional logic, compute in dataset SQL instead.
