# Performance Tuning for SDP

Performance optimization strategies including **Liquid Clustering** (modern approach), materialized view refresh, state management, and compute configuration.

---

## Liquid Clustering (Recommended)

**Liquid Clustering** is the recommended approach for data layout optimization. It replaces manual `PARTITION BY` and `Z-ORDER`.

### What is Liquid Clustering?

- **Adaptive**: Adjusts to data distribution changes
- **Multi-dimensional**: Clusters on multiple columns simultaneously
- **Automatic file sizing**: Maintains optimal file sizes
- **Self-optimizing**: Reduces manual OPTIMIZE commands

### Basic Syntax

**SQL**:
```sql
CREATE OR REPLACE STREAMING TABLE bronze_events
CLUSTER BY (event_type, event_date)
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  CAST(current_date() AS DATE) AS event_date
FROM read_files('/mnt/raw/events/', format => 'json');
```

**Python**:
```python
from pyspark import pipelines as dp

@dp.table(cluster_by=["event_type", "event_date"])
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

### Automatic Cluster Key Selection

```sql
-- Let Databricks choose based on query patterns
CREATE OR REPLACE STREAMING TABLE bronze_events
CLUSTER BY (AUTO)
AS SELECT ...;
```

**When to use AUTO**: Learning phase, unknown access patterns, prototyping
**When to define manually**: Well-known query patterns, production workloads

---

## Cluster Key Selection by Layer

### Bronze Layer

Cluster by event type + date:

```sql
CREATE OR REPLACE STREAMING TABLE bronze_events
CLUSTER BY (event_type, ingestion_date)
TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true')
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  CAST(current_date() AS DATE) AS ingestion_date
FROM read_files('/mnt/raw/events/', format => 'json');
```

**Why**: Bronze filtered by event type for processing and by date for incremental loads.

### Silver Layer

Cluster by primary key + business dimension:

```sql
CREATE OR REPLACE STREAMING TABLE silver_orders
CLUSTER BY (customer_id, order_date)
AS
SELECT
  order_id, customer_id, product_id, amount,
  CAST(order_timestamp AS DATE) AS order_date,
  order_timestamp
FROM STREAM bronze_orders;
```

**Why**: Entity lookups (by ID) and time-range queries (by date).

### Gold Layer

Cluster by aggregation dimensions:

```sql
CREATE OR REPLACE MATERIALIZED VIEW gold_sales_summary
CLUSTER BY (product_category, year_month)
AS
SELECT
  product_category,
  DATE_FORMAT(order_date, 'yyyy-MM') AS year_month,
  SUM(amount) AS total_sales,
  COUNT(*) AS transaction_count,
  AVG(amount) AS avg_order_value
FROM silver_orders
GROUP BY product_category, DATE_FORMAT(order_date, 'yyyy-MM');
```

**Why**: Dashboard filters (category, region, time period).

### Selection Guidelines

| Layer | Good Keys | Rationale |
|-------|-----------|-----------|
| **Bronze** | event_type, ingestion_date | Filter by type; date for incremental |
| **Silver** | primary_key, business_date | Entity lookups + time ranges |
| **Gold** | aggregation_dimensions | Dashboard filters |

**Best practices**:
- First key: Most selective filter (e.g., customer_id)
- Second key: Next common filter (e.g., date)
- Order matters: Most selective first
- Limit to 4 keys: Diminishing returns beyond 4
- **Use AUTO if unsure**

---

## Migration from Legacy PARTITION BY

### Before (Legacy)

```sql
CREATE OR REPLACE STREAMING TABLE events
PARTITIONED BY (date DATE)
TBLPROPERTIES ('pipelines.autoOptimize.zOrderCols' = 'user_id,event_type')
AS SELECT ...;
```

**Issues**: Fixed keys, small file problem, skewed distribution, manual OPTIMIZE required.

### After (Modern with Liquid Clustering)

```sql
CREATE OR REPLACE STREAMING TABLE events
CLUSTER BY (date, user_id, event_type)
AS SELECT ...;
```

**Benefits**: Adaptive, no small files, automatic optimization, 20-50% performance improvement.

### When to Still Use PARTITION BY

**Only use for**:
1. **Regulatory** requirements (physical separation)
2. **Data lifecycle**: Need to `DROP` partitions for retention
3. **Compatibility**: Older Delta Lake versions (< DBR 13.3)
4. **Existing large tables**: Migration cost outweighs benefits

**Otherwise, prefer Liquid Clustering.**

---

## Table Properties

### Auto-Optimize

```sql
CREATE OR REPLACE STREAMING TABLE bronze_events
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
)
AS SELECT * FROM read_files(...);
```

**Benefits**: Reduces small files, improves reads, automatic compaction.

### Change Data Feed

```sql
CREATE OR REPLACE STREAMING TABLE silver_customers
TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true')
AS SELECT * FROM STREAM bronze_customers;
```

**Use when**: Downstream systems need efficient change tracking.

### Retention Periods

```sql
CREATE OR REPLACE STREAMING TABLE bronze_high_volume
TBLPROPERTIES (
  'delta.logRetentionDuration' = '7 days',
  'delta.deletedFileRetentionDuration' = '7 days'
)
AS SELECT * FROM read_files(...);
```

**Use for**: High-volume tables to reduce storage costs.

---

## Materialized View Refresh

### Refresh Frequency

```sql
-- Near-real-time (frequent)
CREATE OR REPLACE MATERIALIZED VIEW gold_live_metrics
REFRESH EVERY 5 MINUTES
AS
SELECT
  metric_name,
  AVG(metric_value) AS avg_value,
  MAX(last_updated) AS freshness
FROM silver_metrics
GROUP BY metric_name;

-- Daily reports (scheduled)
CREATE OR REPLACE MATERIALIZED VIEW gold_daily_summary
REFRESH EVERY 1 DAY
AS
SELECT report_date, SUM(amount) AS total_amount
FROM silver_sales
GROUP BY report_date;
```

### Incremental Refresh (Automatic)

Materialized views auto-use incremental refresh when possible:

```sql
-- Refreshes incrementally if source has row tracking
CREATE OR REPLACE MATERIALIZED VIEW gold_aggregates AS
SELECT
  product_id,
  SUM(quantity) AS total_quantity,
  SUM(amount) AS total_amount
FROM silver_sales
GROUP BY product_id;
```

**Requirements**: Source has Delta row tracking, no row filters, supported aggregations.

### Pre-Aggregation

```sql
-- Instead of querying large table repeatedly
CREATE OR REPLACE MATERIALIZED VIEW orders_monthly AS
SELECT
  customer_id,
  YEAR(order_date) AS year,
  MONTH(order_date) AS month,
  SUM(amount) AS total
FROM large_orders_table
GROUP BY customer_id, YEAR(order_date), MONTH(order_date);

-- Query the MV (fast)
SELECT * FROM orders_monthly WHERE year = 2024;
```

---

## State Management for Streaming

### Understand State Growth

```sql
-- High state: Every unique combination creates state
SELECT
  user_id,       -- 1M users
  product_id,    -- 10K products
  session_id,    -- 100M sessions
  COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, product_id, session_id;  -- Massive state!
```

### Reduce State Size

**Strategy 1: Reduce cardinality**

```sql
-- Aggregate at higher level
SELECT
  user_id,
  product_category,  -- 100 categories (not 10K products)
  DATE(event_time) AS event_date,
  COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, product_category, DATE(event_time);
```

**Strategy 2: Use time windows**

```sql
-- Bounded state with windows
SELECT
  user_id,
  window(event_time, '1 hour') AS time_window,
  COUNT(*) AS events
FROM STREAM bronze_events
GROUP BY user_id, window(event_time, '1 hour');
```

**Strategy 3: Materialize intermediates**

```sql
-- Streaming aggregation (maintains state)
CREATE OR REPLACE STREAMING TABLE user_daily_stats AS
SELECT
  user_id,
  DATE(event_time) AS event_date,
  COUNT(*) AS event_count
FROM STREAM bronze_events
GROUP BY user_id, DATE(event_time);

-- Batch aggregation (no streaming state)
CREATE OR REPLACE MATERIALIZED VIEW user_monthly_stats AS
SELECT
  user_id,
  DATE_TRUNC('month', event_date) AS month,
  SUM(event_count) AS total_events
FROM user_daily_stats
GROUP BY user_id, DATE_TRUNC('month', event_date);
```

---

## Join Optimization

### Stream-to-Static (Efficient)

```sql
-- Small static dimension, large streaming fact
CREATE OR REPLACE STREAMING TABLE sales_enriched AS
SELECT
  s.sale_id, s.product_id, s.amount,
  p.product_name, p.category  -- From small static table
FROM STREAM bronze_sales s
LEFT JOIN dim_products p ON s.product_id = p.product_id;
```

**Best practice**: Keep static dimensions small (<10K rows) for broadcast.

### Stream-to-Stream (Stateful)

```sql
-- Time bounds limit state retention
CREATE OR REPLACE STREAMING TABLE orders_with_payments AS
SELECT
  o.order_id, o.amount AS order_amount,
  p.payment_id, p.amount AS payment_amount
FROM STREAM bronze_orders o
INNER JOIN STREAM bronze_payments p
  ON o.order_id = p.order_id
  AND p.payment_time BETWEEN o.order_time AND o.order_time + INTERVAL 1 HOUR;
```

**Optimization**: Use time bounds in join condition.

---

## Compute Configuration

### Serverless vs Classic

| Aspect | Serverless | Classic |
|--------|-----------|---------|
| Startup | Fast (seconds) | Slower (minutes) |
| Scaling | Automatic, instant | Manual/autoscaling |
| Cost | Pay-per-use | Pay for cluster time |
| Best for | Variable workloads, dev/test | Steady workloads |

### Serverless (Recommended)

Enable at pipeline level:

```yaml
execution_mode: continuous  # or triggered
serverless: true
```

**Advantages**: No cluster management, instant scaling, lower cost for bursty workloads.

---

## Query Optimization

### Filter Early

```sql
-- ✅ Filter at source
CREATE OR REPLACE STREAMING TABLE silver_recent AS
SELECT *
FROM STREAM bronze_events
WHERE event_date >= CURRENT_DATE() - INTERVAL 7 DAYS;

-- ❌ Filter late
CREATE OR REPLACE STREAMING TABLE silver_all AS
SELECT * FROM STREAM bronze_events;

CREATE OR REPLACE MATERIALIZED VIEW gold_recent AS
SELECT * FROM silver_all
WHERE event_date >= CURRENT_DATE() - INTERVAL 7 DAYS;
```

### Select Specific Columns

```sql
-- ❌ Reads all columns
SELECT * FROM large_table;

-- ✅ Only needed columns
SELECT customer_id, order_date, amount FROM large_table;
```

### Use GROUP BY Over DISTINCT

```sql
-- ❌ Expensive on high-cardinality
SELECT DISTINCT transaction_id FROM huge_table;

-- ✅ Better
SELECT transaction_id, COUNT(*) FROM huge_table GROUP BY transaction_id;
```

---

## Monitoring

Track key metrics:

```sql
-- Data freshness
SELECT
  table_name,
  MAX(event_timestamp) AS latest_event,
  CURRENT_TIMESTAMP() AS now,
  TIMESTAMPDIFF(MINUTE, MAX(event_timestamp), CURRENT_TIMESTAMP()) AS lag_minutes
FROM pipeline_monitoring.table_metrics
GROUP BY table_name;
```

**Check for**:
1. Slow streaming tables (high processing lag)
2. Large state operations (high memory)
3. Expensive joins (long processing times)
4. Small files (many small files in Delta)

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Pipeline running slowly | Check partitioning, state size, join patterns |
| High memory usage | Unbounded state - add time windows, reduce cardinality |
| Many small files | Enable auto-optimize, run OPTIMIZE command |
| Expensive queries on large tables | Add clustering, create filtered MVs |
| MV refresh slow | Enable row tracking on source, verify incremental refresh |
