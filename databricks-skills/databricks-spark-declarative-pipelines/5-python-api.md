# Python API Reference (`pyspark.pipelines`)

**Import**: `from pyspark import pipelines as dp`

This is the modern Python API for Spark Declarative Pipelines. For migrating from legacy `dlt` API, see [6-dlt-migration.md](6-dlt-migration.md).

---

## Decorators

### `@dp.table()`

Creates a streaming table or batch table.

```python
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
    return spark.readStream.format("cloudFiles").load("/Volumes/...")
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | str | Table name. Can be unqualified (`my_table`), partially qualified (`schema.table`), or fully qualified (`catalog.schema.table`). |
| `comment` | str | Table description |
| `cluster_by` | list | Columns for Liquid Clustering. Use `["AUTO"]` for automatic selection. |
| `table_properties` | dict | Delta table properties |
| `schema` | str/StructType | Explicit schema (optional, usually inferred) |
| `path` | str | External storage location (optional) |

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
    sequence_by=col("event_timestamp"),
    stored_as_scd_type=2,                    # Integer for Type 2, string "1" for Type 1
    apply_as_deletes=col("operation") == "DELETE",  # Optional: condition for deletes
    except_column_list=["operation", "_ingested_at"],  # Columns to exclude
    track_history_column_list=["price", "status"]      # Type 2: only track these columns
)
```

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `target` | str | Target table name |
| `source` | str | Source table/view name |
| `keys` | list | Primary key columns |
| `sequence_by` | Column | Column for ordering changes (use `col()`) |
| `stored_as_scd_type` | int/str | `2` for Type 2 (history), `"1"` for Type 1 (overwrite) |
| `apply_as_deletes` | Column | Condition identifying delete operations |
| `apply_as_truncates` | Column | Condition identifying truncate operations |
| `except_column_list` | list | Columns to exclude from target |
| `track_history_column_list` | list | Type 2 only: columns that trigger new versions |

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

# Read from file with Auto Loader
df = spark.readStream.format("cloudFiles") \
    .option("cloudFiles.format", "json") \
    .option("cloudFiles.schemaLocation", "/Volumes/.../schemas") \
    .load("/Volumes/catalog/schema/raw/data/")
```

**Do NOT use:**
- `dp.read()` or `dp.read_stream()` - not part of modern API
- `dlt.read()` or `dlt.read_stream()` - legacy API

---

## Table Name Resolution

| Level | Example | When to Use |
|-------|---------|-------------|
| Unqualified | `spark.read.table("my_table")` | Tables in same pipeline (recommended) |
| Schema-qualified | `spark.read.table("other_schema.my_table")` | Different schema, same catalog |
| Fully-qualified | `spark.read.table("other_catalog.schema.table")` | External catalogs |

**Best practice:** Use unqualified names for pipeline-internal tables. Use `spark.conf.get()` for parameterized external references.

---

## Pipeline Parameters

Access configuration values set in pipeline settings:

```python
# Get parameter value
catalog = spark.conf.get("target_catalog")
schema = spark.conf.get("target_schema")
schema_location = spark.conf.get("schema_location_base")

# With default
env = spark.conf.get("environment", "dev")

@dp.table(name=f"{catalog}.{schema}.my_table")
def my_table():
    return spark.readStream.format("cloudFiles") \
        .option("cloudFiles.schemaLocation", f"{schema_location}/my_table") \
        .load("/Volumes/...")
```

---

## Prohibited Operations

**Do NOT include these in dataset definitions:**

```python
# ❌ WRONG - these cause unexpected behavior
@dp.table(name="bad_example")
def bad_example():
    df = spark.read.table("source")
    df.collect()           # ❌ No collect()
    df.count()             # ❌ No count()
    df.toPandas()          # ❌ No toPandas()
    df.save(...)           # ❌ No save()
    df.saveAsTable(...)    # ❌ No saveAsTable()
    return df
```

Dataset functions should only contain code to define the transformation, not execute actions.

---

## Complete Example

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

# Configuration
schema_location = spark.conf.get("schema_location_base")

# Bronze: Ingest raw data
@dp.table(
    name="bronze_orders",
    comment="Raw orders from cloud storage",
    cluster_by=["order_date"]
)
def bronze_orders():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location}/bronze_orders")
        .load("/Volumes/my_catalog/my_schema/raw/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )

# Silver: Clean and validate
@dp.table(
    name="silver_orders",
    comment="Cleaned orders",
    cluster_by=["customer_id", "order_date"]
)
@dp.expect_or_drop("valid_amount", "amount > 0")
@dp.expect_or_drop("valid_customer", "customer_id IS NOT NULL")
def silver_orders():
    return (
        spark.readStream.table("bronze_orders")
        .withColumn("amount", F.col("amount").cast("decimal(10,2)"))
        .withColumn("order_date", F.to_date("order_timestamp"))
        .select("order_id", "customer_id", "amount", "order_date", "_ingested_at")
    )

# Gold: Business aggregation
@dp.materialized_view(
    name="gold_daily_revenue",
    comment="Daily revenue summary",
    cluster_by=["order_date"]
)
def gold_daily_revenue():
    return (
        spark.read.table("silver_orders")
        .groupBy("order_date")
        .agg(
            F.sum("amount").alias("total_revenue"),
            F.count("order_id").alias("order_count"),
            F.countDistinct("customer_id").alias("unique_customers")
        )
    )

# SCD Type 2 dimension
dp.create_streaming_table("dim_customers")

dp.create_auto_cdc_flow(
    target="dim_customers",
    source="customers_cdc_clean",
    keys=["customer_id"],
    sequence_by=F.col("updated_at"),
    stored_as_scd_type=2,
    except_column_list=["_ingested_at", "_source_file"]
)
```

---

## Related Documentation

- **[1-ingestion-patterns.md](1-ingestion-patterns.md)** - Auto Loader, Kafka, file ingestion (SQL + Python)
- **[6-dlt-migration.md](6-dlt-migration.md)** - Migrating from legacy `dlt` API or DLT Python to SDP
- **[9-auto_cdc.md](9-auto_cdc.md)** - CDC patterns and SCD Type 1/2 details
- **[Databricks Python API Docs](https://docs.databricks.com/aws/en/ldp/developer/python-ref)** - Official reference
