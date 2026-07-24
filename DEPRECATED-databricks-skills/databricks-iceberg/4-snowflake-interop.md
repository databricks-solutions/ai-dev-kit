# Snowflake Interoperability

Databricks and Snowflake can share Iceberg data bidirectionally. This file covers both directions: Snowflake reading Databricks-managed tables, and Databricks reading Snowflake-managed Iceberg tables.

**Cloud scope**: AWS-primary examples. Azure/GCS differences noted where relevant.

---

## Direction 1: Snowflake Reading Databricks

Snowflake can read Databricks-managed Iceberg tables (managed Iceberg + UniForm + Compatibility Mode) through a **Catalog Integration** that connects to the Databricks Iceberg REST Catalog (IRC).

### Step 1: Create a Catalog Integration in Snowflake

`ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` is required on AWS for Snowflake to receive temporary STS credentials from the Databricks IRC. Without it, Snowflake cannot access the underlying Parquet files.

**PAT / Bearer token**:

```sql
-- In Snowflake
CREATE OR REPLACE CATALOG INTEGRATION databricks_catalog_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'my_schema'        -- UC schema (default namespace)
  REST_CONFIG = (
    CATALOG_URI = 'https://<databricks-workspace-url>/api/2.1/unity-catalog/iceberg-rest'
    WAREHOUSE = '<catalog-name>'          -- UC catalog name
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<databricks-pat-token>'
  )
  REFRESH_INTERVAL_SECONDS = 300
  ENABLED = TRUE;
```

**OAuth (recommended for production)**:

```sql
CREATE OR REPLACE CATALOG INTEGRATION databricks_catalog_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'my_schema'
  REST_CONFIG = (
    CATALOG_URI = 'https://<databricks-workspace-url>/api/2.1/unity-catalog/iceberg-rest'
    WAREHOUSE = '<catalog-name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<service-principal-client-id>'
    OAUTH_CLIENT_SECRET = '<service-principal-secret>'
    OAUTH_TOKEN_URI = 'https://<databricks-workspace-url>/oidc/v1/token'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  REFRESH_INTERVAL_SECONDS = 300
  ENABLED = TRUE;
```

> **Grant on the Databricks side**: The principal used for authentication needs these privileges in Unity Catalog:
> - `USE CATALOG` on the catalog
> - `USE SCHEMA` on the schema
> - `EXTERNAL USE SCHEMA` on the schema — this is the key privilege that enables external engines to access tables via IRC
> - `SELECT` on the target tables (or schema/catalog for broader access)
>
> Missing `EXTERNAL USE SCHEMA` causes a `Failed to retrieve credentials` error in Snowflake.

### Step 2: External Volume (Azure/GCS Only)

On **AWS with vended credentials**, no external volume is needed — Databricks IRC vends temporary STS credentials automatically.

On **Azure** or **GCS**, you must create an external volume in Snowflake because vended credentials are not supported for those clouds:

```sql
-- Azure example (in Snowflake)
CREATE OR REPLACE EXTERNAL VOLUME databricks_ext_vol
  STORAGE_LOCATIONS = (
    (
      NAME = 'azure_location'
      STORAGE_BASE_URL = 'azure://myaccount.blob.core.windows.net/my-container/iceberg/'
      AZURE_TENANT_ID = '<tenant-id>'
    )
  );
```

### Step 3: Expose Tables in Snowflake

Two approaches available. **Linked catalog** is preferred — it exposes all tables in the namespace at once and updates automatically.

**Option A: Linked Catalog Database (preferred)**

```sql
-- Verify namespaces are visible (should return your UC schemas)
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('databricks_catalog_int', '', 0);

-- Create a linked catalog database exposing all tables in the namespace
CREATE DATABASE my_snowflake_db
  LINKED_CATALOG = (
    CATALOG = 'databricks_catalog_int',
    ALLOWED_NAMESPACES = ('my_schema')   -- UC schema
  );

-- Check link health (executionState should be "RUNNING" with empty failureDetails)
SELECT SYSTEM$CATALOG_LINK_STATUS('my_snowflake_db');

-- Query 
SELECT * FROM my_snowflake_db."my_schema"."my_table"
WHERE event_date >= '2025-01-01';
```

**Option B: Individual Table Reference (legacy)**

```sql
-- AWS (vended creds — no EXTERNAL_VOLUME needed)
CREATE ICEBERG TABLE my_snowflake_db.my_schema.events
  CATALOG = 'databricks_catalog_int'
  CATALOG_TABLE_NAME = 'events';

-- Azure/GCS (EXTERNAL_VOLUME required)
CREATE ICEBERG TABLE my_snowflake_db.my_schema.events
  CATALOG = 'databricks_catalog_int'
  CATALOG_TABLE_NAME = 'events'
  EXTERNAL_VOLUME = 'databricks_ext_vol';

-- Query
SELECT * FROM my_snowflake_db.my_schema.events
WHERE event_date >= '2025-01-01';
```

### Key Gotchas

#### Workspace IP Access Lists Must Allow Snowflake Egress IPs

If the Databricks workspace has **IP access lists** enabled, Snowflake's outbound NAT IPs must be added to the allowlist. Snowflake connects to the Databricks IRC endpoint (`/api/2.1/unity-catalog/iceberg-rest`) over HTTPS (port 443), and a blocked IP produces connection timeouts or `403` errors that can look like auth failures.


> **Diagnosis tip**: If the catalog integration shows `ENABLED = TRUE` but `SYSTEM$CATALOG_LINK_STATUS` returns a connection error (not a credentials error), IP access lists are the first thing to check.

#### REFRESH_INTERVAL_SECONDS Is Per-Integration, Not Per-Table

The `REFRESH_INTERVAL_SECONDS` setting on the catalog integration controls how often Snowflake polls the Databricks IRC for metadata changes. This applies to **all tables** using that integration — you cannot set different refresh intervals per table.

- Lower values = fresher data but more API calls
- Default: 300 seconds (5 minutes)
- Minimum: 60 seconds

#### 1000-Commit Limit

For Iceberg tables created from Delta files in object storage, Snowflake processes a maximum of 1000 Delta commit files each time you refresh a table using CREATE/ALTER ICEBERG TABLE … REFRESH or an automatic refresh; if the table has more than 1000 commit files since the last checkpoint, you can perform additional refreshes and each refresh continues from where the previous one stopped. The 1000‑commit limit applies only to Delta commit files after the latest Delta checkpoint file, and does not limit how many commits the catalog integration can ultimately synchronize over multiple refreshes

**Mitigations**:
- Enable Predictive Optimization (auto-compaction reduces commit frequency)
- Batch writes instead of high-frequency micro-batches
- Run `OPTIMIZE` and `VACUUM` to consolidate metadata manually if needed.

---

## Direction 2: Databricks Reading Snowflake

Databricks can read Snowflake-managed Iceberg tables through a **foreign catalog** that connects to Snowflake's Iceberg catalog. Snowflake Iceberg tables are stored in external volumes (cloud storage), so Databricks reads the Iceberg's Parquet files directly — no Snowflake compute required.

**Assumption**: A Snowflake-managed Iceberg table already exists, created with `CATALOG = 'SNOWFLAKE'` pointing to an external volume:

```sql
-- In Snowflake — prerequisite table
CREATE ICEBERG TABLE sensor_readings (
  device_id    INT,
  device_value STRING
)
  CATALOG         = 'SNOWFLAKE'
  EXTERNAL_VOLUME = 'ICEBERG_SHARED_VOL'
  BASE_LOCATION   = 'sensor_readings/';

INSERT INTO sensor_readings VALUES (1, 'value01'), (2, 'value02');

SELECT * FROM sensor_readings;
```

`CATALOG = 'SNOWFLAKE'` means Snowflake manages the Iceberg metadata. The data files land in the external volume at the `BASE_LOCATION` sub-path. The steps below set up Databricks to read this table.

### Step 1: Find Snowflake External Volume Path

Before setting up the Databricks side, run this in Snowflake to get the S3/ADLS/GCS path where Snowflake stores its Iceberg data. You'll need this path for Steps 2 and 4.

```sql
-- In Snowflake
DESCRIBE EXTERNAL VOLUME <your-external-volume-name>;
-- Note the STORAGE_BASE_URL value (e.g. s3://my-bucket/snowflake-iceberg/)
```

### Step 2: Create a Storage Credential

Create a storage credential for the cloud storage where Snowflake stores its Iceberg data. Assuming that the IAM role already exists. Follow the documentation for details (https://docs.databricks.com/aws/en/connect/unity-catalog/cloud-storage/s3/s3-external-location-manual)

```bash
# In Databricks CLI (AWS example)
databricks storage-credentials create snowflake_storage_cred \
  --aws-iam-role-arn "arn:aws:iam::123456789012:role/snowflake-data-access"
```

### Step 3: Create an External Location

The external location must point to the **root** of the bucket (not a sub-path), so that all Snowflake external volume paths fall under it.

> **Fallback mode**: You do not need this external-location fallback enabled to read Snowflake‑created Iceberg tables via catalog federation. It only affects how storage credentials are resolved for paths, not whether Snowflake Iceberg federation works.

```sql
-- In Databricks (URL should be the bucket root, not a sub-path)
CREATE EXTERNAL LOCATION snowflake_data
URL 's3://snowflake-iceberg-bucket/'
WITH (CREDENTIAL snowflake_storage_cred);
```

### Step 4: Create a Snowflake Connection

```sql
-- In Databricks
CREATE CONNECTION snowflake_conn
TYPE SNOWFLAKE
OPTIONS (
  'host' = '<account>.snowflakecomputing.com',
  'user' = '<username>',
  'password' = '<password>',
  'sfWarehouse' = '<warehouse-name>'
);
```

### Step 5: Create a Foreign Catalog

Two mandatory fields beyond `database`:

- **`authorized_paths`**: The path(s) where Snowflake stores Iceberg table files — from `STORAGE_BASE_URL` in `DESCRIBE EXTERNAL VOLUME`. Databricks can only read Iceberg tables whose data falls under these paths.
- **`storage_root`**: Where Databricks stores catalog metadata for Iceberg reads. Must point to an existing external location. This is required — the foreign catalog creation will fail without it.

```sql
-- In Databricks
CREATE FOREIGN CATALOG snowflake_iceberg
USING CONNECTION snowflake_conn
OPTIONS (
  'catalog' = '<snowflake-database>',
  'authorized_paths' = 's3://snowflake-iceberg-bucket/snowflake-iceberg/',
  'storage_root' = 's3://snowflake-iceberg-bucket/uc-metadata/'
);
```

> **UI workflow note**: The Databricks connection wizard (Catalog Explorer → Add connection → Snowflake) will prompt for authorized paths and storage location in the form and create the foreign catalog automatically. The SQL above is the equivalent DDL.

### Step 6: Refresh, Verify, and Query

```sql
-- Refresh to discover tables
REFRESH FOREIGN CATALOG snowflake_iceberg;

-- Verify provider type before querying at scale:
--   Provider = Iceberg → Databricks reads directly from cloud storage (cheap)
--   Provider = Snowflake → double compute via JDBC (Snowflake + Databricks)
DESCRIBE EXTENDED snowflake_iceberg.my_schema.my_table;

-- Query
SELECT * FROM snowflake_iceberg.my_schema.my_table
WHERE created_at >= '2025-01-01';
```

### Compute Cost Matrix

| Snowflake Table Type | Databricks Read | Compute Cost |
|---------------------|:-:|---|
| **Snowflake Iceberg table** | Yes | Databricks compute only (reads data files directly from cloud storage) |
| **Snowflake native table** | Yes (via federation) | Double compute — Snowflake runs the query, Databricks processes the result |

> **Key insight**: Snowflake Iceberg tables are more cost-efficient to read from Databricks because Databricks reads the Parquet files directly. Native Snowflake tables require Snowflake to run the scan.


---

## Full AWS Example: Snowflake Reading Databricks

```sql
-- ========================================
-- DATABRICKS SIDE (run in Databricks)
-- ========================================

-- 1. Create a managed Iceberg table (v2 — disable DVs and row tracking for CLUSTER BY)
CREATE TABLE main.sales.orders (
  order_id BIGINT,
  customer_id BIGINT,
  amount DECIMAL(10,2),
  order_date DATE
)
USING ICEBERG
TBLPROPERTIES (
  'delta.enableDeletionVectors' = false,
  'delta.enableRowTracking' = false
)
CLUSTER BY (order_date);

-- 2. Grant external access to the service principal used in Snowflake catalog integration
GRANT EXTERNAL USE SCHEMA ON SCHEMA main.sales TO `snowflake-service-principal`;

-- ========================================
-- SNOWFLAKE SIDE (run in Snowflake)
-- ========================================

-- 3. Create catalog integration (ACCESS_DELEGATION_MODE required for vended creds on AWS)
CREATE OR REPLACE CATALOG INTEGRATION databricks_int
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = 'sales'
  REST_CONFIG = (
    CATALOG_URI = 'https://my-workspace.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest'
    WAREHOUSE = 'main'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<service-principal-client-id>'
    OAUTH_CLIENT_SECRET = '<service-principal-secret>'
    OAUTH_TOKEN_URI = 'https://my-workspace.cloud.databricks.com/oidc/v1/token'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  REFRESH_INTERVAL_SECONDS = 300
  ENABLED = TRUE;

-- 4. Verify schemas are visible
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('databricks_int', '', 0);

-- 5. Create linked catalog database (exposes all tables in the namespace)
CREATE DATABASE analytics
  LINKED_CATALOG = (
    CATALOG = 'databricks_int',
    ALLOWED_NAMESPACES = ('sales')
  );

-- 6. Check link health
SELECT SYSTEM$CATALOG_LINK_STATUS('analytics');

-- 7. Query (schema and table names are case-sensitive)
SELECT order_date, SUM(amount) AS daily_revenue
FROM analytics."sales"."orders"
GROUP BY order_date
ORDER BY order_date DESC;
```

---

## Related

- [3-iceberg-rest-catalog.md](3-iceberg-rest-catalog.md) — IRC endpoint details and authentication
