# UniForm and Compatibility Mode

UniForm and Compatibility Mode make Delta tables readable as Iceberg by external engines — without converting to a native Iceberg table. Data is written as Delta, but Iceberg metadata is generated automatically so external tools (Snowflake, PyIceberg, Spark, Trino) can read via UC IRC endpoint.

---

## External Iceberg Reads (fka UniForm) (GA)

**Requirements**: Unity Catalog, DBR 14.3+, column mapping enabled, deletion vectors disabled, the Delta table must have a minReaderVersion >= 2 and minWriterVersion >= 7, both managed and external tables supported.

UniForm adds automatic Iceberg metadata generation to regular Delta tables. The table remains Delta internally but is readable as Iceberg externally.

### Enabling UniForm on a New Table

```sql
CREATE TABLE my_catalog.my_schema.customers (
  customer_id BIGINT,
  name STRING,
  region STRING,
  updated_at TIMESTAMP
)
TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

### Enabling UniForm on an Existing Table

```sql
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

### Requirements and Prerequisites

UniForm requires the following properties to be set explicitly:

| Requirement | Details |
|-------------|---------|
| **Unity Catalog** | Table must be registered in UC |
| **DBR 14.3+** | Minimum runtime version |
| **Deletion vectors disabled** | Set `delta.enableDeletionVectors = false` before enabling UniForm |
| **No column mapping conflicts** | If table uses `id` mode, migrate to `name` mode first |

If deletion vectors are currently enabled:

```sql
-- Disable deletion vectors first
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES ('delta.enableDeletionVectors' = 'false');

-- Rewrite to remove existing deletion vectors
REORG TABLE my_catalog.my_schema.customers
APPLY (PURGE);

-- Then enable UniForm
ALTER TABLE my_catalog.my_schema.customers
SET TBLPROPERTIES (
  'delta.columnMapping.mode' = 'name',
  'delta.enableIcebergCompatV2' = 'true',
  'delta.universalFormat.enabledFormats' = 'iceberg'
);
```

### Async Metadata Generation

Iceberg metadata is generated **asynchronously** after each Delta transaction. There is a brief delay (typically seconds, occasionally minutes for large transactions) before external engines see the latest data.

### Checking UniForm Status

> See [Check Iceberg metadata generation status](https://docs.databricks.com/aws/en/delta/uniform#check-iceberg-metadata-generation-status) for full details.


### Disabling UniForm

```sql
ALTER TABLE my_catalog.my_schema.customers
UNSET TBLPROPERTIES ('delta.universalFormat.enabledFormats');
```

---

## Compatibility Mode

**Requirements**: Unity Catalog, DBR 16.1+, SDP pipeline

Compatibility Mode extends UniForm to **streaming tables (STs)** and **materialized views (MVs)** created by Spark Declarative Pipelines (SDP) or DBSQL. Regular UniForm does not work on STs/MVs — Compatibility Mode is the only option.

**How it works**: When you enable Compatibility Mode, Databricks creates a separate, read-only **"compatibility version"** of the object at the external location you specify (`delta.universalFormat.compatibility.location`). This is a full copy of the data in Iceberg-compatible format — not a pointer to the original Delta data. After the initial full copy, subsequent metadata and data generation is **incremental** (only new/changed data is synced to the external location).

> **Storage cost consideration**: Because Compatibility Mode writes a separate copy of the data to the external location, you incur additional cloud storage costs proportional to the size of the table. Factor this in when enabling Compatibility Mode on large tables.

### Enabling Compatibility Mode

Compatibility Mode is configured via table properties:

**SQL Example (streaming table)**:

```sql
CREATE OR REFRESH STREAMING TABLE my_events
TBLPROPERTIES (
  'delta.universalFormat.enabledFormats' = 'compatibility',
  'delta.universalFormat.compatibility.location' = '<external-location-url>'
)
AS SELECT * FROM STREAM read_files('/Volumes/catalog/schema/raw/events/');
```

**SQL Example (materialized view)**:

```sql
CREATE OR REFRESH MATERIALIZED VIEW daily_summary
TBLPROPERTIES (
  'delta.universalFormat.enabledFormats' = 'compatibility',
  'delta.universalFormat.compatibility.location' = '<external-location-url>'
)
AS SELECT event_date, COUNT(*) AS event_count
FROM my_events
GROUP BY event_date;
```

**Python Example**:

```python
from pyspark import pipelines as dp

@dp.table(
    name="my_events",
    table_properties={
        "delta.universalFormat.enabledFormats": "compatibility",
        "delta.universalFormat.compatibility.location": "<external-location-url>",
    },
)
def my_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/catalog/schema/raw/events/")
    )
```

### Considerations for Compatibility Mode

| Consideration | Details |
|---------------|---------|
| **External location** | `delta.universalFormat.compatibility.location` must point to a configured external location for the Iceberg metadata output path |
| **SDP pipeline only** | Only works with streaming tables and MVs defined in SDP pipelines |
| **Initial generation time** | First metadata generation can take up to 1 hour for large tables |
| **Unity Catalog** | Required |
| **DBR 16.1+** | Minimum runtime for the SDP pipeline |

### Refresh Mechanics

Compatibility Mode metadata can be refreshed manually or controlled via the `delta.universalFormat.compatibility.targetRefreshInterval` property:

```sql
CREATE OR REFRESH STREAMING TABLE my_events
TBLPROPERTIES (
  'delta.universalFormat.enabledFormats' = 'compatibility',
  'delta.universalFormat.compatibility.location' = '<external-location-url>',
  'delta.universalFormat.compatibility.targetRefreshInterval' = '0 MINUTES'
)
AS SELECT * FROM STREAM read_files('/Volumes/catalog/schema/raw/events/');
```

| Interval value | Behavior |
|----------------|----------|
| `0 MINUTES` | Checks for changes after every commit and triggers a refresh if needed — default for streaming tables and MVs |
| `1 HOUR` | Default for non-SDP tables; refreshes at most once per hour |
| Values below `1 HOUR` (e.g. `30 MINUTES`) | Not recommended — won't make refreshes more frequent than once per hour |

Metadata can also be triggered manually:

```sql
REFRESH TABLE my_catalog.my_schema.my_events;
```

### Future Modes

A more efficient mode for streaming tables and materialized views is expected in a future release.

---

## Decision Table: Which Approach?

| Criteria | Managed Iceberg | UniForm | Compatibility Mode |
|----------|:-:|:-:|:-:|
| **Full Iceberg read/write** | Yes | Read-only (as Iceberg) | Read-only (as Iceberg) |
| **Works with Delta features (CDF)** | No | Partial* | Partial*  |
| **Streaming tables / MVs** | No | No | Yes |
| **External engine write via IRC** | Yes | No | No |
| **Existing Delta investment** | Requires migration | No migration | No migration |
| **Predictive Optimization** | Auto-enabled | Auto-enabled (Delta) | Auto-enabled (Delta) |
| **DBR requirement** | 16.1+ | 14.3+ | 16.1+ |

*given that Iceberg doesn't have CDF so the features dependent on it are not supported e.g., 
streaming tables, materialized views, data classification, vector search, data profiling. For Synced tables to Lakebase, only snapshot mode is supported.
### When to Choose Each

- **Managed Iceberg**: You want a native Iceberg table with full read/write from both Databricks and external engines. You don't need Delta-specific features (e.g., CDF).
- **UniForm**: You have existing Delta tables and want to make them readable as Iceberg by external engines without migrating. You want to keep Delta features internally.
- **Compatibility Mode**: You have streaming tables or materialized views that need to be readable as Iceberg by external engines.
