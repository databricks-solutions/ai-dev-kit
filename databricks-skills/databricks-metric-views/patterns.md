# Metric View Patterns & Examples

Common patterns for creating and querying metric views.

## Pattern 1: Simple Metrics from a Single Table

The most basic pattern with direct column dimensions and standard aggregations.

### Create

```sql
CREATE OR REPLACE VIEW catalog.schema.product_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Product sales metrics"
  source: catalog.schema.sales
  dimensions:
    - name: Product Name
      expr: product_name
    - name: Sale Date
      expr: sale_date
  measures:
    - name: Units Sold
      expr: COUNT(1)
    - name: Total Revenue
      expr: SUM(price * quantity)
    - name: Average Price
      expr: AVG(price)
$$
```

### Query

```sql
-- Revenue by product
SELECT
  `Product Name`,
  MEASURE(`Total Revenue`) AS revenue,
  MEASURE(`Units Sold`) AS units
FROM catalog.schema.product_metrics
GROUP BY ALL
ORDER BY revenue DESC
LIMIT 10

-- Monthly trend
SELECT
  DATE_TRUNC('MONTH', `Sale Date`) AS month,
  MEASURE(`Total Revenue`) AS revenue
FROM catalog.schema.product_metrics
GROUP BY ALL
ORDER BY month
```

## Pattern 2: Derived Dimensions with CASE

Transform raw values into business-friendly categories.

```sql
CREATE OR REPLACE VIEW catalog.schema.order_kpis
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders
  dimensions:
    - name: Order Month
      expr: DATE_TRUNC('MONTH', order_date)
    - name: Priority Level
      expr: CASE
        WHEN priority <= 2 THEN 'High'
        WHEN priority <= 4 THEN 'Medium'
        ELSE 'Low'
        END
      comment: "Bucketed priority: High (1-2), Medium (3-4), Low (5)"
    - name: Size Category
      expr: CASE
        WHEN total_amount > 10000 THEN 'Large'
        WHEN total_amount > 1000 THEN 'Medium'
        ELSE 'Small'
        END
  measures:
    - name: Order Count
      expr: COUNT(1)
    - name: Total Amount
      expr: SUM(total_amount)
$$
```

## Pattern 3: Ratio Measures

Ratios and per-unit metrics that safely handle re-aggregation.

```sql
CREATE OR REPLACE VIEW catalog.schema.efficiency_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Efficiency and per-unit metrics"
  source: catalog.schema.transactions
  dimensions:
    - name: Department
      expr: department_name
    - name: Quarter
      expr: DATE_TRUNC('QUARTER', transaction_date)
  measures:
    - name: Total Revenue
      expr: SUM(revenue)
    - name: Total Cost
      expr: SUM(cost)
    - name: Profit Margin
      expr: (SUM(revenue) - SUM(cost)) / SUM(revenue)
      comment: "Profit as percentage of revenue"
    - name: Revenue per Employee
      expr: SUM(revenue) / COUNT(DISTINCT employee_id)
    - name: Average Transaction Size
      expr: SUM(revenue) / COUNT(1)
$$
```

## Pattern 4: Filtered Measures (FILTER clause)

Create measures that only count a subset of rows.

```sql
CREATE OR REPLACE VIEW catalog.schema.order_status_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders
  dimensions:
    - name: Order Month
      expr: DATE_TRUNC('MONTH', order_date)
    - name: Region
      expr: region
  measures:
    - name: Total Orders
      expr: COUNT(1)
    - name: Open Orders
      expr: COUNT(1) FILTER (WHERE status = 'OPEN')
    - name: Fulfilled Orders
      expr: COUNT(1) FILTER (WHERE status = 'FULFILLED')
    - name: Open Revenue
      expr: SUM(amount) FILTER (WHERE status = 'OPEN')
      comment: "Revenue at risk from unfulfilled orders"
    - name: Fulfillment Rate
      expr: COUNT(1) FILTER (WHERE status = 'FULFILLED') * 1.0 / COUNT(1)
      comment: "Percentage of orders fulfilled"
$$
```

### Query filtered measures

```sql
SELECT
  `Order Month`,
  MEASURE(`Total Orders`) AS total,
  MEASURE(`Open Orders`) AS open_orders,
  MEASURE(`Fulfillment Rate`) AS fulfillment_rate
FROM catalog.schema.order_status_metrics
WHERE `Region` = 'EMEA'
GROUP BY ALL
ORDER BY ALL
```

## Pattern 5: Star Schema with Joins

Join a fact table to dimension tables.

```sql
CREATE OR REPLACE VIEW catalog.schema.sales_analytics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "Sales analytics with customer and product dimensions"
  source: catalog.schema.fact_sales

  joins:
    - name: customer
      source: catalog.schema.dim_customer
      on: source.customer_id = customer.customer_id
    - name: product
      source: catalog.schema.dim_product
      on: source.product_id = product.product_id
    - name: store
      source: catalog.schema.dim_store
      on: source.store_id = store.store_id

  dimensions:
    - name: Customer Segment
      expr: customer.segment
    - name: Product Category
      expr: product.category
    - name: Store City
      expr: store.city
    - name: Sale Month
      expr: DATE_TRUNC('MONTH', source.sale_date)

  measures:
    - name: Total Revenue
      expr: SUM(source.amount)
    - name: Unique Customers
      expr: COUNT(DISTINCT source.customer_id)
    - name: Average Basket Size
      expr: SUM(source.amount) / COUNT(DISTINCT source.transaction_id)
$$
```

## Pattern 6: Snowflake Schema (Nested Joins)

Multi-level dimension hierarchies. Requires DBR 17.1+.

```sql
CREATE OR REPLACE VIEW catalog.schema.geo_sales
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.orders

  joins:
    - name: customer
      source: catalog.schema.customer
      on: source.customer_key = customer.customer_key
      joins:
        - name: nation
          source: catalog.schema.nation
          on: customer.nation_key = nation.nation_key
          joins:
            - name: region
              source: catalog.schema.region
              on: nation.region_key = region.region_key

  dimensions:
    - name: Customer Name
      expr: customer.name
    - name: Nation
      expr: nation.name
    - name: Region
      expr: region.name
    - name: Order Year
      expr: EXTRACT(YEAR FROM source.order_date)

  measures:
    - name: Total Revenue
      expr: SUM(source.total_price)
    - name: Order Count
      expr: COUNT(1)
$$
```

### Query across hierarchy levels

```sql
-- Revenue by region (rolls up across nations and customers)
SELECT
  `Region`,
  MEASURE(`Total Revenue`) AS revenue
FROM catalog.schema.geo_sales
GROUP BY ALL

-- Revenue by nation within a specific region
SELECT
  `Nation`,
  MEASURE(`Total Revenue`) AS revenue,
  MEASURE(`Order Count`) AS orders
FROM catalog.schema.geo_sales
WHERE `Region` = 'EUROPE'
GROUP BY ALL
ORDER BY revenue DESC
```

## Pattern 7: Materialized Metric View

Pre-compute common aggregations for faster queries.

```sql
CREATE OR REPLACE VIEW catalog.schema.ecommerce_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  source: catalog.schema.transactions

  dimensions:
    - name: Category
      expr: product_category
    - name: Day
      expr: DATE_TRUNC('DAY', transaction_date)
    - name: Channel
      expr: sales_channel

  measures:
    - name: Revenue
      expr: SUM(amount)
    - name: Transactions
      expr: COUNT(1)
    - name: Unique Buyers
      expr: COUNT(DISTINCT customer_id)

  materialization:
    schedule: every 1 hour
    mode: relaxed
    materialized_views:
      - name: daily_category
        type: aggregated
        dimensions:
          - Category
          - Day
        measures:
          - Revenue
          - Transactions
      - name: full_model
        type: unaggregated
$$
```

## Pattern 8: Using samples.tpch for Quick Demos

The TPC-H sample dataset is available on all Databricks workspaces.

```sql
CREATE OR REPLACE VIEW catalog.schema.tpch_orders_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 1.1
  comment: "TPC-H Orders KPIs - demo metric view"
  source: samples.tpch.orders
  filter: o_orderdate > '1990-01-01'

  dimensions:
    - name: Order Month
      expr: DATE_TRUNC('MONTH', o_orderdate)
      comment: "Month of order"
    - name: Order Status
      expr: CASE
        WHEN o_orderstatus = 'O' THEN 'Open'
        WHEN o_orderstatus = 'P' THEN 'Processing'
        WHEN o_orderstatus = 'F' THEN 'Fulfilled'
        END
      comment: "Status: Open, Processing, or Fulfilled"
    - name: Order Priority
      expr: SPLIT(o_orderpriority, '-')[1]
      comment: "Numeric priority 1-5; 1 is highest"

  measures:
    - name: Order Count
      expr: COUNT(1)
    - name: Total Revenue
      expr: SUM(o_totalprice)
      comment: "Sum of total price"
    - name: Revenue per Customer
      expr: SUM(o_totalprice) / COUNT(DISTINCT o_custkey)
      comment: "Average revenue per distinct customer"
    - name: Open Order Revenue
      expr: SUM(o_totalprice) FILTER (WHERE o_orderstatus = 'O')
      comment: "Potential revenue from open orders"
$$
```

### Demo queries

```sql
-- Monthly revenue trend
SELECT
  `Order Month`,
  MEASURE(`Total Revenue`)::BIGINT AS revenue,
  MEASURE(`Order Count`) AS orders
FROM catalog.schema.tpch_orders_metrics
WHERE extract(year FROM `Order Month`) = 1995
GROUP BY ALL
ORDER BY ALL

-- Revenue by status
SELECT
  `Order Status`,
  MEASURE(`Total Revenue`)::BIGINT AS revenue,
  MEASURE(`Revenue per Customer`)::BIGINT AS rev_per_customer
FROM catalog.schema.tpch_orders_metrics
GROUP BY ALL

-- Open orders risk assessment
SELECT
  `Order Month`,
  MEASURE(`Open Order Revenue`)::BIGINT AS at_risk_revenue,
  MEASURE(`Total Revenue`)::BIGINT AS total_revenue
FROM catalog.schema.tpch_orders_metrics
WHERE extract(year FROM `Order Month`) >= 1995
GROUP BY ALL
ORDER BY ALL
```

## Pattern 9: Window Measures (Experimental)

Window measures enable moving averages, running totals, period-over-period changes, and semiadditive measures. Add a `window` block to any measure definition. See [Window Measures Documentation](https://docs.databricks.com/aws/en/metric-views/data-modeling/window-measures).

### Window Range Values

| Range | Description |
|-------|-------------|
| `current` | Only rows where the window ordering value equals the current row |
| `cumulative` | All rows up to and including the current row |
| `trailing <N> <unit>` | N units before the current row (**excludes** current) |
| `leading <N> <unit>` | N units after the current row |
| `all` | All rows regardless of ordering |

### Trailing Window: 7-Day Distinct Customers

```sql
CREATE OR REPLACE VIEW catalog.schema.customer_activity
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2024-01-01'

  dimensions:
    - name: date
      expr: order_date

  measures:
    - name: t7d_customers
      expr: COUNT(DISTINCT customer_id)
      window:
        - order: date
          range: trailing 7 day
          semiadditive: last
$$
```

**Key:** `trailing 7 day` includes the 7 days **before** each date, **excluding** the current date. `semiadditive: last` returns the last value when the `date` dimension is not in the GROUP BY.

### Running Total (Cumulative)

```sql
CREATE OR REPLACE VIEW catalog.schema.cumulative_sales
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2024-01-01'

  dimensions:
    - name: date
      expr: order_date

  measures:
    - name: running_total_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: cumulative
          semiadditive: last
$$
```

### Period-Over-Period: Day-Over-Day Growth

Compose window measures using `MEASURE()` references in derived measures.

```sql
CREATE OR REPLACE VIEW catalog.schema.daily_growth
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2024-01-01'

  dimensions:
    - name: date
      expr: order_date

  measures:
    - name: previous_day_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: trailing 1 day
          semiadditive: last

    - name: current_day_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: current
          semiadditive: last

    - name: day_over_day_growth
      expr: (MEASURE(current_day_sales) - MEASURE(previous_day_sales)) / MEASURE(previous_day_sales) * 100
$$
```

**Key:** The derived `day_over_day_growth` measure uses `MEASURE()` to reference other window measures. It does NOT need its own `window` block.

### Year-to-Date (Composing Multiple Windows)

A single measure can have multiple window specs to create period-to-date calculations.

```sql
CREATE OR REPLACE VIEW catalog.schema.ytd_metrics
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.orders
  filter: order_date > DATE'2023-01-01'

  dimensions:
    - name: date
      expr: order_date
    - name: year
      expr: DATE_TRUNC('year', order_date)

  measures:
    - name: ytd_sales
      expr: SUM(total_price)
      window:
        - order: date
          range: cumulative
          semiadditive: last
        - order: year
          range: current
          semiadditive: last
$$
```

**Key:** The first window does a cumulative sum over `date`. The second window restricts scope to the `current` year. Together they produce year-to-date.

### Semiadditive Measure: Bank Balance

For measures like balances that should not be summed across time.

```sql
CREATE OR REPLACE VIEW catalog.schema.account_balances
WITH METRICS
LANGUAGE YAML
AS $$
  version: 0.1
  source: catalog.schema.daily_balances

  dimensions:
    - name: date
      expr: date
    - name: customer
      expr: customer_id

  measures:
    - name: balance
      expr: SUM(balance)
      window:
        - order: date
          range: current
          semiadditive: last
$$
```

**Key:** `semiadditive: last` prevents summing across dates (returns the last date's value instead), but the measure **still aggregates across other dimensions** like `customer`. When grouped by date, you get total balance across all customers for that day. When not grouped by date, you get the balance from the most recent date.

### Query window measures

Window measures are queried with the same `MEASURE()` syntax:

```sql
SELECT
  date,
  MEASURE(t7d_customers) AS trailing_7d_customers,
  MEASURE(running_total_sales) AS running_total
FROM catalog.schema.customer_activity
WHERE date >= DATE'2024-06-01'
GROUP BY ALL
ORDER BY ALL
```

## MCP Tool Examples

### Create with joins

```python
manage_metric_views(
    action="create",
    full_name="catalog.schema.sales_metrics",
    source="catalog.schema.fact_sales",
    or_replace=True,
    joins=[
        {
            "name": "customer",
            "source": "catalog.schema.dim_customer",
            "on": "source.customer_id = customer.id"
        },
        {
            "name": "product",
            "source": "catalog.schema.dim_product",
            "on": "source.product_id = product.id"
        }
    ],
    dimensions=[
        {"name": "Customer Segment", "expr": "customer.segment"},
        {"name": "Product Category", "expr": "product.category"},
        {"name": "Sale Month", "expr": "DATE_TRUNC('MONTH', source.sale_date)"},
    ],
    measures=[
        {"name": "Total Revenue", "expr": "SUM(source.amount)"},
        {"name": "Order Count", "expr": "COUNT(1)"},
        {"name": "Unique Customers", "expr": "COUNT(DISTINCT source.customer_id)"},
    ],
)
```

### Alter to add a new measure

```python
manage_metric_views(
    action="alter",
    full_name="catalog.schema.sales_metrics",
    source="catalog.schema.fact_sales",
    joins=[
        {"name": "customer", "source": "catalog.schema.dim_customer", "on": "source.customer_id = customer.id"},
    ],
    dimensions=[
        {"name": "Customer Segment", "expr": "customer.segment"},
        {"name": "Sale Month", "expr": "DATE_TRUNC('MONTH', source.sale_date)"},
    ],
    measures=[
        {"name": "Total Revenue", "expr": "SUM(source.amount)"},
        {"name": "Order Count", "expr": "COUNT(1)"},
        {"name": "Average Order Value", "expr": "AVG(source.amount)"},  # New measure
    ],
)
```

### Query with filters

```python
manage_metric_views(
    action="query",
    full_name="catalog.schema.sales_metrics",
    query_measures=["Total Revenue", "Order Count"],
    query_dimensions=["Customer Segment", "Sale Month"],
    where="`Customer Segment` = 'Enterprise'",
    order_by="ALL",
    limit=50,
)
```
