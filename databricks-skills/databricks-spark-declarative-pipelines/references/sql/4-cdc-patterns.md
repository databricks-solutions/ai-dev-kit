# SQL CDC Patterns (AUTO CDC & SCD)

Change Data Capture patterns using AUTO CDC for SCD Type 1 and Type 2, plus querying SCD history tables.

---

## Overview

AUTO CDC automatically handles Change Data Capture to track changes using Slow Changing Dimensions (SCD). It provides automatic deduplication, change tracking, and handles late-arriving data correctly.

**Where to apply AUTO CDC:**
- **Silver layer**: When business users need deduplicated or historical data
- **Gold layer**: When implementing dimensional modeling (star schema)

---

## SCD Type 1 vs Type 2

### SCD Type 1 (In-place updates)
- **Overwrites** old values with new values
- **No history preserved** - only current state
- **Use for**: Error corrections, attributes where history doesn't matter
- **Syntax**: `STORED AS SCD TYPE 1`

### SCD Type 2 (History tracking)
- **Creates new row** for each change
- **Preserves full history** with `__START_AT` and `__END_AT` timestamps
- **Use for**: Tracking changes over time (addresses, prices, roles)
- **Syntax**: `STORED AS SCD TYPE 2`

---

## Creating AUTO CDC Flows

### SCD Type 2

```sql
-- Step 1: Create target table
CREATE OR REFRESH STREAMING TABLE dim_customers;

-- Step 2: Create AUTO CDC flow
CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO dim_customers
FROM stream(customers_cdc_clean)
KEYS (customer_id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY event_timestamp
COLUMNS * EXCEPT (operation, _ingested_at, _source_file)
STORED AS SCD TYPE 2;
```

**Important:** Put `APPLY AS DELETE WHEN` before `SEQUENCE BY`. Only list columns in `COLUMNS * EXCEPT (...)` that exist in the source.

### SCD Type 1

```sql
-- Step 1: Create target table
CREATE OR REFRESH STREAMING TABLE orders_current;

-- Step 2: Create AUTO CDC flow
CREATE FLOW orders_scd1_flow AS
AUTO CDC INTO orders_current
FROM stream(orders_clean)
KEYS (order_id)
SEQUENCE BY updated_timestamp
COLUMNS * EXCEPT (_ingested_at)
STORED AS SCD TYPE 1;
```

### Selective History Tracking

Track history only when specific columns change:

```sql
CREATE FLOW products_scd2_flow AS
AUTO CDC INTO products_history
FROM stream(products_clean)
KEYS (product_id)
SEQUENCE BY modified_at
COLUMNS * EXCEPT (operation)
STORED AS SCD TYPE 2
TRACK HISTORY ON price, cost;
```

When `price` or `cost` changes, a new version is created. Other column changes update the current record without new versions.

---

## Complete Pattern: Clean + AUTO CDC

### Step 1: Clean and Validate Source Data

```sql
CREATE OR REFRESH STREAMING TABLE customers_cdc_clean AS
SELECT
  customer_id,
  customer_name,
  email,
  phone,
  address,
  CAST(updated_at AS TIMESTAMP) AS event_timestamp,
  operation
FROM STREAM bronze_customers_cdc
WHERE customer_id IS NOT NULL
  AND email IS NOT NULL;
```

### Step 2: Apply AUTO CDC

```sql
CREATE OR REFRESH STREAMING TABLE dim_customers;

CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO dim_customers
FROM stream(customers_cdc_clean)
KEYS (customer_id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY event_timestamp
COLUMNS * EXCEPT (operation)
STORED AS SCD TYPE 2;
```

---

## Querying SCD Type 2 Tables

SCD Type 2 tables include temporal columns:
- `__START_AT` - When this version became effective
- `__END_AT` - When this version expired (NULL for current)

### Current State

```sql
-- All current records
CREATE OR REFRESH MATERIALIZED VIEW dim_customers_current AS
SELECT
  customer_id, customer_name, email, phone, address,
  __START_AT AS valid_from
FROM dim_customers
WHERE __END_AT IS NULL;

-- Specific customer
SELECT *
FROM dim_customers
WHERE customer_id = '12345'
  AND __END_AT IS NULL;
```

### Point-in-Time Queries

Get state as of a specific date:

```sql
-- Products as of January 1, 2024
CREATE OR REFRESH MATERIALIZED VIEW products_as_of_2024_01_01 AS
SELECT
  product_id, product_name, price, category,
  __START_AT, __END_AT
FROM products_history
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL);
```

### Change Analysis

Track all changes for an entity:

```sql
SELECT
  customer_id, customer_name, email, phone,
  __START_AT, __END_AT,
  COALESCE(
    DATEDIFF(DAY, __START_AT, __END_AT),
    DATEDIFF(DAY, __START_AT, CURRENT_TIMESTAMP())
  ) AS days_active
FROM dim_customers
WHERE customer_id = '12345'
ORDER BY __START_AT DESC;
```

Changes within a time period:

```sql
-- Customers who changed during Q1 2024
SELECT
  customer_id, customer_name,
  __START_AT AS change_timestamp,
  'UPDATE' AS change_type
FROM dim_customers
WHERE __START_AT BETWEEN '2024-01-01' AND '2024-03-31'
  AND __START_AT != (
    SELECT MIN(__START_AT)
    FROM dim_customers ch2
    WHERE ch2.customer_id = dim_customers.customer_id
  )
ORDER BY __START_AT;
```

---

## Joining Facts with Historical Dimensions

### At Transaction Time

```sql
-- Join sales with product prices at time of sale
CREATE OR REFRESH MATERIALIZED VIEW sales_with_historical_prices AS
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

### With Current Dimension

```sql
CREATE OR REFRESH MATERIALIZED VIEW sales_with_current_prices AS
SELECT
  s.sale_id, s.product_id, s.sale_date, s.quantity,
  s.amount AS amount_at_sale,
  p.product_name AS current_product_name,
  p.price AS current_price
FROM sales_fact s
INNER JOIN products_history p
  ON s.product_id = p.product_id
  AND p.__END_AT IS NULL;
```

---

## Optimization Patterns

### Pre-Filter Materialized Views

```sql
-- Current state view (most common pattern)
CREATE OR REFRESH MATERIALIZED VIEW dim_products_current AS
SELECT * FROM products_history WHERE __END_AT IS NULL;

-- Recent changes only
CREATE OR REFRESH MATERIALIZED VIEW dim_recent_changes AS
SELECT * FROM products_history
WHERE __START_AT >= CURRENT_DATE() - INTERVAL 90 DAYS;

-- Change frequency stats
CREATE OR REFRESH MATERIALIZED VIEW product_change_stats AS
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

### 1. Filter by __END_AT for Current

```sql
-- Efficient
WHERE __END_AT IS NULL

-- Less efficient
WHERE __START_AT = (SELECT MAX(__START_AT) FROM table WHERE ...)
```

### 2. Use Inclusive Lower, Exclusive Upper

```sql
WHERE __START_AT <= '2024-01-01'
  AND (__END_AT > '2024-01-01' OR __END_AT IS NULL)
```

### 3. Clean Data Before AUTO CDC

Apply type casting, validation, and filtering first:

```sql
-- Clean source
CREATE OR REFRESH STREAMING TABLE users_clean AS
SELECT
  user_id,
  TRIM(email) AS email,
  CAST(updated_at AS TIMESTAMP) AS updated_timestamp
FROM STREAM bronze_users
WHERE user_id IS NOT NULL AND email IS NOT NULL;

-- Then apply AUTO CDC
CREATE FLOW users_scd2_flow AS
AUTO CDC INTO dim_users
FROM stream(users_clean)
KEYS (user_id)
SEQUENCE BY updated_timestamp
STORED AS SCD TYPE 2;
```

### 4. Choose the Right SCD Type

- **Type 2**: Need to query historical states
- **Type 1**: Only need current state or deduplication

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Multiple rows for same key | Missing `__END_AT IS NULL` filter for current state |
| Point-in-time no results | Use `__START_AT <= date AND (__END_AT > date OR __END_AT IS NULL)` |
| Slow temporal join | Create materialized view for specific time period |
| Unexpected duplicates | Multiple changes same day - use SEQUENCE BY with high precision |
| Parse error on AUTO CDC | Put `APPLY AS DELETE WHEN` before `SEQUENCE BY` |
| Columns not in target | Only list existing columns in `COLUMNS * EXCEPT (...)` |
| Type syntax error | Use `SCD TYPE 1` or `SCD TYPE 2` (not quoted) |
