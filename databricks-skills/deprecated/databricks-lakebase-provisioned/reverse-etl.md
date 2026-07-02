# Reverse ETL with Lakebase Provisioned

## Overview

Reverse ETL allows you to sync data from Unity Catalog Delta tables into Lakebase Provisioned as PostgreSQL tables. This enables OLTP access patterns on data processed in the Lakehouse.

## Sync Modes

| Mode | Description | Best For | Notes |
|------|-------------|----------|-------|
| **Snapshot** | One-time full copy | Initial setup, small tables | 10x more efficient if modifying >10% of data |
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
    SyncedTableSchedulingPolicy,
)

w = WorkspaceClient()

# Create a synced table from Unity Catalog to Lakebase Provisioned
synced_table = w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="lakebase_catalog.schema.synced_table",
        database_instance_name="my-lakebase-instance",
        spec=SyncedTableSpec(
            source_table_full_name="analytics.gold.user_profiles",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
        ),
    )
)
print(f"Created synced table: {synced_table.name}")
```

**Key parameters:**

| Parameter | Description |
|-----------|-------------|
| `name` | Fully qualified target table name (catalog.schema.table) |
| `database_instance_name` | Lakebase Provisioned instance name |
| `source_table_full_name` | Fully qualified source Delta table (catalog.schema.table) |
| `primary_key_columns` | List of primary key columns from the source table |
| `scheduling_policy` | `SNAPSHOT`, `TRIGGERED`, or `CONTINUOUS` |

### Using CLI

```bash
databricks database create-synced-database-table \
    --json '{
        "name": "lakebase_catalog.schema.synced_table",
        "database_instance_name": "my-lakebase-instance",
        "spec": {
            "source_table_full_name": "analytics.gold.user_profiles",
            "primary_key_columns": ["user_id"],
            "scheduling_policy": "TRIGGERED"
        }
    }'
```

**Note:** There is no SQL syntax for creating synced tables. Use the Python SDK, CLI, or Catalog Explorer UI.

## Checking Synced Table Status

```python
status = w.database.get_synced_database_table(name="lakebase_catalog.schema.synced_table")
print(f"State: {status.data_synchronization_status.detailed_state}")
print(f"Message: {status.data_synchronization_status.message}")
```

## Deleting a Synced Table

Delete from both Unity Catalog and Postgres:

1. **Unity Catalog:** Delete via Catalog Explorer or SDK
2. **Postgres:** Drop the table to free storage

```python
# Delete the synced table via SDK
w.database.delete_synced_database_table(name="lakebase_catalog.schema.synced_table")
```

```sql
-- Drop the Postgres table to free storage
DROP TABLE your_database.your_schema.your_table;
```

## Use Cases

### 1. Product Catalog for Web App

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ecommerce_catalog.public.products",
        database_instance_name="ecommerce-db",
        spec=SyncedTableSpec(
            source_table_full_name="gold.products.catalog",
            primary_key_columns=["product_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
        ),
    )
)
# Application queries PostgreSQL directly with low-latency point lookups
```

### 2. User Profiles for Authentication

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="auth_catalog.public.user_profiles",
        database_instance_name="auth-db",
        spec=SyncedTableSpec(
            source_table_full_name="gold.users.profiles",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.CONTINUOUS,
        ),
    )
)
```

### 3. Feature Store for Real-time ML

```python
w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="ml_catalog.public.user_features",
        database_instance_name="feature-store-db",
        spec=SyncedTableSpec(
            source_table_full_name="ml.features.user_features",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.CONTINUOUS,
        ),
    )
)
# ML model queries features with low latency
```

## Best Practices

1. **Enable CDF** on source tables before creating Triggered or Continuous synced tables
2. **Choose appropriate sync mode**: Snapshot for small tables or one-time loads, Triggered for hourly/daily refreshes, Continuous for real-time
3. **Monitor sync status**: Check for failures and latency via Catalog Explorer or `get_synced_database_table()`
4. **Index target tables**: Create appropriate indexes in PostgreSQL for your query patterns
5. **Handle schema changes**: Only additive changes (e.g., adding columns) are supported for Triggered/Continuous modes
6. **Account for connection limits**: Each synced table uses up to 16 connections

## Common Issues

| Issue | Solution |
|-------|----------|
| **Sync fails with CDF error** | Enable Change Data Feed on source table before using Triggered or Continuous mode |
| **Schema mismatch** | Only additive schema changes are supported; for breaking changes, delete and recreate the synced table |
| **Sync takes too long** | Switch to Triggered mode for scheduled updates; use Snapshot for initial bulk loads |
| **Target table locked** | Avoid DDL on target during sync operations |
