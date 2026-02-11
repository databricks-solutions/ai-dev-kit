# Zerobus Ingest

Build clients that ingest data directly into Databricks Delta tables via the Zerobus gRPC API.

## Overview

This skill provides end-to-end guidance for building Zerobus Ingest clients that write records directly into Unity Catalog Delta tables without intermediate message bus infrastructure. It activates when users need to create data producers using the Zerobus Ingest SDK, generate Protobuf schemas from UC tables, implement stream-based ingestion with ACK handling, or build near real-time ingestion pipelines. The skill covers five languages (Python, Java, Go, TypeScript, Rust) with both JSON and Protobuf serialization paths, plus production hardening patterns for retries, reconnection, and throughput management.

## What's Included

```
zerobus-ingest/
├── SKILL.md                          # Main skill: overview, quick decision matrix, minimal example, workflow
├── 1-setup-and-authentication.md     # Endpoint formats, service principals, SDK installation per language
├── 2-python-client.md                # Sync/async Python client, JSON and Protobuf flows, reusable class
├── 3-multilanguage-clients.md        # Java, Go, TypeScript/Node.js, and Rust SDK examples
├── 4-protobuf-schema.md              # Generate .proto from UC tables, compile bindings, type mappings
└── 5-operations-and-limits.md        # ACK handling, retry/reconnection, throughput limits, constraints
```

## Key Topics

- Zerobus server endpoint formats for AWS and Azure
- Service principal authentication and table grants
- SDK installation for Python, Java, Go, TypeScript, and Rust
- Stream lifecycle: init SDK -> create stream -> ingest -> ACK -> flush -> close
- JSON ingestion for rapid prototyping
- Protobuf ingestion for type-safe production workloads
- Generating .proto schemas from Unity Catalog table definitions
- Compiling Protobuf bindings for Python, Java, Go
- Synchronous and asynchronous ACK handling patterns
- Retry with exponential backoff and stream reinitialization
- Throughput limits (100 MB/s, 15,000 rows/s per stream)
- At-least-once delivery semantics
- Supported regions and operational constraints
- Delta-to-Protobuf type mappings

## When to Use

- Building a data producer that writes directly to a Databricks Delta table
- Creating a near real-time ingestion pipeline without Kafka/Kinesis/Event Hub
- Working with the `databricks-zerobus-ingest-sdk` in any supported language
- Generating Protobuf schemas from Unity Catalog table definitions
- Implementing stream management with ACK handling and retry logic
- Understanding Zerobus throughput limits and operational constraints
- Migrating from message bus architectures to direct lakehouse ingestion

## Related Skills

- [Databricks Python SDK](../databricks-python-sdk/) -- General SDK patterns and WorkspaceClient for table/schema management
- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- Downstream pipeline processing of ingested data
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- Managing catalogs, schemas, and tables that Zerobus writes to
- [Synthetic Data Generation](../synthetic-data-generation/) -- Generate test data to feed into Zerobus producers
- [Databricks Config](../databricks-config/) -- Profile and authentication setup

## Resources

- [Zerobus Overview](https://docs.databricks.com/aws/en/ingestion/zerobus-overview)
- [Zerobus Ingest SDK](https://docs.databricks.com/aws/en/ingestion/zerobus-ingest)
- [Zerobus Limits](https://docs.databricks.com/aws/en/ingestion/zerobus-limits)
