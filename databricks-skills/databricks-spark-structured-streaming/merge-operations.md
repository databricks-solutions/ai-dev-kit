---
name: merge-operations
description: Comprehensive guide to Delta MERGE operations in streaming including performance optimization, parallel merges, and Liquid Clustering configuration. Use when implementing upserts, optimizing merge performance, performing parallel merges to multiple tables, or eliminating optimize pauses.
---

# Merge Operations in Streaming

Comprehensive guide to Delta MERGE operations: performance optimization, parallel merges to multiple tables, and modern Delta features (Liquid Clustering + Deletion Vectors + Row-Level Concurrency).

## Quick Start

### Basic MERGE with Optimization

```python
from delta.tables import DeltaTable

# Enable modern Delta features
spark.sql("""
    ALTER TABLE target_table SET TBLPROPERTIES (
        'delta.enableDeletionVectors' = true,
        'delta.enableRowLevelConcurrency' = true,
        'delta.liquid.clustering' = true
    )
""")

# MERGE in ForEachBatch
def upsert_batch(batch_df, batch_id):
    batch_df.createOrReplaceTempView("updates")
    spark.sql("""
        MERGE INTO target_table t
        USING updates s ON t.id = s.id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    # No optimize needed - Liquid Clustering handles it automatically

stream.writeStream \
    .foreachBatch(upsert_batch) \
    .option("checkpointLocation", "/checkpoints/merge") \
    .start()
```

### Parallel MERGE to Multiple Tables

```python
from delta.tables import DeltaTable
from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_merge_multiple_tables(batch_df, batch_id):
    """Merge into multiple tables in parallel"""
    
    batch_df.cache()
    
    def merge_table(table_name, merge_key):
        target = DeltaTable.forName(spark, table_name)
        source = batch_df.alias("source")
        
        (target.alias("target")
            .merge(source, f"target.{merge_key} = source.{merge_key}")
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
        return f"Merged {table_name}"
    
    tables = [
        ("silver.customers", "customer_id"),
        ("silver.orders", "order_id"),
        ("silver.products", "product_id")
    ]
    
    # Parallel merges
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(merge_table, table_name, merge_key): table_name
            for table_name, merge_key in tables
        }
        
        for future in as_completed(futures):
            future.result()  # Raise on error
    
    batch_df.unpersist()

stream.writeStream \
    .foreachBatch(parallel_merge_multiple_tables) \
    .option("checkpointLocation", "/checkpoints/parallel_merge") \
    .start()
```

## Core Concepts

### Liquid Clustering + DV + RLC

Enable modern Delta features for optimal merge performance:

```sql
-- Enable for target table
ALTER TABLE target_table SET TBLPROPERTIES (
    'delta.enableDeletionVectors' = true,
    'delta.enableRowLevelConcurrency' = true,
    'delta.liquid.clustering' = true
);
```

**Benefits:**
- **Deletion Vectors**: Soft deletes without file rewrite
- **Row-Level Concurrency**: Concurrent updates to different rows
- **Liquid Clustering**: Automatic optimization without pauses
- **Result**: Eliminates optimize pauses, lower P99 latency, simpler code

## Common Patterns

### Pattern 1: Basic MERGE with Optimization

```python
def optimized_merge(batch_df, batch_id):
    """MERGE with optimized table"""
    batch_df.createOrReplaceTempView("updates")
    
    spark.sql("""
        MERGE INTO target_table t
        USING updates s ON t.id = s.id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    # No optimize needed - Liquid Clustering handles it

stream.writeStream \
    .foreachBatch(optimized_merge) \
    .option("checkpointLocation", "/checkpoints/merge") \
    .start()
```

### Pattern 2: Parallel MERGE to Multiple Tables

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def parallel_merge(batch_df, batch_id):
    """Merge into multiple tables in parallel"""
    
    batch_df.cache()
    
    def merge_one_table(table_name, merge_key):
        target = DeltaTable.forName(spark, table_name)
        source = batch_df.alias("source")
        
        (target.alias("target")
            .merge(source, f"target.{merge_key} = source.{merge_key}")
            .whenMatchedUpdateAll()
            .whenNotMatchedInsertAll()
            .execute()
        )
        return table_name
    
    tables = [
        ("silver.customers", "customer_id"),
        ("silver.orders", "order_id"),
        ("silver.products", "product_id")
    ]
    
    # Optimal thread count: min(number_of_tables, cluster_cores / 2)
    max_workers = min(len(tables), max(2, total_cores // 2))
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(merge_one_table, table_name, merge_key): table_name
            for table_name, merge_key in tables
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
        raise Exception(f"Merge failures: {errors}")
```

### Pattern 3: MERGE with Partition Pruning

```python
def partition_pruned_merge(batch_df, batch_id):
    """MERGE with partition column in condition"""
    batch_df.createOrReplaceTempView("updates")
    
    # Include partition column in merge condition
    spark.sql("""
        MERGE INTO target_table t
        USING updates s 
        ON t.id = s.id AND t.date = s.date  -- partition column
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    # Skips irrelevant partitions for faster execution
```

### Pattern 4: CDC Multi-Target with Parallel MERGE

```python
def cdc_parallel_merge(batch_df, batch_id):
    """Apply CDC changes to multiple tables in parallel"""
    
    batch_df.cache()
    
    # Split by operation type
    deletes = batch_df.filter(col("_op") == "DELETE")
    upserts = batch_df.filter(col("_op").isin(["INSERT", "UPDATE"]))
    
    def merge_cdc_table(table_name, merge_key):
        target = DeltaTable.forName(spark, table_name)
        
        # Upserts
        if upserts.count() > 0:
            (target.alias("target")
                .merge(upserts.alias("source"), f"target.{merge_key} = source.{merge_key}")
                .whenMatchedUpdateAll()
                .whenNotMatchedInsertAll()
                .execute()
            )
        
        # Deletes
        if deletes.count() > 0:
            (target.alias("target")
                .merge(deletes.alias("source"), f"target.{merge_key} = source.{merge_key}")
                .whenMatchedDelete()
                .execute()
            )
    
    tables = [
        ("silver.customers", "customer_id"),
        ("silver.orders", "order_id")
    ]
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(merge_cdc_table, table_name, merge_key): table_name
            for table_name, merge_key in tables
        }
        
        for future in as_completed(futures):
            future.result()
    
    batch_df.unpersist()
```

## Performance Optimization

### Enable Liquid Clustering + DV + RLC

```sql
-- Create table with Liquid Clustering
CREATE TABLE target_table (
    id STRING,
    name STRING,
    updated_at TIMESTAMP
) USING DELTA
CLUSTER BY (id)
TBLPROPERTIES (
    'delta.enableDeletionVectors' = true,
    'delta.enableRowLevelConcurrency' = true
);

-- Or alter existing table
ALTER TABLE target_table SET TBLPROPERTIES (
    'delta.enableDeletionVectors' = true,
    'delta.enableRowLevelConcurrency' = true,
    'delta.liquid.clustering' = true
);
ALTER TABLE target_table CLUSTER BY (id);
```

### Z-Ordering on Merge Key

```sql
-- Z-Order on merge key for faster lookups
OPTIMIZE target_table ZORDER BY (id);

-- Run periodically or via Predictive Optimization
-- 5-10x faster for targeted lookups
```

### File Size Tuning

```sql
-- Target file size for optimal merge
ALTER TABLE target_table SET TBLPROPERTIES (
    'delta.targetFileSize' = '128mb'
);
```

### Optimal Thread Count

```python
# Formula: min(number_of_tables, cluster_cores / 2)
# Example: 4 tables, 8 cores → 4 workers
# Example: 2 tables, 4 cores → 2 workers

max_workers = min(len(tables), max(2, total_cores // 2))
```

## Monitoring

### Track Merge Performance

```python
import time

def monitored_merge(batch_df, batch_id):
    start_time = time.time()
    
    batch_df.createOrReplaceTempView("updates")
    spark.sql("""
        MERGE INTO target_table t
        USING updates s ON t.id = s.id
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED THEN INSERT *
    """)
    
    duration = time.time() - start_time
    print(f"Merge duration: {duration:.2f}s")
    
    # Alert if duration exceeds threshold
    if duration > 30:
        print(f"WARNING: Merge duration {duration:.2f}s exceeds threshold")
```

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **High P99 latency** | OPTIMIZE pauses | Enable Liquid Clustering (no pauses) |
| **Merge conflicts** | Concurrent updates to same rows | Enable Row-Level Concurrency |
| **Slow merges** | Large files, no optimization | Enable Liquid Clustering; Z-Order on merge key |
| **Too many threads** | Resource contention | Reduce max_workers; match to cluster capacity |
| **Partial failures** | One merge fails | Collect all errors; fail batch if any error |

## Production Checklist

- [ ] Liquid Clustering + DV + RLC enabled on all target tables
- [ ] Z-Ordering configured on merge keys
- [ ] Optimal thread count configured (start with 2)
- [ ] Error handling implemented (collect all errors)
- [ ] Performance monitoring per table
- [ ] Cache used to avoid recomputation
- [ ] Unpersist after writes
- [ ] File size tuned (128MB target)

## Related Skills

- `multi-sink-writes` - Multi-sink write patterns
- `partitioning-strategy` - Partition optimization for merges
- `checkpoint-best-practices` - Checkpoint configuration
