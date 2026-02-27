---
name: stream-stream-joins
description: Join two streaming sources in real-time with event-time semantics, watermarks, and state management. Use when correlating events from different streams (orders with payments, clicks with conversions, sensor readings), handling late-arriving data, or implementing windowed aggregations across multiple streams.
---

# Stream-Stream Joins

Join two streaming sources in real-time to correlate events that arrive at different times and speeds. Stream-stream joins require watermarks to manage state and handle late-arriving data.

## Quick Start

```python
from pyspark.sql.functions import expr, from_json, col
from pyspark.sql.types import StructType

# Read two streaming sources
orders = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "orders")
    .load()
    .select(from_json(col("value").cast("string"), order_schema).alias("data"))
    .select("data.*")
    .withWatermark("order_time", "10 minutes")
)

payments = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "payments")
    .load()
    .select(from_json(col("value").cast("string"), payment_schema).alias("data"))
    .select("data.*")
    .withWatermark("payment_time", "10 minutes")
)

# Join with time bounds
matched = (orders
    .join(
        payments,
        expr("""
            orders.order_id = payments.order_id AND
            payments.payment_time >= orders.order_time - interval 5 minutes AND
            payments.payment_time <= orders.order_time + interval 10 minutes
        """),
        "inner"
    )
)

# Write results
query = (matched
    .writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/orders_payments")
    .trigger(processingTime="30 seconds")
    .start("/delta/order_payments")
)
```

## Core Concepts

### Why Stream-Stream Joins Need Watermarks

Stream-stream joins are stateful: both sides must buffer events until matches are found or state expires. Watermarks define when state can be safely cleaned up.

```python
# Watermark = latest_event_time - delay_threshold
.withWatermark("event_time", "10 minutes")

# Events with timestamp < watermark are considered "too late"
# State for late events is automatically cleaned up
```

### Join Types and Behavior

| Join Type | Matches | Late Events | Use Case |
|-----------|---------|-------------|----------|
| **Inner** | Both sides | May still match if other side hasn't expired | Correlation analysis |
| **Left Outer** | All left + matched right | Dropped from left side after watermark | Enrichment with optional data |
| **Right Outer** | All right + matched left | Dropped from right side after watermark | Rarely used |
| **Full Outer** | All events from both | Dropped after watermark | Complete picture |

## Common Patterns

### Pattern 1: Order-Payment Matching

Match orders with payments within a time window:

```python
orders = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "orders")
    .load()
    .select(from_json(col("value").cast("string"), order_schema).alias("data"))
    .select("data.*")
    .withWatermark("order_time", "10 minutes")
)

payments = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "payments")
    .load()
    .select(from_json(col("value").cast("string"), payment_schema).alias("data"))
    .select("data.*")
    .withWatermark("payment_time", "10 minutes")
)

# Match payments within 10 minutes of order
matched = (orders
    .join(
        payments,
        expr("""
            orders.order_id = payments.order_id AND
            payments.payment_time >= orders.order_time - interval 5 minutes AND
            payments.payment_time <= orders.order_time + interval 10 minutes
        """),
        "leftOuter"  # Include orders without payments
    )
    .withColumn("matched", col("payment_id").isNotNull())
)

matched.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/orders_payments") \
    .start("/delta/order_payments")
```

### Pattern 2: Click-Conversion Attribution

Attribute conversions to clicks within a time window:

```python
impressions = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "impressions")
    .load()
    .select(from_json(col("value").cast("string"), impression_schema).alias("data"))
    .select("data.*")
    .withWatermark("impression_time", "1 hour")
)

conversions = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "conversions")
    .load()
    .select(from_json(col("value").cast("string"), conversion_schema).alias("data"))
    .select("data.*")
    .withWatermark("conversion_time", "1 hour")
)

# Attribute conversion to last impression within 24 hours
attributed = (impressions
    .join(
        conversions,
        expr("""
            impressions.user_id = conversions.user_id AND
            impressions.ad_id = conversions.ad_id AND
            conversions.conversion_time >= impressions.impression_time AND
            conversions.conversion_time <= impressions.impression_time + interval 24 hours
        """),
        "inner"
    )
    .withColumn("attribution_window_hours", 
                (col("conversion_time").cast("long") - col("impression_time").cast("long")) / 3600)
)

attributed.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/attribution") \
    .start("/delta/attributed_conversions")
```

### Pattern 3: Sessionization Across Streams

Group events from multiple streams into sessions:

```python
from pyspark.sql.functions import session_window

pageviews = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "pageviews")
    .load()
    .select(from_json(col("value").cast("string"), pageview_schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "30 minutes")
)

clicks = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "clicks")
    .load()
    .select(from_json(col("value").cast("string"), click_schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "30 minutes")
)

# Create session windows for each stream
pageview_sessions = (pageviews
    .groupBy(
        col("user_id"),
        session_window(col("event_time"), "10 minutes")
    )
    .agg(
        count("*").alias("pageview_count"),
        min("event_time").alias("session_start"),
        max("event_time").alias("session_end")
    )
)

click_sessions = (clicks
    .groupBy(
        col("user_id"),
        session_window(col("event_time"), "10 minutes")
    )
    .agg(
        count("*").alias("click_count"),
        min("event_time").alias("session_start"),
        max("event_time").alias("session_end")
    )
)

# Join sessions
joined_sessions = (pageview_sessions
    .join(
        click_sessions,
        ["user_id", "session_window"],
        "outer"
    )
    .withColumn("total_events", 
                coalesce(col("pageview_count"), lit(0)) + 
                coalesce(col("click_count"), lit(0)))
)

joined_sessions.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/sessions") \
    .start("/delta/user_sessions")
```

### Pattern 4: Late Data Handling with Dead Letter Queue

Route late-arriving events to a separate table:

```python
def write_with_late_data_handling(batch_df, batch_id):
    """Separate on-time and late data"""
    from pyspark.sql.functions import current_timestamp, unix_timestamp
    
    # Calculate delay
    processed = batch_df.withColumn(
        "processing_delay_seconds",
        unix_timestamp(current_timestamp()) - unix_timestamp(col("event_time"))
    )
    
    # On-time data (within watermark)
    on_time = processed.filter(col("processing_delay_seconds") < 600)  # 10 minutes
    
    # Late data
    late = processed.filter(col("processing_delay_seconds") >= 600)
    
    # Write on-time data
    (on_time
        .drop("processing_delay_seconds")
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "stream_join_job")
        .saveAsTable("matched_events")
    )
    
    # Write late data to DLQ
    if late.count() > 0:
        (late
            .withColumn("dlq_reason", lit("LATE_ARRIVAL"))
            .withColumn("dlq_timestamp", current_timestamp())
            .write
            .format("delta")
            .mode("append")
            .saveAsTable("late_data_dlq")
        )

matched.writeStream \
    .foreachBatch(write_with_late_data_handling) \
    .option("checkpointLocation", "/checkpoints/orders_payments") \
    .start()
```

## State Management

### Configure RocksDB for Large State

For state stores exceeding memory capacity, use RocksDB:

```python
# Enable RocksDB state store provider
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)

# State is stored on disk, reducing memory pressure
# Recommended for: High cardinality keys, long watermark durations
```

### Monitor State Size

```python
# Read state store directly
state_df = (spark
    .read
    .format("statestore")
    .load("/checkpoints/orders_payments/state")
)

# Check partition balance
state_df.groupBy("partitionId").count().orderBy(desc("count")).show()

# Check state size
state_metadata = (spark
    .read
    .format("state-metadata")
    .load("/checkpoints/orders_payments")
)
state_metadata.show()

# Programmatic monitoring
for stream in spark.streams.active:
    progress = stream.lastProgress
    if progress and "stateOperators" in progress:
        for op in progress["stateOperators"]:
            print(f"State rows: {op.get('numRowsTotal', 0)}")
            print(f"State memory: {op.get('memoryUsedBytes', 0)}")
```

### Control State Growth

```python
# 1. Use watermarks (automatic cleanup)
.withWatermark("event_time", "10 minutes")  # State expires after watermark

# 2. Reduce key cardinality
# Bad: user_id (millions of distinct values)
# Good: session_id (expires naturally)

# 3. Set reasonable time bounds
# Bad: unbounded time range
expr("s2.ts >= s1.ts")  # State grows forever!

# Good: bounded time range
expr("s2.ts BETWEEN s1.ts AND s1.ts + interval 1 hour")
```

## Watermark Configuration

### Choosing Watermark Duration

Balance between latency and completeness:

```python
# Rule of thumb: 2-3x the expected delay
# If 99th percentile delay is 5 minutes → use 10-15 minute watermark

# High tolerance (more matches, larger state)
.withWatermark("event_time", "2 hours")

# Low tolerance (faster results, smaller state)
.withWatermark("event_time", "10 minutes")
```

### Multiple Watermarks

When joining streams with different latencies:

```python
# Stream 1: Fast, low latency
stream1 = stream1.withWatermark("ts", "5 minutes")

# Stream 2: Slow, high latency
stream2 = stream2.withWatermark("ts", "15 minutes")

# Effective watermark = max(5, 15) = 15 minutes
joined = stream1.join(stream2, join_condition, "inner")
```

## Production Best Practices

### Idempotent Writes

Ensure exactly-once semantics:

```python
def idempotent_write(batch_df, batch_id):
    """Write with transaction version for idempotency"""
    (batch_df
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "stream_join_job")
        .saveAsTable("matched_events")
    )

matched.writeStream \
    .foreachBatch(idempotent_write) \
    .option("checkpointLocation", "/checkpoints/orders_payments") \
    .start()
```

### Multi-Stream Joins (3+ Streams)

Chain joins carefully - each adds state overhead:

```python
# Step 1: Join streams A and B
ab = (stream_a
    .withWatermark("ts", "10 minutes")
    .join(
        stream_b.withWatermark("ts", "10 minutes"),
        expr("a.key = b.key AND b.ts BETWEEN a.ts - interval 5 min AND a.ts + interval 5 min"),
        "inner"
    )
)

# Step 2: Join result with stream C
abc = ab.join(
    stream_c.withWatermark("ts", "10 minutes"),
    expr("ab.key = c.key AND c.ts BETWEEN ab.ts - interval 5 min AND ab.ts + interval 5 min"),
    "inner"
)

# Note: Result watermark comes from left side (ab)
```

### Performance Tuning

```python
# State store batch retention
spark.conf.set("spark.sql.streaming.stateStore.minBatchesToRetain", "2")

# State maintenance interval
spark.conf.set("spark.sql.streaming.stateStore.maintenanceInterval", "5m")

# Shuffle partitions (match worker cores)
spark.conf.set("spark.sql.shuffle.partitions", "200")
```

## Monitoring

### Key Metrics

```python
# Programmatic monitoring
for stream in spark.streams.active:
    status = stream.status
    progress = stream.lastProgress
    
    if progress:
        print(f"Stream: {stream.name}")
        print(f"Input rate: {progress.get('inputRowsPerSecond', 0)} rows/sec")
        print(f"Processing rate: {progress.get('processedRowsPerSecond', 0)} rows/sec")
        
        # State metrics
        if "stateOperators" in progress:
            for op in progress["stateOperators"]:
                print(f"State rows: {op.get('numRowsTotal', 0)}")
                print(f"State memory: {op.get('memoryUsedBytes', 0)}")
        
        # Watermark
        if "eventTime" in progress:
            print(f"Watermark: {progress['eventTime'].get('watermark', 'N/A')}")
```

### Spark UI Checks

- **Streaming Tab**: Input rate vs processing rate (processing must exceed input)
- **State Operators**: State size and memory usage
- **Watermark**: Current watermark timestamp
- **Batch Duration**: Should be < trigger interval

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **State too large** | High cardinality keys or long watermark | Reduce key space; decrease watermark duration |
| **Late events dropped** | Watermark too aggressive | Increase watermark delay |
| **No matches** | Time condition wrong | Check time bounds and units (minutes vs hours) |
| **OOM errors** | State explosion | Use RocksDB; increase memory; reduce watermark |
| **Missing watermarks** | State grows forever | Always define watermarks on both sides |
| **Unbounded state** | Open-ended time range | Use bounded time range in join condition |

## Production Checklist

- [ ] Watermark configured on both streaming sources
- [ ] Join condition includes explicit time bounds
- [ ] State store provider set (RocksDB for large state)
- [ ] State size monitored and alerts configured
- [ ] Late data handling strategy defined (DLQ or tolerance)
- [ ] Output mode is "append" (required for streaming joins)
- [ ] Checkpoint location is unique per query
- [ ] Idempotent writes configured (txnVersion/txnAppId)
- [ ] Time zones normalized across streams
- [ ] Performance metrics tracked (input rate, state size, watermark lag)

## Expert Tips

### Event Time vs Processing Time

Always use event time for stream-stream joins:

```python
# ✅ CORRECT: Event time (deterministic)
.withWatermark("event_time", "10 minutes")

# ❌ WRONG: Processing time (non-deterministic)
# Processing time varies based on system load
# Results are not reproducible
```

### Watermark Semantics Deep Dive

Understanding watermark behavior:

```python
# Watermark = max_event_time - delay_threshold
# Example: max_event_time = 10:15, delay = 10 min
# Watermark = 10:05

# Events with timestamp < 10:05 are "too late"
# - Inner join: May still match if other side hasn't expired
# - Outer join: Dropped from outer side after watermark passes

# Effective watermark = max(left_watermark, right_watermark)
```

### State Store Backend Selection

Choose the right state store backend:

```python
# Default: In-memory (fast but limited)
# Use for: Small state (< 10GB), low cardinality keys

# RocksDB: Disk-backed (slower but scalable)
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)
# Use for: Large state (> 10GB), high cardinality keys

# Monitor state size to decide when to switch
```

### Join Condition Best Practices

Always include explicit time bounds:

```python
# ❌ BAD: Unbounded (state grows forever)
expr("s1.key = s2.key AND s2.ts >= s1.ts")

# ✅ GOOD: Bounded (state bounded by watermark)
expr("""
    s1.key = s2.key AND
    s2.ts >= s1.ts - interval 5 minutes AND
    s2.ts <= s1.ts + interval 10 minutes
""")

# Why? Bounded ranges allow state cleanup
# Unbounded ranges cause state to grow indefinitely
```

## Related Skills

- `stream-static-joins` - Enrich streams with Delta dimension tables
- `kafka-to-delta` - Kafka ingestion patterns
- `watermark-configuration` - Deep dive on watermark semantics
- `state-store-management` - State store optimization and monitoring
