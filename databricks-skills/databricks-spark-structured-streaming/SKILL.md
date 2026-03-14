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
| **Checkpoint corruption after schema change** | Checkpoints are tied to the query plan. Schema changes require a new checkpoint location. Back up the old checkpoint before changing |
| **OOM on stateful operations** | Enable RocksDB state store: `spark.conf.set("spark.sql.streaming.stateStore.providerClass", "com.databricks.sql.streaming.state.RocksDBStateStoreProvider")` |
| **`availableNow` trigger processes no data** | Ensure the source has new data since the last checkpoint. Check that the checkpoint path is correct and accessible |
| **Stream-static join returns stale data** | The static side is read once per micro-batch by default. Use `spark.sql.streaming.forceDeleteTempCheckpointLocation` or refresh the static DataFrame |
| **`foreachBatch` MERGE has duplicates** | Use `txnVersion` and `txnAppId` for idempotent writes: `deltaTable.merge(...).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()` |
| **Auto Loader `cloudFiles` schema inference fails** | Set `cloudFiles.schemaLocation` to a persistent path. For schema evolution, use `cloudFiles.schemaEvolutionMode = "addNewColumns"` |
| **Watermark delay too aggressive** | Late data arriving after the watermark is dropped silently. Set watermark delay >= max expected lateness of your data |
| **Streaming query silently stops** | Check the Spark UI for exceptions. Add a `StreamingQueryListener` or monitor `query.lastProgress` for null batches |
