# Storage Credentials, External Locations & Connections

Configure external storage access and connect to foreign data sources.

## Storage Credentials

Storage credentials authenticate Unity Catalog to cloud storage (S3, ADLS, GCS).

### AWS IAM Role

> Storage credentials are created via SDK, CLI, or UI (not SQL).

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import AwsIamRoleRequest

w = WorkspaceClient()

# Create AWS storage credential
credential = w.storage_credentials.create(
    name="aws_s3_credential",
    aws_iam_role=AwsIamRoleRequest(
        role_arn="arn:aws:iam::123456789012:role/unity-catalog-role"
    ),
    comment="S3 access for Unity Catalog"
)

# Validate credential
validation = w.storage_credentials.validate(
    storage_credential_name="aws_s3_credential",
    url="s3://my-bucket/test/"
)
print(f"Valid: {validation.is_valid}")
```

**CLI:**
```bash
# Create storage credential
databricks storage-credentials create aws_s3_credential --json '{
    "aws_iam_role": {
        "role_arn": "arn:aws:iam::123456789012:role/unity-catalog-role"
    },
    "comment": "S3 access for Unity Catalog"
}'

# List credentials
databricks storage-credentials list

# Validate credential
databricks storage-credentials validate aws_s3_credential \
    --url "s3://my-bucket/test/"
```

### Azure Managed Identity

**Python SDK:**
```python
from databricks.sdk.service.catalog import AzureManagedIdentityRequest

credential = w.storage_credentials.create(
    name="azure_adls_credential",
    azure_managed_identity=AzureManagedIdentityRequest(
        access_connector_id="/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.Databricks/accessConnectors/unity-catalog-connector"
    ),
    comment="ADLS Gen2 access"
)

# Validate credential
validation = w.storage_credentials.validate(
    storage_credential_name="azure_adls_credential",
    url="abfss://container@storageaccount.dfs.core.windows.net/test/"
)
print(f"Valid: {validation.is_valid}")
```

**CLI:**
```bash
# Create Azure storage credential
databricks storage-credentials create azure_adls_credential --json '{
    "azure_managed_identity": {
        "access_connector_id": "/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.Databricks/accessConnectors/unity-catalog-connector"
    },
    "comment": "ADLS Gen2 access for Unity Catalog"
}'

# Validate credential
databricks storage-credentials validate azure_adls_credential \
    --url "abfss://container@storageaccount.dfs.core.windows.net/test/"
```

### GCP Service Account

**CLI:**
```bash
# Create GCS storage credential
databricks storage-credentials create gcs_credential --json '{
    "databricks_gcp_service_account": {},
    "comment": "GCS access for Unity Catalog"
}'
```

### Manage Storage Credentials

**SQL:**
```sql
-- List storage credentials
SHOW STORAGE CREDENTIALS;

-- Describe credential
DESCRIBE STORAGE CREDENTIAL aws_s3_credential;

-- Update credential owner
ALTER STORAGE CREDENTIAL aws_s3_credential
OWNER TO `admin_group`;

-- Rename credential
ALTER STORAGE CREDENTIAL aws_s3_credential
RENAME TO aws_s3_credential_v2;

-- Grant usage
GRANT CREATE EXTERNAL LOCATION ON STORAGE CREDENTIAL aws_s3_credential TO `data_engineers`;

-- Delete credential
DROP STORAGE CREDENTIAL aws_s3_credential;
```

**Python SDK:**
```python
# List all credentials
for cred in w.storage_credentials.list():
    print(f"{cred.name}: {cred.comment}")

# Get credential details
cred = w.storage_credentials.get("aws_s3_credential")

# Update credential
w.storage_credentials.update(
    name="aws_s3_credential",
    comment="Updated comment"
)

# Delete credential
w.storage_credentials.delete("aws_s3_credential")
```

---

## External Locations

External locations map cloud storage paths to Unity Catalog with governance.

### Create External Location

**SQL (AWS):**
```sql
-- Create external location (S3)
CREATE EXTERNAL LOCATION landing_zone
URL 's3://my-bucket/landing/'
WITH (STORAGE CREDENTIAL aws_s3_credential)
COMMENT 'Landing zone for raw data ingestion';

-- With read-only access
CREATE EXTERNAL LOCATION archive_data
URL 's3://archive-bucket/data/'
WITH (STORAGE CREDENTIAL aws_s3_credential)
READ_ONLY
COMMENT 'Read-only archive data';
```

**SQL (Azure):**
```sql
-- Create external location (ADLS Gen2)
CREATE EXTERNAL LOCATION landing_zone
URL 'abfss://landing@storageaccount.dfs.core.windows.net/'
WITH (STORAGE CREDENTIAL azure_adls_credential)
COMMENT 'Landing zone for raw data ingestion';

-- With read-only access
CREATE EXTERNAL LOCATION archive_data
URL 'abfss://archive@storageaccount.dfs.core.windows.net/data/'
WITH (STORAGE CREDENTIAL azure_adls_credential)
READ_ONLY
COMMENT 'Read-only archive data';
```

**Python SDK:**
```python
# Create external location (AWS)
location = w.external_locations.create(
    name="landing_zone",
    url="s3://my-bucket/landing/",
    credential_name="aws_s3_credential",
    comment="Landing zone for raw data ingestion"
)

# Create external location (Azure)
location = w.external_locations.create(
    name="landing_zone",
    url="abfss://landing@storageaccount.dfs.core.windows.net/",
    credential_name="azure_adls_credential",
    comment="Landing zone for raw data ingestion"
)

# Create read-only location
location = w.external_locations.create(
    name="archive_data",
    url="abfss://archive@storageaccount.dfs.core.windows.net/data/",
    credential_name="azure_adls_credential",
    read_only=True,
    comment="Read-only archive data"
)

# Validate location (use storage_credentials.validate with the location URL)
validation = w.storage_credentials.validate(
    storage_credential_name="azure_adls_credential",
    url="abfss://landing@storageaccount.dfs.core.windows.net/"
)
print(f"Valid: {validation.is_valid}")
```

**CLI (AWS):**
```bash
# Create external location (S3)
databricks external-locations create landing_zone \
    --url "s3://my-bucket/landing/" \
    --credential-name aws_s3_credential \
    --comment "Landing zone for raw data"
```

**CLI (Azure):**
```bash
# Create external location (ADLS Gen2)
databricks external-locations create landing_zone \
    --url "abfss://landing@storageaccount.dfs.core.windows.net/" \
    --credential-name azure_adls_credential \
    --comment "Landing zone for raw data"

# List locations
databricks external-locations list

# Validate location
databricks external-locations validate landing_zone
```

### Manage External Locations

**SQL:**
```sql
-- List locations
SHOW EXTERNAL LOCATIONS;

-- Describe location
DESCRIBE EXTERNAL LOCATION landing_zone;

-- Grant permissions
GRANT CREATE EXTERNAL TABLE ON EXTERNAL LOCATION landing_zone TO `data_engineers`;
GRANT CREATE EXTERNAL VOLUME ON EXTERNAL LOCATION landing_zone TO `data_engineers`;
GRANT READ FILES ON EXTERNAL LOCATION landing_zone TO `analysts`;
GRANT WRITE FILES ON EXTERNAL LOCATION landing_zone TO `etl_team`;

-- Update location
ALTER EXTERNAL LOCATION landing_zone
SET COMMENT 'Updated landing zone';

-- Delete location
DROP EXTERNAL LOCATION landing_zone;
```

### Use External Locations

**SQL (AWS):**
```sql
-- Create external table using S3 location
CREATE TABLE analytics.bronze.external_events
USING DELTA
LOCATION 's3://my-bucket/landing/events/'
COMMENT 'External events table';

-- Create external volume using S3 location
CREATE EXTERNAL VOLUME analytics.bronze.raw_uploads
LOCATION 's3://my-bucket/landing/uploads/'
COMMENT 'External file uploads';
```

**SQL (Azure):**
```sql
-- Create external table using ADLS Gen2 location
CREATE TABLE analytics.bronze.external_events
USING DELTA
LOCATION 'abfss://landing@storageaccount.dfs.core.windows.net/events/'
COMMENT 'External events table';

-- Create external volume using ADLS Gen2 location
CREATE EXTERNAL VOLUME analytics.bronze.raw_uploads
LOCATION 'abfss://landing@storageaccount.dfs.core.windows.net/uploads/'
COMMENT 'External file uploads';
```

---

## Foreign Connections (Lakehouse Federation)

Connect to external databases and query them through Unity Catalog.

### Create Connections

**SQL - Snowflake:**
```sql
CREATE CONNECTION snowflake_conn
TYPE SNOWFLAKE
OPTIONS (
    host 'account.snowflakecomputing.com',
    port '443',
    user secret('my_scope', 'snowflake_user'),
    password secret('my_scope', 'snowflake_password'),
    sfWarehouse 'COMPUTE_WH'
)
COMMENT 'Snowflake production connection';
```

**SQL - PostgreSQL:**
```sql
CREATE CONNECTION postgres_conn
TYPE POSTGRESQL
OPTIONS (
    host 'postgres.example.com',
    port '5432',
    user secret('my_scope', 'postgres_user'),
    password secret('my_scope', 'postgres_password')
)
COMMENT 'PostgreSQL analytics database';
```

**SQL - MySQL:**
```sql
CREATE CONNECTION mysql_conn
TYPE MYSQL
OPTIONS (
    host 'mysql.example.com',
    port '3306',
    user secret('my_scope', 'mysql_user'),
    password secret('my_scope', 'mysql_password')
)
COMMENT 'MySQL production database';
```

**SQL - SQL Server:**
```sql
CREATE CONNECTION sqlserver_conn
TYPE SQLSERVER
OPTIONS (
    host 'sqlserver.example.com',
    port '1433',
    user secret('my_scope', 'sqlserver_user'),
    password secret('my_scope', 'sqlserver_password')
)
COMMENT 'SQL Server data warehouse';
```

**SQL - BigQuery:**
```sql
CREATE CONNECTION bigquery_conn
TYPE BIGQUERY
OPTIONS (
    GoogleServiceAccountKeyJson secret('my_scope', 'bigquery_key')
)
COMMENT 'BigQuery analytics project';
```

**Python SDK:**
```python
from databricks.sdk.service.catalog import ConnectionType

# Create PostgreSQL connection
conn = w.connections.create(
    name="postgres_conn",
    connection_type=ConnectionType.POSTGRESQL,
    options={
        "host": "postgres.example.com",
        "port": "5432",
        "user": "databricks_user",
        "password": "my_password"  # use Databricks secrets in production
    },
    comment="PostgreSQL analytics database"
)

# List connections
for conn in w.connections.list():
    print(f"{conn.name}: {conn.connection_type}")

# Test connection
# Run a simple query against the foreign catalog
```

**CLI:**
```bash
# Create connection
databricks connections create postgres_conn --json '{
    "connection_type": "POSTGRESQL",
    "options": {
        "host": "postgres.example.com",
        "port": "5432",
        "user": "databricks_user",
        "password": "my_password"
    },
    "comment": "PostgreSQL analytics database"
}'

# List connections
databricks connections list

# Delete connection
databricks connections delete postgres_conn
```

### Create Foreign Catalog

**SQL:**
```sql
-- Create foreign catalog from Snowflake
CREATE FOREIGN CATALOG snowflake_analytics
USING CONNECTION snowflake_conn
OPTIONS (database 'ANALYTICS_DB')
COMMENT 'Snowflake analytics database';

-- Create foreign catalog from PostgreSQL
CREATE FOREIGN CATALOG postgres_analytics
USING CONNECTION postgres_conn
OPTIONS (database 'analytics')
COMMENT 'PostgreSQL analytics';
```

### Query Foreign Data

```sql
-- Query Snowflake table through Unity Catalog
SELECT * FROM snowflake_analytics.public.customers LIMIT 10;

-- Join local and foreign data
SELECT
    l.order_id,
    l.customer_id,
    f.customer_name
FROM analytics.gold.orders l
JOIN snowflake_analytics.public.customers f
    ON l.customer_id = f.customer_id;
```

### Grant Access to Connections

**SQL:**
```sql
-- Grant connection usage
GRANT USE CONNECTION ON CONNECTION postgres_conn TO `data_engineers`;
GRANT CREATE FOREIGN CATALOG ON CONNECTION postgres_conn TO `data_engineers`;

-- Grant foreign catalog access
GRANT USE CATALOG ON CATALOG postgres_analytics TO `analysts`;
GRANT USE SCHEMA, SELECT ON CATALOG postgres_analytics TO `analysts`;
```

---

## Workspace Bindings

Control which workspaces can access a catalog.

### Binding Types

- **OPEN** (default): Catalog is available to all workspaces
- **ISOLATED**: Catalog is only available to explicitly bound workspaces

Workspace bindings are managed via Python SDK or CLI (not SQL).

To set isolation mode on a catalog:

**Python SDK:**
```python
from databricks.sdk.service.catalog import (
    WorkspaceBinding,
    WorkspaceBindingBindingType
)

# Set isolation mode
w.catalogs.update(name="analytics", isolation_mode="ISOLATED")

# Check isolation mode
catalog = w.catalogs.get("analytics")
print(f"Isolation mode: {catalog.isolation_mode}")

# Get current bindings
for b in w.workspace_bindings.get_bindings(
    securable_type="catalog",
    securable_name="analytics"
):
    print(f"Workspace {b.workspace_id}: {b.binding_type}")

# Add workspace binding
w.workspace_bindings.update_bindings(
    securable_type="catalog",
    securable_name="analytics",
    add=[
        WorkspaceBinding(
            workspace_id=1234567890,
            binding_type=WorkspaceBindingBindingType.BINDING_TYPE_READ_WRITE
        )
    ]
)

# Remove workspace binding
w.workspace_bindings.update_bindings(
    securable_type="catalog",
    securable_name="analytics",
    remove=[
        WorkspaceBinding(workspace_id=1234567890)
    ]
)

# Make catalog open again
w.catalogs.update(name="analytics", isolation_mode="OPEN")
```

**CLI:**
```bash
# Get bindings
databricks workspace-bindings get-bindings CATALOG analytics

# Add workspace binding
databricks workspace-bindings update-bindings CATALOG analytics --json '{
    "add": [
        {"workspace_id": 1234567890, "binding_type": "BINDING_TYPE_READ_WRITE"}
    ]
}'

# Remove workspace binding
databricks workspace-bindings update-bindings CATALOG analytics --json '{
    "remove": [
        {"workspace_id": 1234567890}
    ]
}'
```

---

## Best Practices

### Storage Credentials
1. **Use IAM roles/managed identities** over access keys
2. **One credential per use case** (landing, archive, etc.)
3. **Validate after creation** to catch misconfigurations
4. **Restrict CREATE EXTERNAL LOCATION** privilege

### External Locations
1. **Non-overlapping paths**: Each location should cover unique paths
2. **Meaningful names**: `landing_zone`, `archive_data`, not `location1`
3. **Document purpose** in comments
4. **Use READ_ONLY** for archive/reference data

### Foreign Connections
1. **Use secrets** for passwords: `secret('scope', 'key')` in SQL
2. **Minimal privileges** on source database user
3. **Network connectivity**: Ensure firewall rules allow access
4. **Test regularly**: Foreign systems can change

### Workspace Bindings
1. **Start with OPEN** unless compliance requires isolation
2. **Document isolation requirements** for auditors
3. **Use ISOLATED for PII catalogs** that should be restricted
