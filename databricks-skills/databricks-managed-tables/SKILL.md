---
name: databricks-managed-tables
description: "Unity Catalog managed tables with predictive optimization. Covers managed vs external tables, predictive optimization setup, and automatic maintenance. Use when creating tables, choosing managed vs external, or enabling auto-optimization."
---

# Databricks Managed Tables & Predictive Optimization

The single most impactful optimization on Databricks: use **Unity Catalog managed tables** with **predictive optimization** enabled. This eliminates manual OPTIMIZE/VACUUM and lets Databricks automatically maintain your tables.

## When to Use

- Creating new Delta tables (always prefer managed)
- Enabling predictive optimization on existing managed tables
- Understanding the trade-offs between managed and external tables
- Setting up zero-maintenance table lifecycle

## The #1 Best Practice: Managed + Predictive Optimization

```sql
-- Step 1: Create a managed table (no LOCATION clause)
CREATE TABLE catalog.schema.my_table (
    id BIGINT,
    category STRING,
    amount DOUBLE
) CLUSTER BY (category);

-- Step 2: Enable auto-optimization
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES (
    'delta.autoOptimize.autoCompact' = 'auto',
    'delta.autoOptimize.optimizeWrite' = 'true'
);

-- That's it. Databricks handles OPTIMIZE and VACUUM automatically.
```

With this setup:
- **OPTIMIZE** runs automatically when file compaction is needed
- **VACUUM** runs automatically to clean up old files
- **Liquid clustering** is maintained automatically during compaction
- **No cron jobs, no manual maintenance, no forgotten tables**

## Managed vs External Tables

| Aspect | Managed Table | External Table |
|--------|--------------|----------------|
| **Storage** | Databricks-managed location | User-specified LOCATION |
| **Predictive optimization** | Full support | Not supported |
| **Auto OPTIMIZE/VACUUM** | Yes (when PO enabled) | No — manual only |
| **DROP TABLE** | Deletes data + metadata | Deletes metadata only |
| **Data governance** | Full UC governance | UC metadata only |
| **Recommended for** | All new tables | Legacy/shared storage only |

### How to Tell if a Table is Managed

```sql
DESCRIBE TABLE EXTENDED catalog.schema.my_table;
-- Look for:
--   Type: MANAGED
--   Is_managed_location: true
```

Or via DESCRIBE DETAIL:

```sql
DESCRIBE DETAIL catalog.schema.my_table;
-- Managed tables have location under the metastore's managed storage path
-- e.g., s3://bucket/<metastore-id>/tables/<table-uuid>
```

## Predictive Optimization

Predictive optimization is Databricks' automatic table maintenance system. It monitors table health and runs OPTIMIZE and VACUUM when needed — no manual scheduling required.

### Enable at Table Level

```sql
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES (
    'delta.autoOptimize.autoCompact' = 'auto',
    'delta.autoOptimize.optimizeWrite' = 'true'
);
```

| Property | Value | Effect |
|----------|-------|--------|
| `delta.autoOptimize.autoCompact` | `'auto'` | Auto-compacts small files after writes |
| `delta.autoOptimize.optimizeWrite` | `'true'` | Optimizes file sizes during writes |

### Enable at Schema Level (All Tables)

```sql
ALTER SCHEMA catalog.schema
SET DBPROPERTIES (
    'delta.autoOptimize.autoCompact' = 'auto',
    'delta.autoOptimize.optimizeWrite' = 'true'
);
```

New tables in this schema inherit these properties automatically.

### Verify Predictive Optimization Status

```sql
-- Check table properties
SHOW TBLPROPERTIES catalog.schema.my_table;
-- Look for: delta.autoOptimize.autoCompact = auto
--           delta.autoOptimize.optimizeWrite = true

-- Check clusterByAuto in DESCRIBE DETAIL
DESCRIBE DETAIL catalog.schema.my_table;
-- clusterByAuto: false (manual) or true (auto-managed)
```

### Monitor Predictive Optimization Operations

Query the system table to see what PO has done:

```sql
SELECT
    catalog_name,
    schema_name,
    table_name,
    operation_type,
    operation_status,
    start_time,
    end_time,
    usage_quantity,
    usage_unit
FROM system.storage.predictive_optimization_operations_history
WHERE catalog_name = 'my_catalog'
ORDER BY start_time DESC
LIMIT 20;
```

System table columns:

| Column | Description |
|--------|-------------|
| `operation_type` | `COMPACTION`, `VACUUM`, `CLUSTERING` |
| `operation_status` | `SUCCESSFUL`, `FAILED`, `SKIPPED` |
| `usage_quantity` | DBUs consumed |
| `usage_unit` | Always `DBU` |
| `start_time` / `end_time` | Operation window |

## Common Issues

| Issue | Solution |
|-------|----------|
| **`delta.enableOptimizeWrite` unknown config** | Use `delta.autoOptimize.optimizeWrite` instead (the property name changed) |
| **PO not running on external tables** | Predictive optimization only works on managed tables — migrate first |
| **`clusterByAuto` is false** | Set `delta.autoOptimize.autoCompact = 'auto'` on the table |
| **DROP TABLE deleted my data** | This is expected for managed tables — use external tables if you need data to survive DROP |
| **Can't create external table** | Need an external location registered in UC for the target path |
| **PO operations not in system table** | Check `system.storage.predictive_optimization_operations_history` — may take hours to appear |
