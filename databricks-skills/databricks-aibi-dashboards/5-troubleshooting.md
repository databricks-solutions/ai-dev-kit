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

- Ensure each row sums to width=6
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
