---
name: zerobus-ingest
description: Stream data directly into Delta Lake without managing a message bus. Use for high-throughput ingestion from applications, IoT devices, or custom producers where you need at-least-once delivery and don't require Kafka-style retention or multiple consumers.
author: Databricksters Community
source_url: https://www.databricksters.com/p/databricks-zerobus-the-best-bus-is
source_site: databricksters.com
---

# Zerobus Ingest - Direct Lakehouse Streaming

## Overview

Zerobus Ingest is a fully managed service that enables direct record-by-record data ingestion into Delta tables without maintaining complex message bus infrastructure like Kafka. Applications send data directly to Delta Lake through a simple SDK.

**When to Use:**
- Streaming from applications to Lakehouse
- High-throughput ingestion (100MB/s per stream)
- When you don't need message retention or multiple subscribers
- Simplifying operational overhead vs. Kafka

**When NOT to Use:**
- Need exactly-once semantics (not yet supported)
- Multiple consumers reading same stream
- Complex pub-sub patterns
- Message retention/replay requirements

## Architecture Comparison

### Before (With Message Bus)
```
App → Kafka → Connector → Spark → Delta Lake
    (Manage brokers, partitions, connectors, consumers)
```

### After (With Zerobus)
```
App → Zerobus SDK → Delta Lake
    (Managed service, no infrastructure)
```

## Quick Start

### 1. Create Target Delta Table

```sql
-- Create table before connecting
CREATE TABLE events (
    event_id STRING,
    user_id STRING,
    event_type STRING,
    payload STRING,
    event_time TIMESTAMP
) CLUSTER BY (event_type, event_time);
```

### 2. Install SDK

```bash
# Python
pip install databricks-zerobus-ingest

# Go
go get github.com/databricks/zerobus-sdk-go

# Java/Scala (Maven)
<dependency>
    <groupId>com.databricks</groupId>
    <artifactId>zerobus-sdk-java</artifactId>
    <version>1.0.0</version>
</dependency>

# Rust
cargo add databricks-zerobus-sdk-rs

# TypeScript
npm install @databricks/zerobus-ingest-sdk
```

### 3. Configure Ingestion Endpoint

```python
from databricks.zerobus import IngestClient

# Initialize client
client = IngestClient(
    workspace_url="https://your-workspace.cloud.databricks.com",
    table_name="catalog.schema.events",
    auth_token="your-access-token"  # Use secrets in production
)

# Send single record
client.send({
    "event_id": "evt_123",
    "user_id": "user_456",
    "event_type": "click",
    "payload": '{"button": "signup"}',
    "event_time": "2024-01-15T10:30:00Z"
})

# Send batch
records = [
    {"event_id": "evt_1", "user_id": "u1", "event_type": "view", ...},
    {"event_id": "evt_2", "user_id": "u2", "event_type": "click", ...},
]
client.send_batch(records)
```

### 4. Go Example

```go
package main

import (
    "context"
    "log"
    "time"
    
    zerobus "github.com/databricks/zerobus-sdk-go"
)

func main() {
    ctx := context.Background()
    
    // Create client
    client, err := zerobus.NewClient(
        "https://your-workspace.cloud.databricks.com",
        "catalog.schema.events",
        zerobus.WithAuthToken("your-token"),
    )
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()
    
    // Send record
    record := map[string]interface{}{
        "event_id":   "evt_123",
        "user_id":    "user_456",
        "event_type": "click",
        "event_time": time.Now().UTC(),
    }
    
    if err := client.Send(ctx, record); err != nil {
        log.Printf("Failed to send: %v", err)
    }
}
```

## Key Features

### Write-Ahead Log (WAL) Architecture

Records are immediately persisted to durable storage (SSD with high IOPS) and acknowledged in under 50ms. This guarantees durability even if failures occur.

**Benefits:**
- Automatic recovery from network issues
- Automatic retries with exponential backoff
- No data loss on client failures

### Schema Management

Incoming data is validated against the Delta table schema:

```python
# Schema mismatch example - will be rejected
try:
    client.send({
        "wrong_field": "value"  # Doesn't match table schema
    })
except SchemaValidationError as e:
    print(f"Schema error: {e}")
```

### Performance

| Metric | Value |
|--------|-------|
| Max throughput | 100 MB/s per stream |
| Max records/sec | 15,000 rows/s per stream |
| Acknowledgment latency | < 50ms |
| Message size limit | 10 MB per message |

## Production Configuration

### Error Handling

```python
from databricks.zerobus import IngestClient, NonRetriableException, ZerobusException

client = IngestClient(...)

def send_with_retry(record, max_retries=3):
    """Send with application-level retry logic."""
    for attempt in range(max_retries):
        try:
            client.send(record)
            return True
        except NonRetriableException as e:
            # Don't retry - fix the data
            log.error(f"Data error: {e}")
            return False
        except ZerobusException as e:
            # Retryable error
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # Exponential backoff
    
    return False
```

### Monitoring

```sql
-- Check table update frequency
DESCRIBE HISTORY events;

-- Monitor ingestion rate
SELECT 
    date_trunc('minute', _ingestion_timestamp) as minute,
    count(*) as events_per_minute
FROM events
WHERE _ingestion_timestamp > current_timestamp() - interval 1 hour
GROUP BY 1
ORDER BY 1 DESC;
```

## Limitations & Considerations

| Limitation | Details | Mitigation |
|------------|---------|------------|
| **Delivery semantics** | At-least-once (duplicates possible) | Implement idempotent consumers |
| **Availability** | Single AZ (may experience downtime) | Design for retry |
| **Writes only** | Append-only to managed Delta tables | Use Delta for updates/deletes |
| **No schema evolution** | Table schema must match message | Plan schema changes carefully |
| **Message size** | 10 MB max per message | Compress large payloads |

## Comparison with Kafka

| Feature | Zerobus Ingest | Kafka |
|---------|----------------|-------|
| **Management** | Fully managed | Self-managed or MSK |
| **Delivery** | At-least-once | Exactly-once available |
| **Retention** | None (direct to Delta) | Configurable retention |
| **Consumers** | Single (Delta table) | Multiple subscribers |
| **Latency** | ~50ms | ~10ms |
| **Throughput** | 100 MB/s | Higher with partitioning |
| **Cost** | Lower for simple ingestion | Higher operational cost |
| **Use case** | Direct Lakehouse writes | Complex streaming topologies |

## Best Practices

1. **Create table first** - Always create the target Delta table before starting ingestion
2. **Handle duplicates** - Implement idempotent processing downstream
3. **Monitor table history** - Use `DESCRIBE HISTORY` to track ingestion
4. **Use clustering** - Cluster by frequently filtered columns for query performance
5. **Batch when possible** - Use `send_batch()` for higher throughput
6. **Implement retries** - Handle transient failures gracefully

## Troubleshooting

### Issue: Records not appearing in table

**Diagnostics:**
```sql
-- Check table exists and has data
SELECT count(*) FROM your_table;

-- Check recent history
DESCRIBE HISTORY your_table;

-- Look for schema errors in client logs
```

**Solutions:**
1. Verify table exists before sending
2. Check schema matches between message and table
3. Monitor client logs for rejected records

### Issue: High latency

**Solutions:**
1. Ensure client and endpoint are in same region
2. Use batching instead of individual sends
3. Check network connectivity

### Issue: Schema validation errors

**Solutions:**
1. Ensure table schema matches message structure
2. Handle null values appropriately
3. Check data types match exactly

## Attribution

This skill is based on content from **Databricks Zerobus — The Best Bus Is No Bus** from the Databricksters blog.

## Related Resources

- [Zerobus Ingest Documentation](https://docs.databricks.com/aws/en/ingestion/zerobus-ingest)
- [Python SDK](https://github.com/databricks/zerobus-sdk-py)
- [Go SDK](https://github.com/databricks/zerobus-sdk-go)
- [Java SDK](https://github.com/databricks/zerobus-sdk-java)
