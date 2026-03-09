---
name: databricks-delta-optimization
description: "Optimize Delta table performance with liquid clustering, OPTIMIZE, VACUUM, Z-ordering, and table tuning. Use when improving query performance, reducing storage costs, managing table maintenance, or migrating from Hive-style partitioning."
---

# Delta Table Optimization

Patterns for optimizing Delta table performance on Databricks — liquid clustering, compaction, vacuuming, statistics, and migration from legacy partitioning.

## When to Use

- Creating new tables and choosing a clustering strategy
- Improving query performance on existing tables
- Reducing storage costs with VACUUM and compaction
- Migrating from Hive-style partitioning to liquid clustering
- Setting up automated table maintenance
- Diagnosing slow queries caused by data layout

## Quick Start

### Create a Table with Liquid Clustering

```sql
CREATE TABLE catalog.schema.events (
    event_id BIGINT,
    event_type STRING,
    region STRING,
    amount DOUBLE,
    created_at TIMESTAMP
) CLUSTER BY (event_type, region);
```

### Optimize and Vacuum

```sql
OPTIMIZE catalog.schema.events;
VACUUM catalog.schema.events;
```

## Liquid Clustering (Recommended)

Liquid clustering replaces Hive-style partitioning and Z-ordering. It automatically organizes data for fast queries without manual tuning.

### Create with Clustering

```sql
CREATE TABLE catalog.schema.sales (
    id BIGINT,
    category STRING,
    region STRING,
    amount DOUBLE
) CLUSTER BY (category, region);
```

### Change Clustering Columns

Unlike partitioning, clustering columns can be changed without rewriting data:

```sql
ALTER TABLE catalog.schema.sales CLUSTER BY (category, amount);
```

### Remove Clustering

```sql
ALTER TABLE catalog.schema.sales CLUSTER BY NONE;
```

### When to Use Liquid Clustering vs. Partitioning

| Scenario | Use Liquid Clustering | Use Partitioning |
|----------|----------------------|-----------------|
| New tables | Yes | No |
| Filter on multiple columns | Yes | No |
| High-cardinality columns | Yes | No |
| Need to change layout later | Yes | No |
| Existing Hive-partitioned tables | Migrate | Keep if working |
| Streaming ingestion | Yes | Acceptable |

### Choosing Clustering Columns

Pick columns that appear most often in `WHERE` and `JOIN` clauses:

```sql
-- Good: frequently filtered columns
CLUSTER BY (customer_id, event_date)

-- Up to 4 columns recommended
CLUSTER BY (region, product_category, event_date, customer_tier)
```

## OPTIMIZE

Compacts small files into larger ones for better read performance.

### Basic OPTIMIZE

```sql
OPTIMIZE catalog.schema.events;
```

### OPTIMIZE with Z-ORDER (Legacy Tables)

For tables **without** liquid clustering, Z-order provides multi-dimensional co-location:

```sql
OPTIMIZE catalog.schema.events ZORDER BY (event_type, region);
```

**Note:** Z-ORDER is ignored on liquid-clustered tables — OPTIMIZE handles clustering automatically.

### OPTIMIZE with WHERE (Incremental)

```sql
OPTIMIZE catalog.schema.events
WHERE event_date >= current_date() - INTERVAL 7 DAYS;
```

## VACUUM

Removes files no longer referenced by the Delta transaction log.

### Basic VACUUM

```sql
VACUUM catalog.schema.events;
```

Default retention is 7 days. To change:

```sql
VACUUM catalog.schema.events RETAIN 168 HOURS;
```

### VACUUM DRY RUN

Preview files that would be deleted:

```sql
VACUUM catalog.schema.events DRY RUN;
```

## Reference Files

- [table-diagnostics.md](table-diagnostics.md) - DESCRIBE DETAIL, HISTORY, statistics, and performance diagnosis
- [maintenance-automation.md](maintenance-automation.md) - Scheduled OPTIMIZE/VACUUM, predictive optimization, migration patterns

## Common Issues

| Issue | Solution |
|-------|----------|
| **Slow queries on large tables** | Add liquid clustering on filter columns, then run `OPTIMIZE` |
| **Too many small files** | Run `OPTIMIZE` — compacts files for better read performance |
| **Storage costs growing** | Run `VACUUM` to remove old file versions |
| **Z-ORDER not helping** | Migrate to liquid clustering — it's more effective and adaptive |
| **Can't change partition columns** | Migrate to liquid clustering with `ALTER TABLE ... CLUSTER BY` |
| **OPTIMIZE takes too long** | Use `WHERE` clause to optimize incrementally |
| **VACUUM deleting needed files** | Increase retention period: `RETAIN 720 HOURS` (30 days) |
| **`clusterByAuto` is false** | Enable predictive optimization at the table or schema level |
