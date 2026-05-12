# SQL Data Ingestion

Data ingestion patterns for cloud storage and streaming sources.

**Official Documentation:**
- [read_files function reference](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_files)
- [Auto Loader options](https://docs.databricks.com/aws/en/ingestion/cloud-object-storage/auto-loader/options)

---

## Auto Loader (Cloud Files)

Auto Loader incrementally processes new files. Use `STREAM read_files()` in streaming table queries.

### Basic Pattern

```sql
CREATE OR REFRESH STREAMING TABLE bronze_orders AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  _metadata.file_path AS _source_file
FROM STREAM read_files(
  '/Volumes/my_catalog/my_schema/raw/orders/',
  format => 'json',
  schemaHints => 'order_id STRING, amount DECIMAL(10,2)'
);
```

**Key points:**
- Use `FROM STREAM read_files(...)` for streaming tables (not `FROM read_files(...)` which is batch)
- `format` supports: `json`, `csv`, `parquet`, `avro`, `text`, `binaryFile`
- `schemaHints` recommended for production to prevent schema drift
- `_metadata` provides file path, modification time, size

### Schema Handling

```sql
-- Explicit hints (recommended for production)
FROM STREAM read_files(
  '/Volumes/catalog/schema/raw/',
  format => 'json',
  schemaHints => 'id STRING, amount DECIMAL(10,2), date DATE'
)

-- Schema evolution with rescue data
FROM STREAM read_files(
  '/Volumes/catalog/schema/raw/',
  format => 'json',
  schemaHints => 'id STRING',
  mode => 'PERMISSIVE'
)
```

### Rescue Data (Quarantine Pattern)

Handle malformed records:

```sql
-- Flag records with parsing errors
CREATE OR REFRESH STREAMING TABLE bronze_events AS
SELECT
  *,
  current_timestamp() AS _ingested_at,
  CASE WHEN _rescued_data IS NOT NULL THEN TRUE ELSE FALSE END AS _has_errors
FROM STREAM read_files('/Volumes/catalog/schema/raw/events/', format => 'json');

-- Quarantine bad records
CREATE OR REFRESH STREAMING TABLE bronze_quarantine AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NOT NULL;

-- Clean records for downstream
CREATE OR REFRESH STREAMING TABLE silver_clean AS
SELECT * FROM STREAM bronze_events WHERE _rescued_data IS NULL;
```

---

## Streaming Sources

### Kafka

```sql
CREATE OR REFRESH STREAMING TABLE bronze_kafka_events AS
SELECT
  CAST(key AS STRING) AS event_key,
  CAST(value AS STRING) AS event_value,
  topic, partition, offset,
  timestamp AS kafka_timestamp,
  current_timestamp() AS _ingested_at
FROM read_kafka(
  bootstrapServers => '${kafka_brokers}',
  subscribe => 'events-topic',
  startingOffsets => 'latest'
);
```

**Documentation:** [read_kafka function](https://docs.databricks.com/aws/en/sql/language-manual/functions/read_kafka)

### Parse JSON from Kafka

```sql
CREATE OR REFRESH STREAMING TABLE silver_events AS
SELECT
  from_json(event_value, 'event_id STRING, event_type STRING, timestamp TIMESTAMP') AS data,
  kafka_timestamp, _ingested_at
FROM STREAM bronze_kafka_events;
```

---

## Authentication

### Databricks Secrets

```sql
-- Kafka
`kafka.sasl.jaas.config` => '...username="{{secrets/kafka/username}}" password="{{secrets/kafka/password}}";'

-- Event Hub
`eventhubs.connectionString` => '{{secrets/eventhub/connection-string}}'
```

### Pipeline Variables

```sql
-- Reference in SQL
FROM STREAM read_files('${input_path}/orders/', format => 'json')
```

Define in pipeline configuration:
```yaml
configuration:
  input_path: /Volumes/my_catalog/my_schema/raw
```

---

## Best Practices

1. **Always add ingestion metadata:**
```sql
SELECT *, current_timestamp() AS _ingested_at, _metadata.file_path AS _source_file
```

2. **Use schemaHints for production** - prevents unexpected schema changes

3. **Handle rescue data** - route malformed records to quarantine table

4. **Use STREAM keyword** - `FROM STREAM read_files(...)` for streaming tables

---

## Common Issues

| Issue | Solution |
|-------|----------|
| Files not picked up | Verify path and format match actual files |
| "Cannot create streaming table from batch query" | Use `FROM STREAM read_files(...)` not `FROM read_files(...)` |
| Schema evolution breaking | Use `mode => 'PERMISSIVE'` and monitor `_rescued_data` |
| Kafka lag increasing | Check downstream bottlenecks |
