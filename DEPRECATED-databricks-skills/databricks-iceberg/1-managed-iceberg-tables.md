# Managed Iceberg Tables

Managed Iceberg tables are native Apache Iceberg tables created and stored within Unity Catalog. They support full read/write operations in Databricks and are accessible to external engines via the UC Iceberg REST Catalog (IRC) endpoint.

**Requirements**: Unity Catalog, DBR 16.4 LTS+ (Managed Iceberg v2), DBR 17.3+ (Managed Iceberg v3 Beta)

---

## Creating Tables

### Basic DDL

```sql
-- Create an empty Iceberg table (no clustering)
CREATE TABLE my_catalog.my_schema.events (
  event_id BIGINT,
  event_type STRING,
  event_date DATE,
  payload STRING
)
USING ICEBERG;
```

### Create Table As Select (CTAS)

```sql
-- Create from existing data (no clustering)
CREATE TABLE my_catalog.my_schema.events_archive
USING ICEBERG
AS SELECT * FROM my_catalog.my_schema.events
WHERE event_date < '2025-01-01';
```

### Liquid Clustering

Managed Iceberg tables use **Liquid Clustering** for data layout optimization. Both `PARTITIONED BY` and `CLUSTER BY` produce a Liquid Clustered table — **no traditional Hive-style partitions are created**. Unity Catalog interprets the partition clause as clustering keys.

| Syntax | DDL (create table) | Reads via IRC | Iceberg partition fields visible to external engines | DV/row-tracking handling |
|--------|--------------------|---------------|------------------------------------------------------|--------------------------|
| `PARTITIONED BY (col)` | DBR + EMR, OSS Spark, Trino, Flink | Yes | Yes — UC exposes Iceberg partition fields corresponding to clustering keys; external engines can prune | **Auto-handled** |
| `CLUSTER BY (col)` | DBR only | Yes | Yes — same; UC maintains Iceberg partition spec from clustering keys regardless of DDL used | Manual on v2, auto on v3 |

> **Both syntaxes produce the same Iceberg metadata for external engines.** UC maintains an Iceberg partition spec (partition fields corresponding to the clustering keys) that external engines read via IRC. This is Iceberg-style partitioning — not legacy Hive-style directory partitions. External engines see a partitioned Iceberg table and benefit from partition pruning. Internally, UC uses those partition fields as liquid clustering keys.

> **`PARTITIONED BY` limitation**: Only plain column references are supported. Expression transforms (`bucket()`, `years()`, `months()`, `days()`, `hours()`) are **not** supported and will error.

> **`CLUSTER BY` on Iceberg v2**: requires explicitly setting `'delta.enableDeletionVectors' = false` and `'delta.enableRowTracking' = false`, otherwise you get: `[MANAGED_ICEBERG_ATTEMPTED_TO_ENABLE_CLUSTERING_WITHOUT_DISABLING_DVS_OR_ROW_TRACKING]`

**`PARTITIONED BY` — recommended for cross-platform** (auto-handles all required properties):

```sql
-- Single column (v2 or v3 — no TBLPROPERTIES needed)
CREATE TABLE orders (
  order_id BIGINT,
  order_date DATE
)
USING ICEBERG
PARTITIONED BY (order_date);

-- Multi-column
CREATE TABLE orders (
  order_id BIGINT,
  region STRING,
  order_date DATE
)
USING ICEBERG
PARTITIONED BY (region, order_date);
```

**`CLUSTER BY` on Iceberg v2** (DBR-only; must disable DVs and row tracking manually):

```sql
-- Single column clustering (v2)
CREATE TABLE orders (
  order_id BIGINT,
  order_date DATE
)
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (order_date);
```

**`CLUSTER BY` on Iceberg v3** (no extra TBLPROPERTIES needed):

```sql
CREATE TABLE orders (
  order_id BIGINT,
  order_date DATE
)
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (order_date);
```

---

## DML Operations

Managed Iceberg tables support all standard DML operations:

```sql
-- INSERT
INSERT INTO my_catalog.my_schema.events
VALUES (1, 'click', '2025-06-01', '{"page": "home"}');

-- INSERT from query
INSERT INTO my_catalog.my_schema.events
SELECT * FROM staging_events WHERE event_date = current_date();

-- UPDATE
UPDATE my_catalog.my_schema.events
SET event_type = 'page_view'
WHERE event_id = 1;

-- DELETE
DELETE FROM my_catalog.my_schema.events
WHERE event_date < '2024-01-01';

-- MERGE (upsert)
MERGE INTO my_catalog.my_schema.events AS target
USING staging_events AS source
ON target.event_id = source.event_id
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

---

## Time Travel

Query historical snapshots using timestamp or snapshot ID:

```sql
-- Query by timestamp
SELECT * FROM my_catalog.my_schema.events TIMESTAMP AS OF '2025-06-01T00:00:00Z';

-- Query by snapshot ID
SELECT * FROM my_catalog.my_schema.events VERSION AS OF 1234567890;

-- Only for external engines: View snapshot history
SELECT * FROM my_catalog.my_schema.events.snapshots;
```

---

## Predictive Optimization

Predictive Optimization is **recommended** for managed Iceberg tables — it is not auto-enabled and must be turned on explicitly. Once enabled, it automatically runs:

- **Compaction** — consolidates small files
- **Vacuum** — removes expired snapshots and orphan files
- **Statistics collection** — keeps column statistics up to date for query optimization

Enable at the catalog or schema level. Manual operations are still available if needed:

```sql
-- Manual compaction
OPTIMIZE my_catalog.my_schema.events;

-- Manual vacuum
VACUUM my_catalog.my_schema.events;

-- Manual statistics collection
ANALYZE TABLE my_catalog.my_schema.events COMPUTE STATISTICS FOR ALL COLUMNS;
```

---

## Iceberg v3 (Beta)

**Requires**: DBR 17.3+

Iceberg v3 introduces new capabilities on top of v2:

| Feature | Description |
|---------|-------------|
| **Deletion Vectors** | Row-level deletes without rewriting data files — faster UPDATE/DELETE/MERGE |
| **VARIANT Type** | Semi-structured data column (like Delta's VARIANT) |
| **Row Lineage** | Track row-level provenance across transformations |

### Creating an Iceberg v3 Table

```sql
CREATE TABLE my_catalog.my_schema.events_v3 (
  event_id BIGINT,
  event_date DATE,
  data VARIANT
)
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (event_date);
```

### Important Notes

- **Cannot downgrade**: Once a table is upgraded to v3, it cannot be downgraded back to v2
- **External engine compatibility**: External engines must use Iceberg library 1.9.0+ to read v3 tables
- **Deletion vectors**: Enabled by default on v3 tables. External readers must support deletion vectors
- **Beta status**: Iceberg v3 is in Beta — not recommended for production workloads yet

### Upgrading an Existing Table to v3

```sql
ALTER TABLE my_catalog.my_schema.events
SET TBLPROPERTIES ('format-version' = '3');
```

> **Warning**: This is irreversible. Test with non-production data first.

---

## Limitations

| Limitation | Details |
|------------|---------|
| **No Vector Search** | Vector Search indexes are not supported on Iceberg tables |
| **No Change Data Feed (CDF)** | CDF is a Delta-only feature; use Delta + UniForm if CDF is required |
| **Parquet only** | Iceberg tables on Databricks use Parquet as the underlying file format |
| **No shallow clone** | `SHALLOW CLONE` is not supported; use `DEEP CLONE` or CTAS |
| **`PARTITIONED BY` maps to Liquid Clustering** | `PARTITIONED BY` is supported and recommended for cross-platform scenarios — it maps to Liquid Clustering, not traditional partitions. Only plain column references work; expression transforms (`bucket()`, `years()`, etc.) are not supported. |
| **No Structured Streaming sink** | Cannot use `writeStream` to write to Iceberg tables directly; use `INSERT INTO` or `MERGE` in batch or SDP |
| **Compression** | Default compression is `zstd`; older readers may need `snappy` — set `write.parquet.compression-codec` if needed |
| **Do not set metadata path** | Never set `write.metadata.path` or `write.metadata.previous-versions-max` |
| **Do not install Iceberg library** | DBR includes built-in support; installing an Iceberg JAR causes conflicts |

---

## Converting From Other Formats

### Delta to Iceberg (via DEEP CLONE)

```sql
CREATE TABLE my_catalog.my_schema.events_iceberg
USING ICEBERG
DEEP CLONE my_catalog.my_schema.events_delta;
```

### Foreign Iceberg to Managed Iceberg

```sql
-- With Liquid Clustering (v2 — must disable DVs and row tracking)
CREATE TABLE my_catalog.my_schema.events_managed
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (event_date)
AS SELECT * FROM foreign_catalog.foreign_schema.events;

-- With Liquid Clustering (v3 — no extra TBLPROPERTIES needed)
CREATE TABLE my_catalog.my_schema.events_managed
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (event_date)
AS SELECT * FROM foreign_catalog.foreign_schema.events;
```


