# Medallion Architecture Patterns

Patterns for generating data across Bronze, Silver, and Gold layers in a Databricks lakehouse.

## Architecture Overview

```
                          Lakeflow Declarative Pipelines / Spark Structured Streaming
                         ┌─────────────────────────────────────────────────────────────┐
                         │                                                             │
  ┌─────────────────┐    │  ┌───────────┐      ┌───────────┐      ┌───────────┐       │
  │  UC Volumes      │───▶│  │  Bronze   │─────▶│  Silver   │─────▶│   Gold    │       │
  │  (raw JSON/CSV)  │    │  │ (raw ingest)│    │ (cleaned)  │     │ (aggregated)│      │
  └─────────────────┘    │  └───────────┘      └───────────┘      └───────────┘       │
                         │    Auto Loader       Type casting        groupBy + agg       │
                         │    Schema inference  Dedup + nulls       Business metrics    │
                         │                      Expectations                            │
                         └─────────────────────────────────────────────────────────────┘
```

Synthetic data enters the pipeline by writing to Unity Catalog Volumes. Auto Loader picks up new files and streams them through the medallion layers.

## Bronze: Writing Raw Data to Volumes

Generate data with dbldatagen, then land it as raw files in a UC Volume:

```python
import dbldatagen as dg
from pyspark.sql import functions as F

# Create the volume if it doesn't exist
catalog, schema, volume = "demo", "retail", "landing"
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}")

volume_path = f"/Volumes/{catalog}/{schema}/{volume}"

# Generate raw data
orders_spec = (
    dg.DataGenerator(spark, rows=500_000, partitions=10)
    .withColumn("order_id", "long", minValue=1, uniqueValues=500_000)
    .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("product_id", "long", minValue=10_000, maxValue=19_999)
    .withColumn("quantity", "integer", minValue=1, maxValue=20, distribution="exponential")
    .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
    .withColumn("order_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("status", "string",
                values=["completed", "pending", "cancelled", "returned"],
                weights=[70, 15, 10, 5])
)

orders_df = orders_spec.build()

# Write as JSON to the volume (raw landing zone)
(orders_df
 .write
 .format("json")
 .mode("append")
 .save(f"{volume_path}/orders_raw/"))
```

For CSV output:

```python
(orders_df
 .write
 .format("csv")
 .option("header", "true")
 .mode("append")
 .save(f"{volume_path}/orders_csv/"))
```

## Bronze: Auto Loader Ingestion

### Spark Structured Streaming

```python
bronze_df = (
    spark.readStream
    .format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.inferColumnTypes", "true")
    .option("cloudFiles.schemaLocation", f"{volume_path}/_schemas/orders")
    .load(f"{volume_path}/orders_raw/")
    .withColumn("_ingested_at", F.current_timestamp())
    .withColumn("_source_file", F.input_file_name())
)

(bronze_df
 .writeStream
 .format("delta")
 .option("checkpointLocation", f"{volume_path}/_checkpoints/orders_bronze")
 .outputMode("append")
 .toTable(f"{catalog}.{schema}.orders_bronze"))
```

### Spark Declarative Pipelines

```python
import dlt

@dlt.table(
    comment="Raw orders ingested from JSON via Auto Loader"
)
def orders_bronze():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"/Volumes/{catalog}/{schema}/{volume}/orders_raw/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.input_file_name())
    )
```

Adding `_ingested_at` and `_source_file` metadata columns is a best practice — they provide lineage for debugging and auditing.

## Silver: Cleaned Tables

Silver tables apply data quality rules: type casting, deduplication, null handling, and validation.

### Spark SQL

```sql
CREATE OR REPLACE TABLE demo.retail.orders_silver AS
SELECT
    CAST(order_id AS BIGINT) AS order_id,
    CAST(customer_id AS BIGINT) AS customer_id,
    CAST(product_id AS BIGINT) AS product_id,
    CAST(quantity AS INT) AS quantity,
    CAST(unit_price AS DECIMAL(10,2)) AS unit_price,
    quantity * unit_price AS total_amount,
    CAST(order_date AS DATE) AS order_date,
    COALESCE(LOWER(TRIM(status)), 'unknown') AS status,
    _ingested_at
FROM demo.retail.orders_bronze
WHERE order_id IS NOT NULL
QUALIFY ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY _ingested_at DESC) = 1;
```

### Declarative Pipelines with Expectations

```python
import dlt
from pyspark.sql import functions as F

@dlt.table(
    comment="Cleaned and deduplicated orders"
)
@dlt.expect_or_drop("valid_order_id", "order_id IS NOT NULL")
@dlt.expect_or_drop("valid_quantity", "quantity > 0")
@dlt.expect("valid_price", "unit_price > 0")  # warn but don't drop
def orders_silver():
    return (
        dlt.read_stream("orders_bronze")
        .withColumn("order_id", F.col("order_id").cast("long"))
        .withColumn("customer_id", F.col("customer_id").cast("long"))
        .withColumn("product_id", F.col("product_id").cast("long"))
        .withColumn("quantity", F.col("quantity").cast("int"))
        .withColumn("unit_price", F.col("unit_price").cast("decimal(10,2)"))
        .withColumn("total_amount", F.col("quantity") * F.col("unit_price"))
        .withColumn("status", F.coalesce(F.lower(F.trim(F.col("status"))), F.lit("unknown")))
        .dropDuplicates(["order_id"])
    )
```

Expectations are a Spark Declarative Pipelines feature that enforces data quality at the table level. `expect_or_drop` removes invalid rows; `expect` records violations but keeps the data.

## Gold: Aggregations

Gold tables contain business-level aggregations and metrics.

### Declarative Pipeline Materialized View

```python
import dlt
from pyspark.sql import functions as F

@dlt.table(
    comment="Customer 360 metrics"
)
def gold_customer_metrics():
    return (
        dlt.read("orders_silver")
        .groupBy("customer_id")
        .agg(
            F.count("order_id").alias("total_orders"),
            F.sum("total_amount").alias("total_spend"),
            F.avg("total_amount").alias("avg_order_value"),
            F.min("order_date").alias("first_order_date"),
            F.max("order_date").alias("last_order_date"),
            F.countDistinct("product_id").alias("unique_products"),
        )
    )

@dlt.table(
    comment="Daily revenue by product category"
)
def gold_daily_revenue():
    orders = dlt.read("orders_silver")
    products = spark.read.table(f"{catalog}.{schema}.products")
    return (
        orders.join(products, "product_id")
        .groupBy("order_date", "category")
        .agg(
            F.sum("total_amount").alias("revenue"),
            F.count("order_id").alias("order_count"),
            F.sum("quantity").alias("units_sold"),
        )
    )
```

### Spark SQL

```sql
CREATE OR REPLACE TABLE demo.retail.gold_customer_metrics AS
SELECT
    customer_id,
    COUNT(order_id) AS total_orders,
    SUM(total_amount) AS total_spend,
    AVG(total_amount) AS avg_order_value,
    MIN(order_date) AS first_order_date,
    MAX(order_date) AS last_order_date,
    COUNT(DISTINCT product_id) AS unique_products
FROM demo.retail.orders_silver
GROUP BY customer_id;
```

## Complete Example: Retail Pipeline

End-to-end pipeline: generate data, land in volumes, process through all three layers.

### Step 1: Generate and Land Data

```python
import dbldatagen as dg
from pyspark.sql import functions as F

catalog, schema, volume = "demo", "retail", "landing"
volume_path = f"/Volumes/{catalog}/{schema}/{volume}"

# Create infrastructure
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}")

# Generate customers
customers_df = (
    dg.DataGenerator(spark, rows=100_000, partitions=10)
    .withColumn("customer_id", "long", minValue=1_000_000, uniqueValues=100_000)
    .withColumn("name", "string", template=r"\\w \\w")
    .withColumn("email", "string", template=r"\\w.\\w@\\w.com")
    .withColumn("signup_date", "date", begin="2020-01-01", end="2024-12-31", random=True)
    .withColumn("loyalty_tier", "string",
                values=["Bronze", "Silver", "Gold", "Platinum"], weights=[50, 30, 15, 5])
    .build()
)

# Write customers directly to Delta (reference table, not CDC)
customers_df.write.format("delta").mode("overwrite").saveAsTable(
    f"{catalog}.{schema}.customers"
)

# Generate orders and land as JSON
orders_df = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=20)
    .withColumn("order_id", "long", minValue=1, uniqueValues=1_000_000)
    .withColumn("customer_id", "long", minValue=1_000_000, maxValue=1_099_999)
    .withColumn("product_id", "long", minValue=10_000, maxValue=19_999)
    .withColumn("quantity", "integer", minValue=1, maxValue=20, distribution="exponential")
    .withColumn("unit_price", "decimal(10,2)", minValue=5, maxValue=500, random=True)
    .withColumn("order_date", "date", begin="2024-01-01", end="2024-12-31", random=True)
    .withColumn("status", "string",
                values=["completed", "pending", "cancelled"], weights=[75, 15, 10])
    .build()
)

orders_df.write.format("json").mode("overwrite").save(f"{volume_path}/orders_raw/")
```

### Step 2: Spark Declarative Pipeline Notebook

```python
import dlt
from pyspark.sql import functions as F

catalog, schema = "demo", "retail"
volume_path = f"/Volumes/{catalog}/{schema}/landing"

# Bronze: Auto Loader ingestion
@dlt.table(comment="Raw orders from JSON files")
def orders_bronze():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load(f"{volume_path}/orders_raw/")
        .withColumn("_ingested_at", F.current_timestamp())
    )

# Silver: Cleaned orders
@dlt.table(comment="Cleaned and validated orders")
@dlt.expect_or_drop("valid_order_id", "order_id IS NOT NULL")
@dlt.expect_or_drop("positive_quantity", "quantity > 0")
@dlt.expect("valid_status", "status IN ('completed', 'pending', 'cancelled')")
def orders_silver():
    return (
        dlt.read_stream("orders_bronze")
        .withColumn("total_amount",
                    F.col("quantity").cast("int") * F.col("unit_price").cast("decimal(10,2)"))
        .withColumn("status", F.lower(F.trim(F.col("status"))))
        .dropDuplicates(["order_id"])
    )

# Gold: Customer metrics
@dlt.table(comment="Customer 360 aggregation")
def gold_customer_360():
    orders = dlt.read("orders_silver")
    customers = spark.read.table(f"{catalog}.{schema}.customers")
    return (
        orders.groupBy("customer_id")
        .agg(
            F.count("order_id").alias("total_orders"),
            F.sum("total_amount").alias("total_spend"),
            F.avg("total_amount").alias("avg_order_value"),
            F.max("order_date").alias("last_order_date"),
        )
        .join(customers, "customer_id", "left")
    )
```
