# Output Formats Guide

Where and how to save generated synthetic data.

## Storage Destination

### Ask for Catalog and Schema

By default, use the `ai_dev_kit` catalog. Ask the user which schema to use:

> "I'll save the data to `ai_dev_kit.<schema>`. What schema name would you like to use? (You can also specify a different catalog if needed.)"

If the user provides just a schema name, use `ai_dev_kit.{schema}`. If they provide `catalog.schema`, use that instead.

### Create Infrastructure in Script

Always create the schema and volume **inside the Python script** using `spark.sql()`. Do NOT make separate MCP SQL calls - it's much slower.

```python
CATALOG = "ai_dev_kit"
SCHEMA = "synthetic_data"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Note: Assume catalog exists - do NOT create it
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_data")
```

**Important:** Do NOT create catalogs - assume they already exist. Only create schema and volume.

---

## Format Comparison

| Format | Use Case | Extension | Best For |
|--------|----------|-----------|----------|
| **Parquet** | Default - SDP pipeline input | `.parquet` or none | Best compression, query performance |
| **JSON** | Log-style ingestion | `.json` | Simulating external data feeds |
| **CSV** | Legacy systems | `.csv` | Human-readable, spreadsheet import |
| **Delta Table** | Direct analytics | N/A | Skip SDP, query immediately |

---

## Parquet to Volumes (Default)

Standard format for SDP pipeline input. Best compression and query performance.

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Save as parquet files (directory format)
customers_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/customers")
orders_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/orders")
tickets_df.write.mode("overwrite").parquet(f"{VOLUME_PATH}/tickets")
```

**Notes:**
- Files may not use a file extension or might end with `.parquet`
- Spark writes as a directory with part files
- Use `mode("overwrite")` for one-time generation
- Use `mode("append")` for incremental/scheduled jobs

---

## JSON to Volumes

Common pattern for simulating SDP ingestion from external data feeds (logs, webhooks).

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Save as JSON files
customers_df.write.mode("overwrite").json(f"{VOLUME_PATH}/customers_json")
orders_df.write.mode("overwrite").json(f"{VOLUME_PATH}/orders_json")
```

**When to use:**
- Simulating log ingestion
- External API data feeds
- User explicitly requests JSON format

---

## CSV to Volumes

Common pattern for simulating data from legacy systems or spreadsheet exports.

```python
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_data"

# Save as CSV with headers
customers_df.write.mode("overwrite").option("header", "true").csv(f"{VOLUME_PATH}/customers_csv")
orders_df.write.mode("overwrite").option("header", "true").csv(f"{VOLUME_PATH}/orders_csv")
```

**Options:**
```python
# Full options for CSV
df.write \
    .mode("overwrite") \
    .option("header", "true") \
    .option("delimiter", ",") \
    .option("quote", '"') \
    .option("escape", "\\") \
    .csv(f"{VOLUME_PATH}/data_csv")
```

**When to use:**
- Legacy system integration
- Human-readable data
- Spreadsheet import testing

---

## Delta Table (Unity Catalog)

Write directly to managed Delta tables when data is ready for analytics consumption (skip SDP pipeline).

```python
# Ensure schema exists
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

# Save as managed Delta tables
customers_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
orders_df.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.orders")

# With additional options
customers_df.write \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.customers")
```

**When to use:**
- User wants data ready to query immediately
- Skip the SDP bronze/silver/gold pipeline
- Direct SQL analytics

---

## Write Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `overwrite` | Replace existing data | One-time generation, regeneration |
| `append` | Add to existing data | Incremental/scheduled jobs |
| `ignore` | Skip if exists | Idempotent generation |
| `error` | Fail if exists | Safety check |

### Incremental Generation Pattern

```python
WRITE_MODE = "append"  # For scheduled jobs

# Only generate new records since last run
from datetime import datetime, timedelta

LAST_RUN = datetime.now() - timedelta(days=1)
END_DATE = datetime.now()

# Generate only new data
new_orders_df = generate_orders(start_date=LAST_RUN, end_date=END_DATE)
new_orders_df.write.mode(WRITE_MODE).parquet(f"{VOLUME_PATH}/orders")
```

---

## Validation After Write

After successful execution, validate the generated data:

```python
# Read back and verify
customers_check = spark.read.parquet(f"{VOLUME_PATH}/customers")
orders_check = spark.read.parquet(f"{VOLUME_PATH}/orders")

print(f"Customers: {customers_check.count():,} rows")
print(f"Orders: {orders_check.count():,} rows")

# Verify distributions
customers_check.groupBy("tier").count().show()
orders_check.describe("amount").show()
```

Or use `get_volume_folder_details` MCP tool:
- `volume_path`: "my_catalog/my_schema/raw_data/customers"
- `format`: "parquet"
- `table_stat_level`: "SIMPLE"
