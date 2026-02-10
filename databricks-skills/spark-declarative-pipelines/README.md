# Spark Declarative Pipelines

Creates, configures, and updates Databricks Lakeflow Spark Declarative Pipelines (SDP/LDP) using serverless compute.

## Overview

This skill covers the end-to-end lifecycle of Spark Declarative Pipelines (formerly Delta Live Tables), including streaming tables, materialized views, CDC, SCD Type 2, and Auto Loader ingestion patterns. It activates when users build data pipelines, work with Delta Live Tables, ingest streaming data, implement change data capture, or mention SDP, LDP, DLT, Lakeflow, streaming tables, or bronze/silver/gold medallion architectures. The skill supports both Asset Bundle initialization (`databricks pipelines init`) and manual MCP-driven workflows using SQL or the modern `pyspark.pipelines` Python API.

## What's Included

```
spark-declarative-pipelines/
├── SKILL.md
├── 1-ingestion-patterns.md
├── 2-streaming-patterns.md
├── 3-scd-patterns.md
├── 4-performance-tuning.md
├── 5-python-api.md
├── 6-dlt-migration.md
├── 7-advanced-configuration.md
└── 8-project-initialization.md
```

## Key Topics

- Auto Loader ingestion with `read_files()` for JSON, CSV, Parquet, and Avro from cloud storage
- Streaming sources: Kafka, Event Hub, Kinesis
- Deduplication, windowed aggregations, and stateful streaming operations
- Change Data Capture (CDC) with AUTO CDC and SCD Type 1/Type 2 patterns
- Querying SCD Type 2 history tables with `__START_AT` / `__END_AT` temporal columns
- Liquid Clustering (`CLUSTER BY`) replacing legacy `PARTITION BY` and `Z-ORDER`
- Modern Python API (`pyspark.pipelines` as `dp`) vs. legacy DLT API (`import dlt`)
- DLT-to-SDP migration decision matrix and step-by-step guide
- Advanced configuration via `extra_settings` (development mode, continuous pipelines, Photon, Python dependencies)
- Project initialization with `databricks pipelines init` and Asset Bundles
- Medallion architecture (bronze/silver/gold) with flat or subdirectory layouts
- Serverless compute requirements, constraints, and when to fall back to classic clusters

## When to Use

- Creating a new data pipeline on Databricks
- Ingesting files from cloud storage using Auto Loader
- Building streaming tables or materialized views
- Implementing change data capture (CDC) or slowly changing dimensions (SCD Type 2)
- Migrating existing Delta Live Tables (DLT) pipelines to the modern SDP framework
- Setting up a medallion architecture (bronze/silver/gold layers)
- Configuring pipeline performance with Liquid Clustering
- Initializing a new pipeline project with Asset Bundles
- Debugging pipeline errors (empty tables, streaming read failures, column not found)

## Related Skills

- [Databricks Jobs](../databricks-jobs/) -- for orchestrating and scheduling pipeline runs
- [Asset Bundles](../asset-bundles/) -- for multi-environment deployment of pipeline projects
- [Synthetic Data Generation](../synthetic-data-generation/) -- for generating test data to feed into pipelines
- [Databricks Unity Catalog](../databricks-unity-catalog/) -- for catalog/schema/volume management and governance

## Resources

- [Lakeflow Spark Declarative Pipelines Overview](https://docs.databricks.com/aws/en/ldp/)
- [SQL Language Reference](https://docs.databricks.com/aws/en/ldp/developer/sql-dev)
- [Python Language Reference](https://docs.databricks.com/aws/en/ldp/developer/python-ref)
- [Loading Data (Auto Loader, Kafka, Kinesis)](https://docs.databricks.com/aws/en/ldp/load)
- [Change Data Capture (CDC)](https://docs.databricks.com/aws/en/ldp/cdc)
- [Developing Pipelines](https://docs.databricks.com/aws/en/ldp/develop)
- [Liquid Clustering](https://docs.databricks.com/aws/en/delta/clustering)
- [read_files -- Usage in Streaming Tables](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files#usage-in-streaming-tables)
