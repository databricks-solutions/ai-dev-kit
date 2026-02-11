---
name: zerobus-ingest
description: "Build Zerobus Ingest clients for near real-time data ingestion into Databricks Delta tables via gRPC. Use when creating producers that write directly to Unity Catalog tables without a message bus, working with the Zerobus Ingest SDK in Python/Java/Go/TypeScript/Rust, generating Protobuf schemas from UC tables, or implementing stream-based ingestion with ACK handling and retry logic."
---

# Zerobus Ingest

Build clients that ingest data directly into Databricks Delta tables via the Zerobus gRPC API.

**Status:** Public Preview (currently free; Databricks plans to introduce charges in the future)

**Documentation:**
- [Zerobus Overview](https://docs.databricks.com/aws/en/ingestion/zerobus-overview)
- [Zerobus Ingest SDK](https://docs.databricks.com/aws/en/ingestion/zerobus-ingest)
- [Zerobus Limits](https://docs.databricks.com/aws/en/ingestion/zerobus-limits)

---

## What Is Zerobus Ingest?

Zerobus Ingest is a serverless connector that enables direct, record-by-record data ingestion into Delta tables via gRPC. It eliminates the need for message bus infrastructure (Kafka, Kinesis, Event Hub) for lakehouse-bound data. The service validates schemas, materializes data to target tables, and sends durability acknowledgments back to the client.

**Core pattern:** SDK init -> create stream -> ingest records -> handle ACKs -> flush -> close

---

## Quick Decision: What Are You Building?

| Scenario | Language | Serialization | Reference |
|----------|----------|---------------|-----------|
| Quick prototype / test harness | Python | JSON | [2-python-client.md](2-python-client.md) |
| Production Python producer | Python | Protobuf | [2-python-client.md](2-python-client.md) + [4-protobuf-schema.md](4-protobuf-schema.md) |
| JVM microservice | Java | Protobuf | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| Go service | Go | JSON or Protobuf | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| Node.js / TypeScript app | TypeScript | JSON | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| High-performance system service | Rust | JSON or Protobuf | [3-multilanguage-clients.md](3-multilanguage-clients.md) |
| Schema generation from UC table | Any | Protobuf | [4-protobuf-schema.md](4-protobuf-schema.md) |
| Retry / reconnection logic | Any | Any | [5-operations-and-limits.md](5-operations-and-limits.md) |

---

## Prerequisites

Before writing a Zerobus client, you need:

1. **A Unity Catalog managed Delta table** to ingest into
2. **A service principal** with `MODIFY` and `SELECT` on the target table
3. **The Zerobus server endpoint** for your workspace region
4. **The Zerobus Ingest SDK** installed for your target language

See [1-setup-and-authentication.md](1-setup-and-authentication.md) for complete setup instructions.

---

## Minimal Python Example (JSON)

```python
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties

sdk = ZerobusSdk(server_endpoint, workspace_url)
options = StreamConfigurationOptions(record_type=RecordType.JSON)
table_props = TableProperties(table_name)

stream = sdk.create_stream(client_id, client_secret, table_props, options)
try:
    record = {"device_name": "sensor-1", "temp": 22, "humidity": 55}
    ack = stream.ingest_record(record)
    ack.wait_for_ack()
finally:
    stream.close()
```

---

## Reference Files

| Topic | File | When to Read |
|-------|------|--------------|
| Setup & Auth | [1-setup-and-authentication.md](1-setup-and-authentication.md) | Endpoint formats, service principals, SDK install |
| Python Client | [2-python-client.md](2-python-client.md) | Sync/async Python, JSON and Protobuf flows, reusable client class |
| Multi-Language | [3-multilanguage-clients.md](3-multilanguage-clients.md) | Java, Go, TypeScript, Rust SDK examples |
| Protobuf Schema | [4-protobuf-schema.md](4-protobuf-schema.md) | Generate .proto from UC table, compile, type mappings |
| Operations & Limits | [5-operations-and-limits.md](5-operations-and-limits.md) | ACK handling, retries, reconnection, throughput limits, constraints |

---

## Workflow

1. **Setting up a new Zerobus client?** -> Read [1-setup-and-authentication.md](1-setup-and-authentication.md)
2. **Building a Python producer?** -> Read [2-python-client.md](2-python-client.md)
3. **Building in Java/Go/TypeScript/Rust?** -> Read [3-multilanguage-clients.md](3-multilanguage-clients.md)
4. **Need type-safe Protobuf ingestion?** -> Read [4-protobuf-schema.md](4-protobuf-schema.md)
5. **Production hardening / understanding limits?** -> Read [5-operations-and-limits.md](5-operations-and-limits.md)

---

## Key Concepts

- **gRPC + Protobuf**: Zerobus uses gRPC as its transport protocol. Any application that can communicate via gRPC and construct Protobuf messages can produce to Zerobus.
- **JSON or Protobuf serialization**: JSON for quick starts; Protobuf for type safety, forward compatibility, and performance.
- **At-least-once delivery**: The connector provides at-least-once guarantees. Design consumers to handle duplicates.
- **Durability ACKs**: Each ingested record returns an ACK confirming durable write. ACKs indicate all records up to that offset have been durably written.
- **No table management**: Zerobus does not create or alter tables. You must pre-create your target table and manage schema evolution yourself.
- **Single-AZ durability**: The service runs in a single availability zone. Plan for potential zone outages.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Connection refused** | Verify server endpoint format matches your cloud (AWS vs Azure). Check firewall allowlists. |
| **Authentication failed** | Confirm service principal client_id/secret. Verify GRANT statements on the target table. |
| **Schema mismatch** | Ensure record fields match the target table schema exactly. Regenerate .proto if table changed. |
| **Stream closed unexpectedly** | Implement retry with exponential backoff and stream reinitialization. See [5-operations-and-limits.md](5-operations-and-limits.md). |
| **Throughput limits hit** | Max 100 MB/s and 15,000 rows/s per stream. Open multiple streams or contact Databricks. |
| **Region not supported** | Check supported regions in [5-operations-and-limits.md](5-operations-and-limits.md). |
| **Table not found** | Ensure table is a managed Delta table in a supported region with correct three-part name. |

---

## Resources

- [Zerobus Overview](https://docs.databricks.com/aws/en/ingestion/zerobus-overview)
- [Zerobus Ingest SDK](https://docs.databricks.com/aws/en/ingestion/zerobus-ingest)
- [Zerobus Limits](https://docs.databricks.com/aws/en/ingestion/zerobus-limits)
