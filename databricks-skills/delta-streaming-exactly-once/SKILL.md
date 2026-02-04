---
name: delta-streaming-exactly-once
description: Understand and troubleshoot exactly-once semantics in Spark Structured Streaming with Delta Lake. Use when debugging streaming duplicates, understanding checkpoint mechanics, or ensuring fault-tolerant streaming pipelines.
author: Canadian Data Guy
source_url: https://www.canadiandataguy.com/p/inside-delta-lakes-idempotency-magic
source_site: canadiandataguy.com
---

# Delta Lake Exactly-Once Streaming Semantics

## Overview

When a Spark Structured Streaming job fails mid-flight, how does it know where to resume? What prevents duplicate writes to your Delta tables? This skill explores the elegant mechanisms that make Spark Structured Streaming fault-tolerant and exactly-once.

**Key Insight**: The checkpoint directory and Delta Lake's transaction log work together as a distributed two-phase commit to ensure correctness even when clusters die between writing data and recording completion.

## Checkpoint Structure

When you start a streaming query, Spark creates a checkpoint directory:

```
checkpoint/
├── metadata          # Query configuration and ID
├── offsets/          # What to process
│   ├── 0             # Batch 0 offsets
│   ├── 1             # Batch 1 offsets
│   └── ...
├── commits/          # What's been completed
│   ├── 0             # Batch 0 completed
│   ├── 1             # Batch 1 completed
│   └── ...
└── state/            # Stateful operator state (if applicable)
```

### Critical Timing

| File | When Written | Purpose |
|------|--------------|---------|
| `offsets/N` | Before batch N starts | Records intent to process |
| `commits/N` | After batch N succeeds | Records completion |

## Delta Lake's Idempotency Mechanism

Delta Lake records two critical metadata fields with every streaming write:

| Field | Source | Purpose |
|-------|--------|---------|
| `txnAppId` | `metadata/` file | Unique query identifier |
| `txnVersion` | Batch number | Monotonically increasing epoch |

### The Replay Scenario

When a cluster dies after writing to Delta but before writing the commit file:

1. **On restart**, Spark sees:
   - `offsets/N+1` exists
   - `commits/N+1` does not exist
   - Data is already in Delta table

2. **Delta checks**: Has transaction `(queryId, epochId=N+1)` been committed?
   - **If YES**: Skip the duplicate write, create `commits/N+1`
   - **If NO**: Proceed with write, then create `commits/N+1`

This ensures exactly-once semantics even across failures.

## Step-by-Step: Inspecting Streaming Metadata

### Step 1: Find Your Checkpoint Location

```python
# From your streaming query
query = df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/path/to/checkpoint") \
    .start("/path/to/output")

# The query ID is stored in metadata
query_id = query.id
print(f"Query ID: {query_id}")
```

### Step 2: Inspect Checkpoint Contents

```python
# Read checkpoint metadata
metadata_df = spark.read.json("/path/to/checkpoint/metadata")
metadata_df.select("id", "runId", "name").show(truncate=False)
```

### Step 3: View Delta Transaction Log

```sql
-- Check transaction details
DESCRIBE HISTORY your_streaming_table;

-- Look for streaming write markers
SELECT 
  version,
  operation,
  operationParameters,
  operationMetrics
FROM (DESCRIBE HISTORY your_streaming_table)
WHERE operation = 'STREAMING UPDATE'
```

### Step 4: Verify Exactly-Once Guarantees

```python
# Check for duplicate epochs in Delta log
duplicate_check = spark.sql("""
SELECT 
  operationParameters.txnVersion as epoch_id,
  operationParameters.txnAppId as query_id,
  count(*) as occurrence_count
FROM (DESCRIBE HISTORY your_table)
WHERE operation = 'STREAMING UPDATE'
GROUP BY operationParameters.txnVersion, operationParameters.txnAppId
HAVING count(*) > 1
""")

if duplicate_check.count() > 0:
    print("WARNING: Duplicate epochs detected!")
    duplicate_check.show()
else:
    print("OK: No duplicate epochs found")
```

## Examples

### Example 1: Kafka Streaming with Exactly-Once

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import *

spark = SparkSession.builder.appName("ExactlyOnceExample").getOrCreate()

# Read from Kafka
kafka_df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "broker:9092") \
    .option("subscribe", "events") \
    .option("startingOffsets", "latest") \
    .load()

# Process
events_df = kafka_df.select(
    col("key").cast("string"),
    col("value").cast("string"),
    col("topic"),
    col("partition"),
    col("offset"),
    col("timestamp")
)

# Write with exactly-once guarantee
query = events_df.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", "/mnt/checkpoints/kafka_events") \
    .start("/mnt/delta/events")

query.awaitTermination()
```

### Example 2: Troubleshooting Duplicate Records

```python
# Step 1: Identify duplicate records using Delta metadata
from delta.tables import DeltaTable

delta_table = DeltaTable.forPath(spark, "/mnt/delta/events")

# Query with _metadata column
files_with_duplicates = spark.sql("""
SELECT 
  _metadata.file_path,
  _metadata.file_name,
  _metadata.file_modification_time,
  count(*) as row_count
FROM delta_table
GROUP BY _metadata.file_path, _metadata.file_name, _metadata.file_modification_time
HAVING count(*) > 1
""")

# Step 2: Trace back to transaction log versions
problematic_files = files_with_duplicates.select("file_name").collect()
print(f"Found {len(problematic_files)} files with potential duplicates")

# Step 3: Check transaction log for same epoch, different query IDs
history_df = spark.sql("DESCRIBE HISTORY delta_table")
history_df.createOrReplaceTempView("table_history")

epoch_analysis = spark.sql("""
SELECT 
  operationParameters.txnVersion as epoch,
  collect_set(operationParameters.txnAppId) as query_ids,
  size(collect_set(operationParameters.txnAppId)) as unique_query_count
FROM table_history
WHERE operation = 'STREAMING UPDATE'
GROUP BY operationParameters.txnVersion
HAVING size(collect_set(operationParameters.txnAppId)) > 1
""")

if epoch_analysis.count() > 0:
    print("CRITICAL: Same epoch written by different query IDs!")
    print("This indicates checkpoint corruption or reuse")
    epoch_analysis.show(truncate=False)
```

### Example 3: Safe Checkpoint Recovery

```python
# If checkpoint is corrupted, recover safely

def recover_streaming_checkpoint(
    checkpoint_path: str,
    table_path: str,
    new_checkpoint_path: str
):
    """
    Recover from checkpoint corruption by:
    1. Finding last committed epoch in Delta
    2. Creating new checkpoint starting from that point
    """
    
    # Get last committed epoch from Delta
    last_epoch = spark.sql(f"""
        SELECT max(operationParameters.txnVersion) as max_epoch
        FROM (DESCRIBE HISTORY delta.`{table_path}`)
        WHERE operation = 'STREAMING UPDATE'
    """).collect()[0]["max_epoch"]
    
    print(f"Last committed epoch in Delta: {last_epoch}")
    
    # Initialize new checkpoint with proper metadata
    # (Implementation depends on source system)
    
    return new_checkpoint_path
```

## Edge Cases & Troubleshooting

### Issue: Duplicate Records Appearing

**Root Cause**: Checkpoint directory was overwritten or corrupted, causing Spark to reinitialize with a new `queryId` while replaying already-processed batches.

**Detection**:
```python
# Check for same epoch, different query IDs
spark.sql("""
SELECT 
  operationParameters.txnVersion as epoch,
  collect_set(operationParameters.txnAppId) as query_ids
FROM (DESCRIBE HISTORY your_table)
WHERE operation = 'STREAMING UPDATE'
GROUP BY operationParameters.txnVersion
HAVING size(collect_set(operationParameters.txnAppId)) > 1
""").show()
```

**Prevention**:
1. Enable S3 Server Access Logging or CloudTrail
2. Implement strict access control on checkpoint directories using UC Volumes
3. Treat checkpoints as critical infrastructure

### Issue: Streaming Not Resuming from Correct Offset

**Symptoms**: Stream reprocesses old data or skips new data.

**Diagnosis**:
```bash
# Check checkpoint contents
ls -la /mnt/checkpoints/your_stream/commits/
cat /mnt/checkpoints/your_stream/offsets/0
```

**Solutions**:
1. Don't manually modify checkpoint files
2. If corrupted, start fresh with new checkpoint location
3. Consider using `startingOffsets` option carefully

### Issue: Long Recovery Time After Failure

**Symptoms**: Stream takes too long to restart after failure.

**Cause**: Large state store or many uncommitted batches.

**Solutions**:
1. Enable state store partitioning
2. Use `Trigger.Once` for batch recovery scenarios
3. Consider watermarking for stateful operations

## Best Practices

1. **Protect checkpoints**: Use UC Volumes with strict permissions
2. **Monitor checkpoint health**: Alert on unexpected modifications
3. **Never reuse checkpoints** between different queries
4. **Version your checkpoints**: Include app version in checkpoint path
5. **Test failure scenarios**: Regularly verify exactly-once behavior

## Understanding Kafka Offsets

When reading from Kafka, offset boundaries work as follows:

```
Batch N:   start=100 (inclusive) → end=200 (exclusive)
Batch N+1: start=200 (inclusive) → end=300 (exclusive)
```

- **Start offset**: Included in the batch
- **End offset**: Not included in the batch (becomes next start)

## Attribution

This skill is based on content by **Canadian Data Guy** from the Canadian Data Guy blog post:
[Inside Delta Lake's Idempotency Magic: The Secret to Exactly-Once Spark](https://www.canadiandataguy.com/p/inside-delta-lakes-idempotency-magic)

## Related Resources

- [How to Actually Delete Data in Spark](https://www.databricksters.com/p/how-to-actually-delete-data-in-spark) - Safe deletion with streaming
- [Delta Lake Transaction Log Documentation](https://docs.delta.io/latest/delta-streaming.html)
- [Spark Structured Streaming Programming Guide](https://spark.apache.org/docs/latest/structured-streaming-programming-guide.html)
