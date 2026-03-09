---
name: databricks-spark-structured-streaming
description: Comprehensive guide to Spark Structured Streaming for production workloads. Use when building streaming pipelines, implementing real-time data processing, handling stateful operations, or optimizing streaming performance.
---

# Spark Structured Streaming

Production-ready streaming pipelines with Spark Structured Streaming. This skill provides navigation to detailed patterns and best practices.

## Quick Start

```python
from pyspark.sql.functions import col, from_json

# Basic Kafka to Delta streaming
df = (spark
    .readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "topic")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
)

df.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/checkpoints/stream") \
    .trigger(processingTime="30 seconds") \
    .start("/delta/target_table")
```

## Core Patterns

| Pattern | Description | Reference |
|---------|-------------|-----------|
| **Kafka Streaming** | Kafka to Delta, Kafka to Kafka, Real-Time Mode | See [kafka-streaming.md](kafka-streaming.md) |
| **Stream Joins** | Stream-stream joins, stream-static joins | See [stream-stream-joins.md](stream-stream-joins.md), [stream-static-joins.md](stream-static-joins.md) |
| **Multi-Sink Writes** | Write to multiple tables, parallel merges | See [multi-sink-writes.md](multi-sink-writes.md) |
| **Merge Operations** | MERGE performance, parallel merges, optimizations | See [merge-operations.md](merge-operations.md) |

## Configuration

| Topic | Description | Reference |
|-------|-------------|-----------|
| **Checkpoints** | Checkpoint management and best practices | See [checkpoint-best-practices.md](checkpoint-best-practices.md) |
| **Stateful Operations** | Watermarks, state stores, RocksDB configuration | See [stateful-operations.md](stateful-operations.md) |
| **Trigger & Cost** | Trigger selection, cost optimization, RTM | See [trigger-and-cost-optimization.md](trigger-and-cost-optimization.md) |

## Best Practices

| Topic | Description | Reference |
|-------|-------------|-----------|
| **Production Checklist** | Comprehensive best practices | See [streaming-best-practices.md](streaming-best-practices.md) |

## Production Checklist

- [ ] Checkpoint location is persistent (UC volumes, not DBFS)
- [ ] Unique checkpoint per stream
- [ ] Fixed-size cluster (no autoscaling for streaming)
- [ ] Monitoring configured (input rate, lag, batch duration)
- [ ] Exactly-once verified (txnVersion/txnAppId)
- [ ] Watermark configured for stateful operations
- [ ] Left joins for stream-static (not inner)

## Common Issues

| Issue | Solution |
|-------|----------|
| **Checkpoint corruption after schema change** | Checkpoints are tied to the query plan. Schema changes (adding/removing columns) require a new checkpoint location. Back up the old checkpoint before changing |
| **OOM on stateful operations** | Enable RocksDB state store: `spark.conf.set("spark.sql.streaming.stateStore.providerClass", "com.databricks.sql.streaming.state.RocksDBStateStoreProvider")`. This moves state to disk instead of heap |
| **Watermark not dropping late data** | Watermark only guarantees state cleanup, not data filtering. Late data may still appear in output. Use `withWatermark()` on the timestamp column BEFORE the aggregation |
| **`foreachBatch` MERGE duplicates** | Without idempotency, retries can duplicate rows. Use `batchId` as a dedup key or add `WHEN MATCHED` to your MERGE to handle re-processing |
| **Stream-static join returns NULL** | Use LEFT JOIN (not INNER) for stream-static joins. The static side may not have loaded yet on the first micro-batch |
| **`availableNow` vs `once` trigger** | `once` is deprecated. Use `trigger(availableNow=True)` instead — it processes all available data across multiple batches for better parallelism |
| **Checkpoint on DBFS root** | Never use `dbfs:/` for checkpoints in production. Use UC Volumes: `/Volumes/catalog/schema/volume/checkpoints/stream_name` |
| **Autoscaling cluster with streaming** | Disable autoscaling for streaming jobs. Use a fixed-size cluster — autoscaling causes instability as executors are added/removed during micro-batches |
| **Kafka offset reset** | Set `startingOffsets` to `"earliest"` or `"latest"` (default). To replay from a specific offset, use `startingOffsetsByTimestamp` with a JSON map |
| **Multiple streams sharing checkpoint** | Each stream MUST have its own unique checkpoint location. Sharing causes data corruption and "concurrent update" errors |
| **Stream stops silently** | Enable `spark.sql.streaming.metricsEnabled=true` and monitor `StreamingQueryListener` or the Spark UI Streaming tab. Set up alerts on `lastProgress` staleness |
| **`MERGE INTO` slow in `foreachBatch`** | Ensure the target table has liquid clustering on the join key. Use `OPTIMIZE` periodically. Consider `WHEN NOT MATCHED BY SOURCE` for deletes instead of separate DELETE statements |
