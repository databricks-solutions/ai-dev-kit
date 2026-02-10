---
name: checkpoint-best-practices
description: Configure and manage checkpoint locations for reliable Spark Structured Streaming. Use when setting up new streaming jobs, troubleshooting checkpoint issues, migrating checkpoints, or ensuring exactly-once semantics with proper checkpoint storage and organization.
---

# Checkpoint Best Practices

Configure checkpoint locations for reliable streaming with exactly-once semantics. Checkpoints track progress and enable fault tolerance.

## Quick Start

```python
def get_checkpoint_location(table_name):
    """Checkpoint tied to target table"""
    return f"/Volumes/catalog/checkpoints/{table_name}"

# Example:
# Table: prod.analytics.orders
# Checkpoint: /Volumes/prod/checkpoints/orders

query = (df
    .writeStream
    .format("delta")
    .option("checkpointLocation", get_checkpoint_location("orders"))
    .start("/delta/orders")
)
```

## Checkpoint Storage

### Use Persistent Storage

```python
# DO: Use Unity Catalog volumes (S3/ADLS-backed)
checkpoint_path = "/Volumes/catalog/checkpoints/stream_name"

# DON'T: Use DBFS (ephemeral, workspace-local)
checkpoint_path = "/dbfs/checkpoints/stream_name"  # Avoid
```

### Target-Tied Organization

```python
def get_checkpoint_location(table_name):
    """Checkpoint should be tied to TARGET, not source"""
    return f"/Volumes/catalog/checkpoints/{table_name}"

# Why target-tied?
# - Checkpoint already contains source information
# - Systematic organization
# - Easy backup and restore
# - Clear ownership
```

### Unique Checkpoint Per Stream

```python
# CORRECT: Each stream has its own checkpoint
stream1.writeStream \
    .option("checkpointLocation", "/checkpoints/stream1") \
    .start()

stream2.writeStream \
    .option("checkpointLocation", "/checkpoints/stream2") \
    .start()

# WRONG: Never share checkpoints between streams
# This causes data loss and corruption
```

## Checkpoint Structure

### Folder Contents

```
checkpoint_location/
├── metadata/      # Query ID
├── offsets/       # What to process (intent)
├── commits/       # What completed (confirmation)
├── sources/       # Source metadata
└── state/         # Stateful operations (if any)
```

### Stateless vs Stateful

```python
# Stateless (read from Kafka, write to Delta)
# Checkpoint: metadata, offsets, commits, sources
# No state folder

df = (spark.readStream
    .format("kafka")
    .option("subscribe", "topic")
    .load())

# Stateful (with watermark and deduplication)
# Checkpoint: + state folder
df_stateful = (df
    .withWatermark("timestamp", "10 minutes")
    .dropDuplicates(["partition", "offset"])
)
```

## Reading Checkpoint Contents

### Read Offset Files

```python
import json

# Read offset file
offset_file = "/checkpoints/stream/offsets/223"
content = dbutils.fs.head(offset_file)
offset_data = json.loads(content)

# Pretty print
print(json.dumps(offset_data, indent=2))

# Key fields:
# - batchWatermarkMs: Watermark timestamp
# - batchTimestampMs: When batch started
# - source[0].startOffset: Beginning of batch (inclusive)
# - source[0].endOffset: End of batch (exclusive)
# - source[0].latestOffset: Current position in source
```

### Read State Store

```python
# Query state store directly
state_df = (spark
    .read
    .format("statestore")
    .load("/checkpoints/stream/state")
)

state_df.show()
# Shows: key, value, partitionId, expiration timestamp

# Read state metadata
state_metadata = (spark
    .read
    .format("state-metadata")
    .load("/checkpoints/stream")
)
state_metadata.show()
# Shows: operatorName, numPartitions, minBatchId, maxBatchId
```

## Recovery Scenarios

### Lost Checkpoint

```python
# Steps to recover:
# 1. Delete checkpoint folder
dbutils.fs.rm("/checkpoints/stream", recurse=True)

# 2. Restart stream with startingOffsets=earliest
df.writeStream \
    .format("delta") \
    .option("checkpointLocation", "/checkpoints/stream") \
    .option("startingOffsets", "earliest") \
    .start()

# 3. Stream reprocesses from beginning
# 4. Delta sink handles deduplication (if idempotent writes configured)
```

### Corrupted Checkpoint

```python
# Same as lost checkpoint:
# 1. Delete checkpoint folder
# 2. Restart with startingOffsets=earliest
# 3. Or restore from backup if available

# Backup checkpoint before major changes
dbutils.fs.cp(
    "/checkpoints/stream",
    "/checkpoints/stream_backup_20240101",
    recurse=True
)
```

### Crash During Batch

```python
# Scenario: Crash during batch processing
# - Latest offset = 223 (written at start)
# - Commit 223 missing (crash before finish)
# - On restart: Spark reprocesses offset 223
# - Delta deduplication prevents duplicates (if txnVersion configured)
```

## Monitoring

### Checkpoint Size

```python
# Track checkpoint folder size
checkpoint_size = dbutils.fs.ls("/checkpoints/stream")
total_size = sum([f.size for f in checkpoint_size if f.isFile()])
print(f"Checkpoint size: {total_size / (1024*1024):.2f} MB")

# Alert on checkpoint access failures
try:
    dbutils.fs.ls("/checkpoints/stream")
except Exception as e:
    print(f"Checkpoint access failed: {e}")
    # Send alert
```

### State Store Growth

```python
# Monitor state store size (stateful jobs)
state_df = spark.read.format("statestore").load("/checkpoints/stream/state")

# Check partition balance
state_df.groupBy("partitionId").count().orderBy(desc("count")).show()

# Look for skew - one partition with 10x others = problem
# State size = f(watermark duration, key cardinality)
```

### Offset vs Commit Sync

```python
# Check if offsets have matching commits
import json

# Read latest offset
latest_offset_file = sorted(dbutils.fs.ls("/checkpoints/stream/offsets"))[-1].path
offset_data = json.loads(dbutils.fs.head(latest_offset_file))
batch_id = latest_offset_file.split("/")[-1]

# Check if commit exists
commit_file = f"/checkpoints/stream/commits/{batch_id}"
if dbutils.fs.exists(commit_file):
    print(f"Batch {batch_id}: Committed")
else:
    print(f"Batch {batch_id}: Not committed (will reprocess)")
```

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| **State growing too large** | Long watermark duration or high cardinality keys | Reduce watermark duration; reduce key cardinality |
| **Checkpoint corruption** | File system issues or manual deletion | Delete checkpoint and restart; restore from backup |
| **Slow state operations** | Partition imbalance | Check partition balance; ensure keys are evenly distributed |
| **Can't find commit file** | Normal if job crashed | Spark will reprocess on restart |
| **Offsets out of sync** | Offsets without matching commits | Indicates unprocessed batch; will reprocess |

## Production Best Practices

### Checkpoint Location Pattern

```python
def get_checkpoint_path(table_name, environment="prod"):
    """
    Checkpoint should be:
    1. Tied to TARGET table (not source)
    2. In persistent storage (UC Volume, S3, ADLS)
    3. Organized systematically
    """
    return f"/Volumes/{environment}/checkpoints/{table_name}"

# Usage
checkpoint = get_checkpoint_path("orders", "prod")
```

### Backup Strategy

```python
# Backup checkpoint before major changes
def backup_checkpoint(checkpoint_path, backup_suffix):
    backup_path = f"{checkpoint_path}_backup_{backup_suffix}"
    dbutils.fs.cp(checkpoint_path, backup_path, recurse=True)
    return backup_path

# Before code changes or migrations
backup_checkpoint("/checkpoints/stream", "20240101")
```

### Migration

```python
# Migrate checkpoint to new location
def migrate_checkpoint(old_path, new_path):
    # Copy checkpoint folder
    dbutils.fs.cp(old_path, new_path, recurse=True)
    
    # Update code to use new path
    # Old checkpoint remains for rollback
    
    # Restart stream with new checkpoint location
```

## Production Checklist

- [ ] Checkpoint location is persistent (S3/ADLS, not DBFS)
- [ ] Unique checkpoint per stream
- [ ] Target-tied checkpoint organization
- [ ] Backup strategy defined
- [ ] Monitoring configured (checkpoint size, access failures)
- [ ] State store growth monitored (if stateful)
- [ ] Recovery procedure documented
- [ ] Migration procedure documented

## Related Skills

- `kafka-to-delta` - Kafka ingestion with checkpoint management
- `stream-stream-joins` - Stateful operations and state stores
- `state-store-management` - Deep dive on state store optimization
