# Troubleshooting

Common errors and fixes for AI/BI dashboards.

## Structural Errors (JSON Parse Failures)

These errors occur when the JSON structure is wrong:

| Error | Cause | Fix |
|-------|-------|-----|
| "failed to parse serialized dashboard" | Wrong JSON structure | Check: `queryLines` is array (not `"query": "string"`), widgets inline in `layout[].widget`, `pageType` on every page |
| "no selected fields to visualize" | `fields[].name` ≠ `encodings.fieldName` | Names must match exactly (e.g., both `"sum(spend)"`) |
| Widgets in wrong location | Used separate `"widgets"` array | Widgets must be INLINE: `layout[]: {widget: {...}, position: {...}}` |
| Missing page content | Omitted `pageType` | Add `"pageType": "PAGE_TYPE_CANVAS"` or `"PAGE_TYPE_GLOBAL_FILTERS"` |

---

## Widget shows "no selected fields to visualize"

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

## Widget shows "Invalid widget definition"

**Check version numbers:**
- Counters: `version: 2` (NOT 3!)
- Tables: `version: 2` (NOT 1 or 3!)
- Filters: `version: 2`
- Bar/Line/Pie/Area/Scatter charts: `version: 3`
- Combo/Choropleth-map: `version: 1`

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
- Ensure dataset returns exactly 1 row for `disaggregated: true`

## Dashboard shows empty widgets

- Run the dataset SQL query directly to check data exists
- Verify column aliases match widget field expressions
- Check `disaggregated` flag:
  - `true` for pre-aggregated data (1 row)
  - `false` when widget performs aggregation (multi-row)

## Layout has gaps

- Ensure each row sums to width=12
- Check that y positions don't skip values

## Filter shows "Invalid widget definition"

- Check `widgetType` is one of: `filter-multi-select`, `filter-single-select`, `filter-date-range-picker`
- **DO NOT** use `widgetType: "filter"` - this is invalid
- Verify `spec.version` is `2`
- Ensure `queryName` in encodings matches the query `name`
- Confirm `disaggregated: false` in filter queries
- Ensure `frame` with `showTitle: true` is included

## Filter not affecting expected pages

- **Global filters** (on `PAGE_TYPE_GLOBAL_FILTERS` page) affect all datasets containing the filter field
- **Page-level filters** (on `PAGE_TYPE_CANVAS` page) only affect widgets on that same page
- A filter only works on datasets that include the filter dimension column

## Filter shows "UNRESOLVED_COLUMN" error for `associative_filter_predicate_group`

- **DO NOT** use `COUNT_IF(\`associative_filter_predicate_group\`)` in filter queries
- This internal expression causes SQL errors when the dashboard executes queries
- Use a simple field expression instead: `{"name": "field", "expression": "\`field\`"}`

## Text widget shows title and description on same line

- Multiple items in the `lines` array are **concatenated**, not displayed on separate lines
- Use **separate text widgets** for title and subtitle at different y positions
- Example: title at y=0 with height=1, subtitle at y=1 with height=1

## Chart unreadable (too many categories)

- Use TOP-N + "Other" bucketing in dataset SQL
- Aggregate to a higher level (region instead of store)
- Use a table widget instead of a chart for high-cardinality data

## `MEASURE()` errors

- **"Cannot resolve `MEASURE(\`X\`)`"** — measure `X` is not defined on the dataset. Either add it to `dataset.columns[]` with `displayName: "X"`, or (if the source is a metric view) confirm the YAML defines a measure named `X`. Name matching is case-sensitive and backticks are required if the name has spaces.
- **`MEASURE()` returns wrong number** — check that `query.disaggregated: false` is set on the widget. With `true`, the widget bypasses dataset measures and shows raw rows.

## Forecast-line shows blank or partial line

- Dataset must return both historical AND forecast columns, with historical rows having `NULL` in the forecast columns and forecast rows having `NULL` in the historical column. Use `UNION ALL` to glue them — see [2-advanced-widget-specifications.md](2-advanced-widget-specifications.md#forecast-line-with-ai_forecast).
- All four y-encoding fields (`original`, `prediction`, `predictionUpper`, `predictionLower`) must reference columns that exist in `query.fields`.
- `AI_FORECAST` requires the time column to be sorted and have no gaps — pre-aggregate (e.g., `DATE_TRUNC('WEEK', ts)`) before passing to the table function.

## Forecast-line dips right before the prediction starts

The last historical bucket is the **current (partial) period** — e.g., aggregating weekly but today is Tuesday → "this week" bucket has only 2 days of data and looks like a cliff. Filter the partial bucket out in the dataset SQL with a cutoff using the **same `DATE_TRUNC` grain as the aggregation**:

```sql
WHERE DATE_TRUNC('WEEK', event_ts) < DATE_TRUNC('WEEK', current_date())
```

If you change the chart's aggregation grain (weekly → monthly), update **both** the `DATE_TRUNC` in `GROUP BY` and the one in the `WHERE`. Mismatched grains cause the same cliff.

## Range-slider filter shows error or no min/max

- The bound `fieldName` must be a numeric or temporal column. Categorical fields fail at render — use `filter-single-select` / `filter-multi-select` instead.
- Query inside the filter widget must include the field as a plain expression (`{"name": "x", "expression": "\`x\`"}`), not pre-aggregated.

## Symbol-map shows no points

- Verify the dataset returns both `latitude` and `longitude` columns with valid floats (not strings, not nulls for all rows).
- Lat values must be in [-90, 90], lon in [-180, 180]. Out-of-range rows are silently dropped.
- For region-based maps (countries, states), use `choropleth-map`, not `symbol-map`.

## Annotations not appearing on chart

- `annotations` is a sibling of `encodings` inside `spec`, not nested inside it.
- Each annotation needs `type: "vertical-line"`, `encodings.x.dataValue` matching the chart's x-axis type, and a matching `dataType` (`DATETIME` / `STRING` / `NUMBER`).
- Annotations are only rendered on time-series chart types (`line`, `area`, `bar`, `combo`, `forecast-line`). Pie / pivot / map ignore them.
