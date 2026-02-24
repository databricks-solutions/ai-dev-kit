# Data Ingestion Patterns for SDP

Covers data ingestion patterns for Spark Declarative Pipelines including Auto Loader for cloud storage and streaming sources like Kafka and Event Hub.

**Language Support**: SQL (primary), Python via modern `pyspark.pipelines` API. See [5-python-api.md](5-python-api.md) for Python syntax.

---

## Auto Loader (Cloud Files)

Auto Loader incrementally processes new data files as they arrive in cloud storage.

### Basic Pattern

```sql
CREATE OR REPLACE STREAMING TABLE bronze_orders AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS source_file,
  _metadata.file_modification_time AS file_timestamp
FROM read_files(
  '/mnt/raw/orders/',
  format => 'json',
  schemaHints => 'order_id STRING, amount DECIMAL(10,2)'
);
```

### Schema Evolution

```sql
CREATE OR REPLACE STREAMING TABLE bronze_customers AS
SELECT
  *,
  current_timestamp() AS _ingested_at
FROM stream(read_files(
  '/mnt/raw/customers/',
  format => 'json',
  schemaHints => 'customer_id STRING, email STRING',
  mode => 'PERMISSIVE'  -- Handles schema changes gracefully
));
```

### File Formats

**JSON**:
```sql
FROM read_files(
  's3://bucket/data/',
  format => 'json',
  schemaHints => 'id STRING, timestamp TIMESTAMP'
)
```

**CSV**:
```sql
FROM read_files(
  '/mnt/raw/data/',
  format => 'csv',
  schemaHints => 'id STRING, name STRING, amount DECIMAL(10,2)',
  header => true,
  delimiter => ','
)
```

**Parquet** (schema auto-inferred):
```sql
FROM read_files(
  'abfss://container@storage.dfs.core.windows.net/data/',
  format => 'parquet'
)
```

**Avro**:
```sql
FROM read_files(
  '/mnt/raw/events/',
  format => 'avro',
  schemaHints => 'event_id STRING, event_time TIMESTAMP'
)
```

### Schema Inference

**Explicit hints** (recommended for production):
```sql
FROM read_files(
  '/mnt/raw/sales/',
  format => 'json',
  schemaHints => 'sale_id STRING, customer_id STRING, amount DECIMAL(10,2), sale_date DATE'
)
```

**Partial hints** (infer remaining columns):
```sql
FROM read_files(
  '/mnt/raw/data/',
  format => 'json',
  schemaHints => 'id STRING, critical_field DECIMAL(10,2)'  -- Others auto-inferred
)
```

### Rescue Data and Quarantine

Handle malformed records with `_rescued_data`:

```sql
-- Flag records with parsing errors
CREATE OR REPLACE STREAMING TABLE bronze_events AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  CASE WHEN _rescued_data IS NOT NULL THEN TRUE ELSE FALSE END AS has_parsing_errors
FROM read_files(
  '/mnt/raw/events/',
  format => 'json',
  schemaHints => 'event_id STRING, event_time TIMESTAMP'
);

-- Quarantine for investigation
CREATE OR REPLACE STREAMING TABLE bronze_events_quarantine AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NOT NULL;

-- Clean data for downstream
CREATE OR REPLACE STREAMING TABLE silver_events_clean AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NULL;
```

---

## Streaming Sources (Kafka, Event Hub, Kinesis)

### Kafka Source

```sql
CREATE OR REPLACE STREAMING TABLE bronze_kafka_events AS
SELECT
  CAST(key AS STRING) AS event_key,
  CAST(value AS STRING) AS event_value,
  topic,
  partition,
  offset,
  timestamp AS kafka_timestamp,
  current_timestamp() AS _ingested_at
FROM read_stream(
  format => 'kafka',
  kafka.bootstrap.servers => '${kafka_brokers}',
  subscribe => 'events-topic',
  startingOffsets => 'latest',  -- or 'earliest'
  kafka.security.protocol => 'SASL_SSL',
  kafka.sasl.mechanism => 'PLAIN',
  kafka.sasl.jaas.config => 'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="${kafka_username}" password="${kafka_password}";'
);
```

### Kafka with Multiple Topics

```sql
FROM read_stream(
  format => 'kafka',
  kafka.bootstrap.servers => '${kafka_brokers}',
  subscribe => 'topic1,topic2,topic3',
  startingOffsets => 'latest'
)
```

### Azure Event Hub

```sql
CREATE OR REPLACE STREAMING TABLE bronze_eventhub_events AS
SELECT
  CAST(body AS STRING) AS event_body,
  enqueuedTime AS event_time,
  offset,
  sequenceNumber,
  current_timestamp() AS _ingested_at
FROM read_stream(
  format => 'eventhubs',
  eventhubs.connectionString => '${eventhub_connection_string}',
  eventhubs.consumerGroup => '${consumer_group}',
  startingPosition => 'latest'
);
```

### AWS Kinesis

```sql
CREATE OR REPLACE STREAMING TABLE bronze_kinesis_events AS
SELECT
  CAST(data AS STRING) AS event_data,
  partitionKey,
  sequenceNumber,
  approximateArrivalTimestamp AS arrival_time,
  current_timestamp() AS _ingested_at
FROM read_stream(
  format => 'kinesis',
  kinesis.streamName => '${stream_name}',
  kinesis.region => '${aws_region}',
  kinesis.startingPosition => 'LATEST'
);
```

### Parse JSON from Streaming Sources

```sql
-- Parse JSON from Kafka value
CREATE OR REPLACE STREAMING TABLE silver_kafka_parsed AS
SELECT
  from_json(
    event_value,
    'event_id STRING, event_type STRING, user_id STRING, timestamp TIMESTAMP, properties MAP<STRING, STRING>'
  ) AS event_data,
  kafka_timestamp,
  _ingested_at
FROM STREAM bronze_kafka_events;

-- Flatten parsed JSON
CREATE OR REPLACE STREAMING TABLE silver_kafka_flattened AS
SELECT
  event_data.event_id,
  event_data.event_type,
  event_data.user_id,
  event_data.timestamp AS event_timestamp,
  event_data.properties,
  kafka_timestamp,
  _ingested_at
FROM STREAM silver_kafka_parsed;
```

---

## Authentication

### Using Databricks Secrets

**Kafka**:
```sql
kafka.sasl.jaas.config => 'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required username="{{secrets/kafka/username}}" password="{{secrets/kafka/password}}";'
```

**Event Hub**:
```sql
eventhubs.connectionString => '{{secrets/eventhub/connection-string}}'
```

### Using Pipeline Variables

Reference variables in SQL:
```sql
kafka.bootstrap.servers => '${kafka_brokers}'
```

Define in pipeline configuration:
```yaml
variables:
  kafka_brokers:
    default: "broker1:9092,broker2:9092"
```

---

## Key Patterns

### 1. Always Add Ingestion Timestamp

```sql
SELECT
  *,
  current_timestamp() AS _ingested_at  -- Track when data entered system
FROM read_files(...)
```

### 2. Include File Metadata for Debugging

```sql
SELECT
  *,
  _metadata.file_path AS source_file,
  _metadata.file_modification_time AS file_timestamp,
  _metadata.file_size AS file_size
FROM read_files(...)
```

### 3. Use Schema Hints for Production

```sql
-- ✅ Explicit schema prevents surprises
FROM read_files(
  '/mnt/data/',
  format => 'json',
  schemaHints => 'id STRING, amount DECIMAL(10,2), date DATE'
)

-- ❌ Fully inferred schemas can drift
FROM read_files('/mnt/data/', format => 'json')
```

### 4. Handle Rescue Data for Quality

```sql
-- Route errors to quarantine, clean to downstream
CREATE OR REPLACE STREAMING TABLE bronze_data_quarantine AS
SELECT * FROM STREAM bronze_data WHERE has_errors;

CREATE OR REPLACE STREAMING TABLE silver_data AS
SELECT * FROM STREAM bronze_data WHERE NOT has_errors;
```

### 5. Starting Positions

**Development**: `startingOffsets => 'latest'` (new data only)
**Backfill**: `startingOffsets => 'earliest'` (all available data)
**Recovery**: Checkpoints handle automatically

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Files not picked up | Verify format matches files and path is correct |
| Schema evolution breaking | Use `mode => 'PERMISSIVE'` and monitor `_rescued_data` |
| Kafka lag increasing | Check downstream bottlenecks, increase parallelism |
| Duplicate events | Implement deduplication in silver layer (see [2-streaming-patterns.md](2-streaming-patterns.md)) |
| Parsing errors | Use rescue data pattern to quarantine malformed records |

---

## Python API Examples

For Python, use modern `pyspark.pipelines` API. See [5-python-api.md](5-python-api.md) for complete guidance.

### Auto Loader (Python)

```python
from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.table(name="bronze_orders", cluster_by=["order_date"])
def bronze_orders():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("cloudFiles.schemaLocation", "/checkpoints/bronze_orders")
        .option("cloudFiles.schemaHints", "order_id STRING, amount DECIMAL(10,2)")
        .load("/mnt/raw/orders/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_file", F.col("_metadata.file_path"))
    )
```

### Kafka (Python)

```python
@dp.table(name="bronze_kafka_events")
def bronze_kafka_events():
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", spark.conf.get("kafka_brokers"))
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

### Quarantine (Python)

```python
@dp.table(name="bronze_events", cluster_by=["ingestion_date"])
def bronze_events():
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", "json")
        .option("rescuedDataColumn", "_rescued_data")
        .load("/mnt/raw/events/")
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("ingestion_date", F.current_date())
        .withColumn("_has_parsing_errors",
                   F.when(F.col("_rescued_data").isNotNull(), True)
                   .otherwise(False))
    )

@dp.table(name="bronze_events_quarantine")
def bronze_events_quarantine():
    return (
        spark.read.table("catalog.schema.bronze_events")
        .filter(F.col("_has_parsing_errors") == True)
    )
```
