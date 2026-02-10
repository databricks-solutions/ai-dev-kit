---
name: "streaming-best-practices"
description: "Production-proven best practices for Spark Streaming: trigger intervals, partitioning, checkpoint management, and cluster configuration for reliable pipelines."
tags: ["spark-streaming", "best-practices", "production", "performance", "expert"]
---

# Streaming Best Practices Expert Pack

## Overview

A comprehensive checklist distilled from production experience. These practices should hold true in almost all scenarios.

**Source**: Canadian Data Guy — "Spark Streaming Best Practices"

## Beginner Checklist

### 1. Always Set a Trigger Interval

```python
# ✅ Good: Controls API costs and listing operations
stream.writeStream \
    .trigger(processingTime='5 seconds') \
    .start()

# ❌ Bad: No trigger means continuous microbatches
# Can cause excessive S3/ADLS listing costs
```

**Why**: Fast processing (<1 sec) repeats listing operations, causing unintended costs.

### 2. Use Auto Loader Notification Mode

```python
# Switch from file listing to event-based
spark.readStream \
    .format("cloudFiles") \
    .option("cloudFiles.useNotifications", "true") \
    .load("/path/to/data")
```

[Auto Loader File Notification Mode](https://docs.databricks.com/ingestion/auto-loader/file-notification-mode.html)

### 3. Disable S3 Versioning

```python
# ❌ Don't enable versioning on S3 buckets with Delta
# ✅ Delta has time travel — no need for S3 versioning
# Versioning adds significant latency at scale
```

### 4. Co-Locate Compute and Storage

```python
# ✅ Keep compute and storage in the same region
# Cross-region = latency + egress costs
```

### 5. Use ADLS Gen2 on Azure

```python
# ✅ ADLS Gen2 is optimized for big data analytics
# ❌ Regular blob storage = slower performance
```

### 6. Partition Strategy

```python
# ✅ Partition on low-cardinality columns: date, region, country
# ❌ Avoid high-cardinality: user_id, transaction_id

# Rule of thumb: < 100,000 partitions
# Example: 10 years × 365 days × 20 countries = 73,000 partitions ✅
```

### 7. Name Your Streaming Query

```python
# ✅ Easily identifiable in Spark UI
stream.writeStream \
    .option("queryName", "IngestFromKafka") \
    .start()

# Shows up as "IngestFromKafka" in Streaming tab
```

### 8. One Checkpoint Per Stream

```python
# ✅ Each stream has its own checkpoint
# ❌ Never share checkpoints between streams

# Example: Two sources → one target
# Source 1 → checkpoint_1 → target
# Source 2 → checkpoint_2 → target
```

### 9. Don't Multiplex Streams

```python
# ❌ Don't run multiple streams on same driver
# Can cause stability issues

# ✅ Use separate jobs or benchmark thoroughly
```

### 10. Optimal Partition Size

```python
# Target: 100-200MB per partition in memory

# Tune with:
.option("maxFilesPerTrigger", "100")
.option("maxBytesPerTrigger", "100MB")

# Monitor in Spark UI → Stages → Partition size
```

### 11. Prefer Broadcast Hash Join

```python
# ✅ BroadcastHashJoin is faster than SortMergeJoin
# Spark auto-broadcasts tables < 100MB

# Increase threshold if needed:
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "1g")
```

## Advanced Checklist

### 12. Checkpoint Naming Convention

```python
# Structure: {table_location}/_checkpoints/_{target_table_name}_starting_{identifier}

# Examples:
# 1. By timestamp: /delta/events/_checkpoints/_events_starting_2024_01_15
# 2. By version: /delta/events/_checkpoints/_events_startingVersion_12345

# Why: Multiple checkpoints over table lifetime (upgrades, logic changes)
```

### 13. Minimize Shuffle Spill

```python
# ✅ Goal: Shuffle spill (disk) = 0
# ✅ Only shuffle read should exist

# Check: Spark UI → SQL → Exchange operators
# If spill > 0: Increase memory or reduce partition size
```

### 14. Use RocksDB for Stateful Operations

```python
# For large state stores, use RocksDB backend
spark.conf.set(
    "spark.sql.streaming.stateStore.providerClass",
    "com.databricks.sql.streaming.state.RocksDBStateProvider"
)
```

### 15. Event Hubs via Kafka Connector

```python
# ✅ Use Kafka protocol for Azure Event Hubs
# More flexible partition handling

# Note: With EventHubs Kafka connector
# Number of cores can differ from partitions
# (vs native EventHubs: cores == partitions)
```

### 16. Watermark for State Cleanup

```python
# ✅ Always use watermark with stateful ops
# Prevents infinite state growth

stream.withWatermark("timestamp", "10 minutes") \
    .groupBy("user_id") \
    .agg(sum("amount"))

# Exception: If infinite state needed, store in Delta + ZORDER
```

### 17. Deduplication at Scale

```python
# At trillion-record scale:
# ✅ Delta merge over dropDuplicates

# dropDuplicates: State store grows very large
# Delta merge: Use table for lookup

# Example:
spark.sql("""
    MERGE INTO target t
    USING source s ON t.event_id = s.event_id
    WHEN NOT MATCHED THEN INSERT *
""")
```

### 18. Azure Instance Family Selection

| Workload | Instance Family |
|----------|----------------|
| Map-heavy (parsing, JSON) | F-series |
| Multiple streams from same source | Fsv2-series |
| Joins/aggregations/optimize | DS_v2-series |
| Delta caching | L-series (SSD) |

### 19. Shuffle Partitions

```python
# Set equal to total worker cores
spark.conf.set("spark.sql.shuffle.partitions", "200")

# ❌ Don't set too high
# If changing: Clear checkpoint (stores the old value)
```

## Quick Reference

### Trigger Selection

| Latency Requirement | Trigger |
|---------------------|---------|
| < 1 second | Real-Time Mode (RTM) |
| 1-10 seconds | processingTime('5 seconds') |
| 1-60 minutes | processingTime based on SLA/3 |
| Batch-like | availableNow=True |

### Cluster Sizing

```python
# Fixed-size cluster recommended for streaming
# ❌ Don't use auto-scaling for streaming workloads

# Why: Pre-allocated resources = predictable latency
```

## Monitoring Checklist

- [ ] Input rate vs processing rate (processing > input)
- [ ] Max offsets behind latest (should decrease over time)
- [ ] Batch duration vs trigger interval (headroom exists)
- [ ] State store size (if using stateful ops)
- [ ] Shuffle spill = 0
- [ ] Null rate in left joins (data quality)

## Common Mistakes

| Mistake | Impact | Fix |
|---------|--------|-----|
| Shared checkpoint | Data loss/corruption | Separate checkpoints |
| No watermark | State explosion | Add watermark |
| S3 versioning | Latency | Disable versioning |
| Autoscaling clusters | Unpredictable latency | Fixed-size clusters |
| High-cardinality partitions | Small files | Partition by date |

## Related Skills

- `spark-streaming-master-class-kafka-to-delta` — End-to-end patterns
- `mastering-checkpoints-in-spark-streaming` — Checkpoint deep dive
- `scaling-spark-streaming-jobs` — Performance tuning
