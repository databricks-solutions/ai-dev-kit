# Table Diagnostics

## When to Use

Use these commands to diagnose table health, understand data layout, and identify optimization opportunities.

## DESCRIBE DETAIL

Returns table metadata including format, size, file count, and clustering configuration:

```sql
DESCRIBE DETAIL catalog.schema.my_table;
```

Key columns returned:

| Column | Description | Example |
|--------|-------------|---------|
| `format` | Table format | `delta` |
| `name` | Fully qualified name | `main.schema.table` |
| `location` | Storage path | `s3://bucket/path/tables/...` |
| `clusteringColumns` | Liquid clustering columns | `["category","region"]` |
| `numFiles` | Number of data files | `42` |
| `sizeInBytes` | Total data size | `1048576` |
| `partitionColumns` | Hive partition columns | `["date"]` |
| `minReaderVersion` | Delta protocol reader version | `3` |
| `minWriterVersion` | Delta protocol writer version | `7` |
| `tableFeatures` | Enabled Delta features | `["clustering","deletionVectors",...]` |
| `clusterByAuto` | Predictive optimization enabled | `false` |

### Diagnosing Issues

```sql
-- Check if table needs OPTIMIZE (many small files)
SELECT numFiles, sizeInBytes,
       ROUND(sizeInBytes / numFiles / 1024 / 1024, 1) as avg_file_mb
FROM (DESCRIBE DETAIL catalog.schema.my_table);
-- Target: avg_file_mb between 64-256 MB
```

## DESCRIBE HISTORY

Shows the transaction log — every operation performed on the table:

```sql
DESCRIBE HISTORY catalog.schema.my_table LIMIT 20;
```

Key columns:

| Column | Description |
|--------|-------------|
| `version` | Transaction version number |
| `timestamp` | When the operation occurred |
| `operation` | Operation type (WRITE, OPTIMIZE, VACUUM, CLUSTER BY, etc.) |
| `operationParameters` | Parameters used |
| `operationMetrics` | Metrics (rows written, files added/removed) |

### Common Operations in History

| Operation | Meaning |
|-----------|---------|
| `WRITE` | Data was inserted/appended |
| `MERGE` | MERGE INTO was executed |
| `DELETE` | Rows were deleted |
| `OPTIMIZE` | Files were compacted |
| `VACUUM START` / `VACUUM END` | Old files were cleaned up |
| `CLUSTER BY` | Clustering columns were changed |
| `SET TBLPROPERTIES` | Table properties were modified |

## ANALYZE TABLE

Computes column-level statistics for the query optimizer:

```sql
ANALYZE TABLE catalog.schema.my_table
COMPUTE STATISTICS FOR ALL COLUMNS;
```

For specific columns:

```sql
ANALYZE TABLE catalog.schema.my_table
COMPUTE STATISTICS FOR COLUMNS category, region, amount;
```

## SHOW TBLPROPERTIES

Displays all table properties including Delta configuration:

```sql
SHOW TBLPROPERTIES catalog.schema.my_table;
```

Key properties for optimization:

| Property | Description |
|----------|-------------|
| `clusteringColumns` | Current liquid clustering columns |
| `delta.enableDeletionVectors` | Whether deletion vectors are enabled |
| `delta.enableRowTracking` | Whether row tracking is enabled |
| `delta.checkpointPolicy` | Checkpoint format (v2 = optimized) |
| `delta.parquet.compression.codec` | Compression codec (zstd = default) |

## Performance Diagnosis Workflow

1. **Check file count and sizes:**
   ```sql
   DESCRIBE DETAIL catalog.schema.my_table;
   -- If numFiles > 1000 or avg file < 32MB → run OPTIMIZE
   ```

2. **Check clustering alignment:**
   ```sql
   -- Verify clustering columns match your query patterns
   SELECT clusteringColumns FROM (DESCRIBE DETAIL catalog.schema.my_table);
   ```

3. **Check recent operations:**
   ```sql
   -- See if OPTIMIZE has been running
   DESCRIBE HISTORY catalog.schema.my_table LIMIT 10;
   ```

4. **Compute fresh statistics:**
   ```sql
   ANALYZE TABLE catalog.schema.my_table COMPUTE STATISTICS FOR ALL COLUMNS;
   ```
