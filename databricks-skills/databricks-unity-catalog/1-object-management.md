# Unity Catalog Object Management

CRUD operations for catalogs, schemas, tables, volumes, and functions.

> **Prefer Liquid Clustering** (`CLUSTER BY`) over `PARTITIONED BY` for all new Delta tables.
> **Prefer managed tables** unless external storage governance is required.

## Catalogs

### Create Catalog

**SQL (AWS):**
```sql
-- Basic catalog
CREATE CATALOG IF NOT EXISTS my_catalog
COMMENT 'Production data catalog';

-- Catalog with managed storage location (S3)
CREATE CATALOG my_catalog
MANAGED LOCATION 's3://my-bucket/unity-catalog/my_catalog'
COMMENT 'Catalog with custom storage';

-- Foreign catalog (Lakehouse Federation)
CREATE FOREIGN CATALOG snowflake_catalog
USING CONNECTION snowflake_conn
OPTIONS (database 'PROD_DB');
```

**SQL (Azure):**
```sql
-- Catalog with managed storage location (ADLS Gen2)
CREATE CATALOG my_catalog
MANAGED LOCATION 'abfss://unity-catalog@storageaccount.dfs.core.windows.net/my_catalog'
COMMENT 'Catalog with custom storage';
```

**SQL (GCP):**
```sql
-- Catalog with managed storage location (GCS)
CREATE CATALOG my_catalog
MANAGED LOCATION 'gs://my-bucket/unity-catalog/my_catalog'
COMMENT 'Catalog with custom storage';
```

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Create catalog
catalog = w.catalogs.create(
    name="my_catalog",
    comment="Production data catalog"
)

# Create with storage location (AWS)
catalog = w.catalogs.create(
    name="my_catalog",
    storage_root="s3://my-bucket/unity-catalog/my_catalog",
    comment="Catalog with custom storage"
)

# Create with storage location (Azure)
catalog = w.catalogs.create(
    name="my_catalog",
    storage_root="abfss://unity-catalog@storageaccount.dfs.core.windows.net/my_catalog",
    comment="Catalog with custom storage"
)

# Create with storage location (GCP)
catalog = w.catalogs.create(
    name="my_catalog",
    storage_root="gs://my-bucket/unity-catalog/my_catalog",
    comment="Catalog with custom storage"
)

# List catalogs
for cat in w.catalogs.list():
    print(f"{cat.name}: {cat.comment}")

# Get catalog details
catalog = w.catalogs.get("my_catalog")

# Update catalog
w.catalogs.update(
    name="my_catalog",
    comment="Updated comment",
    owner="admin_group"
)

# Delete catalog (must be empty)
w.catalogs.delete("my_catalog", force=True)
```

**CLI:**
```bash
# Create catalog
databricks catalogs create my_catalog --comment "Production data catalog"

# Create with storage (AWS)
databricks catalogs create my_catalog \
    --storage-root "s3://my-bucket/unity-catalog/my_catalog" \
    --comment "Catalog with custom storage"

# Create with storage (Azure)
databricks catalogs create my_catalog \
    --storage-root "abfss://unity-catalog@storageaccount.dfs.core.windows.net/my_catalog" \
    --comment "Catalog with custom storage"

# List catalogs
databricks catalogs list

# Get catalog
databricks catalogs get my_catalog

# Update catalog
databricks catalogs update my_catalog --comment "Updated comment"

# Delete catalog
databricks catalogs delete my_catalog
```

---

## Schemas

### Create Schema

**SQL (AWS):**
```sql
-- Basic schema
CREATE SCHEMA IF NOT EXISTS my_catalog.bronze
COMMENT 'Raw data layer';

-- Schema with managed storage (S3)
CREATE SCHEMA my_catalog.bronze
MANAGED LOCATION 's3://my-bucket/bronze'
COMMENT 'Bronze layer with custom storage';
```

**SQL (Azure):**
```sql
-- Schema with managed storage (ADLS Gen2)
CREATE SCHEMA my_catalog.bronze
MANAGED LOCATION 'abfss://data@storageaccount.dfs.core.windows.net/bronze'
COMMENT 'Bronze layer with custom storage';
```

**SQL (GCP):**
```sql
-- Schema with managed storage (GCS)
CREATE SCHEMA my_catalog.bronze
MANAGED LOCATION 'gs://my-bucket/bronze'
COMMENT 'Bronze layer with custom storage';
```

**Python SDK:**
```python
# Create schema
schema = w.schemas.create(
    name="bronze",
    catalog_name="my_catalog",
    comment="Raw data layer"
)

# Create with storage root (AWS)
schema = w.schemas.create(
    name="bronze",
    catalog_name="my_catalog",
    storage_root="s3://my-bucket/bronze",
    comment="Bronze layer with custom storage"
)

# Create with storage root (Azure)
schema = w.schemas.create(
    name="bronze",
    catalog_name="my_catalog",
    storage_root="abfss://data@storageaccount.dfs.core.windows.net/bronze",
    comment="Bronze layer with custom storage"
)

# Create with storage root (GCP)
schema = w.schemas.create(
    name="bronze",
    catalog_name="my_catalog",
    storage_root="gs://my-bucket/bronze",
    comment="Bronze layer with custom storage"
)

# List schemas in catalog
for schema in w.schemas.list(catalog_name="my_catalog"):
    print(f"{schema.full_name}: {schema.comment}")

# Get schema
schema = w.schemas.get("my_catalog.bronze")

# Update schema
w.schemas.update(
    full_name="my_catalog.bronze",
    comment="Updated bronze layer"
)

# Delete schema
w.schemas.delete("my_catalog.bronze")
```

**CLI:**
```bash
# Create schema
databricks schemas create bronze my_catalog --comment "Raw data layer"

# Create with storage (AWS)
databricks schemas create bronze my_catalog \
    --storage-root "s3://my-bucket/bronze" \
    --comment "Bronze with custom storage"

# Create with storage (Azure)
databricks schemas create bronze my_catalog \
    --storage-root "abfss://data@storageaccount.dfs.core.windows.net/bronze" \
    --comment "Bronze with custom storage"

# List schemas
databricks schemas list my_catalog

# Get schema
databricks schemas get my_catalog.bronze

# Delete schema
databricks schemas delete my_catalog.bronze
```

---

## Tables

### Create Tables

**SQL:**
```sql
-- Managed table (UC manages storage)
CREATE TABLE my_catalog.bronze.raw_orders (
    order_id BIGINT COMMENT 'Unique order identifier',
    customer_id BIGINT,
    order_date DATE,
    amount DECIMAL(10, 2),
    _ingested_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
COMMENT 'Raw orders from source system'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- External table (user manages storage) - AWS
CREATE TABLE my_catalog.bronze.external_events
USING DELTA
LOCATION 's3://my-bucket/events/'
COMMENT 'External event data';

-- External table - Azure
CREATE TABLE my_catalog.bronze.external_events
USING DELTA
LOCATION 'abfss://data@storageaccount.dfs.core.windows.net/events/'
COMMENT 'External event data';

-- External table - GCP
CREATE TABLE my_catalog.bronze.external_events
USING DELTA
LOCATION 'gs://my-bucket/events/'
COMMENT 'External event data';

-- Create table from query
CREATE TABLE my_catalog.silver.cleaned_orders AS
SELECT
    order_id,
    customer_id,
    order_date,
    amount
FROM my_catalog.bronze.raw_orders
WHERE amount > 0;

-- Liquid Clustering (recommended over PARTITIONED BY)
CREATE TABLE my_catalog.gold.daily_sales (
    sale_date DATE,
    region STRING,
    total_amount DECIMAL(18, 2)
)
USING DELTA
CLUSTER BY (sale_date, region)
COMMENT 'Daily sales aggregates';

-- Partitioned table (legacy, use CLUSTER BY for new tables)
CREATE TABLE my_catalog.gold.daily_sales_legacy (
    sale_date DATE,
    region STRING,
    total_amount DECIMAL(18, 2)
)
USING DELTA
PARTITIONED BY (sale_date)
COMMENT 'Daily sales aggregates';

-- UniForm Iceberg table (readable by Iceberg clients)
CREATE TABLE my_catalog.silver.orders_iceberg (
    order_id BIGINT,
    customer_id BIGINT,
    amount DECIMAL(10, 2),
    order_date DATE
)
CLUSTER BY (order_date)
TBLPROPERTIES (
    'delta.universalFormat.enabledFormats' = 'iceberg'
)
COMMENT 'Orders table with Iceberg interoperability';

-- Managed Iceberg table (native Iceberg format)
CREATE TABLE my_catalog.silver.events_iceberg (
    event_id BIGINT,
    event_type STRING,
    event_date DATE
)
USING ICEBERG
COMMENT 'Native Iceberg table managed by UC';
```

**Python SDK:**
```python
# List tables in schema
for table in w.tables.list(catalog_name="my_catalog", schema_name="bronze"):
    print(f"{table.full_name}: {table.table_type}")

# Get table details
table = w.tables.get("my_catalog.bronze.raw_orders")
print(f"Columns: {[c.name for c in table.columns]}")
print(f"Storage location: {table.storage_location}")

# Delete table
w.tables.delete("my_catalog.bronze.old_table")
```

**CLI:**
```bash
# List tables
databricks tables list my_catalog bronze

# Get table details
databricks tables get my_catalog.bronze.raw_orders

# Check if table exists
databricks tables exists my_catalog.bronze.raw_orders

# Delete table
databricks tables delete my_catalog.bronze.old_table
```

### Table Cloning

**SQL:**
```sql
-- Shallow clone (shares data files, fast)
CREATE TABLE my_catalog.dev.orders_test
SHALLOW CLONE my_catalog.prod.orders;

-- Deep clone (copies data files, independent)
CREATE TABLE my_catalog.staging.orders_backup
DEEP CLONE my_catalog.prod.orders;

-- Clone with time travel (by version)
CREATE TABLE my_catalog.audit.orders_snapshot
DEEP CLONE my_catalog.prod.orders VERSION AS OF 5;

-- Clone with time travel (by timestamp)
CREATE TABLE my_catalog.audit.orders_snapshot_ts
DEEP CLONE my_catalog.prod.orders TIMESTAMP AS OF '2025-01-01';
```

---

## Volumes

### Create Volumes

**SQL (AWS):**
```sql
-- Managed volume (UC manages storage)
CREATE VOLUME my_catalog.bronze.raw_files
COMMENT 'Raw file uploads';

-- External volume (user manages storage) - S3
CREATE EXTERNAL VOLUME my_catalog.bronze.landing_zone
LOCATION 's3://my-bucket/landing/'
COMMENT 'External landing zone';
```

**SQL (Azure):**
```sql
-- External volume (user manages storage) - ADLS Gen2
CREATE EXTERNAL VOLUME my_catalog.bronze.landing_zone
LOCATION 'abfss://landing@storageaccount.dfs.core.windows.net/'
COMMENT 'External landing zone';
```

**SQL (GCP):**
```sql
-- External volume (user manages storage) - GCS
CREATE EXTERNAL VOLUME my_catalog.bronze.landing_zone
LOCATION 'gs://my-bucket/landing/'
COMMENT 'External landing zone';
```

**Python SDK:**
```python
from databricks.sdk.service.catalog import VolumeType

# Create managed volume
volume = w.volumes.create(
    catalog_name="my_catalog",
    schema_name="bronze",
    name="raw_files",
    volume_type=VolumeType.MANAGED,
    comment="Raw file uploads"
)

# Create external volume (AWS)
volume = w.volumes.create(
    catalog_name="my_catalog",
    schema_name="bronze",
    name="landing_zone",
    volume_type=VolumeType.EXTERNAL,
    storage_location="s3://my-bucket/landing/",
    comment="External landing zone"
)

# Create external volume (Azure)
volume = w.volumes.create(
    catalog_name="my_catalog",
    schema_name="bronze",
    name="landing_zone",
    volume_type=VolumeType.EXTERNAL,
    storage_location="abfss://landing@storageaccount.dfs.core.windows.net/",
    comment="External landing zone"
)

# Create external volume (GCP)
volume = w.volumes.create(
    catalog_name="my_catalog",
    schema_name="bronze",
    name="landing_zone",
    volume_type=VolumeType.EXTERNAL,
    storage_location="gs://my-bucket/landing/",
    comment="External landing zone"
)

# List volumes
for vol in w.volumes.list(catalog_name="my_catalog", schema_name="bronze"):
    print(f"{vol.full_name}: {vol.volume_type}")

# Get volume
volume = w.volumes.read("my_catalog.bronze.raw_files")

# Delete volume
w.volumes.delete("my_catalog.bronze.old_volume")
```

**CLI:**
```bash
# Create managed volume
databricks volumes create my_catalog bronze raw_files MANAGED \
    --comment "Raw file uploads"

# Create external volume (AWS)
databricks volumes create my_catalog bronze landing_zone EXTERNAL \
    --storage-location "s3://my-bucket/landing/" \
    --comment "External landing zone"

# Create external volume (Azure)
databricks volumes create my_catalog bronze landing_zone EXTERNAL \
    --storage-location "abfss://landing@storageaccount.dfs.core.windows.net/" \
    --comment "External landing zone"

# Create external volume (GCP)
databricks volumes create my_catalog bronze landing_zone EXTERNAL \
    --storage-location "gs://my-bucket/landing/" \
    --comment "External landing zone"

# List volumes
databricks volumes list my_catalog bronze

# Delete volume
databricks volumes delete my_catalog.bronze.old_volume
```

### Accessing Volume Files

```python
# Volume path format
# /Volumes/<catalog>/<schema>/<volume>/<path>

# Read file from volume
df = spark.read.csv("/Volumes/my_catalog/bronze/raw_files/data.csv")

# Write to volume
df.write.parquet("/Volumes/my_catalog/bronze/raw_files/output/")

# List files (use dbutils or Python)
files = dbutils.fs.ls("/Volumes/my_catalog/bronze/raw_files/")
```

---

## Functions

### Create Functions

**SQL:**
```sql
-- SQL scalar function
CREATE FUNCTION my_catalog.utils.mask_email(email STRING)
RETURNS STRING
COMMENT 'Mask email address for privacy'
RETURN CONCAT(
    LEFT(email, 2),
    '***@',
    SPLIT(email, '@')[1]
);

-- SQL table function
CREATE FUNCTION my_catalog.utils.date_range(start_date DATE, end_date DATE)
RETURNS TABLE (dt DATE)
COMMENT 'Generate date range'
RETURN SELECT explode(sequence(start_date, end_date)) AS dt;

-- Python UDF (requires cluster with UC enabled)
CREATE FUNCTION my_catalog.utils.sentiment(text STRING)
RETURNS STRING
LANGUAGE PYTHON
COMMENT 'Simple sentiment analysis'
AS $$
    if not text:
        return 'neutral'
    positive_words = ['good', 'great', 'excellent', 'love']
    negative_words = ['bad', 'terrible', 'hate', 'awful']
    text_lower = text.lower()
    if any(w in text_lower for w in positive_words):
        return 'positive'
    elif any(w in text_lower for w in negative_words):
        return 'negative'
    return 'neutral'
$$;
```

**Python SDK:**
```python
# List functions
for func in w.functions.list(catalog_name="my_catalog", schema_name="utils"):
    print(f"{func.full_name}: {func.data_type}")

# Get function
func = w.functions.get("my_catalog.utils.mask_email")

# Delete function
w.functions.delete("my_catalog.utils.old_function")
```

**CLI:**
```bash
# List functions
databricks functions list my_catalog utils

# Get function
databricks functions get my_catalog.utils.mask_email

# Delete function
databricks functions delete my_catalog.utils.old_function
```

### Using Functions

```sql
-- Use scalar function
SELECT
    customer_id,
    my_catalog.utils.mask_email(email) AS masked_email
FROM my_catalog.gold.customers;

-- Use table function
SELECT * FROM my_catalog.utils.date_range('2024-01-01', '2024-01-31');
```

---

## Describe and Inspect

**SQL:**
```sql
-- Describe catalog
DESCRIBE CATALOG my_catalog;
DESCRIBE CATALOG EXTENDED my_catalog;

-- Describe schema
DESCRIBE SCHEMA my_catalog.bronze;
DESCRIBE SCHEMA EXTENDED my_catalog.bronze;

-- Describe table
DESCRIBE TABLE my_catalog.bronze.raw_orders;
DESCRIBE TABLE EXTENDED my_catalog.bronze.raw_orders;
DESCRIBE DETAIL my_catalog.bronze.raw_orders;

-- Show table history
DESCRIBE HISTORY my_catalog.bronze.raw_orders;

-- Show table properties
SHOW TBLPROPERTIES my_catalog.bronze.raw_orders;

-- Describe volume
DESCRIBE VOLUME my_catalog.bronze.raw_files;
```

---

## Alter and Update

**SQL:**
```sql
-- Rename table
ALTER TABLE my_catalog.bronze.old_name RENAME TO new_name;

-- Add column
ALTER TABLE my_catalog.bronze.raw_orders
ADD COLUMN (
    source_system STRING COMMENT 'Origin system',
    processed BOOLEAN DEFAULT false
);

-- Change column comment
ALTER TABLE my_catalog.bronze.raw_orders
ALTER COLUMN order_id COMMENT 'Primary key from source';

-- Set table properties
ALTER TABLE my_catalog.bronze.raw_orders
SET TBLPROPERTIES ('delta.logRetentionDuration' = '30 days');

-- Drop column (Delta Lake)
ALTER TABLE my_catalog.bronze.raw_orders
DROP COLUMN source_system;

-- Enable Liquid Clustering (migrate from partitioned)
ALTER TABLE my_catalog.gold.daily_sales
CLUSTER BY (sale_date, region);

-- Enable UniForm Iceberg format
ALTER TABLE my_catalog.silver.orders
SET TBLPROPERTIES ('delta.universalFormat.enabledFormats' = 'iceberg');

-- Change owner
ALTER CATALOG my_catalog SET OWNER TO `admin_group`;
ALTER SCHEMA my_catalog.bronze SET OWNER TO `data_team`;
ALTER TABLE my_catalog.bronze.raw_orders SET OWNER TO `etl_user`;
```
