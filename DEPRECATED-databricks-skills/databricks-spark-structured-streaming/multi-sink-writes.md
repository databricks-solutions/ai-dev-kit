---
name: multi-sink-writes
description: Write a single Spark stream to multiple Delta tables or Kafka topics using ForEachBatch. Use when fanning out streaming data to multiple sinks, implementing medallion architecture (bronze/silver/gold), conditional routing, CDC patterns, or creating materialized views from a single stream.
---

# Multi-Sink Writes

Write a single streaming source to multiple Delta tables or Kafka topics efficiently using ForEachBatch. Read once, write many - avoiding reprocessing the source multiple times.

## Quick Start

```python
from pyspark.sql.functions import col, current_timestamp

def write_multiple_tables(batch_df, batch_id):
    """Write batch to multiple sinks"""
    # Bronze - raw data
    batch_df.write \
        .format("delta") \
        .mode("append") \
        .option("txnVersion", batch_id) \
        .option("txnAppId", "multi_sink_job") \
        .save("/delta/bronze_events")
    
    # Silver - cleansed
    cleansed = batch_df.dropDuplicates(["event_id"])
    cleansed.write \
        .format("delta") \
        .mode("append") \
        .option("txnVersion", batch_id) \
        .option("txnAppId", "multi_sink_job_silver") \
        .save("/delta/silver_events")
    
    # Gold - aggregated
    aggregated = batch_df.groupBy("category").count()
    aggregated.write \
        .format("delta") \
        .mode("append") \
        .option("txnVersion", batch_id) \
        .option("txnAppId", "multi_sink_job_gold") \
        .save("/delta/category_counts")

stream.writeStream \
    .foreachBatch(write_multiple_tables) \
    .option("checkpointLocation", "/checkpoints/multi_sink") \
    .start()
```

## Core Concepts

### One Source, One Checkpoint

Use a single checkpoint for the entire multi-sink stream:

```python
# CORRECT: One checkpoint for all sinks
stream.writeStream \
    .foreachBatch(multi_sink_function) \
    .option("checkpointLocation", "/checkpoints/single_source_multi_sink") \
    .start()

# WRONG: Don't create separate streams
# Each stream would reprocess the source independently
```

### Transactional Guarantees

Each ForEachBatch call represents one epoch. All writes within the batch:
- See the same input data
- Share the same batch_id
- Are idempotent if using txnVersion

## Common Patterns

### Pattern 1: Bronze-Silver-Gold Medallion Architecture

Single stream feeding all three medallion layers:

```python
from pyspark.sql.functions import window, count, sum, current_timestamp

def medallion_architecture(batch_df, batch_id):
    """Single stream feeding all three medallion layers"""
    
    # Bronze: Raw ingestion
    (batch_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "medallion_bronze")
        .saveAsTable("bronze.events")
    )
    
    # Silver: Cleansed and validated
    silver_df = (batch_df
        .dropDuplicates(["event_id"])
        .filter(col("status").isin(["active", "pending"]))
        .withColumn("processed_at", current_timestamp())
    )
    
    (silver_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "medallion_silver")
        .saveAsTable("silver.events")
    )
    
    # Gold: Business aggregates
    gold_df = (silver_df
        .groupBy(window(col("timestamp"), "5 minutes"), "category")
        .agg(
            count("*").alias("event_count"),
            sum("amount").alias("total_amount")
        )
    )
    
    (gold_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "medallion_gold")
        .saveAsTable("gold.category_metrics")
    )

stream.writeStream \
    .foreachBatch(medallion_architecture) \
    .trigger(processingTime="30 seconds") \
    .option("checkpointLocation", "/checkpoints/medallion") \
    .start()
```

### Pattern 2: Conditional Routing

Route events to different tables based on criteria:

```python
def route_by_type(batch_df, batch_id):
    """Route events to different tables based on type"""
    
    # Split by event type
    orders = batch_df.filter(col("event_type") == "order")
    refunds = batch_df.filter(col("event_type") == "refund")
    reviews = batch_df.filter(col("event_type") == "review")
    
    # Write to respective tables
    if orders.count() > 0:
        (orders.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "router_orders")
            .saveAsTable("orders")
        )
    
    if refunds.count() > 0:
        (refunds.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "router_refunds")
            .saveAsTable("refunds")
        )
    
    if reviews.count() > 0:
        (reviews.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "router_reviews")
            .saveAsTable("reviews")
        )
```

### Pattern 3: Parallel Fan-Out

Write to multiple sinks in parallel for independent tables:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_write(batch_df, batch_id):
    """Write to multiple sinks in parallel"""
    
    # Cache to avoid recomputation
    batch_df.cache()
    
    def write_table(table_name, filter_expr=None):
        """Write filtered data to table"""
        df = batch_df.filter(filter_expr) if filter_expr else batch_df
        (df.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", f"parallel_{table_name}")
            .saveAsTable(table_name)
        )
        return f"Wrote {table_name}"
    
    # Define tables and filters
    tables = [
        ("bronze.all_events", None),
        ("silver.errors", col("level") == "ERROR"),
        ("silver.warnings", col("level") == "WARN"),
        ("gold.metrics", col("type") == "metric")
    ]
    
    # Parallel writes
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(write_table, table_name, filter_expr): table_name 
            for table_name, filter_expr in tables
        }
        
        errors = []
        for future in as_completed(futures):
            table_name = futures[future]
            try:
                future.result()
            except Exception as e:
                errors.append((table_name, str(e)))
    
    batch_df.unpersist()
    
    if errors:
        raise Exception(f"Write failures: {errors}")
```

### Pattern 4: Materialized Views

Create multiple derived views from the same stream:

```python
from pyspark.sql.functions import window, count, sum

def create_materialized_views(batch_df, batch_id):
    """Create multiple derived views from the same stream"""
    
    # Base: All events
    (batch_df.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "views_raw")
        .save("/delta/views/raw")
    )
    
    # View 1: Hourly aggregations
    hourly = (batch_df
        .withWatermark("event_time", "1 hour")
        .groupBy(window(col("event_time"), "1 hour"), col("category"))
        .agg(
            count("*").alias("event_count"),
            sum("value").alias("total_value")
        )
    )
    
    (hourly.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "views_hourly")
        .save("/delta/views/hourly")
    )
    
    # View 2: User sessions (15 min window)
    sessions = (batch_df
        .withWatermark("event_time", "15 minutes")
        .groupBy(window(col("event_time"), "15 minutes"), col("user_id"))
        .agg(count("*").alias("actions"))
    )
    
    (sessions.write
        .format("delta")
        .mode("append")
        .option("txnVersion", batch_id)
        .option("txnAppId", "views_sessions")
        .save("/delta/views/sessions")
    )
```

### Pattern 5: Error Handling with Dead Letter Queue

Route invalid records to DLQ:

```python
from pyspark.sql.functions import when, lit

def write_with_dlq(batch_df, batch_id):
    """Write valid records to target, invalid to dead letter queue"""
    
    # Validation
    valid = batch_df.filter(
        col("required_field").isNotNull() & 
        col("timestamp").isNotNull()
    )
    invalid = batch_df.filter(
        col("required_field").isNull() | 
        col("timestamp").isNull()
    )
    
    # Write valid data
    if valid.count() > 0:
        (valid.write
            .format("delta")
            .mode("append")
            .option("txnVersion", batch_id)
            .option("txnAppId", "multi_sink_valid")
            .saveAsTable("silver.valid_events")
        )
    
    # Write invalid to DLQ with metadata
    if invalid.count() > 0:
        dlq_df = (invalid
            .withColumn("_error_reason", 
                when(col("required_field").isNull(), "missing_required_field")
                .otherwise("missing_timestamp"))
            .withColumn("_batch_id", lit(batch_id))
            .withColumn("_processed_at", current_timestamp())
        )
        
        (dlq_df.write
            .format("delta")
            .mode("append")
            .saveAsTable("errors.dead_letter_queue")
        )
```

## Performance Optimization

### Minimize Recomputation

Cache the batch DataFrame to avoid recomputation:

```python
def optimized_multi_sink(batch_df, batch_id):
    """Cache to avoid recomputation"""
    
    # Cache the batch
    batch_df.cache()
    
    # Multiple writes from cached data
    batch_df.write...  # Sink 1
    batch_df.filter(...).write...  # Sink 2
    batch_df.filter(...).write...  # Sink 3
    
    # Unpersist when done
    batch_df.unpersist()
```

### Parallel Writes

Use ThreadPoolExecutor for independent writes:

```python
from concurrent.futures import ThreadPoolExecutor

def parallel_write(batch_df, batch_id):
    """Write to independent tables in parallel"""
    
    batch_df.cache()
    
    def write_table(table_name, df):
        df.write.format("delta").mode("append").saveAsTable(table_name)
    
    # Parallel writes
    with ThreadPoolExecutor(max_workers=4) as executor:
        executor.submit(write_table, "table1", batch_df)
        executor.submit(write_table, "table2", batch_df.filter(...))
        executor.submit(write_table, "table3", batch_df.filter(...))
    
    batch_df.unpersist()
```

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **Slow writes** | Sequential processing | Use parallel ThreadPoolExecutor |
| **Recomputation** | Multiple actions on same DataFrame | Cache the batch DataFrame |
| **Partial failures** | One sink fails | Use idempotent writes; Spark retries entire batch |
| **Schema conflicts** | Tables have different schemas | Transform before each write |
| **Resource contention** | Too many concurrent writes | Limit parallelism; batch writes |

## Production Best Practices

### Idempotent Writes

Always use txnVersion with batch_id:

```python
.write
    .format("delta")
    .option("txnVersion", batch_id)
    .option("txnAppId", "unique_app_id_per_table")
    .mode("append")
```

### Keep Batch Processing Fast

```python
# GOOD: Simple filters and writes
def efficient_write(df, batch_id):
    df.filter(...).write.save("/delta/table1")
    df.filter(...).write.save("/delta/table2")

# BAD: Expensive aggregations (move to stream definition)
def inefficient_write(df, batch_id):
    df.groupBy(...).agg(...).write.save("/delta/table3")  # Move to stream!
```

## Production Checklist

- [ ] One checkpoint per multi-sink stream
- [ ] Idempotent writes configured (txnVersion/txnAppId)
- [ ] Cache used to avoid recomputation
- [ ] Parallel writes for independent tables
- [ ] Error handling and DLQ configured
- [ ] Schema evolution handled
- [ ] Performance monitoring per sink

## Related Skills

- `merge-operations` - Parallel MERGE operations
- `kafka-streaming` - Kafka ingestion patterns
- `stream-static-joins` - Enrichment before multi-sink writes
- `checkpoint-best-practices` - Checkpoint configuration
