---
name: databricks-vacuum
description: Optimize Delta Lake storage costs using VACUUM commands. Use when cleaning up old data files, reducing storage bloat, or maintaining Delta tables. Covers VACUUM FULL, VACUUM LITE, and VACUUM USING INVENTORY modes with practical guidance on when to use each.
author: Canadian Data Guy
source_url: https://www.databricksters.com/p/your-storage-bill-is-too-high-here
source_site: databricksters.com
---

# Delta Lake VACUUM Optimization

## Overview

Delta Lake's time travel feature preserves historical data files, enabling powerful capabilities like `VERSION AS OF` and `TIMESTAMP AS OF` queries. However, without proper cleanup, these accumulated files can dramatically inflate storage costs—sometimes leaving active data at just 18% of total storage footprint.

This skill covers three VACUUM modes to optimize storage:
- **VACUUM FULL**: Comprehensive cleanup (establishes baseline)
- **VACUUM LITE**: Fast routine cleanup (daily use)
- **VACUUM USING INVENTORY**: Specialized for petabyte-scale (complex setup)

## Quick Decision Guide

| Scenario | VACUUM Mode | Frequency |
|----------|-------------|-----------|
| First VACUUM on table | FULL | Once |
| Daily maintenance | LITE | Daily |
| After failed jobs | FULL | As needed |
| Compliance-critical cleanup | FULL | Weekly/Monthly |
| Petabyte-scale with dedicated platform team | USING INVENTORY | Weekly |

## Step-by-Step Instructions

### Step 1: Check Your Delta Lake Version

VACUUM LITE requires Delta Lake 3.3.0+ (Databricks Runtime 16.1+):

```sql
-- Check Delta Lake version
SELECT substring(version, 1, 5) as delta_version FROM (DESCRIBE HISTORY your_table LIMIT 1)
```

### Step 2: Run VACUUM FULL (Establish Baseline)

Required before first VACUUM LITE run or when recovering from errors:

```sql
-- Standard VACUUM FULL with 7-day retention (default)
VACUUM your_table RETAIN 168 HOURS

-- For tables with frequent updates, you may need longer retention
VACUUM your_table RETAIN 336 HOURS  -- 14 days
```

### Step 3: Schedule VACUUM LITE for Routine Cleanup

```sql
-- Fast daily cleanup (typically completes in minutes)
VACUUM your_table LITE RETAIN 168 HOURS
```

### Step 4: Verify VACUUM Success

```sql
-- Check table size before and after VACUUM
DESCRIBE DETAIL your_table

-- View file statistics
SELECT 
  num_files,
  size_in_bytes / 1024 / 1024 / 1024 as size_gb
FROM (DESCRIBE DETAIL your_table)
```

## Examples

### Example 1: Hybrid VACUUM Strategy

```sql
-- Weekly FULL VACUUM (run on Sunday mornings)
VACUUM high_churn_table RETAIN 168 HOURS

-- Daily LITE VACUUM (scheduled job)
VACUUM high_churn_table LITE RETAIN 168 HOURS
```

### Example 2: PySpark VACUUM with Error Handling

```python
from delta.tables import DeltaTable

# Get Delta table
delta_table = DeltaTable.forName(spark, "your_table")

# Run VACUUM LITE with 7-day retention
try:
    delta_table.vacuum(168, lite=True)
    print("VACUUM LITE completed successfully")
except Exception as e:
    if "DELTA_CANNOT_VACUUM_LITE" in str(e):
        print("Running VACUUM FULL to establish baseline...")
        delta_table.vacuum(168)  # FULL mode (default)
    else:
        raise
```

### Example 3: Cost-Optimized Single-Node VACUUM

For VACUUM LITE, a single-node cluster can be more cost-effective:

```python
# Configure single-node cluster for VACUUM
# Driver: 32-64 cores (compute-optimized)
# Workers: 0

# Run VACUUM
spark.sql("VACUUM your_table LITE RETAIN 168 HOURS")
```

## Cluster Configuration

### Standard Configuration (VACUUM FULL)

| Component | Recommendation |
|-----------|---------------|
| Workers | 1-4 (auto-scaling) |
| Instance type | Compute-optimized (AWS C5, Azure F-series, GCP C2) |
| Cores per worker | 8 |
| Driver cores | 8-32 |

### Cost-Optimized Configuration (VACUUM LITE)

| Component | Recommendation |
|-----------|---------------|
| Workers | 0 (single-node) |
| Driver | Large compute-optimized (32-64 cores) |
| Mode | Single-node cluster |

## Edge Cases & Troubleshooting

### Error: DELTA_CANNOT_VACUUM_LITE

**Problem**: VACUUM LITE fails with baseline error.

**Solution**: Run VACUUM FULL once to establish baseline:

```sql
VACUUM your_table RETAIN 168 HOURS
```

Then retry VACUUM LITE.

### Issue: VACUUM Taking Too Long

**Problem**: VACUUM FULL running for 30-60+ minutes on large tables.

**Solutions**:
1. Switch to VACUUM LITE for routine cleanup
2. Use single-node cluster configuration
3. Ensure you're not over-partitioned (check file counts)

### Issue: Storage Still High After VACUUM

**Problem**: Storage usage remains elevated post-VACUUM.

**Diagnostics**:

```sql
-- Check for unreferenced files
DESCRIBE DETAIL your_table

-- Review table history for large operations
DESCRIBE HISTORY your_table

-- Check if time travel retention is too long
SHOW TBLPROPERTIES your_table ('delta.logRetentionDuration')
```

### Issue: Compliance Requirements

**Problem**: Need guaranteed deletion for GDPR/CCPA compliance.

**Solution**: Use VACUUM FULL for compliance-critical scenarios:

```sql
-- Run FULL VACUUM for thorough cleanup
VACUUM sensitive_data_table RETAIN 168 HOURS

-- Verify deletion through cloud storage APIs
```

## Best Practices

1. **Use LITE for routine, FULL for baseline**: Schedule daily LITE runs with weekly FULL runs
2. **Monitor storage growth**: Track table size trends to catch bloat early
3. **Right-size retention**: Balance time travel needs with storage costs
4. **Consider single-node clusters**: For VACUUM LITE, reduce costs with driver-only execution
5. **Don't run OPTIMIZE after every write**: Let Predictive Optimization handle compaction

## Attribution

This skill is based on content by **Canadian Data Guy** from the Databricksters blog post:
[Your Storage Bill Is Too High. Here Are 3 Levels of VACUUM to Fix It](https://www.databricksters.com/p/your-storage-bill-is-too-high-here)

## Related Resources

- [Delta Lake 3.3.0 Release Notes](https://github.com/delta-io/delta/releases/tag/v3.3.0)
- [Databricks VACUUM Documentation](https://docs.databricks.com/en/delta/vacuum.html)
- [Delta Lake GitHub Repository](https://github.com/delta-io/delta)
