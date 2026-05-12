# SQL Syntax Basics

Core SQL syntax for Spark Declarative Pipelines (SDP).

---

## Table Types

### Streaming Table

Processes data incrementally. Use for continuous ingestion and transformations.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
COMMENT 'Raw event data'
CLUSTER BY (event_type, event_date)
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',
  'delta.autoOptimize.autoCompact' = 'true'
)
AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files('/Volumes/my_catalog/my_schema/raw/events/', format => 'json');
```

**Key points:**
- Use `STREAM` keyword with source for incremental processing
- `CLUSTER BY` enables Liquid Clustering (recommended over PARTITION BY)
- Returns streaming DataFrame

### Materialized View

Batch table with automatic incremental refresh.

```sql
CREATE OR REFRESH MATERIALIZED VIEW gold_daily_summary
COMMENT 'Daily aggregated metrics'
CLUSTER BY (report_date)
AS
SELECT
  report_date,
  SUM(amount) AS total_amount,
  COUNT(*) AS transaction_count
FROM silver_orders
GROUP BY report_date;
```

**Key points:**
- No `STREAM` keyword - reads batch
- Automatically refreshes incrementally when source changes
- Use for aggregations and reporting tables

### View (Persisted)

A regular view published to Unity Catalog. Unlike materialized views, it doesn't store data - the query runs each time the view is accessed.

```sql
CREATE VIEW taxi_raw AS
SELECT * FROM read_files("/Volumes/catalog/schema/raw/taxi/");

CREATE VIEW active_customers AS
SELECT customer_id, name, email
FROM dim_customers
WHERE status = 'active';
```

**Key points:**
- Persisted in Unity Catalog (visible outside pipeline)
- No data storage - query executes on access
- Cannot use streaming queries or constraints
- Requires Unity Catalog pipeline with default publishing mode

**Documentation:** [CREATE VIEW reference](https://docs.databricks.com/aws/en/ldp/developer/ldp-sql-ref-create-view)

### Temporary View

Pipeline-scoped view, not persisted. Useful for intermediate transformations.

```sql
CREATE TEMPORARY VIEW orders_with_calculations AS
SELECT
  *,
  quantity * price AS total,
  quantity * price * discount_rate AS discount_amount
FROM STREAM bronze_orders
WHERE quantity > 0;
```

**Key points:**
- Exists only during pipeline execution
- No storage cost
- Not visible outside pipeline
- Useful before AUTO CDC flows

### Choosing Between View Types

| Type | Persisted | Stores Data | Streaming | Use Case |
|------|-----------|-------------|-----------|----------|
| **Materialized View** | Yes | Yes | No | Aggregations, reporting tables |
| **View** | Yes | No | No | Simple transformations, external access |
| **Temporary View** | No | No | Yes | Intermediate steps, before AUTO CDC |

---

## Data Quality (Expectations)
**Documentation:** [Expectations]https://docs.databricks.com/aws/en/ldp/expectations)

### Constraint Syntax

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders (
  CONSTRAINT valid_amount EXPECT (amount > 0) ON VIOLATION DROP ROW,
  CONSTRAINT valid_customer EXPECT (customer_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT critical_field EXPECT (order_id IS NOT NULL) ON VIOLATION FAIL UPDATE
)
AS
SELECT * FROM STREAM bronze_orders;
```

| Violation Action | Behavior |
|-----------------|----------|
| `ON VIOLATION DROP ROW` | Drop rows that violate |
| `ON VIOLATION FAIL UPDATE` | Fail pipeline if any row violates |
| (no action) | Log warning, keep all rows |

### WHERE Clause Alternative

For simple filtering without tracking:

```sql
CREATE OR REFRESH STREAMING TABLE silver_orders AS
SELECT * FROM STREAM bronze_orders
WHERE amount > 0 AND customer_id IS NOT NULL;
```

---

## Liquid Clustering

Use `CLUSTER BY` instead of legacy `PARTITION BY`. See **[5-performance.md](5-performance.md#liquid-clustering-recommended)** for detailed guidance on key selection by layer.

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
CLUSTER BY (event_type, event_date)
AS SELECT ...;
```

---

## Table Properties

```sql
CREATE OR REFRESH STREAMING TABLE bronze_events
TBLPROPERTIES (
  'delta.autoOptimize.optimizeWrite' = 'true',    -- Optimize file sizes on write
  'delta.autoOptimize.autoCompact' = 'true',      -- Automatic compaction
  'delta.enableChangeDataFeed' = 'true',          -- Enable CDF for downstream
  'delta.logRetentionDuration' = '7 days',        -- Log retention
  'delta.deletedFileRetentionDuration' = '7 days' -- Deleted file retention
)
AS SELECT ...;
```

---

## Refresh Scheduling (Materialized Views)

```sql
-- Near-real-time
CREATE OR REFRESH MATERIALIZED VIEW gold_live_metrics
REFRESH EVERY 5 MINUTES
AS SELECT ...;

-- Daily
CREATE OR REFRESH MATERIALIZED VIEW gold_daily_summary
REFRESH EVERY 1 DAY
AS SELECT ...;
```

---

## Table Name Resolution

| Level | Example | When to Use |
|-------|---------|-------------|
| Unqualified | `FROM bronze_orders` | Tables in same pipeline (recommended) |
| Schema-qualified | `FROM other_schema.orders` | Different schema, same catalog |
| Fully-qualified | `FROM other_catalog.schema.orders` | External catalogs |

**Best practice:** Use unqualified names for pipeline-internal tables.

### Multi-Schema Pattern (One Pipeline)

Write to multiple schemas from a single pipeline using fully qualified names:

```sql
-- bronze_orders.sql → writes to bronze schema
CREATE OR REFRESH STREAMING TABLE my_catalog.bronze.raw_orders
AS SELECT *, current_timestamp() AS _ingested_at
FROM STREAM read_files('/Volumes/my_catalog/raw/orders/', format => 'json');

-- silver_orders.sql → writes to silver schema, reads from bronze
CREATE OR REFRESH STREAMING TABLE my_catalog.silver.clean_orders
AS SELECT * FROM STREAM my_catalog.bronze.raw_orders
WHERE order_id IS NOT NULL;
```

---

## Pipeline Parameters

Reference configuration values in SQL:

```sql
-- In SQL, use ${variable_name} syntax
CREATE OR REFRESH STREAMING TABLE bronze_orders AS
SELECT * FROM STREAM read_files(
  '${input_path}/orders/',
  format => 'json'
);
```

Define in pipeline configuration (YAML):
```yaml
configuration:
  input_path: /Volumes/my_catalog/my_schema/raw
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Missing `STREAM` keyword | Use `FROM STREAM table_name` for streaming tables |
| Constraint syntax error | Use `CONSTRAINT name EXPECT (condition)` |
| Cluster key not working | Verify column exists, limit to 4 keys |
| Parameter not resolved | Check `${var}` syntax and pipeline configuration |
| Using legacy `LIVE` keyword | Use `CREATE OR REFRESH STREAMING TABLE` \| `MATERIALIZED VIEW`, not `CREATE LIVE TABLE` \| `STREAMING LIVE TABLE` |
| Using `input_file_name()` | Use `_metadata.file_path` |
