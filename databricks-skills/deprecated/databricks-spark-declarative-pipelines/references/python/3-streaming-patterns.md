# Python Streaming Patterns

Streaming-specific patterns including deduplication, windowed aggregations, late-arriving data handling, and stateful operations.

**Import**: `from pyspark import pipelines as dp`

---

## Deduplication Patterns

### By Key

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

@dp.table(name="silver_events_dedup", cluster_by=["event_date"])
def silver_events_dedup():
    """Deduplicate by event_id, keeping first occurrence."""
    window_spec = Window.partitionBy("event_id").orderBy("event_timestamp")
    return (
        spark.readStream.table("bronze_events")
        .withColumn("rn", F.row_number().over(window_spec))
        .filter(F.col("rn") == 1)
        .drop("rn")
    )
```

### With Time Window

Deduplicate within time window to handle late arrivals:

```python
@dp.table(name="silver_events_dedup")
def silver_events_dedup():
    return (
        spark.readStream.table("bronze_events")
        .groupBy(
            "event_id", "user_id", "event_type", "event_timestamp",
            F.window("event_timestamp", "1 hour")
        )
        .agg(F.min("_ingested_at").alias("first_seen_at"))
    )
```

### Composite Key

```python
@dp.table(name="silver_transactions_dedup")
def silver_transactions_dedup():
    return (
        spark.readStream.table("bronze_transactions")
        .groupBy("transaction_id", "customer_id", "amount", "transaction_timestamp")
        .agg(F.min("_ingested_at").alias("_ingested_at"))
    )
```

---

## Windowed Aggregations

### Tumbling Windows

Non-overlapping fixed-size windows:

```python
@dp.table(name="silver_sensor_5min", cluster_by=["sensor_id"])
def silver_sensor_5min():
    """5-minute tumbling window aggregations."""
    return (
        spark.readStream.table("bronze_sensor_events")
        .groupBy(
            F.col("sensor_id"),
            F.window("event_timestamp", "5 minutes")
        )
        .agg(
            F.avg("temperature").alias("avg_temperature"),
            F.min("temperature").alias("min_temperature"),
            F.max("temperature").alias("max_temperature"),
            F.count("*").alias("event_count")
        )
    )
```

### Multiple Window Sizes

```python
# 1-minute for real-time monitoring
@dp.table(name="gold_sensor_1min")
def gold_sensor_1min():
    return (
        spark.readStream.table("silver_sensor_data")
        .groupBy(
            "sensor_id",
            F.window("event_timestamp", "1 minute")
        )
        .agg(
            F.avg("value").alias("avg_value"),
            F.count("*").alias("event_count")
        )
        .select(
            "sensor_id",
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "avg_value",
            "event_count"
        )
    )

# 1-hour for trend analysis
@dp.table(name="gold_sensor_1hour")
def gold_sensor_1hour():
    return (
        spark.readStream.table("silver_sensor_data")
        .groupBy(
            "sensor_id",
            F.window("event_timestamp", "1 hour")
        )
        .agg(
            F.avg("value").alias("avg_value"),
            F.stddev("value").alias("stddev_value")
        )
    )
```

### Session Windows

Group events into sessions based on inactivity gaps:

```python
@dp.table(name="silver_user_sessions")
def silver_user_sessions():
    """Group user events into sessions with 30-minute inactivity timeout."""
    return (
        spark.readStream.table("bronze_user_events")
        .groupBy(
            F.col("user_id"),
            F.session_window("event_timestamp", "30 minutes")
        )
        .agg(
            F.min("event_timestamp").alias("session_start"),
            F.max("event_timestamp").alias("session_end"),
            F.count("*").alias("event_count"),
            F.collect_list("event_type").alias("event_sequence")
        )
    )
```

---

## Late-Arriving Data

### Event-Time vs Processing-Time

Always use event timestamp for business logic:

```python
@dp.table(name="gold_daily_orders")
def gold_daily_orders():
    return (
        spark.readStream.table("silver_orders")
        .groupBy(F.to_date("order_timestamp").alias("order_date"))  # Event time
        .agg(
            F.count("*").alias("order_count"),
            F.sum("amount").alias("total_amount")
        )
    )
```

**Keep processing time for debugging:**
```python
.select(
    "order_id", "order_timestamp",  # Event time (business logic)
    "customer_id", "amount",
    "_ingested_at"                  # Processing time (debugging only)
)
```

---

## Joins

### Stream-to-Static Joins

Enrich streaming data with dimension tables:

```python
@dp.table(name="silver_sales_enriched", cluster_by=["product_id"])
def silver_sales_enriched():
    """Enrich streaming sales with static product dimension."""
    sales = spark.readStream.table("bronze_sales")
    products = spark.read.table("dim_products")
    return (
        sales.join(products, "product_id", "left")
        .select(
            "sale_id", "product_id", "quantity", "sale_timestamp",
            "product_name", "category", "price"
        )
        .withColumn("total_amount", F.col("quantity") * F.col("price"))
    )
```

### Stream-to-Stream Joins

```python
@dp.table(name="silver_orders_with_payments")
def silver_orders_with_payments():
    """Join orders with payments within 1-hour window."""
    orders = spark.readStream.table("bronze_orders")
    payments = spark.readStream.table("bronze_payments")

    return (
        orders.join(
            payments,
            (orders.order_id == payments.order_id) &
            (payments.payment_timestamp >= orders.order_timestamp) &
            (payments.payment_timestamp <= orders.order_timestamp + F.expr("INTERVAL 1 HOUR")),
            "inner"
        )
        .select(
            orders.order_id,
            orders.customer_id,
            orders.order_timestamp,
            orders.amount.alias("order_amount"),
            payments.payment_id,
            payments.payment_timestamp,
            payments.amount.alias("payment_amount")
        )
    )
```

**Important:** Use time bounds in join condition to limit state retention.

---

## Incremental Aggregations

### Running Totals

```python
@dp.table(name="silver_customer_running_totals")
def silver_customer_running_totals():
    return (
        spark.readStream.table("bronze_transactions")
        .groupBy("customer_id")
        .agg(
            F.sum("amount").alias("total_spent"),
            F.count("*").alias("transaction_count"),
            F.max("transaction_timestamp").alias("last_transaction_at")
        )
    )
```

---

## Anomaly Detection

### Real-Time Outlier Detection

```python
@dp.table(name="silver_sensor_with_anomalies")
def silver_sensor_with_anomalies():
    window_spec = Window.partitionBy("sensor_id").orderBy("event_timestamp").rowsBetween(-100, 0)

    return (
        spark.readStream.table("bronze_sensor_events")
        .withColumn("rolling_avg", F.avg("temperature").over(window_spec))
        .withColumn("rolling_stddev", F.stddev("temperature").over(window_spec))
        .withColumn("anomaly_flag",
            F.when(F.col("temperature") > F.col("rolling_avg") + (3 * F.col("rolling_stddev")), "HIGH_OUTLIER")
            .when(F.col("temperature") < F.col("rolling_avg") - (3 * F.col("rolling_stddev")), "LOW_OUTLIER")
            .otherwise("NORMAL")
        )
    )

@dp.table(name="silver_sensor_anomalies")
def silver_sensor_anomalies():
    return (
        spark.readStream.table("silver_sensor_with_anomalies")
        .filter(F.col("anomaly_flag").isin("HIGH_OUTLIER", "LOW_OUTLIER"))
    )
```

### Threshold-Based Filtering

```python
@dp.table(name="silver_high_value_transactions")
def silver_high_value_transactions():
    return (
        spark.readStream.table("bronze_transactions")
        .filter(F.col("amount") > 10000)
    )
```

---

## Monitoring Lag

```python
@dp.table(name="monitoring_lag")
def monitoring_lag():
    return (
        spark.readStream.table("bronze_kafka_events")
        .groupBy(F.window("kafka_timestamp", "1 minute"))
        .agg(
            F.lit("kafka_events").alias("source"),
            F.max("kafka_timestamp").alias("max_event_timestamp"),
            F.current_timestamp().alias("processing_timestamp")
        )
        .withColumn("lag_seconds",
            F.unix_timestamp("processing_timestamp") - F.unix_timestamp("max_event_timestamp")
        )
    )
```

---

## Best Practices

### 1. Use Event Timestamps

```python
# Correct: Event timestamp for logic
.groupBy(F.date_trunc("hour", "event_timestamp"))

# Avoid: Processing timestamp
# .groupBy(F.date_trunc("hour", "_ingested_at"))
```

### 2. Window Size Selection

- **1-5 minutes**: Real-time monitoring
- **15-60 minutes**: Operational dashboards
- **1-24 hours**: Analytical reports

### 3. State Management

Higher cardinality = more state:

```python
# High state: 1M users x 10K products x 100M sessions
.groupBy("user_id", "product_id", "session_id")

# Lower state: 1M users x 100 categories x days
.groupBy("user_id", "product_category", F.to_date("event_time"))
```

Use time windows to bound state retention.

### 4. Deduplicate Early

Apply at bronze → silver transition:

```python
# Bronze: Accept duplicates
@dp.table(name="bronze_events")
def bronze_events():
    return spark.readStream.format("cloudFiles")...

# Silver: Deduplicate immediately
@dp.table(name="silver_events")
def silver_events():
    return spark.readStream.table("bronze_events").dropDuplicates(["event_id"])

# Gold: Work with clean data
@dp.table(name="gold_metrics")
def gold_metrics():
    return spark.readStream.table("silver_events")...
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
