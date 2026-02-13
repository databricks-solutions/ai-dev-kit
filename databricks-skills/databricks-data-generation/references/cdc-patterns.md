# CDC Patterns

Patterns for generating Change Data Capture (CDC) data for Databricks pipeline demos.

## CDC Overview

CDC records capture data changes as a stream of operations. Each record includes:
- `operation`: The type of change — `APPEND`, `UPDATE`, or `DELETE`
- `operation_date`: When the change occurred (used for sequencing)

This pattern is used in virtually every Databricks lakehouse pipeline. CDC data flows into Bronze as raw change events, then gets applied to Silver tables via `MERGE INTO` or Spark Declarative Pipelines `APPLY CHANGES`.

## Basic CDC Pattern

Generate CDC records with weighted operation types using dbldatagen:

```python
import dbldatagen as dg

cdc_spec = (
    dg.DataGenerator(spark, rows=500_000, partitions=10)
    .withColumn("id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("operation", "string",
                values=["APPEND", "UPDATE", "DELETE", None],
                weights=[50, 30, 10, 1])
    .withColumn("operation_date", "timestamp",
                begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("name", "string", template=r"\\w \\w")
    .withColumn("email", "string", template=r"\\w.\\w@\\w.com")
    .withColumn("address", "string", template=r"dddd \\w \\w St")
    .withColumn("city", "string",
                values=["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"])
    .withColumn("state", "string",
                values=["NY", "CA", "IL", "TX", "AZ"])
    .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=5000, random=True)
)

cdc_df = cdc_spec.build()
```

The `None` value with weight 1 simulates occasional corrupt/missing operations — useful for testing data quality expectations.

## Multi-Batch CDC

Real CDC pipelines process data in batches: an initial full load followed by incremental change batches.

### Initial Load (All APPENDs)

```python
def generate_initial_load(spark, n_records=100_000):
    """Generate initial full load — all records are APPEND operations."""
    return (
        dg.DataGenerator(spark, rows=n_records, partitions=10)
        .withColumn("id", "long", minValue=1_000_000, uniqueValues=n_records)
        .withColumn("operation", "string", values=["APPEND"])
        .withColumn("operation_date", "timestamp",
                    begin="2024-01-01 00:00:00", end="2024-01-01 00:00:00")
        .withColumn("name", "string", template=r"\\w \\w")
        .withColumn("email", "string", template=r"\\w.\\w@\\w.com")
        .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=5000, random=True)
        .build()
    )
```

### Incremental Batch

```python
def generate_incremental_batch(spark, batch_number, n_existing=100_000, n_changes=10_000):
    """Generate incremental CDC batch with mixed operations.

    - UPDATEs and DELETEs target existing IDs (1_000_000 to 1_000_000 + n_existing)
    - New APPENDs get IDs beyond the existing range
    """
    batch_date = f"2024-01-{batch_number + 1:02d}"

    # Changes to existing records (60% UPDATE, 20% DELETE)
    changes = (
        dg.DataGenerator(spark, rows=int(n_changes * 0.8), partitions=4)
        .withColumn("id", "long",
                    minValue=1_000_000, maxValue=1_000_000 + n_existing - 1)
        .withColumn("operation", "string",
                    values=["UPDATE", "DELETE"], weights=[75, 25])
        .withColumn("operation_date", "timestamp",
                    begin=f"{batch_date} 00:00:00", end=f"{batch_date} 23:59:59",
                    random=True)
        .withColumn("name", "string", template=r"\\w \\w")
        .withColumn("email", "string", template=r"\\w.\\w@\\w.com")
        .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=5000, random=True)
        .build()
    )

    # New records (APPENDs with new IDs)
    new_id_start = 1_000_000 + n_existing + (batch_number * n_changes)
    new_records = (
        dg.DataGenerator(spark, rows=int(n_changes * 0.2), partitions=2)
        .withColumn("id", "long",
                    minValue=new_id_start, uniqueValues=int(n_changes * 0.2))
        .withColumn("operation", "string", values=["APPEND"])
        .withColumn("operation_date", "timestamp",
                    begin=f"{batch_date} 00:00:00", end=f"{batch_date} 23:59:59",
                    random=True)
        .withColumn("name", "string", template=r"\\w \\w")
        .withColumn("email", "string", template=r"\\w.\\w@\\w.com")
        .withColumn("amount", "decimal(10,2)", minValue=10, maxValue=5000, random=True)
        .build()
    )

    return changes.unionByName(new_records)
```

### Generating Multiple Batches

```python
# Generate initial load + 5 incremental batches
initial_df = generate_initial_load(spark, n_records=100_000)
n_existing = 100_000

batches = [initial_df]
for batch_num in range(1, 6):
    batch_df = generate_incremental_batch(spark, batch_num, n_existing=n_existing)
    batches.append(batch_df)
    n_existing += int(10_000 * 0.2)  # Track new APPENDs added
```

## Writing CDC to Volumes

Write CDC DataFrames as JSON to Unity Catalog Volumes for Auto Loader pickup:

```python
def write_cdc_to_volume(df, catalog, schema, volume, batch_name="batch_001"):
    """Write CDC DataFrame as JSON to a UC Volume, partitioned by date."""
    volume_path = f"/Volumes/{catalog}/{schema}/{volume}/cdc_raw/{batch_name}"

    (df
     .withColumn("_date", F.to_date("operation_date"))
     .write
     .format("json")
     .mode("append")
     .partitionBy("_date")
     .save(volume_path))

# Setup
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}")

# Write initial load
write_cdc_to_volume(initial_df, "demo", "pipeline", "landing", "initial_load")

# Write incremental batches
for i, batch_df in enumerate(batches[1:], start=1):
    write_cdc_to_volume(batch_df, "demo", "pipeline", "landing", f"batch_{i:03d}")
```

Partitioning by date enables efficient Auto Loader file discovery and allows downstream consumers to process changes in chronological order.

## Consuming CDC with MERGE INTO

Apply CDC records to a target Delta table using `MERGE INTO` with deduplication:

```sql
-- Create target table
CREATE TABLE IF NOT EXISTS demo.pipeline.customers_silver (
    id BIGINT,
    name STRING,
    email STRING,
    amount DECIMAL(10,2),
    updated_at TIMESTAMP
);

-- Apply CDC with deduplication (keep latest operation per ID)
MERGE INTO demo.pipeline.customers_silver AS target
USING (
    SELECT *
    FROM (
        SELECT *,
            ROW_NUMBER() OVER (
                PARTITION BY id
                ORDER BY operation_date DESC
            ) AS rn
        FROM demo.pipeline.customers_bronze
    )
    WHERE rn = 1
) AS source
ON target.id = source.id
WHEN MATCHED AND source.operation = 'DELETE' THEN DELETE
WHEN MATCHED AND source.operation != 'DELETE' THEN UPDATE SET
    target.name = source.name,
    target.email = source.email,
    target.amount = source.amount,
    target.updated_at = source.operation_date
WHEN NOT MATCHED AND source.operation != 'DELETE' THEN INSERT (
    id, name, email, amount, updated_at
) VALUES (
    source.id, source.name, source.email, source.amount, source.operation_date
);
```

The `ROW_NUMBER()` deduplication is critical — without it, multiple operations for the same ID in a single batch can cause non-deterministic results.

## Consuming CDC with APPLY CHANGES

Spark Declarative Pipelines provides native CDC support via `APPLY CHANGES`.

### SQL Syntax

```sql
CREATE OR REFRESH STREAMING TABLE customers_silver;

CREATE FLOW customers_cdc_flow
AS APPLY CHANGES INTO LIVE.customers_silver
FROM STREAM(LIVE.customers_bronze)
KEYS (id)
APPLY AS DELETE WHEN operation = "DELETE"
SEQUENCE BY operation_date
COLUMNS * EXCEPT (operation, operation_date);
```

### Python Syntax

```python
import dlt
from pyspark.sql.functions import col, expr

@dlt.table(
    comment="Bronze CDC events from Auto Loader"
)
def customers_bronze():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load("/Volumes/demo/pipeline/landing/cdc_raw/")
    )

dlt.create_streaming_table("customers_silver")

dlt.apply_changes(
    target="customers_silver",
    source="customers_bronze",
    keys=["id"],
    sequence_by=col("operation_date"),
    apply_as_deletes=expr("operation = 'DELETE'"),
    except_column_list=["operation", "operation_date"]
)
```

### Declarative Pipelines Python Syntax (dp API)

```python
import dlt as dp
from pyspark.sql.functions import col, expr

@dp.table
def customers_bronze():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load("/Volumes/demo/pipeline/landing/cdc_raw/")
    )

dp.create_streaming_table("customers_silver")

dp.apply_changes(
    target="customers_silver",
    source="customers_bronze",
    keys=["id"],
    sequence_by=col("operation_date"),
    apply_as_deletes=expr("operation = 'DELETE'"),
    except_column_list=["operation", "operation_date"]
)
```

## Delta Change Data Feed

Delta Change Data Feed (CDF) captures row-level changes made to a Delta table, enabling downstream consumers to process only what changed.

### Enable CDF on a Table

```sql
-- Enable on existing table
ALTER TABLE demo.pipeline.customers_silver
SET TBLPROPERTIES (delta.enableChangeDataFeed = true);

-- Or enable at creation
CREATE TABLE demo.pipeline.customers_silver (
    id BIGINT,
    name STRING,
    email STRING,
    amount DECIMAL(10,2)
) TBLPROPERTIES (delta.enableChangeDataFeed = true);
```

### Read Changes

```python
# Batch read: changes since version 5
changes_df = (
    spark.read
    .option("readChangeFeed", "true")
    .option("startingVersion", 5)
    .table("demo.pipeline.customers_silver")
)

# Batch read: changes within a timestamp range
changes_df = (
    spark.read
    .option("readChangeFeed", "true")
    .option("startingTimestamp", "2024-06-01")
    .option("endingTimestamp", "2024-06-30")
    .table("demo.pipeline.customers_silver")
)

# Streaming read: continuous change feed
changes_stream = (
    spark.readStream
    .option("readChangeFeed", "true")
    .option("startingVersion", 0)
    .table("demo.pipeline.customers_silver")
)
```

CDF records include metadata columns: `_change_type` (`insert`, `update_preimage`, `update_postimage`, `delete`), `_commit_version`, and `_commit_timestamp`.
