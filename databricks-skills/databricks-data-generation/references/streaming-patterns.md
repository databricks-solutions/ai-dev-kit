# Streaming Patterns

Patterns for generating real-time streaming data with dbldatagen and integrating with Databricks streaming infrastructure.

## dbldatagen Streaming Basics

dbldatagen can generate continuous streaming DataFrames using Spark's rate source under the hood:

```python
import dbldatagen as dg

streaming_spec = (
    dg.DataGenerator(spark, rows=1_000_000, partitions=10)
    .withColumn("device_id", "long", minValue=1000, maxValue=2000)
    .withColumn("temperature", "float", minValue=15.0, maxValue=35.0, distribution="normal")
    .withColumn("humidity", "float", minValue=30.0, maxValue=90.0, random=True)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", interval="1 second")
)

streaming_df = streaming_spec.build(withStreaming=True, options={"rowsPerSecond": 5000})
```

The `withStreaming=True` flag converts the batch spec into a structured streaming source. The `rowsPerSecond` option controls throughput. The generated stream runs continuously until stopped.

## Rate Control

### Rows Per Second

```python
# Low throughput (testing/development)
streaming_df = spec.build(withStreaming=True, options={"rowsPerSecond": 100})

# Medium throughput (demo)
streaming_df = spec.build(withStreaming=True, options={"rowsPerSecond": 5_000})

# High throughput (load testing)
streaming_df = spec.build(withStreaming=True, options={"rowsPerSecond": 50_000})
```

### Partition Impact

More partitions enable higher throughput since each partition reads from a separate rate source micro-partition:

```python
# Higher partitions for higher throughput
spec = dg.DataGenerator(spark, rows=10_000_000, partitions=50)

# Each partition generates rowsPerSecond / numPartitions rows
# 50_000 rows/sec with 50 partitions = 1000 rows/sec/partition
streaming_df = spec.build(withStreaming=True, options={"rowsPerSecond": 50_000})
```

## Streaming to Delta

Write a streaming DataFrame to a Delta table with checkpointing:

```python
catalog, schema = "demo", "streaming"

(streaming_df
 .writeStream
 .format("delta")
 .outputMode("append")
 .option("checkpointLocation", f"/Volumes/{catalog}/{schema}/checkpoints/sensor_stream")
 .toTable(f"{catalog}.{schema}.sensor_readings"))
```

With trigger options:

```python
# Process all available data then stop (useful for testing)
(streaming_df
 .writeStream
 .format("delta")
 .trigger(availableNow=True)
 .option("checkpointLocation", f"/Volumes/{catalog}/{schema}/checkpoints/sensor_stream")
 .toTable(f"{catalog}.{schema}.sensor_readings"))

# Process in fixed intervals
(streaming_df
 .writeStream
 .format("delta")
 .trigger(processingTime="10 seconds")
 .option("checkpointLocation", f"/Volumes/{catalog}/{schema}/checkpoints/sensor_stream")
 .toTable(f"{catalog}.{schema}.sensor_readings"))
```

## Streaming to Volumes

Write streaming data as JSON files to a UC Volume for Auto Loader pickup downstream:

```python
volume_path = f"/Volumes/{catalog}/{schema}/landing"

(streaming_df
 .writeStream
 .format("json")
 .outputMode("append")
 .option("checkpointLocation", f"{volume_path}/_checkpoints/sensor_json")
 .option("maxRecordsPerFile", 10_000)  # control file size
 .start(f"{volume_path}/sensor_raw/"))
```

This pattern is useful when you want to simulate an external system landing files in a volume, which a separate pipeline then ingests via Auto Loader.

## IoT Streaming Example

Complete example generating streaming sensor data with anomaly injection:

```python
import dbldatagen as dg

sensor_spec = (
    dg.DataGenerator(spark, rows=10_000_000, partitions=20)
    .withColumn("device_id", "long", minValue=1000, maxValue=1500)
    .withColumn("device_type", "string",
                values=["temperature", "pressure", "humidity", "vibration"],
                weights=[30, 25, 25, 20])
    .withColumn("location", "string",
                values=["building_a", "building_b", "building_c", "warehouse"],
                weights=[30, 30, 20, 20])
    .withColumn("base_reading", "float", minValue=20.0, maxValue=80.0,
                distribution="normal", omit=True)
    .withColumn("noise", "float", expr="rand() * 4 - 2", omit=True)
    .withColumn("is_anomaly", "boolean", expr="rand() < 0.03")
    .withColumn("anomaly_spike", "float",
                expr="case when is_anomaly then (rand() * 50 + 20) else 0 end", omit=True)
    .withColumn("reading", "float", expr="base_reading + noise + anomaly_spike")
    .withColumn("battery_pct", "integer", minValue=5, maxValue=100, random=True)
    .withColumn("signal_strength", "integer", minValue=-90, maxValue=-30, random=True)
    .withColumn("timestamp", "timestamp", begin="2024-01-01", interval="1 second")
)

# Start streaming at 5000 events/sec
sensor_stream = sensor_spec.build(withStreaming=True, options={"rowsPerSecond": 5_000})

# Write to Delta
(sensor_stream
 .writeStream
 .format("delta")
 .outputMode("append")
 .option("checkpointLocation", "/Volumes/demo/iot/checkpoints/sensors")
 .toTable("demo.iot.sensor_readings"))
```

## Transaction Streaming Example

Financial transaction stream with realistic patterns — higher volume during business hours and burst periods:

```python
import dbldatagen as dg

txn_spec = (
    dg.DataGenerator(spark, rows=5_000_000, partitions=20)
    .withColumn("txn_id", "long", minValue=1, uniqueValues=5_000_000)
    .withColumn("account_id", "long", minValue=100_000, maxValue=199_999,
                distribution=dg.distributions.Exponential(1.5))
    .withColumn("merchant_id", "long", minValue=50_000, maxValue=59_999)
    .withColumn("txn_type", "string",
                values=["purchase", "refund", "transfer", "withdrawal"],
                weights=[70, 10, 12, 8])
    .withColumn("amount", "decimal(10,2)", minValue=1, maxValue=10_000,
                distribution="exponential")
    .withColumn("currency", "string",
                values=["USD", "EUR", "GBP"], weights=[70, 20, 10])
    .withColumn("channel", "string",
                values=["online", "in_store", "mobile", "atm"],
                weights=[35, 25, 30, 10])
    .withColumn("is_fraud", "boolean", expr="rand() < 0.015")
    .withColumn("risk_score", "float",
                expr="case when is_fraud then 0.7 + rand() * 0.3 else rand() * 0.4 end")
    .withColumn("timestamp", "timestamp", begin="2024-01-01", interval="500 milliseconds")
)

txn_stream = txn_spec.build(withStreaming=True, options={"rowsPerSecond": 2_000})

(txn_stream
 .writeStream
 .format("delta")
 .outputMode("append")
 .option("checkpointLocation", "/Volumes/demo/finance/checkpoints/transactions")
 .toTable("demo.finance.transactions"))
```

## Spark Declarative Pipelines Integration

Use streaming synthetic data with Spark Declarative Pipelines:

### Auto Loader Source (from Volume)

```python
import dlt
from pyspark.sql import functions as F

@dlt.table(
    comment="Raw streaming events from Auto Loader"
)
def streaming_events_bronze():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.inferColumnTypes", "true")
        .load("/Volumes/demo/streaming/landing/events_raw/")
        .withColumn("_ingested_at", F.current_timestamp())
    )

@dlt.table(
    comment="Cleaned streaming events"
)
@dlt.expect_or_drop("valid_event_id", "event_id IS NOT NULL")
@dlt.expect_or_drop("valid_timestamp", "timestamp IS NOT NULL")
def streaming_events_silver():
    return (
        dlt.read_stream("streaming_events_bronze")
        .withColumn("event_id", F.col("event_id").cast("long"))
        .withColumn("timestamp", F.col("timestamp").cast("timestamp"))
        .dropDuplicates(["event_id"])
    )
```

### Direct Streaming Table

```python
import dlt

@dlt.table(
    comment="Live sensor readings (streaming table)"
)
def live_sensor_readings():
    """Streaming table that continuously ingests from a Delta streaming source."""
    return (
        spark.readStream
        .table("demo.iot.sensor_readings")
        .withWatermark("timestamp", "10 minutes")
    )
```

### Windowed Aggregations in Spark Declarative Pipelines

```python
import dlt
from pyspark.sql import functions as F

@dlt.table(
    comment="5-minute aggregated sensor metrics"
)
def sensor_metrics_5min():
    return (
        dlt.read_stream("live_sensor_readings")
        .withWatermark("timestamp", "10 minutes")
        .groupBy(
            F.window("timestamp", "5 minutes"),
            "device_id",
            "device_type"
        )
        .agg(
            F.avg("reading").alias("avg_reading"),
            F.min("reading").alias("min_reading"),
            F.max("reading").alias("max_reading"),
            F.count("*").alias("event_count"),
            F.sum(F.col("is_anomaly").cast("int")).alias("anomaly_count"),
        )
    )
```
