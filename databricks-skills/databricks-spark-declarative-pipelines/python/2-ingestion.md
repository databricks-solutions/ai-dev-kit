# Python Data Ingestion

Data ingestion patterns using the modern `pyspark.pipelines` API.

**Official Documentation:**
- [Auto Loader options](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/options)
- [Structured Streaming + Kafka](https://docs.databricks.com/aws/en/structured-streaming/kafka)

---

## Auto Loader (Cloud Files)

**IMPORTANT**: When using `spark.readStream.format("cloudFiles")`, you **must specify a `cloudFiles.schemaLocation`** for schema metadata storage.

### Schema Location

**Never use the source data volume** - causes permission conflicts.

**Recommended pattern:**
```
/Volumes/{catalog}/{schema}/{pipeline_name}_metadata/schemas/{table_name}
```

Configure in pipeline settings:
```yaml
configuration:
  schema_location_base: /Volumes/my_catalog/pipeline_metadata/my_pipeline/schemas
```

### Basic Pattern

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

schema_location_base = spark.conf.get("schema_location_base")

@dp.table(name="bronze_orders", cluster_by=["order_date"])
def bronze_orders():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_orders")
        .option("cloudFiles.inferColumnTypes", "true")
        .load("/Volumes/my_catalog/my_schema/raw/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )
```

**Key options:**
- `cloudFiles.format`: `json`, `csv`, `parquet`, `avro`, `text`, `binaryFile`
- `cloudFiles.schemaLocation`: Required for schema inference
- `cloudFiles.inferColumnTypes`: Infer types (default strings)
- `cloudFiles.schemaHints`: Hint specific column types

### Rescue Data (Quarantine Pattern)

```python
@dp.table(name="bronze_events", cluster_by=["ingestion_date"])
def bronze_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", f"{schema_location_base}/bronze_events")
        .option("rescuedDataColumn", "_rescued_data")
        .load("/Volumes/catalog/schema/raw/events/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_has_errors", F.col("_rescued_data").isNotNull())
    )

@dp.table(name="bronze_quarantine")
def bronze_quarantine():
    return spark.readStream.table("bronze_events").filter("_has_errors = true")

@dp.table(name="silver_clean")
def silver_clean():
    return spark.readStream.table("bronze_events").filter("_has_errors = false")
```

---

## Streaming Sources

### Kafka

```python
@dp.table(name="bronze_kafka_events")
def bronze_kafka_events():
    kafka_brokers = spark.conf.get("kafka_brokers")
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", kafka_brokers)
        .option("subscribe", "events-topic")
        .option("startingOffsets", "latest")
        .load()
        .selectExpr(
            "CAST(key AS STRING) AS event_key",
            "CAST(value AS STRING) AS event_value",
            "topic", "partition", "offset",
            "timestamp AS kafka_timestamp"
        )
        .withColumn("_ingested_at", F.current_timestamp())
    )
```

### Parse JSON from Kafka

```python
from pyspark.sql.types import StructType, StructField, StringType, TimestampType

event_schema = StructType([
    StructField("event_id", StringType()),
    StructField("event_type", StringType()),
    StructField("timestamp", TimestampType())
])

@dp.table(name="silver_events")
def silver_events():
    return (
        spark.readStream.table("bronze_kafka_events")
        .withColumn("data", F.from_json("event_value", event_schema))
        .select("data.*", "kafka_timestamp", "_ingested_at")
    )
```

---

## Authentication

### Databricks Secrets

```python
username = dbutils.secrets.get(scope="kafka", key="username")
password = dbutils.secrets.get(scope="kafka", key="password")
```

### Pipeline Parameters

```python
kafka_brokers = spark.conf.get("kafka_brokers")
input_path = spark.conf.get("input_path")
```

---

## Best Practices

1. **Always specify schemaLocation** for Auto Loader (required in Python)

2. **Add ingestion metadata:**
```python
.withColumn("_ingested_at", F.current_timestamp())
.withColumn("_source_file", F.col("_metadata.file_path"))
```

3. **Handle rescue data** - route malformed records to quarantine

4. **Use pipeline parameters** for paths and connection strings

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Missing schemaLocation error | Always specify `cloudFiles.schemaLocation` |
| Schema location permission error | Use dedicated metadata volume, not source data volume |
| Files not picked up | Verify path and format match actual files |
| Kafka lag increasing | Check downstream bottlenecks |
