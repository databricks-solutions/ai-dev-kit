---
name: databricks-iceberg
description: "Apache Iceberg tables on Databricks — Managed Iceberg tables, External Iceberg Reads (fka Uniform), Compatibility Mode, Iceberg REST Catalog (IRC), Iceberg v3, Snowflake interop, PyIceberg, OSS Spark, external engine access and credential vending. Use when creating Iceberg tables, enabling External Iceberg Reads (uniform) on Delta tables (including Streaming Tables and Materialized Views via compatibility mode), configuring external engines to read Databricks tables via Unity Catalog IRC, integrating with Snowflake catalog to read Foreign Iceberg tables"
---

# Apache Iceberg on Databricks

Databricks provides multiple ways to work with Apache Iceberg: native managed Iceberg tables, UniForm for Delta-to-Iceberg interoperability, and the Iceberg REST Catalog (IRC) for external engine access.

---

## Critical Rules (always follow)

- **MUST** use Unity Catalog — all Iceberg features require UC-enabled workspaces
- **MUST NOT** install an Iceberg library into Databricks Runtime (DBR includes built-in Iceberg support; adding a library causes version conflicts)
- **MUST NOT** set `write.metadata.path` or `write.metadata.previous-versions-max` — Databricks manages metadata locations automatically; overriding causes corruption
- **MUST** determine which Iceberg pattern fits the use case before writing code — see the [When to Use](#when-to-use) section below
- **MUST** know that both `PARTITIONED BY` and `CLUSTER BY` produce the same Iceberg metadata for external engines — UC maintains an Iceberg partition spec with partition fields corresponding to the clustering keys, so external engines reading via IRC see a partitioned Iceberg table (not Hive-style, but proper Iceberg partition fields) and can prune on those fields; internally UC uses those fields as liquid clustering keys; the only differences between the two syntaxes are: (1) `PARTITIONED BY` is standard Iceberg DDL (any engine can create the table), while `CLUSTER BY` is DBR-only DDL; (2) `PARTITIONED BY` **auto-handles** DV/row-tracking properties, while `CLUSTER BY` requires manual TBLPROPERTIES on v2
- **MUST NOT** use expression-based partition transforms (`bucket()`, `years()`, `months()`, `days()`, `hours()`) with `PARTITIONED BY` on managed Iceberg tables — only plain column references are supported; expression transforms cause errors
- **MUST** disable deletion vectors and row tracking when using `CLUSTER BY` on Iceberg v2 tables — set `'delta.enableDeletionVectors' = false` and `'delta.enableRowTracking' = false` in TBLPROPERTIES (Iceberg v3 handles this automatically; `PARTITIONED BY` handles this automatically on both v2 and v3)

---

## Key Concepts

| Concept | Summary |
|---------|---------|
| **Managed Iceberg Table** | Native Iceberg table created with `USING ICEBERG` — full read/write in Databricks and via external Iceberg engines |
| **External Iceberg Reads (Uniform)** | Delta table that auto-generates Iceberg metadata — read as Iceberg externally, write as Delta internally |
| **Compatibility Mode** | UniForm variant for streaming tables and materialized views in SDP pipelines |
| **Iceberg REST Catalog (IRC)** | Unity Catalog's built-in REST endpoint implementing the Iceberg REST Catalog spec — lets external engines (Spark, PyIceberg, Snowflake) access UC-managed Iceberg data |
| **Iceberg v3** | Next-gen format (Beta, DBR 17.3+) — deletion vectors, VARIANT type, row lineage |

---

## Quick Start

### Create a Managed Iceberg Table

```sql
-- No clustering
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
AS SELECT * FROM raw_events;

-- PARTITIONED BY (recommended for cross-platform): standard Iceberg syntax, works on EMR/OSS Spark/Trino/Flink
-- auto-disables DVs and row tracking — no TBLPROPERTIES needed on v2 or v3
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
PARTITIONED BY (event_date)
AS SELECT * FROM raw_events;

-- CLUSTER BY on Iceberg v2 (DBR-only syntax): must manually disable DVs and row tracking
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (event_date)
AS SELECT * FROM raw_events;

-- CLUSTER BY on Iceberg v3 (DBR-only syntax): no TBLPROPERTIES needed
CREATE TABLE my_catalog.my_schema.events
USING ICEBERG
TBLPROPERTIES ('format-version' = '3')
CLUSTER BY (event_date)
AS SELECT * FROM raw_events;
```

### Enable UniForm on an Existing Delta Table

```sql
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

---

## Read/Write Capability Matrix

| Table Type | Databricks Read | Databricks Write | External IRC Read | External IRC Write |
|------------|:-:|:-:|:-:|:-:|
| Managed Iceberg (`USING ICEBERG`) | Yes | Yes | Yes | Yes |
| Delta + UniForm | Yes (as Delta) | Yes (as Delta) | Yes (as Iceberg) | No |
| Delta + Compatibility Mode | Yes (as Delta) | Yes | Yes (as Iceberg) | No |

---

## Reference Files

| File | Summary | Keywords |
|------|---------|----------|
| [1-managed-iceberg-tables.md](1-managed-iceberg-tables.md) | Creating and managing native Iceberg tables — DDL, DML, Liquid Clustering, Predictive Optimization, Iceberg v3, limitations | CREATE TABLE USING ICEBERG, CTAS, MERGE, time travel, deletion vectors, VARIANT |
| [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md) | Making Delta tables readable as Iceberg — UniForm for regular tables, Compatibility Mode for streaming tables and MVs | UniForm, universalFormat, Compatibility Mode, streaming tables, materialized views, SDP |
| [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md) | Exposing Databricks tables to external engines via the IRC endpoint — auth, credential vending, IP access lists | IRC, REST Catalog, credential vending, EXTERNAL USE SCHEMA, PAT, OAuth |
| [4-snowflake-interop.md](4-snowflake-interop.md) | Bidirectional Snowflake-Databricks integration — catalog integration, foreign catalogs, vended credentials | Snowflake, catalog integration, external volume, vended credentials, REFRESH_INTERVAL_SECONDS |
| [5-external-engine-interop.md](5-external-engine-interop.md) | Connecting PyIceberg, OSS Spark, AWS EMR, Apache Flink, and Kafka Connect via IRC | PyIceberg, OSS Spark, EMR, Flink, Kafka Connect, pyiceberg.yaml |

---

## When to Use

- **Creating a new Iceberg table** → [1-managed-iceberg-tables.md](1-managed-iceberg-tables.md)
- **Making an existing Delta table readable as Iceberg** → [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md)
- **Making a streaming table or MV readable as Iceberg** → [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md) (Compatibility Mode section)
- **Choosing between Managed Iceberg vs UniForm vs Compatibility Mode** → decision table in [2-uniform-and-compatibility.md](2-uniform-and-compatibility.md)
- **Exposing Databricks tables to external engines via REST API** → [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md)
- **Integrating Databricks with Snowflake (either direction)** → [4-snowflake-interop.md](4-snowflake-interop.md)
- **Connecting PyIceberg, OSS Spark, Flink, EMR, or Kafka** → [5-external-engine-interop.md](5-external-engine-interop.md)

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **No Change Data Feed (CDF)** | CDF is not supported on managed Iceberg tables. Use Delta + UniForm if you need CDF. |
| **UniForm async delay** | Iceberg metadata generation is asynchronous. After a write, there may be a brief delay before external engines see the latest data. Check status with `DESCRIBE EXTENDED table_name`. |
| **Compression codec change** | Managed Iceberg tables use `zstd` compression by default (not `snappy`). Older Iceberg readers that don't support zstd will fail. Verify reader compatibility or set `write.parquet.compression-codec` to `snappy`. |
| **Snowflake 1000-commit limit** | Snowflake's Iceberg catalog integration can only see the last 1000 Iceberg commits. High-frequency writers must compact metadata or Snowflake will lose visibility of older data. |
| **Deletion vectors with UniForm** | UniForm requires deletion vectors to be disabled (`delta.enableDeletionVectors = false`). If your table has deletion vectors enabled, disable them before enabling UniForm. |
| **No shallow clone for Iceberg** | `SHALLOW CLONE` is not supported for Iceberg tables. Use `DEEP CLONE` or `CREATE TABLE ... AS SELECT` instead. |
| **Version mismatch with external engines** | Ensure external engines use an Iceberg library version compatible with the format version of your tables. Iceberg v3 tables require Iceberg library 1.9.0+. |

---

## Related Skills

- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — catalog/schema management, governance, system tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** — SDP pipelines (streaming tables, materialized views with Compatibility Mode)
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — Python SDK and REST API for Databricks operations
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** — SQL warehouse features, query patterns

---

## Resources

- **[Iceberg Overview](https://docs.databricks.com/aws/en/iceberg/)** — main hub for Iceberg on Databricks
- **[UniForm](https://docs.databricks.com/aws/en/delta/uniform.html)** — Delta Universal Format
- **[Iceberg REST Catalog](https://docs.databricks.com/aws/en/external-access/iceberg)** — IRC endpoint and external engine access
- **[Compatibility Mode](https://docs.databricks.com/aws/en/external-access/compatibility-mode)** — UniForm for streaming tables and MVs
- **[Iceberg v3](https://docs.databricks.com/aws/en/iceberg/iceberg-v3)** — next-gen format features (Beta)
- **[Foreign Tables](https://docs.databricks.com/aws/en/query-data/foreign-tables.html)** — reading external catalog data
