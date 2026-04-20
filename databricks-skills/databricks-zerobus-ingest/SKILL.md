---
name: databricks-zerobus-ingest
description: "Build Zerobus Ingest clients for near real-time data ingestion into Databricks Delta tables via gRPC. Use when creating producers that write directly to Unity Catalog tables without a message bus, working with the Zerobus Ingest SDK in Python/Java/Go/TypeScript/Rust, generating Protobuf schemas from UC tables, or implementing stream-based ingestion with ACK handling and retry logic."
---

# Zerobus Ingest

Build clients that ingest data directly into Databricks Delta tables via the Zerobus gRPC API.

**Status:** GA (Generally Available since February 2026; billed under Lakeflow Jobs Serverless SKU)

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

If not specified, default to python.

---

## Common Libraries

These libraries are essential for ZeroBus data ingestion:

- **databricks-sdk>=0.85.0**: Databricks workspace client for authentication and metadata
- **databricks-zerobus-ingest-sdk>=1.0.0**: ZeroBus SDK for high-performance streaming ingestion
- **grpcio-tools**
These are typically NOT pre-installed on Databricks. Install them using `execute_code` tool:
- `code`: "%pip install databricks-sdk>=VERSION databricks-zerobus-ingest-sdk>=VERSION"

Save the returned `cluster_id` and `context_id` for subsequent calls.

Smart Installation Approach

# Check protobuf version first, then install compatible 
grpcio-tools
import google.protobuf
runtime_version = google.protobuf.__version__
print(f"Runtime protobuf version: {runtime_version}")

if runtime_version.startswith("5.26") or
runtime_version.startswith("5.29"):
    %pip install grpcio-tools==1.62.0
else:
    %pip install grpcio-tools  # Use latest for newer protobuf 
versions
---

## Prerequisites

You must never execute the skill without confirming the below objects are valid: 

1. **A Unity Catalog managed Delta table** to ingest into
2. **A service principal id and secret** with `MODIFY` and `SELECT` on the target table
3. **The Zerobus server endpoint** for your workspace region
4. **The Zerobus Ingest SDK** installed for your target language

See [1-setup-and-authentication.md](1-setup-and-authentication.md) for complete setup instructions.

---

## Minimal Python Example (JSON)

```python
import json
from zerobus.sdk.sync import ZerobusSdk
from zerobus.sdk.shared import RecordType, StreamConfigurationOptions, TableProperties

sdk = ZerobusSdk(server_endpoint, workspace_url)
options = StreamConfigurationOptions(record_type=RecordType.JSON)
table_props = TableProperties(table_name)

stream = sdk.create_stream(client_id, client_secret, table_props, options)
try:
    record = {"device_name": "sensor-1", "temp": 22, "humidity": 55}
    stream.ingest_record(json.dumps(record))
    stream.flush()
finally:
    stream.close()
```

---

## Detailed guides

| Topic | File | When to Read |
|-------|------|--------------|
| Setup & Auth | [1-setup-and-authentication.md](1-setup-and-authentication.md) | Endpoint formats, service principals, SDK install |
| Python Client | [2-python-client.md](2-python-client.md) | Sync/async Python, JSON and Protobuf flows, reusable client class |
| Multi-Language | [3-multilanguage-clients.md](3-multilanguage-clients.md) | Java, Go, TypeScript, Rust SDK examples |
| Protobuf Schema | [4-protobuf-schema.md](4-protobuf-schema.md) | Generate .proto from UC table, compile, type mappings |
| Operations & Limits | [5-operations-and-limits.md](5-operations-and-limits.md) | ACK handling, retries, reconnection, throughput limits, constraints |

---

You must always follow all the steps in the Workflow

## Workflow
0. **Display the plan of your execution**
1. **Determine the type of client**
2. **Get schema** Always use 4-protobuf-schema.md
3. **Write Python code to a local file** following the instructions in the relevant guide (e.g., `scripts/zerobus_ingest.py`)
4. **Upload to workspace**: `databricks workspace import-dir ./scripts /Workspace/Users/<user>/scripts`
5. **Execute on Databricks** using a job or notebook
6. **If execution fails**: Edit the local file, re-upload, and re-execute

---

## Important
- Never install local packages
- **Serverless limitation**: The Zerobus SDK cannot pip-install on serverless compute. Use classic compute clusters, or use the [Zerobus REST API](https://docs.databricks.com/aws/en/ingestion/zerobus-rest-api) (Beta) for notebook-based ingestion without the SDK.
- **Explicit table grants**: Service principals need explicit `MODIFY` and `SELECT` grants on the target table. Schema-level inherited permissions may not be sufficient for the `authorization_details` OAuth flow.

---

### Execution Workflow

**Step 1: Upload code to workspace**
```bash
databricks workspace import-dir ./scripts /Workspace/Users/<user>/scripts
```

**Step 2: Create and run a job**
```bash
databricks jobs create --json '{
  "name": "zerobus-ingest",
  "tasks": [{
    "task_key": "ingest",
    "spark_python_task": {
      "python_file": "/Workspace/Users/<user>/scripts/zerobus_ingest.py"
    },
    "new_cluster": {
      "spark_version": "16.1.x-scala2.12",
      "node_type_id": "i3.xlarge",
      "num_workers": 0
    }
  }]
}'

databricks jobs run-now JOB_ID
```

**If execution fails:**
1. Read the error from the job run output
2. Edit the local Python file to fix the issue
3. Re-upload: `databricks workspace import-dir ./scripts /Workspace/Users/<user>/scripts`
4. Re-run: `databricks jobs run-now JOB_ID`

---

### Installing Libraries

Databricks provides Spark, pandas, numpy, and common data libraries by default. **Only install a library if you get an import error.**

Add to the job configuration:
```json
"libraries": [
  {"pypi": {"package": "databricks-zerobus-ingest-sdk>=1.0.0"}}
]
```

Or use init scripts in the cluster configuration.

## 🚨 Critical Learning: Timestamp Format Fix

**BREAKTHROUGH**: ZeroBus requires **timestamp fields as Unix integer timestamps**, NOT string timestamps.
The timestamp generation must use microseconds for Databricks.

---

## Key Concepts

- **gRPC + Protobuf**: Zerobus uses gRPC as its transport protocol. Any application that can communicate via gRPC and construct Protobuf messages can produce to Zerobus.
- **JSON or Protobuf serialization**: JSON for quick starts; Protobuf for type safety, forward compatibility, and performance.
- **At-least-once delivery**: The connector provides at-least-once guarantees. Design consumers to handle duplicates.
- **Durability ACKs**: Each ingested record returns a `RecordAcknowledgment`. Use `flush()` to ensure all buffered records are durably written, or use `wait_for_offset(offset)` for offset-based tracking.
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
| **SDK install fails on serverless** | The Zerobus SDK cannot be pip-installed on serverless compute. Use classic compute clusters or the REST API (Beta) from notebooks. |
| **Error 4024 / authorization_details** | Service principal lacks explicit table-level grants. Grant `MODIFY` and `SELECT` directly on the target table — schema-level inherited grants may be insufficient. |

---

## Related Skills

- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - General SDK patterns and WorkspaceClient for table/schema management
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Downstream pipeline processing of ingested data
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Managing catalogs, schemas, and tables that Zerobus writes to
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate test data to feed into Zerobus producers
- **[databricks-config](../databricks-config/SKILL.md)** - Profile and authentication setup

## Resources

- [Zerobus Overview](https://docs.databricks.com/aws/en/ingestion/zerobus-overview)
- [Zerobus Ingest SDK](https://docs.databricks.com/aws/en/ingestion/zerobus-ingest)
- [Zerobus Limits](https://docs.databricks.com/aws/en/ingestion/zerobus-limits)
