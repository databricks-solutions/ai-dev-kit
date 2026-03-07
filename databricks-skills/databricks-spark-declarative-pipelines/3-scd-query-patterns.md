# SCD Query Patterns

How to query SCD Type 2 history tables effectively, including current state queries, point-in-time analysis, and change tracking.

---

## Understanding SCD Type 2 Structure

When you create an SCD Type 2 flow, the system automatically adds temporal columns:

```sql
CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO customers_history
FROM stream(customers_cdc_clean)
KEYS (customer_id)
SEQUENCE BY event_timestamp
STORED AS SCD TYPE 2
TRACK HISTORY ON *;
```

**Resulting table structure** (Lakeflow uses double-underscore temporal columns):
```
customers_history
├── customer_id        -- Business key
├── customer_name
├── email
├── phone
├── __START_AT         -- When this version became effective (auto-generated)
├── __END_AT           -- When this version expired (NULL for current)
└── ...other columns
```

**Important:** Query using `__START_AT` and `__END_AT` (double underscore), not `START_AT`/`END_AT`.

---

## Current State Queries

### All Current Records

```sql
-- __END_AT IS NULL indicates active record (Lakeflow uses double underscore)
CREATE OR REPLACE MATERIALIZED VIEW dim_customers_current AS
SELECT
  customer_id, customer_name, email, phone, address,
  __START_AT AS valid_from
FROM customers_history
WHERE __END_AT IS NULL;
```

### Specific Customer

```sql
SELECT *
FROM customers_history
WHERE customer_id = '12345'
  AND __END_AT IS NULL;
```

---

## Point-in-Time Queries

### As-Of Date Query

Get state of records as they were on a specific date:

```sql
-- Products as of January 1, 2024 (use __START_AT / __END_AT)
CREATE OR REPLACE MATERIALIZED VIEW products_as_of_2024_01_01 AS
SELECT
  product_id, product_name, price, category,
  __START_AT, __END_AT
FROM products_history
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL);
```

---

## Change Analysis

### Track All Changes for Entity

```sql
-- Complete history for a customer (use __START_AT / __END_AT)
SELECT
  customer_id, customer_name, email, phone,
  __START_AT, __END_AT,
  COALESCE(
    DATEDIFF(DAY, __START_AT, __END_AT),
    DATEDIFF(DAY, __START_AT, CURRENT_TIMESTAMP())
  ) AS days_active
FROM customers_history
WHERE customer_id = '12345'
ORDER BY __START_AT DESC;
```

### Changes Within Time Period

```sql
-- Customers who changed during Q1 2024 (use __START_AT)
SELECT
  customer_id, customer_name,
  __START_AT AS change_timestamp,
  'UPDATE' AS change_type
FROM customers_history
WHERE __START_AT BETWEEN '2024-01-01' AND '2024-03-31'
  AND __START_AT != (
    SELECT MIN(__START_AT)
    FROM customers_history ch2
    WHERE ch2.customer_id = customers_history.customer_id
  )
ORDER BY __START_AT;
```

---

## Joining Facts with Historical Dimensions

### Enrich Facts with Dimension at Transaction Time

```sql
-- Join sales with product prices at time of sale
CREATE OR REPLACE MATERIALIZED VIEW sales_with_historical_prices AS
SELECT
  s.sale_id, s.product_id, s.sale_date, s.quantity,
  p.product_name, p.price AS unit_price_at_sale_time,
  s.quantity * p.price AS calculated_amount,
  p.category
FROM sales_fact s
INNER JOIN products_history p
  ON s.product_id = p.product_id
  AND s.sale_date >= p.__START_AT
  AND (s.sale_date < p.__END_AT OR p.__END_AT IS NULL);
```

### Join with Current Dimension

```sql
-- Join sales with current product information
CREATE OR REPLACE MATERIALIZED VIEW sales_with_current_prices AS
SELECT
  s.sale_id, s.product_id, s.sale_date, s.quantity,
  s.amount AS amount_at_sale,
  p.product_name AS current_product_name,
  p.price AS current_price,
  p.category AS current_category
FROM sales_fact s
INNER JOIN products_history p
  ON s.product_id = p.product_id
  AND p.__END_AT IS NULL;  -- Current version only
```

---

## Selective History Tracking

When using `TRACK HISTORY ON specific_columns`:

```sql
-- Only price changes trigger new versions
CREATE FLOW products_scd2_flow AS
AUTO CDC INTO products_history
FROM stream(products_cdc_clean)
KEYS (product_id)
SEQUENCE BY event_timestamp
STORED AS SCD TYPE 2
TRACK HISTORY ON price, cost;  -- Only these columns
```

---

## Optimization Patterns

### Pre-Filter Materialized Views

```sql
-- Current state view (most common pattern)
CREATE OR REPLACE MATERIALIZED VIEW dim_products_current AS
SELECT * FROM products_history WHERE __END_AT IS NULL;

-- Recent changes only
CREATE OR REPLACE MATERIALIZED VIEW dim_recent_changes AS
SELECT * FROM products_history
WHERE __START_AT >= CURRENT_DATE() - INTERVAL 90 DAYS;

-- Change frequency stats
CREATE OR REPLACE MATERIALIZED VIEW product_change_stats AS
SELECT
  product_id,
  COUNT(*) AS version_count,
  MIN(__START_AT) AS first_seen,
  MAX(__START_AT) AS last_updated
FROM products_history
GROUP BY product_id;
```

---

## Best Practices

### 1. Always Filter by __END_AT for Current (Lakeflow uses double underscore)

```sql
-- ✅ Efficient
WHERE __END_AT IS NULL

-- ❌ Less efficient
WHERE __START_AT = (SELECT MAX(__START_AT) FROM table WHERE ...)
```

### 2. Use Inclusive Lower, Exclusive Upper

```sql
-- ✅ Standard pattern
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL)
```

### 3. Create MVs for Common Patterns

```sql
-- Current state
CREATE OR REPLACE MATERIALIZED VIEW dim_current AS
SELECT * FROM history WHERE __END_AT IS NULL;

-- Recent changes
CREATE OR REPLACE MATERIALIZED VIEW dim_recent_changes AS
SELECT * FROM history
WHERE __START_AT >= CURRENT_DATE() - INTERVAL 90 DAYS;
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Multiple rows for same key | Missing `__END_AT IS NULL` filter for current state |
| Point-in-time no results | Use `__START_AT <= date AND (__END_AT > date OR __END_AT IS NULL)` |
| Slow temporal join | Create materialized view for specific time period |
| Unexpected duplicates | Multiple changes same day - use SEQUENCE BY with high precision |
