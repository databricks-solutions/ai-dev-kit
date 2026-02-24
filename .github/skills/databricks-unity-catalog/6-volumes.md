# Unity Catalog Volumes

Comprehensive reference for working with Unity Catalog Volumes: file operations, permissions, and best practices.

## Overview

Volumes are a Unity Catalog capability for accessing, storing, and governing files. Unlike tables (structured data), volumes store unstructured or semi-structured files.

| Volume Type | Description | Storage |
|-------------|-------------|---------|
| **Managed** | Databricks manages the storage location | Default metastore location |
| **External** | You manage the storage location | Your cloud storage (S3, ADLS, GCS) |

**Common Use Cases:**
- ML training data (images, audio, video, PDFs)
- Data exploration and staging
- Library files (.whl, .jar)
- Config files and scripts
- ETL landing zones

---

## Volume Path Format

All volume operations use the path format:

```
/Volumes/<catalog>/<schema>/<volume>/<path_to_file>
```

**Examples:**
```
/Volumes/main/default/my_volume/data.csv
/Volumes/analytics/raw/landing_zone/2024/01/orders.parquet
/Volumes/ml/training/images/cats/cat_001.jpg
```

---

## MCP Tools

### List Files in Volume

```python
# List files and directories
list_volume_files(
    volume_path="/Volumes/main/default/my_volume/data/"
)
# Returns: [{"name": "file.csv", "path": "...", "is_directory": false, "file_size": 1024, "last_modified": "..."}]
```

### Upload File to Volume

```python
# Upload a local file
upload_to_volume(
    local_path="/tmp/data.csv",
    volume_path="/Volumes/main/default/my_volume/data.csv",
    overwrite=True
)
# Returns: {"local_path": "...", "volume_path": "...", "success": true}
```

### Download File from Volume

```python
# Download to local path
download_from_volume(
    volume_path="/Volumes/main/default/my_volume/data.csv",
    local_path="/tmp/downloaded.csv",
    overwrite=True
)
# Returns: {"volume_path": "...", "local_path": "...", "success": true}
```

### Create Directory

```python
# Create directory (creates parents like mkdir -p)
create_volume_directory(
    volume_path="/Volumes/main/default/my_volume/data/2024/01"
)
# Returns: {"volume_path": "...", "success": true}
```

### Delete File

```python
# Delete a file
delete_volume_file(
    volume_path="/Volumes/main/default/my_volume/old_data.csv"
)
# Returns: {"volume_path": "...", "success": true}
```

### Get File Info

```python
# Get file metadata
get_volume_file_info(
    volume_path="/Volumes/main/default/my_volume/data.csv"
)
# Returns: {"name": "data.csv", "file_size": 1024, "last_modified": "...", "success": true}
```

---

## Python SDK Examples

### Volume CRUD Operations

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import VolumeType

w = WorkspaceClient()

# List volumes in a schema
for volume in w.volumes.list(catalog_name="main", schema_name="default"):
    print(f"{volume.full_name}: {volume.volume_type}")

# Get volume details
volume = w.volumes.read(name="main.default.my_volume")
print(f"Storage: {volume.storage_location}")

# Create managed volume
managed = w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_managed_volume",
    volume_type=VolumeType.MANAGED,
    comment="Managed volume for ML data"
)

# Create external volume
external = w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_external_volume",
    volume_type=VolumeType.EXTERNAL,
    storage_location="s3://my-bucket/volumes/data",
    comment="External volume on S3"
)

# Update volume
w.volumes.update(
    name="main.default.my_volume",
    comment="Updated description"
)

# Delete volume
w.volumes.delete(name="main.default.my_volume")
```

### File Operations

```python
from databricks.sdk import WorkspaceClient
import io

w = WorkspaceClient()

# Upload file from memory
data = b"col1,col2\n1,2\n3,4"
w.files.upload(
    file_path="/Volumes/main/default/my_volume/data.csv",
    contents=io.BytesIO(data),
    overwrite=True
)

# Upload file from disk (recommended for large files)
w.files.upload_from(
    file_path="/Volumes/main/default/my_volume/large_file.parquet",
    source_path="/local/path/large_file.parquet",
    overwrite=True,
    use_parallel=True  # Parallel upload for large files
)

# List directory contents
for entry in w.files.list_directory_contents("/Volumes/main/default/my_volume/"):
    file_type = "dir" if entry.is_directory else "file"
    print(f"{entry.name}: {file_type} ({entry.file_size} bytes)")

# Download file to memory
response = w.files.download("/Volumes/main/default/my_volume/data.csv")
content = response.contents.read()

# Download file to disk (recommended for large files)
w.files.download_to(
    file_path="/Volumes/main/default/my_volume/large_file.parquet",
    destination="/local/path/downloaded.parquet",
    use_parallel=True  # Parallel download for large files
)

# Create directory
w.files.create_directory("/Volumes/main/default/my_volume/new_folder/")

# Delete file
w.files.delete("/Volumes/main/default/my_volume/old_data.csv")

# Delete empty directory
w.files.delete_directory("/Volumes/main/default/my_volume/empty_folder/")

# Get file metadata
metadata = w.files.get_metadata("/Volumes/main/default/my_volume/data.csv")
print(f"Size: {metadata.content_length}, Modified: {metadata.last_modified}")
```

---

## SQL Operations

### Query Volume Metadata

```sql
-- List all volumes in a catalog
SELECT
    volume_catalog,
    volume_schema,
    volume_name,
    volume_type,
    storage_location,
    comment,
    created,
    created_by
FROM system.information_schema.volumes
WHERE volume_catalog = 'analytics'
ORDER BY volume_schema, volume_name;

-- Find volumes by type
SELECT volume_name, storage_location
FROM system.information_schema.volumes
WHERE volume_type = 'EXTERNAL';
```

### Read Files from Volumes

```sql
-- Read CSV file
SELECT * FROM read_files('/Volumes/main/default/my_volume/data.csv');

-- Read with options
SELECT * FROM read_files(
    '/Volumes/main/default/my_volume/data/',
    format => 'csv',
    header => true,
    inferSchema => true
);

-- Read Parquet files
SELECT * FROM read_files(
    '/Volumes/main/default/my_volume/parquet_data/',
    format => 'parquet'
);

-- Read JSON files
SELECT * FROM read_files(
    '/Volumes/main/default/my_volume/events/*.json',
    format => 'json'
);

-- Create table from volume files
CREATE TABLE analytics.bronze.raw_orders AS
SELECT * FROM read_files('/Volumes/analytics/raw/landing/orders/');
```

### Write Files to Volumes

```sql
-- Copy data to volume as Parquet
COPY INTO '/Volumes/main/default/my_volume/export/'
FROM (SELECT * FROM analytics.gold.customers)
FILEFORMAT = PARQUET;

-- Export as CSV
COPY INTO '/Volumes/main/default/my_volume/export/'
FROM (SELECT * FROM analytics.gold.report)
FILEFORMAT = CSV
HEADER = true;
```

---

## Permissions

### Required Permissions

| Operation | Required Privilege |
|-----------|-------------------|
| List files | `READ VOLUME` |
| Read files | `READ VOLUME` |
| Write files | `WRITE VOLUME` |
| Create volume | `CREATE VOLUME` on schema |
| Delete volume | Owner or `MANAGE` |

**Note:** Also requires `USE CATALOG` on parent catalog and `USE SCHEMA` on parent schema.

### Grant Permissions

```sql
-- Grant read access to a volume
GRANT READ VOLUME ON VOLUME main.default.my_volume TO `data_readers`;

-- Grant write access
GRANT WRITE VOLUME ON VOLUME main.default.my_volume TO `data_writers`;

-- Grant ability to create volumes in a schema
GRANT CREATE VOLUME ON SCHEMA main.default TO `data_engineers`;

-- Revoke access
REVOKE WRITE VOLUME ON VOLUME main.default.my_volume FROM `data_writers`;
```

### Python SDK Permissions

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import SecurableType, PermissionsChange, Privilege

w = WorkspaceClient()

# Grant permissions
w.grants.update(
    securable_type=SecurableType.VOLUME,
    full_name="main.default.my_volume",
    changes=[
        PermissionsChange(
            add=[Privilege.READ_VOLUME],
            principal="data_readers"
        )
    ]
)

# Get current permissions
grants = w.grants.get(
    securable_type=SecurableType.VOLUME,
    full_name="main.default.my_volume"
)
for grant in grants.privilege_assignments:
    print(f"{grant.principal}: {grant.privileges}")
```

---

## Best Practices

### Organization

1. **Use meaningful paths** - Organize by date, source, or type
   ```
   /Volumes/catalog/schema/volume/year=2024/month=01/file.parquet
   /Volumes/catalog/schema/volume/source=salesforce/accounts.csv
   ```

2. **Separate raw and processed** - Use different volumes for landing vs. curated
   ```
   /Volumes/analytics/raw/landing_zone/    # Raw uploads
   /Volumes/analytics/curated/processed/   # Cleaned data
   ```

3. **Archive old data** - Move infrequently accessed files to archive volumes

### Performance

1. **Use parallel uploads** for large files (SDK v0.72.0+)
   ```python
   w.files.upload_from(..., use_parallel=True)
   ```

2. **Batch small files** - Combine many small files into larger archives

3. **Use Parquet** for analytics - Columnar format is more efficient

4. **Partition by date** - Enables efficient pruning in queries

### Security

1. **Use managed volumes** when Databricks should control storage

2. **Use external volumes** when you need:
   - Existing data in cloud storage
   - Cross-workspace access
   - Custom retention policies

3. **Apply least privilege** - Grant only required permissions

4. **Audit access** - Monitor volume access in audit logs
   ```sql
   SELECT *
   FROM system.access.audit
   WHERE action_name LIKE '%Volume%'
     AND event_date >= current_date() - 7;
   ```

---

## Troubleshooting

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `PERMISSION_DENIED` | Missing volume permissions | Grant `READ VOLUME` or `WRITE VOLUME` |
| `NOT_FOUND` | Volume or path doesn't exist | Check path spelling, ensure volume exists |
| `ALREADY_EXISTS` | File exists, overwrite=False | Set `overwrite=True` or delete first |
| `RESOURCE_DOES_NOT_EXIST` | Parent directory doesn't exist | Create parent directories first |
| `INVALID_PARAMETER_VALUE` | Invalid path format | Use `/Volumes/catalog/schema/volume/path` format |

### Debug Checklist

1. **Verify volume exists:**
   ```sql
   SELECT * FROM system.information_schema.volumes
   WHERE volume_name = 'my_volume';
   ```

2. **Check permissions:**
   ```python
   grants = w.grants.get(
       securable_type=SecurableType.VOLUME,
       full_name="catalog.schema.volume"
   )
   ```

3. **Verify path format:**
   - Must start with `/Volumes/`
   - Three-level namespace: `catalog/schema/volume`
   - No double slashes (`//`)

4. **Check file exists:**
   ```python
   try:
       w.files.get_metadata("/Volumes/catalog/schema/volume/file.csv")
   except Exception as e:
       print(f"File not found: {e}")
   ```

### External Volume Issues

1. **Storage credential required** - External volumes need a storage credential
   ```python
   # Create storage credential first
   w.storage_credentials.create(
       name="my_s3_cred",
       aws_iam_role={"role_arn": "arn:aws:iam::..."}
   )
   
   # Create external location
   w.external_locations.create(
       name="my_s3_location",
       url="s3://my-bucket/path",
       credential_name="my_s3_cred"
   )
   
   # Then create external volume
   w.volumes.create(
       ...
       volume_type=VolumeType.EXTERNAL,
       storage_location="s3://my-bucket/path/volume"
   )
   ```

2. **Network access** - Ensure workspace can reach cloud storage

3. **IAM permissions** - Verify IAM role has bucket access
