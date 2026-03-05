---
name: databricks-spark-structured-streaming
description: "Comprehensive guide to Spark Structured Streaming for production workloads. Use when building streaming pipelines, implementing real-time data processing, handling stateful operations, or optimizing streaming performance."
---

# Spark Structured Streaming

Production-ready streaming pipelines with Spark Structured Streaming on Databricks.

## When to Use This Skill

Use this skill when:
- Building **Kafka-to-Delta** or **Kafka-to-Kafka** streaming pipelines
- Implementing **stream-stream joins** or **stream-static joins**
- Configuring **watermarks**, **state stores**, or **RocksDB** for stateful operations
- Choosing between **processingTime**, **availableNow**, and **Real-Time Mode** triggers
- Optimizing **streaming costs** (trigger tuning, cluster sizing, scheduled streaming)
- Writing **foreachBatch MERGE** patterns for upserts
- Managing **checkpoints** (location, recovery, migration)
- Troubleshooting streaming issues (lag, state bloat, checkpoint corruption)

## Reference Files

| Topic | File | When to Read |
|-------|------|--------------|
| Kafka Streaming | [kafka-streaming.md](kafka-streaming.md) | Kafka-to-Delta ingestion, Kafka-to-Kafka, Real-Time Mode, authentication |
| Stream-Stream Joins | [stream-stream-joins.md](stream-stream-joins.md) | Joining two streams with watermarks and time-range conditions |
| Stream-Static Joins | [stream-static-joins.md](stream-static-joins.md) | Enriching streams with dimension tables, broadcast hints |
| Multi-Sink Writes | [multi-sink-writes.md](multi-sink-writes.md) | Writing one stream to multiple Delta tables in parallel |
| Merge Operations | [merge-operations.md](merge-operations.md) | foreachBatch MERGE, parallel merges, deduplication |
| Checkpoints | [checkpoint-best-practices.md](checkpoint-best-practices.md) | Checkpoint location, recovery, migration, cleanup |
| Stateful Operations | [stateful-operations.md](stateful-operations.md) | Watermarks, state stores, RocksDB, state monitoring |
| Triggers & Cost | [trigger-and-cost-optimization.md](trigger-and-cost-optimization.md) | Trigger selection, cost optimization, cluster right-sizing |
| Best Practices | [streaming-best-practices.md](streaming-best-practices.md) | Production checklist, beginner through expert tips |

---

## Quick Start: Kafka to Delta

```python
from pyspark.sql.functions import col, from_json
from pyspark.sql.types import StructType, StructField, StringType, TimestampType

schema = StructType([
    StructField("event_id", StringType()),
    StructField("user_id", StringType()),
    StructField("event_type", StringType()),
    StructField("event_time", TimestampType()),
])

df = (spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "events")
    .option("startingOffsets", "earliest")
    .option("minPartitions", "6")
    .load()
    .select(from_json(col("value").cast("string"), schema).alias("data"))
    .select("data.*")
)

df.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/events") \
    .trigger(processingTime="30 seconds") \
    .toTable("catalog.schema.bronze_events")
```

## Quick Start: foreachBatch MERGE (Upserts)

```python
from delta.tables import DeltaTable

def upsert_batch(batch_df, batch_id):
    target = DeltaTable.forName(spark, "catalog.schema.customers")
    (target.alias("t")
        .merge(batch_df.alias("s"), "t.customer_id = s.customer_id")
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute())

(spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "broker:9092")
    .option("subscribe", "customer-updates")
    .load()
    .select(from_json(col("value").cast("string"), customer_schema).alias("data"))
    .select("data.*")
    .writeStream
    .foreachBatch(upsert_batch)
    .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/customers")
    .trigger(processingTime="1 minute")
    .start()
)
```

## Quick Start: availableNow (Scheduled Streaming)

```python
(spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", "/Volumes/catalog/schema/schemas/events")
    .load("/Volumes/catalog/schema/landing/events/")
    .writeStream
    .format("delta")
    .option("checkpointLocation", "/Volumes/catalog/schema/checkpoints/events")
    .trigger(availableNow=True)
    .toTable("catalog.schema.bronze_events")
)
```

Schedule via Databricks Jobs every 15 minutes for near-real-time at a fraction of continuous cost.

---

## Trigger Selection Guide

| Latency Requirement | Trigger | Cost | Use Case |
|---------------------|---------|------|----------|
| < 800ms | `realTime=True` | $$$ | Real-time analytics, alerts |
| 1–30 seconds | `processingTime="N seconds"` | $$ | Near real-time dashboards |
| 15–60 minutes | `availableNow=True` (scheduled) | $ | Batch-style SLA |
| > 1 hour | `availableNow=True` (scheduled) | $ | ETL pipelines |

See [trigger-and-cost-optimization.md](trigger-and-cost-optimization.md) for detailed cost calculations and cluster sizing.

---

## Watermark Essentials

Watermarks are **required** for stateful operations (joins, aggregations, deduplication) to bound state and handle late data.

```python
df.withWatermark("event_time", "10 minutes")
```

| Watermark | Effect | Use Case |
|-----------|--------|----------|
| `"5 minutes"` | Low latency, tight state | Real-time analytics |
| `"10 minutes"` | Moderate latency | General streaming |
| `"1 hour"` | High completeness | Financial transactions |
| `"24 hours"` | Batch-like completeness | Backfill scenarios |

**Rule of thumb**: Start with 2–3x your p95 event latency. Monitor late data rate and adjust.

See [stateful-operations.md](stateful-operations.md) for RocksDB configuration, state monitoring, and advanced patterns.

---

## Stream Join Patterns

### Stream-Stream Join

Both sides must have watermarks. Use time-range conditions to bound state:

```python
orders = spark.readStream.table("catalog.schema.orders") \
    .withWatermark("order_time", "10 minutes")

payments = spark.readStream.table("catalog.schema.payments") \
    .withWatermark("payment_time", "10 minutes")

joined = orders.join(payments,
    expr("""
        order_id = payment_order_id
        AND payment_time >= order_time
        AND payment_time <= order_time + INTERVAL 1 HOUR
    """),
    "inner"
)
```

See [stream-stream-joins.md](stream-stream-joins.md) for left outer joins, multiple join keys, and monitoring.

### Stream-Static Join

Use broadcast hints for small dimension tables:

```python
from pyspark.sql.functions import broadcast

dim_products = spark.table("catalog.schema.products")

enriched = stream_df.join(
    broadcast(dim_products),
    "product_id",
    "left"
)
```

See [stream-static-joins.md](stream-static-joins.md) for refresh strategies and cache invalidation.

---

## Checkpoint Best Practices

- **Always use UC Volumes** for checkpoint storage: `/Volumes/catalog/schema/volume/checkpoints/stream_name`
- **One checkpoint per stream** — never share checkpoints between streams
- **Never delete checkpoints** of a running stream — this resets offsets
- **Fixed-size clusters** — autoscaling causes task redistribution issues with streaming

See [checkpoint-best-practices.md](checkpoint-best-practices.md) for migration, recovery, and cleanup patterns.

---

## Production Checklist

- [ ] Checkpoint location is persistent (UC Volumes, not DBFS)
- [ ] Unique checkpoint per stream
- [ ] Fixed-size cluster (no autoscaling for streaming)
- [ ] Trigger interval explicitly set (never use default continuous)
- [ ] Monitoring configured (input rate, processing rate, batch duration)
- [ ] Watermark configured for all stateful operations
- [ ] Schema defined explicitly (not inferred) for Kafka sources
- [ ] `minPartitions` set to match Kafka partition count
- [ ] Error handling in foreachBatch (idempotent writes)
- [ ] Exactly-once verified (txnVersion/txnAppId for foreachBatch MERGE)

See [streaming-best-practices.md](streaming-best-practices.md) for the full beginner-to-expert checklist.

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **Increasing batch duration** | State store growing unbounded | Add or reduce watermark duration; enable RocksDB |
| **High S3/ADLS listing costs** | No trigger interval set | Always set `processingTime` or `availableNow` |
| **Duplicate records** | Missing deduplication in MERGE | Use `dropDuplicates` or add dedup logic in foreachBatch |
| **Stream-static join stale data** | Static DataFrame cached at start | Restart stream periodically or use Delta change feed |
| **Checkpoint corruption** | Cluster terminated mid-write | Delete last incomplete batch folder; restart stream |
| **OOM on state operations** | In-memory state store too large | Switch to RocksDB state store provider |
| **Late data dropped** | Watermark too aggressive | Increase watermark duration; monitor late event rate |

## Related Skills

- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** — higher-level streaming with DLT/SDP (streaming tables, Auto Loader)
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — scheduling `availableNow` streaming jobs
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — checkpoint storage in UC Volumes, system tables for monitoring

## Resources

- [Structured Streaming Programming Guide](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html)
- [Databricks Structured Streaming Docs](https://docs.databricks.com/en/structured-streaming/index.html)
- [Real-Time Mode](https://docs.databricks.com/en/structured-streaming/real-time.html)
