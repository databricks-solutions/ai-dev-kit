# Python Syntax Basics

Core Python syntax for Spark Declarative Pipelines (SDP) using the modern `pyspark.pipelines` API.

**Import**: `from pyspark import pipelines as dp`

---

## Decorators

### `@dp.table()`

Creates a streaming table or batch table.

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(
    name="bronze_events",              # Table name (can be fully qualified: catalog.schema.table)
    comment="Raw event data",          # Optional description
    cluster_by=["event_type", "date"], # Liquid Clustering columns (recommended)
    table_properties={                 # Delta table properties
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true"
    },
    schema="col1 STRING, col2 INT",    # Optional explicit schema
    path="/path/to/external/location"  # Optional external location
)
def bronze_events():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | str | Table name. Can be unqualified (`my_table`), schema-qualified (`schema.table`), or fully qualified (`catalog.schema.table`). |
| `comment` | str | Table description |
| `cluster_by` | list | Columns for Liquid Clustering. Use `["AUTO"]` for automatic selection. |
| `table_properties` | dict | Delta table properties |
| `schema` | str/StructType | Explicit schema (optional, usually inferred) |
| `path` | str | External storage location (optional) |

**Streaming vs Batch:**
- Return `spark.readStream...` for streaming table
- Return `spark.read...` for batch table

### `@dp.materialized_view()`

Creates a materialized view (batch, incrementally refreshed).

```python
@dp.materialized_view(
    name="gold_daily_summary",
    comment="Daily aggregated metrics",
    cluster_by=["report_date"]
)
def gold_daily_summary():
    return (
        spark.read.table("silver_orders")
        .groupBy("report_date")
        .agg(F.sum("amount").alias("total_amount"))
    )
```

**Parameters:** Same as `@dp.table()`.

### `@dp.temporary_view()`

Creates a pipeline-scoped temporary view (not persisted, exists only during pipeline execution).

```python
@dp.temporary_view()
def orders_with_calculations():
    """Intermediate view for complex logic before AUTO CDC."""
    return (
        spark.readStream.table("bronze_orders")
        .withColumn("total", F.col("quantity") * F.col("price"))
        .filter(F.col("total") > 0)
    )
```

**Constraints:**
- Cannot specify `catalog` or `schema` (pipeline-scoped only)
- Cannot use `cluster_by` (not persisted)
- Useful for intermediate transformations before AUTO CDC

---

## Expectation Decorators (Data Quality)

```python
@dp.table(name="silver_validated")
@dp.expect("valid_id", "id IS NOT NULL")                    # Warn only, keep all rows
@dp.expect_or_drop("valid_amount", "amount > 0")            # Drop invalid rows
@dp.expect_or_fail("critical_field", "timestamp IS NOT NULL") # Fail pipeline if violated
def silver_validated():
    return spark.read.table("bronze_events")
```

| Decorator | Behavior |
|-----------|----------|
| `@dp.expect(name, condition)` | Log warning, keep all rows |
| `@dp.expect_or_drop(name, condition)` | Drop rows that violate |
| `@dp.expect_or_fail(name, condition)` | Fail pipeline if any row violates |

---

## Functions

### `dp.create_streaming_table()`

Creates an empty streaming table (typically used before `create_auto_cdc_flow`).

```python
dp.create_streaming_table(
    name="customers_history",
    comment="SCD Type 2 customer dimension"
)
```

### `dp.create_auto_cdc_flow()`

Creates a Change Data Capture flow for SCD Type 1 or Type 2.

```python
from pyspark.sql.functions import col

dp.create_streaming_table("dim_customers")

dp.create_auto_cdc_flow(
    target="dim_customers",
    source="customers_cdc_clean",
    keys=["customer_id"],
    sequence_by=col("event_timestamp"),              # Note: use col(), not string
    stored_as_scd_type=2,                            # Integer for Type 2
    apply_as_deletes=col("operation") == "DELETE",   # Optional
    except_column_list=["operation", "_ingested_at"], # Columns to exclude
    track_history_column_list=["price", "status"]    # Type 2: only track these
)
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | str | Target table name |
| `source` | str | Source table/view name |
| `keys` | list | Primary key columns |
| `sequence_by` | Column | Column for ordering changes (**use `col()`**) |
| `stored_as_scd_type` | int/str | `2` for Type 2 (history), `"1"` for Type 1 (overwrite) |
| `apply_as_deletes` | Column | Condition identifying delete operations |
| `apply_as_truncates` | Column | Condition identifying truncate operations |
| `except_column_list` | list | Columns to exclude from target |
| `track_history_column_list` | list | Type 2 only: columns that trigger new versions |

**Important:** `stored_as_scd_type` is integer `2` for Type 2, string `"1"` for Type 1.

### `dp.create_auto_cdc_from_snapshot_flow()`

Creates CDC from periodic snapshots (compares consecutive snapshots to detect changes).

```python
dp.create_streaming_table("dim_products")

dp.create_auto_cdc_from_snapshot_flow(
    target="dim_products",
    source="products_snapshot",
    keys=["product_id"],
    stored_as_scd_type=2
)
```

### `dp.append_flow()`

Appends data from a source to a target table.

```python
dp.create_streaming_table("events_archive")

dp.append_flow(
    target="events_archive",
    source="old_events_source"
)
```

### `dp.create_sink()`

Creates a custom sink for streaming data.

```python
def write_to_kafka(batch_df, batch_id):
    batch_df.write.format("kafka").option("topic", "output").save()

dp.create_sink(
    name="kafka_sink",
    sink_fn=write_to_kafka
)
```

---

## Reading Data

**Use standard Spark APIs** - SDP automatically tracks dependencies:

```python
# Batch read (for materialized views or batch tables)
df = spark.read.table("catalog.schema.source_table")

# Streaming read (for streaming tables)
df = spark.readStream.table("catalog.schema.source_table")

# Unqualified name (uses pipeline's default catalog/schema)
df = spark.read.table("source_table")

# Read from file with Auto Loader (schema location managed automatically in SDP)
df = spark.readStream.format("cloudFiles") \
    .option("cloudFiles.format", "json") \
    .load("/Volumes/catalog/schema/raw/data/")
```

**Do NOT use:**
- `dp.read()` or `dp.read_stream()` - not part of modern API
- `dlt.read()` or `dlt.read_stream()` - legacy API
- `dlt.apply_changes()` - legacy API; use `dp.create_auto_cdc_flow()` instead
- `import dlt` - legacy module; use `from pyspark import pipelines as dp`

---

## Table Name Resolution

| Level | Example | When to Use |
|-------|---------|-------------|
| Unqualified | `spark.read.table("my_table")` | Tables in same pipeline (recommended) |
| Schema-qualified | `spark.read.table("other_schema.my_table")` | Different schema, same catalog |
| Fully-qualified | `spark.read.table("other_catalog.schema.table")` | External catalogs |

**Best practice:** Use unqualified names for pipeline-internal tables.

### Multi-Schema Pattern (One Pipeline)

Write to multiple schemas from a single pipeline using fully qualified names:

```python
from pyspark import pipelines as dp

# Bronze → writes to bronze schema
@dp.table(name="my_catalog.bronze.raw_orders")
def bronze_orders():
    return spark.readStream.format("cloudFiles") \
        .option("cloudFiles.format", "json") \
        .load("/Volumes/my_catalog/raw/orders/")

# Silver → writes to silver schema, reads from bronze
@dp.table(name="my_catalog.silver.clean_orders")
def silver_orders():
    return spark.readStream.table("my_catalog.bronze.raw_orders") \
        .filter("order_id IS NOT NULL")
```

---

## Pipeline Parameters

Access configuration values set in pipeline settings:

```python
# Get parameter value
catalog = spark.conf.get("target_catalog")
schema = spark.conf.get("target_schema")

# With default
env = spark.conf.get("environment", "dev")

@dp.table(name=f"{catalog}.{schema}.my_table")
def my_table():
    return spark.readStream.format("cloudFiles") \
        .option("cloudFiles.format", "json") \
        .load("/Volumes/...")
```

---

## Prohibited Operations

**Do NOT include these in dataset definitions:**

```python
# These cause unexpected behavior
@dp.table(name="bad_example")
def bad_example():
    df = spark.read.table("source")
    df.collect()           # No collect()
    df.count()             # No count()
    df.toPandas()          # No toPandas()
    df.save(...)           # No save()
    df.saveAsTable(...)    # No saveAsTable()
    return df
```

Dataset functions should only contain code to define the transformation, not execute actions.

---

## Common Issues

| Issue | Solution |
|-------|----------|
| `sequence_by` type error | Use `col("column")` not string in `create_auto_cdc_flow()` |
| SCD type syntax error | Type 2 uses integer `2`, Type 1 uses string `"1"` |
| Table not found | Check catalog/schema qualification or pipeline default settings |
| Parameter not resolved | Use `spark.conf.get("param_name")` |
| Actions in definition | Remove `collect()`, `count()`, `save()` from table functions |
| Using legacy `dlt` API | Replace `import dlt` with `from pyspark import pipelines as dp` |
| Using `input_file_name()` | Use `F.col("_metadata.file_path")` |
