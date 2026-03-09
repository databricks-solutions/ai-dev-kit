# Migration Patterns: Converting to Managed Tables

## When to Use

Use these patterns when migrating existing external or foreign tables to Unity Catalog managed tables to gain predictive optimization, automatic maintenance, and full governance.

## Why Migrate?

External and foreign tables miss out on:
- **Predictive optimization** — no automatic OPTIMIZE/VACUUM/clustering
- **Automatic maintenance** — must schedule manual OPTIMIZE and VACUUM jobs
- **Full DROP semantics** — managed tables clean up data + metadata completely
- **Simplified governance** — managed storage is fully controlled by Unity Catalog

## External to Managed: `SET MANAGED` (Recommended)

`ALTER TABLE ... SET MANAGED` is the **recommended** way to convert external tables to managed. It is superior to DEEP CLONE or CTAS because it:

- Minimizes reader and writer downtime
- Handles concurrent writes during conversion
- Retains full table history
- Keeps the same table name, settings, permissions, and views
- Supports rollback via `UNSET MANAGED` within 14 days

**Requires:** Databricks Runtime 17.0+ or Serverless compute. All readers/writers must use name-based access (not path-based).

### Basic Conversion

```sql
-- For tables WITHOUT UniForm (Iceberg reads) enabled
ALTER TABLE catalog.schema.my_external_table SET MANAGED;

-- For tables WITH UniForm (Iceberg reads) already enabled (requires DBR 17.2+)
ALTER TABLE catalog.schema.my_external_table SET MANAGED TRUNCATE UNIFORM HISTORY;
```

### Verify Conversion

```sql
DESCRIBE EXTENDED catalog.schema.my_external_table;
-- Type should now show: MANAGED
```

### How SET MANAGED Works

1. **Initial data copy (no downtime):** Data and Delta log are copied from external to managed location. Readers and writers continue normally.
2. **Switch to managed location (brief downtime):** Remaining commits are moved, metadata is updated. Writers are briefly blocked. Readers on DBR 16.1+ experience no downtime.

### Estimated Conversion Times

| Table Size | Recommended Compute | Data Copy Time | Downtime |
|-----------|-------------------|---------------|----------|
| ≤100 GB | 32-core / XL warehouse | ~6 min | ~1-2 min |
| 1 TB | 64-core / 2XL warehouse | ~30 min | ~1-2 min |
| 10 TB | 256-core / 4XL warehouse | ~1.5 hrs | ~1-5 min |

### Rollback (Within 14 Days)

```sql
ALTER TABLE catalog.schema.my_managed_table UNSET MANAGED;
-- Table reverts to EXTERNAL, original data location is restored
```

After rollback, Databricks deletes data in the managed location after 7 days.

### Post-Conversion Steps

1. **Restart streaming jobs** — any streaming readers/writers must be restarted
2. **Verify readers/writers** — confirm all consumers work with the managed table
3. **Predictive optimization** — automatically enabled after conversion (unless manually disabled)
4. **VACUUM after 14 days** — Databricks auto-deletes external location data via PO; if PO is disabled, run `VACUUM` manually

### Important Precautions

- **Cancel OPTIMIZE jobs** before conversion — cancel any running OPTIMIZE, liquid clustering, compaction, or ZORDER jobs on the table
- **Don't run multiple SET MANAGED** on the same table concurrently
- **All access must be name-based** — path-based access (`delta.\`s3://...\``) is not supported and may cause data corruption
- If interrupted, rerun `SET MANAGED` — it resumes from where it left off

## Foreign to Managed: `SET MANAGED {MOVE | COPY}`

For tables federated from external catalogs (HMS, AWS Glue), use `SET MANAGED` with either `MOVE` or `COPY` mode.

**Requires:** Databricks Runtime 17.3+, Delta Lake format, `OWNER`/`MANAGE` on table + `CREATE` on external location. Currently in Public Preview.

### MOVE Mode (Recommended)

Converts the table and **disables access** from the external catalog:

```sql
ALTER TABLE catalog.schema.my_foreign_table SET MANAGED MOVE;
```

- Access through the external catalog or path-based access fails after conversion
- All readers/writers must use Unity Catalog namespace
- Supports rollback:

```sql
-- Rollback: table becomes external, then re-federates as foreign on next sync
ALTER TABLE catalog.schema.my_managed_table UNSET MANAGED;
```

**Warning:** You MUST run `UNSET MANAGED` before dropping a moved table. Dropping without `UNSET MANAGED` can cause data loss.

### COPY Mode

Converts the table **without disrupting** the source in the external catalog:

```sql
ALTER TABLE catalog.schema.my_foreign_table SET MANAGED COPY;
```

- Creates a separate managed copy — two copies of data exist
- Source table in external catalog remains accessible
- Rollback: just drop the managed table; source re-federates on next catalog sync
- You are responsible for migrating workloads and disabling access to the source

### MOVE vs COPY

| Aspect | MOVE | COPY |
|--------|------|------|
| Source table access after conversion | Disabled | Still accessible |
| Data copies | 1 (moved) | 2 (original + managed) |
| Rollback method | `UNSET MANAGED` | Drop table |
| Risk of dual-write conflicts | None | Possible if source not disabled |
| Recommended for | Production cutover | Gradual migration |

## Batch Migration at Schema/Catalog Level

For converting entire schemas or catalogs, use the discoverx labs project:

```python
df = (dx.from_tables("prod.*.*")
    .with_sql("ALTER TABLE {full_table_name} SET MANAGED;")
    .apply())
```

Or iterate with the SDK:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "<warehouse-id>"

# Find all external tables in a schema
tables = w.statement_execution.execute_statement(
    warehouse_id=wh_id,
    statement="""
        SELECT table_catalog, table_schema, table_name
        FROM system.information_schema.tables
        WHERE table_catalog = 'my_catalog'
          AND table_schema = 'my_schema'
          AND table_type = 'EXTERNAL'
    """,
    wait_timeout="30s"
)

for row in tables.result.data_array:
    full_name = f"{row[0]}.{row[1]}.{row[2]}"
    print(f"Converting {full_name}...")
    w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=f"ALTER TABLE {full_name} SET MANAGED",
        wait_timeout="0s"  # async for large tables
    )
```

## Migration Checklist

| Step | Action | Verification |
|------|--------|-------------|
| 1 | Identify external/foreign tables | `DESCRIBE TABLE EXTENDED` → `Type: EXTERNAL` or `FOREIGN` |
| 2 | Check table size | `DESCRIBE DETAIL` → `sizeInBytes` |
| 3 | Cancel running OPTIMIZE/ZORDER jobs | Verify no active maintenance jobs |
| 4 | Verify all access is name-based | No `delta.\`path\`` access patterns |
| 5 | Run `ALTER TABLE ... SET MANAGED` | Command completes without error |
| 6 | Verify conversion | `DESCRIBE EXTENDED` → `Type: MANAGED` |
| 7 | Restart streaming jobs | Stop and restart all streaming readers/writers |
| 8 | Verify predictive optimization | `SHOW TBLPROPERTIES` or check PO system table |
| 9 | Validate consumers | Run key queries, confirm dashboards/jobs work |
| 10 | VACUUM after 14 days | Run `VACUUM` if PO is disabled (PO handles it automatically otherwise) |

## Common Conversion Errors

| Error | Cause | Solution |
|-------|-------|---------|
| `DELTA_TRUNCATED_TRANSACTION_LOG` | Table has `columnMapping` feature with specific protocol versions | Check `DESCRIBE DETAIL` for protocol versions |
| `DELTA_ALTER_TABLE_SET_MANAGED_INTERNAL_ERROR` | Cluster shut down during conversion | Retry the `SET MANAGED` command |
| `FILE_VALIDATION_FAILED` | Files missing from source location | Check Spark driver logs, verify source files exist, retry |
| `DELTA_TXN_LOG_FAILED_INTEGRITY` | Corrupted external table | Verify table health with `DESCRIBE DETAIL` first |

## Best Practices

1. **Use `SET MANAGED` over DEEP CLONE** — it's the official recommended approach with minimal downtime
2. **Always use managed tables for new tables** — no reason to use external unless sharing storage with non-Databricks tools
3. **Enable PO at the schema level** so all new tables inherit it automatically
4. **Cancel OPTIMIZE jobs** before running `SET MANAGED`
5. **Keep the 14-day rollback window** — don't drop external locations immediately
6. **Restart streaming jobs** after conversion — this is required, not optional
7. **For foreign tables, prefer MOVE** for clean cutover; use COPY for gradual migration
