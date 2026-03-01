# Metric Views — Check & Build (Steps 12–13)

Steps 12 and 13 of the migration workflow: detect existing metric views, classify KPIs, and create or update metric views.

---

## Step 12: Check Existing Metric Views

**Before building metric views**, check whether any KPIs already exist in metric views in the target catalog/schema. This prevents duplication and enables incremental updates.

**If Databricks access is available**, discover existing metric views:

```sql
SELECT table_name, view_definition
FROM <catalog>.information_schema.views
WHERE table_schema = '<schema>'
  AND view_definition LIKE '%WITH METRICS%';
```

For each discovered metric view, use `manage_metric_views` MCP tool to inspect its measures:

```
CallMcpTool:
  server: "user-databricks"
  toolName: "manage_metric_views"
  arguments:
    action: "describe"
    full_name: "<catalog>.<schema>.<view_name>"
```

The result includes `measures` (name + expression) and `dimensions` (name + expression).

### Comparison Logic

For each KPI from `kpi/kpi_definitions.md`, compare against all measures in existing metric views:

```
For each kpi in kpi_definitions:
  match = find measure where normalize(measure.name) == normalize(kpi.name)
  if no match:
    classification = "new"
  elif normalize(measure.expr) == normalize(kpi.sql_equivalent):
    classification = "exists"
  else:
    classification = "update"
```

**Normalization** for comparison: lowercase, strip whitespace, remove surrounding quotes, normalize whitespace in expressions, remove catalog/schema prefixes for column references.

### KPI Classification

| Classification | Condition | Action in Step 13 |
|---------------|-----------|-------------------|
| `new` | Measure name not found in any existing metric view | `CREATE OR REPLACE VIEW ... WITH METRICS` |
| `update` | Measure name exists but SQL expression differs | `ALTER VIEW` or `manage_metric_views` with `action: "alter"` |
| `exists` | Measure name and expression match | Skip — log as "already deployed" in deployment checklist |

**If no Databricks access**, skip this step and treat all KPIs as `new`. Log in the deployment checklist: "Manual verification recommended — could not check for existing metric views."

### Output: reference/existing_metric_views.md

```markdown
## Existing Metric View Analysis

### Discovery
Found 2 metric views in `analytics.gold`:
- `sales_metrics` (2 measures: Total Sales, Order Count)
- `customer_metrics` (2 measures: Customer Count, Repeat Customer Rate)

### KPI Classification
| KPI Name | Domain | Classification | Existing View | Notes |
|----------|--------|---------------|---------------|-------|
| Total Sales | Sales | exists | sales_metrics | Expression matches |
| Avg Order Value | Sales | new | — | Not in any existing view |
| Sales YoY Growth | Sales | new | — | Not in any existing view |
| Customer Count | Customer | exists | customer_metrics | Expression matches |
| Gross Margin | Finance | new | — | No finance view exists |

### Views to Modify
- None (no `update` classifications in this run)

### New Metric Views to Create
- **sales_metrics**: ALTER to add `Avg Order Value` and `Sales YoY Growth`
- **finance_metrics**: CREATE new view with `Gross Margin`

### Skipped (Already Deployed)
- Total Sales (in sales_metrics)
- Customer Count (in customer_metrics)
```

---

## Step 13: Build or Update Metric Views

Based on the classification from Step 12:

- **New KPIs**: Create metric views with `CREATE OR REPLACE VIEW ... WITH METRICS`
- **Updated KPIs**: Use `ALTER VIEW` or `manage_metric_views` with `action: "alter"`
- **Existing KPIs**: Skip — log in deployment checklist as "already deployed"

Create folders on demand:

```bash
bash scripts/init_project.sh --models
```

Use the `databricks-metric-views` skill for complete YAML syntax details.

### Metric View SQL Template

```sql
CREATE OR REPLACE VIEW <catalog>.<schema>.domain_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: "Sales KPIs translated from Power BI semantic model"
  source: <catalog>.<schema>.fact_table
  dimensions:
    - name: Dimension Name
      expr: column_expression
      comment: "Description"
  measures:
    - name: Measure Name
      expr: AGG_FUNC(column)
      comment: "DAX: ORIGINAL_FORMULA"
  joins:
    - name: dim_table
      source: <catalog>.<schema>.dim_table
      on: fact_table.join_key = dim_table.join_key
$$;
```

### Full Example: Sales Metrics

```sql
CREATE OR REPLACE VIEW analytics.gold.sales_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  comment: "Sales KPIs translated from Power BI semantic model"
  source: analytics.gold.sales_fact

  dimensions:
    - name: Order Date
      expr: date_key
    - name: Customer Segment
      expr: customer_segment
    - name: Product Category
      expr: product_category

  measures:
    - name: Total Sales
      expr: SUM(total_amount)
      comment: "DAX: SUM(SalesFact[TotalAmount])"
    - name: Order Count
      expr: COUNT(1)
    - name: Avg Order Value
      expr: SUM(total_amount) / NULLIF(COUNT(1), 0)
      comment: "DAX: DIVIDE([Total Sales], COUNTROWS(SalesFact))"
    - name: Distinct Customers
      expr: COUNT(DISTINCT customer_id)
      comment: "DAX: DISTINCTCOUNT(SalesFact[CustomerID])"

  joins:
    - name: customer_dim
      source: analytics.gold.customer_dim
      on: sales_fact.customer_id = customer_dim.customer_id
    - name: date_dim
      source: analytics.gold.date_dim
      on: sales_fact.date_key = date_dim.date_key
$$;
```

### Altering an Existing Metric View

To add new measures to an existing metric view:

```sql
ALTER VIEW analytics.gold.sales_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  source: analytics.gold.sales_fact
  dimensions:
    - name: Order Month
      expr: date_trunc('month', order_date)
    - name: Region
      expr: region
  measures:
    - name: Total Sales
      expr: SUM(total_amount)
      comment: "DAX: SUM(SalesFact[TotalAmount])"
    - name: Avg Order Value
      expr: SUM(total_amount) / NULLIF(COUNT(1), 0)
      comment: "DAX: DIVIDE([Total Sales], COUNTROWS(SalesFact))"
    - name: Sales YoY Growth
      expr: (SUM(total_amount) - LAG(SUM(total_amount)) OVER (ORDER BY date_trunc('month', order_date))) / NULLIF(LAG(SUM(total_amount)) OVER (ORDER BY date_trunc('month', order_date)), 0)
      comment: "DAX: DIVIDE([Total Sales] - CALCULATE([Total Sales], SAMEPERIODLASTYEAR(...)), ...)"
$$;
```

### Querying a Metric View

```sql
SELECT
  `Order Date`,
  `Customer Segment`,
  MEASURE(`Total Sales`) AS total_sales,
  MEASURE(`Avg Order Value`) AS avg_order_value,
  MEASURE(`Distinct Customers`) AS unique_customers
FROM analytics.gold.sales_metrics
GROUP BY ALL
ORDER BY ALL;
```

### Output Files

Store metric view SQL in `models/metric_views/` — one file per business domain:

```
models/metric_views/
├── sales_metrics.sql
├── finance_metrics.sql
└── customer_metrics.sql
```
