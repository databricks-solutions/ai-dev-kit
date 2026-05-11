# Reverse ETL / synced tables

Reverse ETL syncs Unity Catalog Delta tables into Lakebase Autoscaling as PostgreSQL tables for OLTP access.

Important namespace split:
- Lakebase Autoscaling infrastructure: `w.postgres`
- Synced tables: `w.database`

Reverse ETL is Delta-to-Postgres only; Postgres-to-Delta sync is not supported here.

## How synced tables work

A synced table creates/maintains:
1. A managed/read-only Unity Catalog table for pipeline state/output.
2. A PostgreSQL table in Lakebase queried by apps.

The sync pipeline uses managed Lakeflow Spark Declarative Pipelines.

Performance planning:
- Continuous writes: ~1,200 rows/sec per CU.
- Bulk writes: ~15,000 rows/sec per CU.
- Each synced table can use up to 16 Postgres connections.

## Sync modes

| Mode | Behavior | Use when | CDF required |
|---|---|---|---|
| `SNAPSHOT` | one-time full copy | initial loads, historical copy, large replacement | no |
| `TRIGGERED` | scheduled/on-demand incremental updates | hourly/daily operational refresh | yes |
| `CONTINUOUS` | streaming updates, seconds latency | live applications | yes |

Triggered and Continuous require Delta Change Data Feed on the source table:

```sql
ALTER TABLE catalog.schema.table
SET TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

Snapshot can be more efficient when modifying >10% of the data.

## Create a synced table

Use `databricks.sdk.service.database` models:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.database import (
    NewPipelineSpec,
    SyncedDatabaseTable,
    SyncedTableSchedulingPolicy,
    SyncedTableSpec,
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
```

Status:

```python
st = w.database.get_synced_database_table(
    name="lakebase_catalog.schema.synced_table"
)
state = st.data_synchronization_status.detailed_state
message = st.data_synchronization_status.message
```

Deletion cleanup:
1. Delete the synced table / UC object.
2. Drop the Postgres target table if needed to free Lakebase storage.

```sql
DROP TABLE schema.table;
```

## Type mapping

| Unity Catalog | Postgres |
|---|---|
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

Unsupported:
- `GEOGRAPHY`
- `GEOMETRY`
- `VARIANT`
- `OBJECT`

## Limits and gotchas

- Up to 16 Postgres connections per synced table; include this in endpoint connection-capacity planning.
- Size limit: 2 TB total across all synced tables.
- Recommended: <1 TB per synced table.
- Database/schema/table names: `[A-Za-z0-9_]+`.
- Triggered/Continuous schema evolution: additive changes only.
- Create indexes in Postgres for application query patterns after sync.
- Monitor detailed sync state in Catalog Explorer or with `get_synced_database_table`.
- Delete synced-table dependencies before deleting the Lakebase project.
