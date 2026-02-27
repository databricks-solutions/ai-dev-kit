---
name: stream-static-joins
description: Enrich streaming data with Delta dimension tables in real-time. Use when joining fast-moving streaming events with slowly-changing reference data (device dimensions, user profiles, product catalogs), implementing real-time data enrichment, or adding context to streaming events without state management overhead.
---

# Stream-Static Joins

Enrich streaming data with slowly-changing reference data stored in Delta tables. Stream-static joins are stateless and automatically refresh dimension data each microbatch.

## Quick Start

```python
from pyspark.sql.functions import col, from_json

# Streaming source (IoT events from Kafka)
iot_stream = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "iot-events")
    .load()
    .select(from_json(col("value").cast("string"), event_schema).alias("data"))
    .select("data.*")
)

# Static Delta dimension table (refreshes each microbatch)
device_dim = spark.table("device_dimensions")

# Enrich streaming data with left join (recommended)
enriched = iot_stream.join(
    device_dim,
    "device_id",
    "left"  # Preserves all streaming events
).select(
    iot_stream["*"],
    device_dim["device_type"],
    device_dim["location"],
    device_dim["manufacturer"],
    device_dim["updated_at"].alias("dim_updated_at")
)

# Write enriched data
query = (enriched
    .writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/enriched_events")
    .trigger(processingTime="30 seconds")
    .start("/delta/enriched_iot_events")
)
```

## Core Concepts

### Why Delta Tables Matter

Delta tables enable automatic version checking each microbatch:

```python
# Delta table: Version checked every microbatch
device_dim = spark.table("device_dimensions")  # Reads latest version automatically

# Non-Delta format: Read once at startup (truly static)
device_dim = spark.read.parquet("/path/to/devices")  # No refresh
```

**Key Insight**: Delta's versioning ensures each microbatch gets the latest dimension data without manual refresh.

### Join Types and Production Use

| Join Type | Behavior | Production Use |
|-----------|----------|----------------|
| **Left** | Preserves all stream events | ✅ Recommended - prevents data loss |
| **Inner** | Drops unmatched events | ⚠️ Risk of data loss - avoid in production |
| **Right** | Preserves all dimension rows | Rarely used |
| **Full** | Preserves both sides | Rarely used |

**Production Rule**: Always use left join to prevent dropping valid streaming events.

## Common Patterns

### Pattern 1: Basic Device Enrichment

Enrich IoT events with device metadata:

```python
# Streaming IoT events
iot_stream = (spark
    .readStream
    .format("kafka")
    .option("subscribe", "iot-events")
    .load()
    .select(from_json(col("value").cast("string"), event_schema).alias("data"))
    .select("data.*")
)

# Device dimension table
device_dim = spark.table("device_dimensions")

# Left join to preserve all events
enriched = iot_stream.join(
    device_dim,
    "device_id",
    "left"
).select(
    iot_stream["*"],
    device_dim["device_type"],
    device_dim["location"],
    device_dim["status"]
)

enriched.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/enriched") \
    .start("/delta/enriched_events")
```

### Pattern 2: Multi-Table Enrichment

Chain multiple dimension joins:

```python
# Multiple dimension tables
devices = spark.table("device_dimensions")
locations = spark.table("location_dimensions")
categories = spark.table("category_dimensions")

# Chain joins (each is stateless)
enriched = (iot_stream
    .join(devices, "device_id", "left")
    .join(locations, "location_id", "left")
    .join(categories, "category_id", "left")
    .select(
        iot_stream["*"],
        devices["device_type"],
        devices["manufacturer"],
        locations["region"],
        locations["country"],
        categories["category_name"]
    )
)

# Each join refreshes independently each microbatch
```

### Pattern 3: Broadcast Hash Join Optimization

Optimize joins by ensuring broadcast:

```python
from pyspark.sql.functions import broadcast

# Option 1: Select only needed columns
small_dim = device_dim.select("device_id", "device_type", "location")

# Option 2: Filter to active records
active_dim = device_dim.filter(col("status") == "active")

# Option 3: Force broadcast hint
enriched = iot_stream.join(
    broadcast(active_dim),
    "device_id",
    "left"
)

# Verify in Spark UI: Look for "BroadcastHashJoin" in query plan
```

### Pattern 4: Audit Dimension Freshness

Track how fresh dimension data is:

```python
from pyspark.sql.functions import unix_timestamp, current_timestamp

enriched = (iot_stream
    .join(device_dim, "device_id", "left")
    .withColumn(
        "dim_lag_seconds",
        unix_timestamp(current_timestamp()) - 
        unix_timestamp(col("dim_updated_at"))
    )
    .withColumn(
        "dim_fresh",
        col("dim_lag_seconds") < 3600  # Less than 1 hour old
    )
)

# Monitor: Alert if dim_lag_seconds > threshold
# Use for data quality checks
```

### Pattern 5: Time-Travel Dimension Lookup

Join with dimension as-of event time:

```python
from delta import DeltaTable

def enrich_with_time_travel(batch_df, batch_id):
    """Enrich with dimension version at event time"""
    from pyspark.sql.functions import max as spark_max
    
    # Get latest dimension version
    latest_version = DeltaTable.forName(spark, "device_dimensions") \
        .history() \
        .select(spark_max("version").alias("max_version")) \
        .first()[0]
    
    # Read dimension at specific version
    dim_at_version = (spark
        .read
        .format("delta")
        .option("versionAsOf", latest_version)
        .table("device_dimensions")
    )
    
    # Join with batch
    enriched = batch_df.join(dim_at_version, "device_id", "left")
    
    # Write
    (enriched
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "enrichment_job")
        .saveAsTable("enriched_events")
    )

iot_stream.writeStream \
    .foreachBatch(enrich_with_time_travel) \
    .option("checkpointLocation", "/checkpoints/enriched") \
    .start()
```

### Pattern 6: Backfill Missing Dimensions

Daily job to fix null dimensions from left join:

```python
# Daily batch job to backfill missing dimensions
spark.sql("""
    MERGE INTO enriched_events target
    USING device_dimensions source
    ON target.device_id = source.device_id
      AND target.device_type IS NULL
    WHEN MATCHED THEN 
        UPDATE SET 
            device_type = source.device_type,
            location = source.location,
            manufacturer = source.manufacturer,
            dim_updated_at = source.updated_at
""")

# Run after dimension table updates
# Fixes events that arrived before dimension was available
```

### Pattern 7: Dimension Change Detection

Stream that reacts to dimension changes:

```python
def update_reference_cache(batch_df, batch_id):
    """Update in-memory cache when dimension changes"""
    # Dimension table changed
    # Update application cache or notify downstream systems
    pass

# Stream dimension table changes
dim_changes = (spark
    .readStream
    .format("delta")
    .table("device_dimensions")
    .writeStream
    .foreachBatch(update_reference_cache)
    .option("checkpointLocation", "/checkpoints/dim_changes")
    .start()
)
```

## Performance Optimization

### Checklist

- [ ] Dimension table < 100MB for broadcast (or increase threshold)
- [ ] Select only needed columns before join
- [ ] Filter dimension to active records only
- [ ] Verify "BroadcastHashJoin" in query plan
- [ ] Partition size 100-200MB in memory
- [ ] Use same region for compute and storage

### Configuration

```python
# Increase broadcast threshold if dimension is larger
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "1g")

# Control partition size
spark.conf.set("spark.sql.shuffle.partitions", "200")

# Optimize dimension table reads
spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")
spark.conf.set("spark.databricks.delta.autoCompact.enabled", "true")
```

### Reduce Dimension Size

```python
# Before join: Select only needed columns
small_dim = device_dim.select(
    "device_id",
    "device_type",
    "location",
    "status"
)

# Filter to active records
active_dim = small_dim.filter(col("status") == "active")

# Join with smaller dimension
enriched = iot_stream.join(active_dim, "device_id", "left")
```

## Monitoring

### Key Metrics

```python
# Null rate (left join quality)
spark.sql("""
    SELECT 
        date_trunc('hour', timestamp) as hour,
        count(*) as total_events,
        count(device_type) as matched_events,
        count(*) - count(device_type) as unmatched_events,
        (count(*) - count(device_type)) * 100.0 / count(*) as null_rate_pct
    FROM enriched_events
    GROUP BY 1
    ORDER BY 1 DESC
""")

# Dimension freshness
spark.sql("""
    SELECT 
        date_trunc('hour', timestamp) as hour,
        avg(dim_lag_seconds) as avg_lag_seconds,
        max(dim_lag_seconds) as max_lag_seconds,
        count(*) as events_with_dim
    FROM enriched_events
    WHERE dim_updated_at IS NOT NULL
    GROUP BY 1
    ORDER BY 1 DESC
""")
```

### Programmatic Monitoring

```python
# Monitor stream health
for stream in spark.streams.active:
    status = stream.status
    progress = stream.lastProgress
    
    if progress:
        print(f"Stream: {stream.name}")
        print(f"Input rate: {progress.get('inputRowsPerSecond', 0)} rows/sec")
        print(f"Processing rate: {progress.get('processedRowsPerSecond', 0)} rows/sec")
        print(f"Batch duration: {progress.get('durationMs', {}).get('triggerExecution', 0)} ms")
```

### Spark UI Checks

- **Streaming Tab**: Input rate vs processing rate (processing must exceed input)
- **SQL Tab**: Look for "BroadcastHashJoin" (not "SortMergeJoin")
- **Jobs Tab**: Check for shuffle operations (should be minimal)
- **Stages Tab**: Verify partition sizes (100-200MB target)

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **Data loss** | Inner join dropping unmatched events | Switch to left join |
| **Slow joins** | Shuffle join instead of broadcast | Reduce dimension size; force broadcast |
| **Stale data** | Non-Delta format | Convert dimension table to Delta |
| **Memory issues** | Large dimension table | Filter before join; increase broadcast threshold |
| **Skewed joins** | Hot keys in dimension | Salt the join key or partition dimension table |
| **High null rate** | Dimension updates lagging | Monitor dimension freshness; backfill job |

## Production Best Practices

### Always Use Left Join

```python
# WRONG: Inner join loses data
enriched = iot_stream.join(device_dim, "device_id", "inner")

# CORRECT: Left join preserves all events
enriched = iot_stream.join(device_dim, "device_id", "left")

# Why? New devices may send data before dimension table is updated
# Left join preserves events; backfill dimensions later
```

### Handle Null Dimensions

```python
# Add null handling in transformations
enriched = (iot_stream
    .join(device_dim, "device_id", "left")
    .withColumn(
        "device_type",
        coalesce(col("device_type"), lit("UNKNOWN"))
    )
    .withColumn(
        "location",
        coalesce(col("location"), lit("UNKNOWN"))
    )
)

# Or flag for manual review
enriched = enriched.withColumn(
    "needs_review",
    col("device_type").isNull()
)
```

### Idempotent Writes

```python
def idempotent_write(batch_df, batch_id):
    """Write with transaction version for idempotency"""
    (batch_df
        .write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "enrichment_job")
        .saveAsTable("enriched_events")
    )

enriched.writeStream \
    .foreachBatch(idempotent_write) \
    .option("checkpointLocation", "/checkpoints/enriched") \
    .start()
```

## Production Checklist

- [ ] Left join used (not inner join)
- [ ] Dimension table is Delta format
- [ ] Broadcast hash join verified in query plan
- [ ] Dimension size optimized (< 100MB or threshold increased)
- [ ] Null rate monitored and alerts configured
- [ ] Dimension freshness tracked
- [ ] Backfill job scheduled for missing dimensions
- [ ] Checkpoint location is unique per query
- [ ] Idempotent writes configured (txnVersion/txnAppId)
- [ ] Performance metrics tracked (input rate, batch duration)

## Expert Tips

### Delta Version Checking

Delta tables automatically refresh each microbatch by checking the latest version:

```python
# Each microbatch:
# 1. Spark checks Delta table version
# 2. Reads latest version if changed
# 3. Uses cached version if unchanged
# 4. No manual refresh needed

# This is why Delta tables work better than Parquet for dimensions
# Parquet: Read once at startup (truly static)
# Delta: Version checked each microbatch (semi-static)
```

### Broadcast Join Verification

Always verify broadcast joins in production:

```python
# Check query plan
enriched.explain(extended=True)

# Look for:
# - BroadcastHashJoin ✅ (fast, no shuffle)
# - SortMergeJoin ⚠️ (slower, requires shuffle)

# If seeing SortMergeJoin:
# 1. Reduce dimension size (select columns, filter rows)
# 2. Increase broadcast threshold
# 3. Force broadcast hint
```

### Dimension Table Optimization

Optimize dimension tables for streaming joins:

```python
# 1. Use Z-order or liquid clustering on join key
spark.sql("""
    OPTIMIZE device_dimensions
    ZORDER BY (device_id)
""")

# 2. Keep dimension tables small (< 100MB ideal)
# 3. Use Delta for automatic version checking
# 4. Partition by frequently filtered columns
```

## Related Skills

- `stream-stream-joins` - Join two streaming sources with state management
- `kafka-to-delta` - Kafka ingestion patterns
- `write-multiple-tables` - Fan-out patterns for multiple sinks
- `checkpoint-best-practices` - Checkpoint configuration and management
