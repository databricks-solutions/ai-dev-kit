# Lakebase Autoscaling — Reverse ETL (deep dive)

Deep dive for synced tables. Basic CLI is in [SKILL.md](SKILL.md).

## How Synced Tables Work

A synced table is a managed replica of a Unity Catalog Delta table, materialized into Lakebase as a queryable Postgres table. Two artifacts are created:

1. A **Unity Catalog synced table** (read-only from the user's perspective, owned by the sync pipeline)
2. A **Postgres table** inside the Lakebase database, updated by the same pipeline

The pipeline is a managed Lakeflow Spark Declarative Pipeline that runs on Databricks compute — the user doesn't provision it directly.

## Performance Envelope

| Mode | Throughput (per CU) | Latency |
|------|---------------------|---------|
| Continuous writes | ~1,200 rows/s | seconds |
| Bulk writes (initial load / snapshot) | ~15,000 rows/s | minutes-hours depending on size |

Each synced table uses **up to 16 connections** on the target endpoint. Account for this when sizing concurrency-heavy apps alongside reverse ETL on the same endpoint.

## Sync Modes

| Mode | Mechanism | Best for | Requires CDF |
|------|-----------|----------|--------------|
| `SNAPSHOT` | One-shot full copy | Initial load, historical analysis, small reference tables; use when you'd modify >10% of data anyway | No |
| `TRIGGERED` | Scheduled incremental updates | Dashboards refreshed hourly/daily | Yes |
| `CONTINUOUS` | Streaming, min 15 s intervals | Real-time features, live apps (highest cost) | Yes |

Enable CDF on the source before creating TRIGGERED or CONTINUOUS synced tables:

```sql
ALTER TABLE your_catalog.your_schema.your_table
SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
```

## Data Type Mapping (UC → Postgres)

| Unity Catalog | Postgres |
|---------------|----------|
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
| ARRAY / MAP / STRUCT | JSONB |

**Unsupported:** GEOGRAPHY, GEOMETRY, VARIANT, OBJECT.

## Naming & Schema Rules

- Database, schema, and table names: `[A-Za-z0-9_]+` only.
- Schema evolution on TRIGGERED/CONTINUOUS: **additive only** (new columns). Breaking changes require dropping and re-creating the synced table.
- Primary key column(s) on the source are required and must be unique.

## Capacity Planning

| Dimension | Limit / guideline |
|-----------|-------------------|
| Connections used per synced table | up to 16 |
| Total synced-table size per branch | 2 TB |
| Recommended size per synced table | < 1 TB |
| CDF retention on source | Longer than the sync pipeline's commit cadence |

## Deletion

Synced tables exist in two places — drop both:

1. Remove the UC synced table (Catalog Explorer, CLI, or SDK).
2. Drop the Postgres table to free branch storage:

```sql
DROP TABLE your_database.your_schema.your_table;
```

## Best Practices

- Enable CDF **before** creating TRIGGERED/CONTINUOUS tables, not after — the initial snapshot won't include incremental updates otherwise.
- Pick the cheapest mode that meets latency: most dashboards are fine on TRIGGERED hourly.
- Index Postgres targets for your query patterns — synced tables arrive without indexes.
- Monitor pipeline status (`data_synchronization_status`) — it surfaces backpressure and schema mismatches before they affect readers.
- Keep reverse-ETL pipelines on their own branch (or at least a sized-up endpoint) when running alongside OLTP traffic.

## Example Use Cases

Product catalog for a web app (hourly refresh is plenty):

```bash
databricks database create-synced-database-table \
    --json '{"name": "ecommerce_catalog.public.products",
             "spec": {"source_table_full_name": "gold.products.catalog",
                      "primary_key_columns": ["product_id"],
                      "scheduling_policy": "TRIGGERED"}}'
```

Real-time feature serving for ML (needs CDF on `ml.features.user_features`):

```bash
databricks database create-synced-database-table \
    --json '{"name": "ml_catalog.public.user_features",
             "spec": {"source_table_full_name": "ml.features.user_features",
                      "primary_key_columns": ["user_id"],
                      "scheduling_policy": "CONTINUOUS"}}'
```

## SDK Equivalents

Synced tables use the `w.database` SDK module (not `w.postgres`):

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    SyncedDatabaseTable, SyncedTableSpec,
    NewPipelineSpec, SyncedTableSchedulingPolicy,
)

w = WorkspaceClient()

w.database.create_synced_database_table(
    SyncedDatabaseTable(
        name="lakebase_catalog.schema.synced_table",
        spec=SyncedTableSpec(
            source_table_full_name="analytics.gold.user_profiles",
            primary_key_columns=["user_id"],
            scheduling_policy=SyncedTableSchedulingPolicy.TRIGGERED,
            new_pipeline_spec=NewPipelineSpec(
                storage_catalog="lakebase_catalog",
                storage_schema="staging",
            ),
        ),
    )
)

status = w.database.get_synced_database_table(name="lakebase_catalog.schema.synced_table")
print(status.data_synchronization_status.detailed_state)
```
