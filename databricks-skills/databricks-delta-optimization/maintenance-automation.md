# Maintenance Automation

## When to Use

Use these patterns to automate table maintenance (OPTIMIZE, VACUUM) and migrate from legacy partitioning to liquid clustering.

## Predictive Optimization (Recommended)

For managed tables, **predictive optimization** eliminates the need for manual OPTIMIZE/VACUUM entirely. See the [databricks-managed-tables](../databricks-managed-tables/SKILL.md) skill for full setup, monitoring, and external-to-managed migration patterns.

Quick setup:

```sql
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES (
    'delta.autoOptimize.autoCompact' = 'auto',
    'delta.autoOptimize.optimizeWrite' = 'true'
);
```

**Note:** Use `delta.autoOptimize.optimizeWrite`, not `delta.enableOptimizeWrite` (the latter is invalid and throws `DELTA_UNKNOWN_CONFIGURATION`).

## Scheduled Maintenance with Jobs (External Tables)

### OPTIMIZE + VACUUM Job

Create a Databricks Job that runs maintenance on a schedule:

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create a SQL task for maintenance
w.jobs.create(
    name="delta-maintenance-weekly",
    tasks=[{
        "task_key": "optimize_tables",
        "sql_task": {
            "query": {
                "value": """
                    OPTIMIZE catalog.schema.table1;
                    OPTIMIZE catalog.schema.table2;
                    VACUUM catalog.schema.table1;
                    VACUUM catalog.schema.table2;
                """
            },
            "warehouse_id": "<warehouse-id>"
        }
    }],
    schedule={
        "quartz_cron_expression": "0 0 2 ? * SUN",
        "timezone_id": "UTC"
    }
)
```

### Notebook-Based Maintenance

For dynamic table discovery:

```python
tables = spark.sql("SHOW TABLES IN catalog.schema").collect()
for table in tables:
    full_name = f"catalog.schema.{table.tableName}"
    print(f"Optimizing {full_name}...")
    spark.sql(f"OPTIMIZE {full_name}")
    spark.sql(f"VACUUM {full_name}")
```

## Migration from Hive Partitioning to Liquid Clustering

### Step 1: Add Clustering (Non-Breaking)

```sql
ALTER TABLE catalog.schema.my_table
CLUSTER BY (category, region);
```

This does NOT rewrite existing data — it only affects future OPTIMIZE runs.

### Step 2: Run OPTIMIZE to Recluster

```sql
OPTIMIZE catalog.schema.my_table;
```

OPTIMIZE will reorganize data according to the new clustering columns.

### Step 3: Drop Old Partition Columns (Optional)

If the table was Hive-partitioned, the partition columns remain as regular columns. The partitioning metadata is superseded by liquid clustering.

### Migration Considerations

| Aspect | Detail |
|--------|--------|
| **Downtime** | None — ALTER CLUSTER BY is instant |
| **Data rewrite** | Only happens during OPTIMIZE, not ALTER |
| **Rollback** | `ALTER TABLE ... CLUSTER BY NONE` removes clustering |
| **Partition columns** | Remain as regular columns, still queryable |
| **Concurrent reads** | Unaffected during migration |

## Table Properties for Optimization

### Enable Optimized Writes

Reduces small files during writes:

```sql
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');
```

### Enable Deletion Vectors

Faster DELETE/UPDATE/MERGE operations:

```sql
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES ('delta.enableDeletionVectors' = 'true');
```

### Enable Row Tracking

Required for some advanced features:

```sql
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES ('delta.enableRowTracking' = 'true');
```

### Tune Target File Size

Default is ~1GB. For tables with many small queries:

```sql
ALTER TABLE catalog.schema.my_table
SET TBLPROPERTIES ('delta.targetFileSize' = '134217728');  -- 128 MB
```

## Best Practices

1. **Use liquid clustering for all new tables** — it's strictly better than partitioning + Z-order
2. **Run OPTIMIZE weekly** on tables with frequent writes
3. **Run VACUUM weekly** to reclaim storage (default 7-day retention)
4. **Choose 1-4 clustering columns** based on query filter patterns
5. **Enable optimized writes** for streaming and frequent small writes
6. **Monitor with DESCRIBE DETAIL** — check `numFiles` and `sizeInBytes` regularly
7. **Use managed tables + predictive optimization** — see [databricks-managed-tables](../databricks-managed-tables/SKILL.md) for the zero-maintenance approach
