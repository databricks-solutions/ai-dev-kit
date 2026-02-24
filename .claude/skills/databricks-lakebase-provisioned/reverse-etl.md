# Reverse ETL with Lakebase

## Overview

Reverse ETL allows you to sync data from Unity Catalog Delta tables into Lakebase Provisioned as PostgreSQL tables. This enables OLTP access patterns on data processed in the Lakehouse.

## Creating Synced Tables

### Using Python SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create a synced table from Unity Catalog
synced_table = w.database.create_synced_table(
    instance_name="my-lakebase-instance",
    source_table_name="catalog.schema.source_table",
    target_table_name="target_table",
    sync_mode="FULL",  # FULL or INCREMENTAL
)

print(f"Synced table created: {synced_table.target_table_name}")
```

### Using SQL

```sql
-- Create synced table via SQL
CREATE SYNCED TABLE my_lakebase.target_table
FROM catalog.schema.source_table
USING LAKEBASE INSTANCE 'my-lakebase-instance';
```

### Using CLI

```bash
databricks database create-synced-table \
    --instance-name my-lakebase-instance \
    --source-table-name catalog.schema.source_table \
    --target-table-name target_table \
    --sync-mode FULL
```

## Sync Modes

### Full Sync

Complete replacement of target table on each sync:

```python
synced_table = w.database.create_synced_table(
    instance_name="my-lakebase-instance",
    source_table_name="catalog.schema.customers",
    target_table_name="customers",
    sync_mode="FULL"
)
```

**Use when:**
- Source table is small-medium size
- Need complete consistency with source
- Incremental changes are complex to track

### Incremental Sync

Only sync changed rows (requires change tracking):

```python
synced_table = w.database.create_synced_table(
    instance_name="my-lakebase-instance",
    source_table_name="catalog.schema.events",
    target_table_name="events",
    sync_mode="INCREMENTAL",
    incremental_column="updated_at"  # Column to track changes
)
```

**Use when:**
- Source table is large
- Have reliable change tracking column
- Minimize sync time and resource usage

## Managing Synced Tables

### List Synced Tables

```python
synced_tables = w.database.list_synced_tables(
    instance_name="my-lakebase-instance"
)
for table in synced_tables:
    print(f"{table.target_table_name}: {table.sync_status}")
```

### Trigger Manual Sync

```python
w.database.sync_table(
    instance_name="my-lakebase-instance",
    table_name="customers"
)
```

### Delete Synced Table

```python
w.database.delete_synced_table(
    instance_name="my-lakebase-instance",
    table_name="customers"
)
```

## Scheduling Syncs

### Using Databricks Jobs

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Task, NotebookTask, CronSchedule

w = WorkspaceClient()

# Create job to sync tables on schedule
job = w.jobs.create(
    name="Lakebase Sync Job",
    tasks=[
        Task(
            task_key="sync_customers",
            notebook_task=NotebookTask(
                notebook_path="/Repos/sync/sync_customers"
            )
        )
    ],
    schedule=CronSchedule(
        quartz_cron_expression="0 0 * * * ?",  # Every hour
        timezone_id="UTC"
    )
)
```

### Sync Notebook Example

```python
# Databricks notebook: sync_customers

from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Trigger sync for specific tables
tables_to_sync = ["customers", "orders", "products"]

for table in tables_to_sync:
    try:
        w.database.sync_table(
            instance_name="my-lakebase-instance",
            table_name=table
        )
        print(f"Synced: {table}")
    except Exception as e:
        print(f"Failed to sync {table}: {e}")
```

## Use Cases

### 1. Product Catalog for Web App

```python
# Sync product data for e-commerce app
w.database.create_synced_table(
    instance_name="ecommerce-db",
    source_table_name="gold.products.catalog",
    target_table_name="products",
    sync_mode="FULL"
)

# Application queries PostgreSQL directly
# with low-latency point lookups
```

### 2. User Profiles for Authentication

```python
# Sync user profiles for auth service
w.database.create_synced_table(
    instance_name="auth-db",
    source_table_name="gold.users.profiles",
    target_table_name="user_profiles",
    sync_mode="INCREMENTAL",
    incremental_column="last_modified"
)
```

### 3. Feature Store for Real-time ML

```python
# Sync features for online serving
w.database.create_synced_table(
    instance_name="feature-store-db",
    source_table_name="ml.features.user_features",
    target_table_name="user_features",
    sync_mode="INCREMENTAL",
    incremental_column="computed_at"
)

# ML model queries features with low latency
```

## Best Practices

1. **Choose appropriate sync mode**: Use FULL for small tables, INCREMENTAL for large tables with change tracking
2. **Schedule during low-traffic periods**: Heavy syncs can impact both source and target
3. **Monitor sync status**: Check for failures and latency
4. **Index target tables**: Create appropriate indexes in PostgreSQL for query patterns
5. **Handle schema changes**: Synced tables need updates when source schema changes

## Common Issues

| Issue | Solution |
|-------|----------|
| **Sync takes too long** | Switch to INCREMENTAL mode; add indexes on source |
| **Schema mismatch** | Drop and recreate synced table after source schema changes |
| **Sync fails with timeout** | Increase sync timeout; reduce batch size |
| **Target table locked** | Avoid DDL on target during sync operations |
