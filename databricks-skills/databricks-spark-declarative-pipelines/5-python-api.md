# Python API: Modern vs Legacy

**Last Updated**: January 2026
**Status**: Modern API (`pyspark.pipelines`) recommended for all new projects

---

## Overview

Databricks provides two Python APIs for Spark Declarative Pipelines:

1. **Modern API** (`pyspark.pipelines` as `dp`) - **Recommended (2025)**
2. **Legacy API** (`dlt`) - Older Delta Live Tables API, still supported

**Key Recommendation**: Always use **modern API** for new projects. Only use legacy for maintaining existing DLT code.

---

## Quick Comparison

| Aspect | Modern (`dp`) | Legacy (`dlt`) |
|--------|---------------|----------------|
| **Import** | `from pyspark import pipelines as dp` | `import dlt` |
| **Status** | ✅ **Recommended** | ⚠️ Legacy |
| **Table decorator** | `@dp.table()` | `@dlt.table()` |
| **Read** | `spark.read.table("table")` | `dlt.read("table")` |
| **CDC/SCD** | `dp.create_auto_cdc_flow()` | `dlt.apply_changes()` |
| **Use for** | New projects | Maintaining existing |

---

## Side-by-Side Examples

### Basic Table Definition

**Modern (Recommended)**:
```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(name="bronze_events", comment="Raw events")
def bronze_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/mnt/raw/events")
    )
```

**Legacy**:
```python
import dlt
from pyspark.sql import functions as F

@dlt.table(name="bronze_events", comment="Raw events")
def bronze_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/mnt/raw/events")
    )
```

### Reading Tables

**Modern (Recommended)**:
```python
@dp.table(name="silver_events")
def silver_events():
    # Explicit Unity Catalog path
    return spark.read.table("bronze_events").filter(...)
```

**Legacy**:
```python
@dlt.table(name="silver_events")
def silver_events():
    # Implicit LIVE schema
    return dlt.read("bronze_events").filter(...)
```

**Key Difference**: Modern uses explicit UC paths, legacy uses implicit `LIVE.*`.

### Streaming Reads

**Modern (Recommended)**:
```python
@dp.table(name="silver_events")
def silver_events():
    # Context-aware (no separate read_stream)
    return (
        spark.readStream.table("catalog.schema.bronze_events")
        .filter(F.col("event_type").isNotNull())
    )
```

**Legacy**:
```python
@dlt.table(name="silver_events")
def silver_events():
    # Explicit streaming read
    return (
        dlt.read_stream("bronze_events")
        .filter(F.col("event_type").isNotNull())
    )
```

### Data Quality Expectations

**Modern (Recommended)**:
```python
@dp.table(name="silver_validated")
@dp.expect_or_drop("valid_id", "id IS NOT NULL")
@dp.expect_or_drop("valid_amount", "amount > 0")
@dp.expect_or_fail("critical_field", "timestamp IS NOT NULL")
def silver_validated():
    return spark.read.table("catalog.schema.bronze_events")
```

**Legacy**:
```python
@dlt.table(name="silver_validated")
@dlt.expect_or_drop("valid_id", "id IS NOT NULL")
@dlt.expect_or_drop("valid_amount", "amount > 0")
@dlt.expect_or_fail("critical_field", "timestamp IS NOT NULL")
def silver_validated():
    return dlt.read("bronze_events")
```

**Note**: Expectations API identical between versions.

### SCD Type 2 (AUTO CDC)

**Modern (Recommended)**:
```python
from pyspark.sql.functions import col

dp.create_streaming_table("customers_history")

dp.create_auto_cdc_flow(
    target="customers_history",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by=col("event_timestamp"),
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**Legacy**:
```python
dlt.create_streaming_table("customers_history")

dlt.apply_changes(
    target="customers_history",
    source="customers_cdc",
    keys=["customer_id"],
    sequence_by="event_timestamp",
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**Key Difference**: Modern uses `create_auto_cdc_flow()`, legacy uses `apply_changes()`.

### Liquid Clustering

**Modern (Recommended)**:
```python
@dp.table(
    name="bronze_events",
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true"
    },
    cluster_by=["event_type", "event_date"]  # Liquid Clustering
)
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

**Legacy**:
```python
@dlt.table(
    name="bronze_events",
    table_properties={
        "pipelines.autoOptimize.managed": "true",
        "pipelines.autoOptimize.zOrderCols": "event_type"
    },
    partition_cols=["event_date"]  # Legacy partitioning
)
def bronze_events():
    return spark.readStream.format("cloudFiles").load("/data")
```

**Key Difference**: Modern supports `cluster_by` for Liquid Clustering.

---

## Decision Matrix

### Use Modern API (`dp`) When:
- ✅ **Starting new project** (default choice)
- ✅ **Learning SDP/LDP** (learn current standard)
- ✅ **Want Liquid Clustering**
- ✅ **Prefer explicit Unity Catalog paths**
- ✅ **Following 2025 best practices**

### Use Legacy API (`dlt`) When:
- ⚠️ **Maintaining existing DLT pipelines** (don't rewrite working code)
- ⚠️ **Team trained on DLT** (consistency with existing)
- ⚠️ **Older DBR versions** (if modern API not available)

**Default**: Use modern `dp` API unless specific reason for legacy.

---

## Migration Guide: dlt → dp

### Step 1: Update Imports

**Before**:
```python
import dlt
```

**After**:
```python
from pyspark import pipelines as dp
```

### Step 2: Update Decorators

**Before**: `@dlt.table(name="my_table")`
**After**: `@dp.table(name="my_table")`

### Step 3: Update Reads

**Before**:
```python
dlt.read("source_table")
dlt.read_stream("source_table")
```

**After**:
```python
spark.table("catalog.schema.source_table")
# Streaming context-aware, no separate read_stream
```

### Step 4: Update CDC/SCD Operations

**Before**:
```python
dlt.apply_changes(target="dim_customer", source="cdc_source", ...)
```

**After**:
```python
from pyspark.sql.functions import col

dp.create_auto_cdc_flow(
    target="dim_customer",
    source="cdc_source",
    keys=["customer_id"],
    sequence_by=col("event_timestamp"),
    stored_as_scd_type="2",
    track_history_column_list=["*"]
)
```

**Key Change**: `dlt.apply_changes()` → `dp.create_auto_cdc_flow()`

### Step 5: Update Clustering

**Before**: `@dlt.table(partition_cols=["date"])`
**After**: `@dp.table(cluster_by=["date", "other_col"])`

---

## Key Patterns (2025)

### 1. Use Liquid Clustering

```python
@dp.table(cluster_by=["key_col", "date_col"])
def my_table():
    return ...

# Or automatic
@dp.table(cluster_by=["AUTO"])
def my_table():
    return ...
```

### 2. Explicit UC Paths

```python
# ✅ Modern: explicit path
spark.table("catalog.schema.table")

# ❌ Legacy: implicit LIVE
dlt.read("table")
```

### 3. forEachBatch for Custom Sinks

```python
def write_to_custom_sink(batch_df, batch_id):
    batch_df.write.format("custom").save(...)

@dp.table(name="my_table")
def my_table():
    return (
        spark.readStream
        .format("cloudFiles")
        .load("/data")
        .writeStream
        .foreachBatch(write_to_custom_sink)
    )
```

---

## Summary

**For New Projects**: Use modern `pyspark.pipelines` (`dp`)
- ✅ Current best practice (2025)
- ✅ Liquid Clustering support
- ✅ Explicit Unity Catalog paths

**For Existing Projects**: Legacy `dlt` fully supported
- ⚠️ Migrate when convenient, not urgent
- ⚠️ Consider modern API for new files

**Key Takeaway**: Modern API provides same functionality plus new features. Start all new projects with `from pyspark import pipelines as dp`.
