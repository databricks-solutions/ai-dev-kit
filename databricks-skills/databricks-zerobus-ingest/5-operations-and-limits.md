# Operations and Limits

ACK handling, retry and reconnection patterns, throughput limits, delivery semantics, and operational constraints for Zerobus Ingest.

---

## Acknowledgment (ACK) Handling

Every ingested record returns a durability acknowledgment. An ACK indicates that **all records up to that offset** have been durably written to the target Delta table.

### Strategies

| Strategy | When to Use | Trade-off |
|----------|-------------|-----------|
| **Sync block per record** | Low-volume, strict ordering | Simplest; lower throughput |
| **ACK callback** | High-volume producers | Higher throughput; more complex |
| **Periodic flush** | Batch-oriented workloads | Best throughput; eventual consistency |

### Sync Block (Python)

```python
ack = stream.ingest_record(record)
ack.wait_for_ack()  # Blocks until durable
```

### ACK Callback (Python)

```python
from zerobus.sdk.shared import IngestRecordResponse

last_acked_offset = 0

def on_ack(response: IngestRecordResponse) -> None:
    global last_acked_offset
    last_acked_offset = response.durability_ack_up_to_offset

options = StreamConfigurationOptions(
    record_type=RecordType.JSON,
    ack_callback=on_ack,
)
```

### Flush-Based

```python
# Send many records without blocking
for record in batch:
    stream.ingest_record(record)

# Flush ensures all buffered records are sent
stream.flush()
```

---

## Retry and Reconnection

Zerobus streams can close due to server maintenance, network issues, or zone failures. Implement retry with exponential backoff and stream reinitialization.

### Pattern (Any Language)

```
1. Attempt ingest
2. On connection/closed error:
   a. Close the current stream
   b. Wait with exponential backoff (1s, 2s, 4s, ...)
   c. Reinitialize the stream
   d. Retry the record
3. After max retries, log failure and escalate
```

### Python Implementation

```python
import time
import logging

logger = logging.getLogger(__name__)

def ingest_with_retry(stream_factory, record, max_retries=5):
    """Ingest a record with retry and stream reinitialization.

    Args:
        stream_factory: Callable that returns a new stream.
        record: The record to ingest.
        max_retries: Maximum retry attempts.
    """
    stream = stream_factory()

    for attempt in range(max_retries):
        try:
            ack = stream.ingest_record(record)
            ack.wait_for_ack()
            return stream  # Return the (possibly new) stream
        except Exception as e:
            err = str(e).lower()
            logger.warning("Attempt %d/%d failed: %s", attempt + 1, max_retries, e)

            if "closed" in err or "connection" in err or "unavailable" in err:
                try:
                    stream.close()
                except Exception:
                    pass
                backoff = min(2 ** attempt, 30)  # Cap at 30s
                time.sleep(backoff)
                stream = stream_factory()
            elif attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise

    return stream
```

### Key Points

- **Always reinitialize the stream** on connection errors, not just retry the same stream
- **Cap backoff** at a reasonable maximum (e.g., 30 seconds)
- **Log failures** with enough context to diagnose (endpoint, table, error message)
- **Design for at-least-once**: your downstream consumers should handle duplicate records

---

## Delivery Semantics

Zerobus provides **at-least-once** delivery guarantees:

- Records may be delivered more than once (e.g., after a retry where the original was actually persisted)
- There is **no exactly-once** semantics
- Design your target table and downstream consumers to handle duplicates (e.g., deduplication via `MERGE` or unique constraints)

---

## Throughput Limits

| Limit | Value | Notes |
|-------|-------|-------|
| **Throughput per stream** | 100 MB/s | Based on 1 KB messages |
| **Rows per stream** | 15,000 rows/s | |
| **Max message size** | 10 MB (10,485,760 bytes) | Per individual record |
| **Max columns** | 2,000 | Per proto schema / table |

### Scaling Beyond One Stream

If you need higher throughput than a single stream provides:

- Open **multiple streams** to the same table from different clients
- Zerobus supports **thousands of concurrent clients** writing to the same table
- Partition your data across streams by key (e.g., device ID, region)
- Contact Databricks for custom throughput requirements

---

## Regional Availability

Workspace and target tables must be in a supported region for your cloud provider.

### AWS Supported Regions

| Region | Code |
|--------|------|
| US East (N. Virginia) | `us-east-1` |
| US East (Ohio) | `us-east-2` |
| US West (Oregon) | `us-west-2` |
| Europe (Frankfurt) | `eu-central-1` |
| Europe (Ireland) | `eu-west-1` |
| Asia Pacific (Singapore) | `ap-southeast-1` |
| Asia Pacific (Sydney) | `ap-southeast-2` |
| Asia Pacific (Tokyo) | `ap-northeast-1` |
| Canada (Central) | `ca-central-1` |

### Azure Supported Regions

| Region | Code |
|--------|------|
| Canada Central | `canadacentral` |
| West US | `westus` |
| East US | `eastus` |
| East US 2 | `eastus2` |
| Central US | `centralus` |
| North Central US | `northcentralus` |
| Sweden Central | `swedencentral` |
| West Europe | `westeurope` |
| North Europe | `northeurope` |
| Australia East | `australiaeast` |
| Southeast Asia | `southeastasia` |

**Performance note:** Optimal throughput requires the client application and Zerobus endpoint to be in the **same region**.

---

## Durability and Availability

- **Single-AZ only**: Zerobus runs in a single availability zone. The service may experience downtime if that zone is unavailable.
- **No geographic redundancy**: Plan for zone outages in your producer's retry logic.
- **Maintenance windows**: The server may close streams during maintenance. Your client should handle reconnection gracefully.

---

## Target Table Constraints

| Constraint | Details |
|------------|---------|
| **Table type** | Managed Delta tables only (no external storage) |
| **Table names** | ASCII letters, digits, underscores only |
| **Schema changes** | No auto-evolution; regenerate proto and redeploy |
| **Table creation** | Zerobus does not create tables; pre-create via SQL DDL |
| **Table recreation** | Cannot recreate an existing target table via Zerobus |

---

## Supported Data Types

| Delta Type | Protobuf Type | Conversion Notes |
|------------|---------------|------------------|
| STRING | string | Direct mapping |
| INT / INTEGER | int32 | Direct mapping |
| LONG / BIGINT | int64 | Direct mapping |
| FLOAT | float | Direct mapping |
| DOUBLE | double | Direct mapping |
| BOOLEAN | bool | Direct mapping |
| BINARY | bytes | Direct mapping |
| ARRAY\<T\> | repeated T | Recursive mapping |
| MAP\<K,V\> | map\<K,V\> | Key must be string or integer |
| STRUCT | nested message | Recursive mapping |
| DATE | int32 | Epoch days since 1970-01-01 |
| TIMESTAMP | int64 | Epoch microseconds |
| VARIANT | string | JSON-encoded string |

---

## Monitoring and Observability

Zerobus does not currently expose built-in metrics dashboards. Monitor your producers with:

- **Application-level logging**: Log ACK offsets, retry counts, and error rates
- **ACK callback tracking**: Track the last-acked offset to measure ingestion lag
- **Table row counts**: Periodically query the target table to verify data is arriving
- **Health checks**: Attempt a lightweight ingest (or stream creation) to verify connectivity

```python
# Simple health check
def check_zerobus_health(sdk, client_id, client_secret, table_props, options):
    try:
        stream = sdk.create_stream(client_id, client_secret, table_props, options)
        stream.close()
        return True
    except Exception as e:
        logger.error("Zerobus health check failed: %s", e)
        return False
```
