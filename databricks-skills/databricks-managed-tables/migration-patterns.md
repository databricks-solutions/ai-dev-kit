# Migration Patterns: External to Managed Tables

## When to Use

Use these patterns when migrating existing external tables to managed tables to gain predictive optimization, automatic maintenance, and full Unity Catalog governance.

## Why Migrate?

External tables miss out on:
- **Predictive optimization** — no automatic OPTIMIZE/VACUUM
- **Automatic clustering maintenance** — liquid clustering requires manual OPTIMIZE
- **Full DROP semantics** — managed tables clean up completely
- **Simplified governance** — managed storage is fully controlled by UC

## Migration Methods

### Method 1: DEEP CLONE (Recommended)

Creates a new managed table as a full copy. The original external table is untouched.

```sql
-- Clone external table to a new managed table (no LOCATION = managed)
CREATE TABLE catalog.schema.my_table_managed
DEEP CLONE catalog.schema.my_table_external;

-- Verify it's managed
DESCRIBE TABLE EXTENDED catalog.schema.my_table_managed;
-- Type: MANAGED
-- Is_managed_location: true

-- Verify row count matches
SELECT
    (SELECT count(*) FROM catalog.schema.my_table_external) as external_count,
    (SELECT count(*) FROM catalog.schema.my_table_managed) as managed_count;

-- Add liquid clustering on the new managed table
ALTER TABLE catalog.schema.my_table_managed
CLUSTER BY (frequently_filtered_column);

-- Enable predictive optimization
ALTER TABLE catalog.schema.my_table_managed
SET TBLPROPERTIES (
    'delta.autoOptimize.autoCompact' = 'auto',
    'delta.autoOptimize.optimizeWrite' = 'true'
);

-- Once validated, update downstream consumers to point to the new table
-- Then drop the old external table when ready
```

**Advantages:**
- Zero downtime — original table stays available
- Can validate before switching
- Preserves table history in the clone

**Considerations:**
- Doubles storage temporarily (until old table is dropped)
- Large tables may take significant time to clone

### Method 2: CTAS (Create Table As Select)

```sql
CREATE TABLE catalog.schema.my_table_managed AS
SELECT * FROM catalog.schema.my_table_external;

-- Add PK constraint if needed
ALTER TABLE catalog.schema.my_table_managed
ADD CONSTRAINT pk PRIMARY KEY (id);

-- Add clustering
ALTER TABLE catalog.schema.my_table_managed
CLUSTER BY (category, region);
```

**When to use:** When you want to transform or filter data during migration.

### Method 3: In-Place Conversion (Upgrade)

For tables that were originally created as managed but moved to external, or for converting external to managed within the same catalog:

```sql
-- This only works if the external location is within the metastore's managed storage
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES ('delta.universalFormat.enabledFormats' = 'iceberg');
-- Note: in-place conversion has limitations; DEEP CLONE is more reliable
```

## Migration Checklist

| Step | Action | Verification |
|------|--------|-------------|
| 1 | Identify external tables | `DESCRIBE TABLE EXTENDED` → `Type: EXTERNAL` |
| 2 | Check table size | `DESCRIBE DETAIL` → `sizeInBytes` |
| 3 | DEEP CLONE to managed | `CREATE TABLE ... DEEP CLONE ...` |
| 4 | Verify row count | Compare `count(*)` on both tables |
| 5 | Add clustering | `ALTER TABLE ... CLUSTER BY (...)` |
| 6 | Enable PO | `SET TBLPROPERTIES ('delta.autoOptimize.autoCompact' = 'auto')` |
| 7 | Run OPTIMIZE once | `OPTIMIZE catalog.schema.table` (initial compaction) |
| 8 | Update consumers | Point views/jobs/dashboards to new table |
| 9 | Validate | Run key queries, compare results |
| 10 | Drop old table | `DROP TABLE catalog.schema.my_table_external` |

## Batch Migration Script

For migrating multiple tables:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
wh_id = "<warehouse-id>"

tables_to_migrate = [
    ("catalog.schema.external_table1", "catalog.schema.managed_table1", ["col_a"]),
    ("catalog.schema.external_table2", "catalog.schema.managed_table2", ["col_b", "col_c"]),
]

for source, target, cluster_cols in tables_to_migrate:
    print(f"Migrating {source} → {target}")

    # Clone
    w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=f"CREATE TABLE {target} DEEP CLONE {source}",
        wait_timeout="0s"  # async for large tables
    )

    # After clone completes, add clustering + PO
    cluster_by = ", ".join(cluster_cols)
    w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=f"ALTER TABLE {target} CLUSTER BY ({cluster_by})",
        wait_timeout="30s"
    )
    w.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=f"""ALTER TABLE {target} SET TBLPROPERTIES (
            'delta.autoOptimize.autoCompact' = 'auto',
            'delta.autoOptimize.optimizeWrite' = 'true'
        )""",
        wait_timeout="30s"
    )
    print(f"  ✓ {target} migrated with clustering on ({cluster_by})")
```

## Best Practices

1. **Always use managed tables for new tables** — no reason to use external unless sharing storage with non-Databricks tools
2. **Enable PO at the schema level** so all new tables inherit it automatically
3. **Migrate external tables in batches** during low-traffic windows
4. **Validate row counts** before and after migration
5. **Keep the external table** for a rollback window (1-2 weeks) before dropping
6. **Run OPTIMIZE once** after migration to apply initial clustering
