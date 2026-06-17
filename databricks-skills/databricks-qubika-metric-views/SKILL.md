---
name: qubika-metric-views
description: "Define governed, reusable business KPIs (revenue, conversion, order metrics) as Unity Catalog Metric Views. Use when building a KPI layer shared across dashboards, Genie Spaces, and SQL queries, or when defining ratio/window metrics that need safe re-aggregation."
version: 1.0.0
domain: data-analytics
owner: data-platform-team
---

# Qubika Metric Views

Unity Catalog Metric Views are the **canonical KPI layer** at Qubika. They separate metric definitions (what Revenue means, how Conversion Rate is calculated) from the query consuming them, making it safe to re-aggregate ratios and share consistent numbers across AI/BI dashboards, Genie Spaces, and ad-hoc SQL — without copy-pasting business logic.

---

## When to Use This Skill

Use this skill when:
- Defining a business KPI that will be consumed by more than one dashboard or team
- Building ratio or per-unit metrics (Revenue per Customer, Fulfillment Rate) that break when re-aggregated naively
- Creating a Gold-layer semantic layer on top of existing Silver or Gold Delta tables
- Enabling a Genie Space with governed, pre-defined measures
- Setting up period-over-period, YTD, or moving-average measures (window measures)

Do NOT use this skill when:
- Writing a one-off analytical query — use a SQL notebook instead
- The "metric" is a simple column alias that doesn't need governance or reuse
- The source table is in the Bronze layer — metric views belong on Silver or Gold

---

## Plan & Confirm Gates

Before creating any metric view, Claude must:

1. Present a numbered plan of every object to be created (catalog, schema, view name, source table, dimensions, measures).
2. Confirm the **catalog** with the engineer — never default to one.
3. Wait for explicit approval before issuing any `CREATE` or MCP `create` call.

```
✅ CORRECT:
   "Here is my plan:
    1. Create metric view `qubika_dev.sales_gold.order_kpis`
       - Source: `qubika_dev.sales_silver.orders`
       - Dimensions: Order Month, Customer Segment, Region
       - Measures: Order Count, Total Revenue, Revenue per Customer, Fulfillment Rate
    2. Add UC descriptions to the view and all measures (CLAUDE.md §11)
    Shall I proceed?"

❌ WRONG:
   Creating the view and running the first query without asking.
```

---

## Quick Start

### Step 1 — Inspect the source table

```python
get_table_stats_and_schema(
    catalog="qubika_dev",
    schema="sales_silver",
    table_names=["orders"],
    table_stat_level="SIMPLE"
)
```

### Step 2 — Create the metric view

```sql
CREATE OR REPLACE VIEW qubika_dev.sales_gold.order_kpis
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: qubika_dev.sales_silver.orders
  comment: "Core order KPIs for the Sales domain — shared across dashboards and Genie"
  filter: order_date >= '2023-01-01'

  dimensions:
    - name: Order Month
      expr: DATE_TRUNC('MONTH', order_date)
      comment: "Calendar month of the order, UTC"
    - name: Customer Segment
      expr: CASE
        WHEN customer_tier = 'A' THEN 'Enterprise'
        WHEN customer_tier = 'B' THEN 'Mid-Market'
        ELSE 'SMB'
        END
      comment: "Derived from customer_tier: A=Enterprise, B=Mid-Market, else SMB"
    - name: Region
      expr: region
      comment: "Geographic region — source column, self-reported by sales rep"

  measures:
    - name: Order Count
      expr: COUNT(1)
      comment: "Total number of orders"
    - name: Total Revenue
      expr: SUM(total_price)
      comment: "Sum of total_price (USD). Excludes cancelled orders via global filter."
    - name: Revenue per Customer
      expr: SUM(total_price) / COUNT(DISTINCT customer_id)
      comment: "Average revenue per unique customer — safe ratio, not a simple AVG"
    - name: Fulfillment Rate
      expr: COUNT(1) FILTER (WHERE status = 'FULFILLED') * 1.0 / COUNT(1)
      comment: "Fraction of orders fulfilled. Value 0–1, multiply by 100 for percentage."
$$
```

### Step 3 — Add UC descriptions (mandatory, CLAUDE.md §11)

```sql
COMMENT ON VIEW qubika_dev.sales_gold.order_kpis
  IS 'Core order KPIs for the Sales domain. Metric view on top of sales_silver.orders. Use MEASURE() to query measures.';
```

> **Note:** The `comment` fields inside the YAML are stored as column-level descriptions in the Catalog Explorer. The `COMMENT ON VIEW` above adds the table-level description. Both are required.

### Step 4 — Query

All measures must use the `MEASURE()` function. `SELECT *` is not supported.

```sql
-- Monthly revenue by segment
SELECT
  `Order Month`,
  `Customer Segment`,
  MEASURE(`Total Revenue`)        AS total_revenue,
  MEASURE(`Order Count`)          AS order_count,
  MEASURE(`Revenue per Customer`) AS rev_per_customer
FROM qubika_dev.sales_gold.order_kpis
WHERE EXTRACT(YEAR FROM `Order Month`) = 2024
GROUP BY ALL
ORDER BY `Order Month`, total_revenue DESC

-- Single KPI scalar (for a counter widget)
SELECT MEASURE(`Total Revenue`) AS total_revenue
FROM qubika_dev.sales_gold.order_kpis
WHERE `Order Month` >= DATE_TRUNC('MONTH', CURRENT_DATE())
GROUP BY ALL
```

### Step 5 — Via MCP tool

```python
manage_metric_views(
    action="create",
    full_name="qubika_dev.sales_gold.order_kpis",
    source="qubika_dev.sales_silver.orders",
    or_replace=True,
    comment="Core order KPIs for the Sales domain — shared across dashboards and Genie",
    filter_expr="order_date >= '2023-01-01'",
    dimensions=[
        {"name": "Order Month",       "expr": "DATE_TRUNC('MONTH', order_date)",          "comment": "Calendar month of the order, UTC"},
        {"name": "Customer Segment",  "expr": "CASE WHEN customer_tier = 'A' THEN 'Enterprise' WHEN customer_tier = 'B' THEN 'Mid-Market' ELSE 'SMB' END", "comment": "Derived from customer_tier"},
        {"name": "Region",            "expr": "region",                                    "comment": "Geographic region — source column"},
    ],
    measures=[
        {"name": "Order Count",          "expr": "COUNT(1)",                                                             "comment": "Total number of orders"},
        {"name": "Total Revenue",        "expr": "SUM(total_price)",                                                     "comment": "Sum of total_price (USD)"},
        {"name": "Revenue per Customer", "expr": "SUM(total_price) / COUNT(DISTINCT customer_id)",                       "comment": "Average revenue per unique customer"},
        {"name": "Fulfillment Rate",     "expr": "COUNT(1) FILTER (WHERE status = 'FULFILLED') * 1.0 / COUNT(1)",        "comment": "Fraction of orders fulfilled (0–1)"},
    ],
)
```

---

## Naming Conventions

| Object | Convention | Example |
|--------|------------|---------|
| Catalog | `qubika_dev` (dev) / `qubika_prod` (prod) | `qubika_dev` |
| Schema | `{domain}_gold` — metric views live on Gold | `sales_gold` |
| View name | `{domain}_{entity}_kpis` or `{domain}_{entity}_metrics` | `sales_order_kpis` |
| Dimension names | Title case with spaces | `Order Month`, `Customer Segment` |
| Measure names | Title case, noun phrase | `Total Revenue`, `Fulfillment Rate` |

---

## Common Patterns

See [patterns.md](patterns.md) for full code examples. Summary:

- **Simple flat table** — Pattern 1 (single source, direct column dims + standard aggregations)
- **Business-friendly categories** — Pattern 2 (CASE-derived dimensions for bucketing)
- **Ratios and per-unit KPIs** — Pattern 3 (profit margin, revenue per employee)
- **Status-segmented measures** — Pattern 4 (FILTER clause — open vs. fulfilled, active vs. churned)
- **Star schema** — Pattern 5 (fact + dim_customer + dim_product joins)
- **Snowflake / geographic hierarchy** — Pattern 6 (nested joins — requires DBR 17.1+)
- **Pre-computed aggregations** — Pattern 7 (materialization for high-query-volume KPIs)
- **Moving averages, YTD, running totals** — Pattern 9 (window measures — experimental, `version: 0.1`)

---

## Anti-Patterns

```sql
-- ❌ WRONG — ratio computed in the query, breaks on re-aggregation
SELECT
  region,
  SUM(revenue) / COUNT(customer_id) AS rev_per_customer  -- NOT safe across GROUP BY
FROM qubika_dev.sales_gold.order_kpis
GROUP BY region

-- ✅ CORRECT — define the ratio as a measure, query it with MEASURE()
SELECT
  `Region`,
  MEASURE(`Revenue per Customer`) AS rev_per_customer
FROM qubika_dev.sales_gold.order_kpis
GROUP BY ALL
```

```sql
-- ❌ WRONG — SELECT * is not supported on metric views
SELECT * FROM qubika_dev.sales_gold.order_kpis

-- ✅ CORRECT — explicitly list dimensions and wrap measures in MEASURE()
SELECT `Region`, MEASURE(`Total Revenue`) AS revenue
FROM qubika_dev.sales_gold.order_kpis
GROUP BY ALL
```

```sql
-- ❌ WRONG — metric view on a Bronze table
CREATE OR REPLACE VIEW qubika_dev.raw.order_kpis   -- raw = Bronze, not appropriate
WITH METRICS ...

-- ✅ CORRECT — metric views sit on Silver or Gold
CREATE OR REPLACE VIEW qubika_dev.sales_gold.order_kpis
WITH METRICS ...
```

| Anti-pattern | Problem | Correct alternative |
|---|---|---|
| Ratio computed in the SELECT query | Breaks when GROUP BY changes | Define as a measure with SUM/COUNT, use `MEASURE()` |
| `SELECT *` on a metric view | Not supported — runtime error | Explicitly list dimensions + `MEASURE()` calls |
| Building on Bronze tables | Data not validated; no medallion contract | Source from Silver or Gold only |
| Skipping `comment` on measures | No documentation in Catalog Explorer or Genie | Every measure and dimension must have a `comment` |
| Missing `COMMENT ON VIEW` | Table-level UC description is blank | Always run `COMMENT ON VIEW` after creation |
| Hardcoding `qubika_prod` without approval | Writes to production | Always use `qubika_dev` and confirm prod promotion explicitly |
| Using spaces in backtick-quoted identifiers inconsistently | Query errors | Backtick-quote all dimension/measure names that contain spaces |

---

## UC Descriptions Checklist (CLAUDE.md §11)

After creating or altering a metric view, verify:

- [ ] `comment` field populated on the view (top-level YAML)
- [ ] `comment` field populated on **every** dimension
- [ ] `comment` field populated on **every** measure
- [ ] `COMMENT ON VIEW catalog.schema.view IS '...'` executed (table-level UC description)

Column-level comments travel into Catalog Explorer, Genie, and AI/BI dashboard column pickers. Without them, analysts have no context on what a measure means.

---

## Runtime Requirements

| Feature | Minimum DBR |
|---------|-------------|
| Metric views (YAML v1.1) | 17.2+ |
| Metric views (YAML v0.1) | 16.4+ |
| Snowflake / nested joins | 17.1+ |
| Materialization | 17.2+ (serverless required) |
| Window measures | 16.4+ (experimental, `version: 0.1`) |

---

## Reference Files

- [patterns.md](patterns.md) — Nine common patterns with full code (single table, joins, ratios, filtered measures, window measures, materialization)
- [yaml-reference.md](yaml-reference.md) — Complete YAML spec: dimensions, measures, joins, filters, materialization, window blocks
- [Databricks Metric Views docs](https://docs.databricks.com/en/metric-views/)
- [MEASURE() function reference](https://docs.databricks.com/en/sql/language-manual/functions/measure)

---

## FAQ

| Question | Answer |
|----------|--------|
| Can I source a metric view from another metric view? | No — source must be a table or view, not another metric view. |
| Can dimensions reference columns from joined tables? | Yes — use `join_name.column_name` in the `expr`. |
| Why does `MEASURE()` exist instead of just SUM()? | It signals to the engine that safe re-aggregation rules apply (e.g. ratio measures). Without it, the query errors. |
| Can I add a metric view to an AI/BI dashboard? | Yes — add it as a dataset in the dashboard. Queries must use `MEASURE()`. |
| Can I add a metric view to a Genie Space? | Yes — Genie natively understands metric views and the MEASURE() contract. |
| Should metric views be in `qubika_dev` or `qubika_prod`? | Always develop in `qubika_dev`. Promote to `qubika_prod` only after explicit confirmation (CLAUDE.md §12). |
| What if my source table is updated frequently? | Use materialization (`every N hours`) or accept live re-computation — metric views run on the warehouse at query time. |

---

## Related Skills

- `qubika-aibi-dashboards` — consume this KPI layer in Lakeview dashboards
- `qubika-medallion-architecture` — metric views sit on the Gold layer of the medallion
- `qubika-unity-catalog-governance` — catalog/schema creation, UC permissions, and descriptions
- `qubika-data-quality` — validate the Silver tables that feed this metric view
- `qubika-databricks-jobs` — schedule materialization pipeline refreshes

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | 2026-06-12 | Initial version — adapted from databricks-metric-views (ai-dev-kit) with Qubika naming conventions, plan gates, UC description requirements, and anti-patterns |