# Reverse ETL with Lakebase Autoscaling

## Overview

Reverse ETL allows you to sync data from Unity Catalog Delta tables into Lakebase Autoscaling as PostgreSQL tables. This enables OLTP access patterns on data processed in the Lakehouse.

## How It Works

Synced tables create a managed copy of Unity Catalog data in Lakebase:

1. A new Unity Catalog table (read-only, managed by the sync pipeline)
2. A Postgres table in Lakebase (queryable by applications)

The sync pipeline uses managed Lakeflow Spark Declarative Pipelines to continuously update both tables.

### Performance

- **Continuous writes:** ~1,200 rows/sec per CU
- **Bulk writes:** ~15,000 rows/sec per CU
- **Connections used:** Up to 16 per synced table

## Sync Modes

| Mode | Description | Best For | Notes |
|------|-------------|----------|-------|
| **Snapshot** | One-time full copy | Initial setup, historical analysis | 10x more efficient if modifying >10% of data |
| **Triggered** | Scheduled updates on demand | Dashboards updated hourly/daily | Requires CDF on source table |
| **Continuous** | Real-time streaming (seconds of latency) | Live applications | Highest cost, minimum 15s intervals, requires CDF |

**Note:** Triggered and Continuous modes require Change Data Feed (CDF) enabled on the source table:

```sql
ALTER TABLE your_catalog.your_schema.your_table
SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
```

## Creating Synced Tables

### Using Python SDK

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    SyncedDatabaseTable,
    SyncedTableSpec,
    NewPipelineSpec,
    SyncedTableSchedulingPolicy,
)

w = WorkspaceClient()

# Create a synced table
synced_table = w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="lakebase_catalog.schema.synced_table",
        spec=SyncedTableSpec(
            source_table_full_name="analytics.gold.user_profiles",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
            new_pipeline_spec=NewPipelineSpec(
                storage_catalog="lakebase_catalog",
                storage_schema="staging"
            )
        ),
    )
)
print(f"Created synced table: {synced_table.name}")
```

### Using CLI

```bash
databricks database create-synced-database-table \
    --json '{
        "name": "lakebase_catalog.schema.synced_table",
        "spec": {
            "source_table_full_name": "analytics.gold.user_profiles",
            "primary_key_columns": ["user_id"],
            "scheduling_policy": "TRIGGERED",
            "new_pipeline_spec": {
                "storage_catalog": "lakebase_catalog",
                "storage_schema": "staging"
            }
        }
    }'
```

## Checking Synced Table Status

```python
status = w.database.get_synced_database_table(name="lakebase_catalog.schema.synced_table")
print(f"State: {status.data_synchronization_status.detailed_state}")
print(f"Message: {status.data_synchronization_status.message}")
```

## Deleting a Synced Table

Delete from both Unity Catalog and Postgres:

1. **Unity Catalog:** Delete from Catalog Explorer or SDK
2. **Postgres:** Drop the table to free storage

```sql
DROP TABLE your_database.your_schema.your_table;
```

## Data Type Mapping

| Unity Catalog Type | Postgres Type |
|-------------------|---------------|
| BIGINT | BIGINT |
| BINARY | BYTEA |
| BOOLEAN | BOOLEAN |
| DATE | DATE |
| DECIMAL(p,s) | NUMERIC |
| DOUBLE | DOUBLE PRECISION |
| FLOAT | REAL |
| INT | INTEGER |
| INTERVAL | INTERVAL |
| SMALLINT | SMALLINT |
| STRING | TEXT |
| TIMESTAMP | TIMESTAMP WITH TIME ZONE |
| TIMESTAMP_NTZ | TIMESTAMP WITHOUT TIME ZONE |
| TINYINT | SMALLINT |
| ARRAY | JSONB |
| MAP | JSONB |
| STRUCT | JSONB |

**Unsupported types:** GEOGRAPHY, GEOMETRY, VARIANT, OBJECT

## Capacity Planning

- **Connection usage:** Each synced table uses up to 16 connections
- **Size limits:** 2 TB total across all synced tables; recommend < 1 TB per table
- **Naming:** Database, schema, and table names only allow `[A-Za-z0-9_]+`
- **Schema evolution:** Only additive changes (e.g., adding columns) for Triggered/Continuous modes

## Use Cases

### Product Catalog for Web App

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ecommerce_catalog.public.products",
        spec=SyncedTableSpec(
            source_table_full_name="gold.products.catalog",
            primary_key_columns=["product_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
        ),
    )
)
```

### Real-time Feature Serving

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ml_catalog.public.user_features",
        spec=SyncedTableSpec(
            source_table_full_name="ml.features.user_features",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.CONTINUOUS,
        ),
    )
)
```

## Best Practices

1. **Enable CDF** on source tables before creating Triggered or Continuous synced tables
2. **Choose appropriate sync mode**: Snapshot for small tables, Triggered for hourly/daily, Continuous for real-time
3. **Monitor sync status**: Check for failures and latency via Catalog Explorer
4. **Index target tables**: Create appropriate indexes in Postgres for your query patterns
5. **Handle schema changes**: Only additive changes are supported for streaming modes
6. **Account for connection limits**: Each synced table uses up to 16 connections
