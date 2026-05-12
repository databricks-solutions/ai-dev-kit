---
name: stateful-operations
description: Configure watermarks and manage state stores for Spark Structured Streaming stateful operations. Use when setting up stateful operations, tuning watermark duration, handling late-arriving data, configuring RocksDB for large state, monitoring state store size, or optimizing state performance.
---

# Stateful Operations: Watermarks and State Stores

Configure watermarks to handle late-arriving data and manage state stores for stateful streaming operations. Watermarks control state cleanup, while state stores handle the storage and retrieval of stateful data.

## Quick Start

```python
# Enable RocksDB for large state stores
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)

# Stateful operation with watermark
df = (spark.readStream
    .format("kafka")
    .option("subscribe", "events")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "10 minutes")  # Late data threshold + state cleanup
    .dropDuplicates(["event_id"])  # Stateful operation
)

# Watermark = latest_event_time - 10 minutes
# State automatically expires after watermark duration
```

## Watermark Configuration

### How Watermarks Work

```python
# Watermark = latest_event_time - delay_threshold
.withWatermark("event_time", "10 minutes")

# Events with timestamp < watermark are considered "too late"
# State for late events is automatically cleaned up
# Late events may be dropped (outer joins) or processed (inner joins)
```

### Watermark Duration Selection

| Watermark Setting | Effect | Use Case |
|-------------------|--------|----------|
| `"10 minutes"` | Moderate latency | General streaming |
| `"1 hour"` | High completeness | Financial transactions |
| `"5 minutes"` | Low latency | Real-time analytics |
| `"24 hours"` | Batch-like | Backfill scenarios |

**Rule of thumb**: Start with 2-3× your p95 latency. Monitor late data rate and adjust.

### Watermark and State Size

```python
# Watermark directly affects state store size
# State kept for watermark duration + processing time

# Example calculation:
# - 10 minute watermark
# - 1M events/min
# - State size = ~10M keys × key_size

# Reduce watermark to reduce state size
.withWatermark("event_time", "5 minutes")  # Smaller state

# State automatically expires after watermark duration
# No manual cleanup needed
```

## State Store Configuration

### Enable RocksDB

Use RocksDB for state stores exceeding memory capacity:

```python
# Enable RocksDB state store provider
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)

# Benefits:
# - State stored on disk, reducing memory pressure
# - Recommended for: High cardinality keys, long watermark durations
# - Better performance for large state stores
```

### State Store Configuration

```python
# State store batch retention
spark.conf.set("spark.sql.streaming.stateStore.minBatchesToRetain", "2")

# State maintenance interval
spark.conf.set("spark.sql.streaming.stateStore.maintenanceInterval", "5m")

# State store location (default: checkpoint/state)
# Automatically managed by Spark
```

## Common Patterns

### Pattern 1: Basic Stateful Operation with Watermark

```python
# Watermark for deduplication
df = (spark.readStream
    .format("kafka")
    .option("subscribe", "events")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
    .withWatermark("event_time", "10 minutes")
    .dropDuplicates(["event_id"])
)

# State expires after watermark duration
# Prevents infinite state growth
```

### Pattern 2: Join-Specific Watermark Tuning

Different watermarks for streams with different latencies:

```python
# Fast source: 5 minute watermark
impressions = (spark.readStream
    .format("kafka")
    .option("subscribe", "impressions")
    .load()
    .select(from_json(col("value").cast("string"), impression_schema).alias("data"))
    .select("data.*")
    .withWatermark("impression_time", "5 minutes")
)

# Slower source: 15 minute watermark
clicks = (spark.readStream
    .format("kafka")
    .option("subscribe", "clicks")
    .load()
    .select(from_json(col("value").cast("string"), click_schema).alias("data"))
    .select("data.*")
    .withWatermark("click_time", "15 minutes")
)

# Effective watermark = max(5, 15) = 15 minutes
joined = impressions.join(
    clicks,
    expr("""
        impressions.ad_id = clicks.ad_id AND
        clicks.click_time BETWEEN impressions.impression_time AND
                                impressions.impression_time + interval 1 hour
    """),
    "inner"
)
```

### Pattern 3: Windowed Aggregations with Watermark

```python
from pyspark.sql.functions import window, count, sum, max, current_timestamp

windowed = (df
    .withWatermark("event_time", "10 minutes")
    .groupBy(
        window(col("event_time"), "5 minutes"),
        col("user_id")
    )
    .agg(
        count("*").alias("event_count"),
        sum("value").alias("total_value"),
        max("event_time").alias("latest_event")
    )
    .withColumn("processing_time", current_timestamp())
)

# Use update mode for corrected results when late data arrives
windowed.writeStream \
    .outputMode("update") \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/windowed") \
    .start("/delta/windowed_metrics")
```

### Pattern 4: Monitor State Partition Balance

Check for state store skew:

```python
def check_state_balance(checkpoint_path):
    """Check state store partition balance"""
    state_df = spark.read.format("statestore").load(f"{checkpoint_path}/state")
    
    partition_counts = state_df.groupBy("partitionId").count().orderBy(desc("count"))
    partition_counts.show()
    
    # Calculate skew
    counts = [row['count'] for row in partition_counts.collect()]
    if counts:
        max_count = max(counts)
        min_count = min(counts)
        skew_ratio = max_count / min_count if min_count > 0 else float('inf')
        
        print(f"State skew ratio: {skew_ratio:.2f}")
        if skew_ratio > 10:
            print("WARNING: High state skew detected")
            return False
    return True
```

### Pattern 5: Monitor State Growth

```python
def monitor_state_growth(checkpoint_path):
    """Track state store growth"""
    state_df = spark.read.format("statestore").load(f"{checkpoint_path}/state")
    
    # Current state size
    total_rows = state_df.count()
    
    print(f"State rows: {total_rows}")
    
    # Check expiration
    from pyspark.sql.functions import current_timestamp, col
    expired = state_df.filter(col("expirationMs") < current_timestamp().cast("long") * 1000)
    expired_count = expired.count()
    
    print(f"Expired state rows: {expired_count}")
    print(f"Active state rows: {total_rows - expired_count}")
```

## State Size Control

### Use Watermarks

Watermarks automatically clean up expired state:

```python
# State expires after watermark duration
.withWatermark("event_time", "10 minutes")

# State size = f(watermark duration, key cardinality)
# 10 min watermark × 1M events/min = manageable
# 72 hour watermark × 1M events/min = very large
```

### Reduce Key Cardinality

```python
# Bad: High cardinality keys
.dropDuplicates(["user_id"])  # Millions of distinct values

# Good: Lower cardinality or expiring keys
.dropDuplicates(["session_id"])  # Sessions expire naturally
.dropDuplicates(["event_id", "date"])  # Partition by date reduces cardinality
```

## Monitoring

### Programmatic State Monitoring

```python
# Monitor state size programmatically
for stream in spark.streams.active:
    progress = stream.lastProgress
    
    if progress and "stateOperators" in progress:
        for op in progress["stateOperators"]:
            print(f"Operator: {op.get('operatorName', 'unknown')}")
            print(f"State rows: {op.get('numRowsTotal', 0)}")
            print(f"State memory: {op.get('memoryUsedBytes', 0)}")
            print(f"State on disk: {op.get('diskBytesUsed', 0)}")
```

### Track Late Data Rates

```python
# Monitor late data impact
late_data_stats = spark.sql("""
    SELECT 
        date_trunc('hour', event_time) as hour,
        COUNT(*) as total_events,
        SUM(CASE 
            WHEN unix_timestamp(processing_time) - unix_timestamp(event_time) > 600 
            THEN 1 ELSE 0 
        END) as late_events,
        AVG(unix_timestamp(processing_time) - unix_timestamp(event_time)) as avg_delay_seconds,
        MAX(unix_timestamp(processing_time) - unix_timestamp(event_time)) as max_delay_seconds
    FROM events
    WHERE processing_time >= current_timestamp() - interval 24 hours
    GROUP BY 1
    ORDER BY 1 DESC
""")
```

## Late Data Classification

| Delay | Category | Handling |
|-------|----------|----------|
| < Watermark | On-time | Normal processing |
| Watermark < delay < 2×Watermark | Late | Join with inner match; may still process |
| > 2×Watermark | Very late | DLQ for manual handling |

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **State store explosion** | Watermark too long | Reduce watermark; archive old state |
| **Late data dropped** | Watermark too short | Increase watermark; analyze latency patterns |
| **State too large** | High cardinality keys or long watermark | Reduce key cardinality; decrease watermark duration |
| **State partition skew** | Uneven key distribution | Ensure keys are evenly distributed; consider salting |
| **OOM errors** | State exceeds memory | Enable RocksDB; increase memory; reduce watermark |
| **State not expiring** | Watermark not configured | Add watermark to stateful operations |

## State Store Recovery

```python
# Scenario 1: State store corruption
# Solution: Delete state folder, restart stream
# State will rebuild from watermark

dbutils.fs.rm("/checkpoints/stream/state", recurse=True)

# Restart stream - state rebuilds automatically
# Note: May reprocess some data within watermark window

# Scenario 2: State store too large
# Solution: Reduce watermark duration
.withWatermark("event_time", "5 minutes")  # Reduced from 10 minutes

# Scenario 3: State partition imbalance
# Solution: Ensure keys are evenly distributed
# Consider salting keys if needed
```

## Production Best Practices

### Always Use Watermarks for Stateful Operations

```python
# REQUIRED: Watermark for stateful operations
df.withWatermark("event_time", "10 minutes").dropDuplicates(["id"])

# REQUIRED: Watermark for aggregations
df.withWatermark("event_time", "10 minutes").groupBy(...).agg(...)

# REQUIRED: Watermark for stream-stream joins
stream1.withWatermark("ts", "10 min").join(stream2.withWatermark("ts", "10 min"))
```

### Watermark Selection

```python
# Rule of thumb: 2-3× p95 latency
# Example: p95 latency = 5 minutes → watermark = 10-15 minutes

# Start conservative, adjust based on monitoring
.withWatermark("event_time", "10 minutes")  # Start here
# Monitor late data rate
# Increase if too many late events
# Decrease if state too large
```

### Use RocksDB for Large State

```python
# Enable RocksDB if state > memory capacity
# Typical threshold: > 100M keys or > 10GB state

spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)
```

## Production Checklist

- [ ] Watermark configured for all stateful operations
- [ ] Watermark duration matches latency requirements (2-3× p95)
- [ ] RocksDB enabled for large state stores
- [ ] State size monitored and alerts configured
- [ ] State partition balance checked regularly
- [ ] State growth tracked over time
- [ ] Late data monitoring configured
- [ ] Recovery procedure documented

## Related Skills

- `stream-stream-joins` - Late data in joins
- `checkpoint-best-practices` - Checkpoint and state recovery
