# Streaming Patterns for SDP

Streaming-specific patterns including deduplication, windowed aggregations, late-arriving data handling, and stateful operations.

---

## Deduplication Patterns

### By Key

```sql
-- Bronze: Ingest all (may contain duplicates)
CREATE OR REPLACE STREAMING TABLE bronze_events AS
SELECT *, current_timestamp() AS _ingested_at
FROM read_stream(...);

-- Silver: Deduplicate by event_id
CREATE OR REPLACE STREAMING TABLE silver_events_dedup AS
SELECT
  event_id, user_id, event_type, event_timestamp, _ingested_at
FROM (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_timestamp) AS rn
  FROM STREAM bronze_events
)
WHERE rn = 1;
```

### With Time Window

Deduplicate within time window to handle late arrivals:

```sql
CREATE OR REPLACE STREAMING TABLE silver_events_dedup AS
SELECT
  event_id, user_id, event_type, event_timestamp,
  MIN(_ingested_at) AS first_seen_at
FROM STREAM bronze_events
GROUP BY
  event_id, user_id, event_type, event_timestamp,
  window(event_timestamp, '1 hour')  -- Deduplicate within 1-hour windows
HAVING COUNT(*) >= 1;
```

### Composite Key

```sql
CREATE OR REPLACE STREAMING TABLE silver_transactions_dedup AS
SELECT
  transaction_id, customer_id, amount, transaction_timestamp,
  MIN(_ingested_at) AS _ingested_at
FROM STREAM bronze_transactions
GROUP BY transaction_id, customer_id, amount, transaction_timestamp;
```

---

## Windowed Aggregations

### Tumbling Windows

```sql
-- 5-minute non-overlapping windows
CREATE OR REPLACE STREAMING TABLE silver_sensor_5min AS
SELECT
  sensor_id,
  window(event_timestamp, '5 minutes') AS time_window,
  AVG(temperature) AS avg_temperature,
  MIN(temperature) AS min_temperature,
  MAX(temperature) AS max_temperature,
  COUNT(*) AS event_count
FROM STREAM bronze_sensor_events
GROUP BY sensor_id, window(event_timestamp, '5 minutes');
```

### Multiple Window Sizes

```sql
-- 1-minute for real-time monitoring
CREATE OR REPLACE STREAMING TABLE gold_sensor_1min AS
SELECT
  sensor_id,
  window(event_timestamp, '1 minute').start AS window_start,
  window(event_timestamp, '1 minute').end AS window_end,
  AVG(value) AS avg_value,
  COUNT(*) AS event_count
FROM STREAM silver_sensor_data
GROUP BY sensor_id, window(event_timestamp, '1 minute');

-- 1-hour for trend analysis
CREATE OR REPLACE STREAMING TABLE gold_sensor_1hour AS
SELECT
  sensor_id,
  window(event_timestamp, '1 hour').start AS window_start,
  AVG(value) AS avg_value,
  STDDEV(value) AS stddev_value
FROM STREAM silver_sensor_data
GROUP BY sensor_id, window(event_timestamp, '1 hour');
```

---

## Late-Arriving Data

### Event-Time vs Processing-Time

Always use event timestamp for business logic, not ingestion timestamp:

```sql
-- ✅ Use event timestamp
CREATE OR REPLACE STREAMING TABLE silver_orders AS
SELECT
  order_id, order_timestamp,  -- Event time from source
  customer_id, amount,
  _ingested_at                -- Processing time (debugging only)
FROM STREAM bronze_orders;

-- Group by event time
CREATE OR REPLACE STREAMING TABLE gold_daily_orders AS
SELECT
  CAST(order_timestamp AS DATE) AS order_date,  -- Event time
  COUNT(*) AS order_count,
  SUM(amount) AS total_amount
FROM STREAM silver_orders
GROUP BY CAST(order_timestamp AS DATE);
```

### Handling Out-of-Order with SCD2

Use SEQUENCE BY with event timestamp:

```sql
CREATE OR REFRESH STREAMING TABLE silver_customers_history;

CREATE FLOW customers_scd2_flow AS
AUTO CDC INTO silver_customers_history
FROM stream(bronze_customer_cdc)
KEYS (customer_id)
SEQUENCE BY event_timestamp  -- Handles out-of-order
APPLY AS DELETE WHEN operation = "DELETE"
COLUMNS * EXCEPT (operation, _rescued_data)
STORED AS SCD TYPE 2
TRACK HISTORY ON *;
```

---

## Stateful Operations

### Stream-to-Stream Joins

```sql
-- Join two streaming sources
CREATE OR REPLACE STREAMING TABLE silver_orders_with_payments AS
SELECT
  o.order_id, o.customer_id, o.order_timestamp, o.amount AS order_amount,
  p.payment_id, p.payment_timestamp, p.payment_method, p.amount AS payment_amount
FROM STREAM bronze_orders o
INNER JOIN STREAM bronze_payments p
  ON o.order_id = p.order_id
  AND p.payment_timestamp BETWEEN o.order_timestamp AND o.order_timestamp + INTERVAL 1 HOUR;
```

### Stream-to-Static Joins

Enrich streaming data with dimension tables:

```sql
-- Static dimension (changes infrequently)
CREATE OR REPLACE TABLE dim_products AS
SELECT * FROM catalog.schema.products;

-- Stream-to-static join
CREATE OR REPLACE STREAMING TABLE silver_sales_enriched AS
SELECT
  s.sale_id, s.product_id, s.quantity, s.sale_timestamp,
  p.product_name, p.category, p.price,
  s.quantity * p.price AS total_amount
FROM STREAM bronze_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

### Incremental Aggregations

```sql
-- Running totals by customer (stateful)
CREATE OR REPLACE STREAMING TABLE silver_customer_running_totals AS
SELECT
  customer_id,
  SUM(amount) AS total_spent,
  COUNT(*) AS transaction_count,
  MAX(transaction_timestamp) AS last_transaction_at
FROM STREAM bronze_transactions
GROUP BY customer_id;
```

---

## Session Windows

Group events into sessions based on inactivity gaps:

```sql
-- 30-minute inactivity timeout
CREATE OR REPLACE STREAMING TABLE silver_user_sessions AS
SELECT
  user_id,
  session_window(event_timestamp, '30 minutes') AS session,
  MIN(event_timestamp) AS session_start,
  MAX(event_timestamp) AS session_end,
  COUNT(*) AS event_count,
  COLLECT_LIST(event_type) AS event_sequence
FROM STREAM bronze_user_events
GROUP BY user_id, session_window(event_timestamp, '30 minutes');
```

---

## Anomaly Detection

### Real-Time Outlier Detection

```sql
CREATE OR REPLACE STREAMING TABLE silver_sensor_with_anomalies AS
SELECT
  sensor_id, event_timestamp, temperature,
  AVG(temperature) OVER (
    PARTITION BY sensor_id ORDER BY event_timestamp
    ROWS BETWEEN 100 PRECEDING AND CURRENT ROW
  ) AS rolling_avg_100,
  STDDEV(temperature) OVER (
    PARTITION BY sensor_id ORDER BY event_timestamp
    ROWS BETWEEN 100 PRECEDING AND CURRENT ROW
  ) AS rolling_stddev_100,
  CASE
    WHEN temperature > rolling_avg_100 + (3 * rolling_stddev_100) THEN 'HIGH_OUTLIER'
    WHEN temperature < rolling_avg_100 - (3 * rolling_stddev_100) THEN 'LOW_OUTLIER'
    ELSE 'NORMAL'
  END AS anomaly_flag
FROM STREAM bronze_sensor_events;

-- Route anomalies for alerting
CREATE OR REPLACE STREAMING TABLE silver_sensor_anomalies AS
SELECT *
FROM STREAM silver_sensor_with_anomalies
WHERE anomaly_flag IN ('HIGH_OUTLIER', 'LOW_OUTLIER');
```

### Threshold-Based Filtering

```sql
CREATE OR REPLACE STREAMING TABLE silver_high_value_transactions AS
SELECT transaction_id, customer_id, amount, transaction_timestamp
FROM STREAM bronze_transactions
WHERE amount > 10000;
```

---

## Execution Modes

Configure at pipeline level (not in SQL):

**Continuous** (real-time, sub-second latency):
```yaml
execution_mode: continuous
serverless: true
```

**Triggered** (scheduled, cost-optimized):
```yaml
execution_mode: triggered
schedule: "0 * * * *"  # Hourly
```

**When to use**:
- **Continuous**: Real-time dashboards, alerting, sub-minute SLAs
- **Triggered**: Daily/hourly reports, batch processing

---

## Key Patterns

### 1. Use Event Timestamps

```sql
-- ✅ Event timestamp for logic
GROUP BY date_trunc('hour', event_timestamp)

-- ❌ Processing timestamp
GROUP BY date_trunc('hour', _ingested_at)
```

### 2. Window Size Selection

- **1-5 minutes**: Real-time monitoring
- **15-60 minutes**: Operational dashboards
- **1-24 hours**: Analytical reports

### 3. State Management

Higher cardinality = more state:

```sql
-- High state: 1M users × 10K products × 100M sessions
GROUP BY user_id, product_id, session_id

-- Lower state: 1M users × 100 categories × days
GROUP BY user_id, product_category, DATE(event_time)
```

Use time windows to bound state retention.

### 4. Deduplicate Early

Apply at bronze → silver transition:

```sql
-- Bronze: Accept duplicates
CREATE OR REPLACE STREAMING TABLE bronze_events AS
SELECT * FROM read_stream(...);

-- Silver: Deduplicate immediately
CREATE OR REPLACE STREAMING TABLE silver_events AS
SELECT DISTINCT event_id, event_type, event_timestamp, user_id
FROM STREAM bronze_events;

-- Gold: Work with clean data
CREATE OR REPLACE STREAMING TABLE gold_metrics AS
SELECT ... FROM STREAM silver_events;
```

### 5. Monitor Lag

```sql
CREATE OR REPLACE STREAMING TABLE monitoring_lag AS
SELECT
  'kafka_events' AS source,
  MAX(kafka_timestamp) AS max_event_timestamp,
  current_timestamp() AS processing_timestamp,
  (unix_timestamp(current_timestamp()) - unix_timestamp(MAX(kafka_timestamp))) AS lag_seconds
FROM STREAM bronze_kafka_events
GROUP BY window(kafka_timestamp, '1 minute');
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| High memory with windows | Use larger windows, reduce group-by cardinality |
| Duplicate events in output | Add explicit deduplication by unique key |
| Missing late-arriving events | Increase window size or use longer retention |
| Stream-to-stream join empty | Verify join conditions and time bounds |
| State growth over time | Add time windows, reduce cardinality, materialize intermediates |
