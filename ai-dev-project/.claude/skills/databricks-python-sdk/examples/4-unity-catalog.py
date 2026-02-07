"""
Databricks SDK - Unity Catalog Examples

Catalogs: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html
Schemas: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html
Tables: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html
Volumes: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html
"""

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import VolumeType

w = WorkspaceClient()

# =============================================================================
# CATALOGS
# =============================================================================

# List all catalogs
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html
for catalog in w.catalogs.list():
    print(f"Catalog: {catalog.name} (owner: {catalog.owner})")


# Get catalog details
catalog = w.catalogs.get(name="main")
print(f"Catalog: {catalog.name}")
print(f"Comment: {catalog.comment}")


# Create a new catalog
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/catalogs.html
new_catalog = w.catalogs.create(
    name="my_catalog",
    comment="My analytics catalog"
)
print(f"Created catalog: {new_catalog.name}")


# Update catalog
w.catalogs.update(
    name="my_catalog",
    comment="Updated description",
    owner="admin@company.com"
)


# Delete catalog (must be empty or use force=True)
w.catalogs.delete(name="my_catalog", force=True)


# =============================================================================
# SCHEMAS
# =============================================================================

# List schemas in a catalog
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html
for schema in w.schemas.list(catalog_name="main"):
    print(f"Schema: {schema.full_name}")


# Get schema details
schema = w.schemas.get(full_name="main.default")
print(f"Schema: {schema.name}")
print(f"Catalog: {schema.catalog_name}")


# Create a new schema
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/schemas.html
new_schema = w.schemas.create(
    name="analytics",
    catalog_name="main",
    comment="Analytics data schema"
)


# Update schema
w.schemas.update(
    full_name="main.analytics",
    comment="Updated analytics schema"
)


# Delete schema
w.schemas.delete(full_name="main.analytics")


# =============================================================================
# TABLES
# =============================================================================

# List tables in a schema
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html
for table in w.tables.list(catalog_name="main", schema_name="default"):
    print(f"Table: {table.full_name} ({table.table_type})")


# Get table summaries (faster, less detail)
for summary in w.tables.list_summaries(
    catalog_name="main",
    schema_name_pattern="*",
    table_name_pattern="events*"
):
    print(f"Table: {summary.full_name}")


# Get table details
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html
table = w.tables.get(full_name="main.default.my_table")
print(f"Table: {table.name}")
print(f"Type: {table.table_type}")
print(f"Location: {table.storage_location}")

# Print column info
for col in table.columns:
    print(f"  {col.name}: {col.type_name} (nullable: {col.nullable})")


# Check if table exists
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/tables.html
exists = w.tables.exists(full_name="main.default.my_table")
print(f"Table exists: {exists.table_exists}")


# Update table owner
w.tables.update(
    full_name="main.default.my_table",
    owner="new_owner@company.com"
)


# Delete table
w.tables.delete(full_name="main.default.my_table")


# =============================================================================
# VOLUMES
# =============================================================================

# List volumes in a schema
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html
for volume in w.volumes.list(catalog_name="main", schema_name="default"):
    print(f"Volume: {volume.full_name} ({volume.volume_type})")


# Get volume details
volume = w.volumes.read(name="main.default.my_volume")
print(f"Volume: {volume.name}")
print(f"Type: {volume.volume_type}")
print(f"Storage: {volume.storage_location}")


# Create a managed volume (Databricks manages storage)
# Doc: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/catalog/volumes.html
managed_volume = w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_managed_volume",
    volume_type=VolumeType.MANAGED,
    comment="Managed volume for data files"
)


# Create an external volume (you manage storage)
external_volume = w.volumes.create(
    catalog_name="main",
    schema_name="default",
    name="my_external_volume",
    volume_type=VolumeType.EXTERNAL,
    storage_location="s3://my-bucket/volumes/data",
    comment="External volume pointing to S3"
)


# Update volume
w.volumes.update(
    name="main.default.my_volume",
    comment="Updated description"
)


# Delete volume
w.volumes.delete(name="main.default.my_volume")


# =============================================================================
# WORKING WITH VOLUME FILES
# =============================================================================
# See also: https://databricks-sdk-py.readthedocs.io/en/latest/workspace/files/files.html

# Upload file to volume
w.files.upload(
    file_path="/Volumes/main/default/my_volume/data.csv",
    contents=open("local_file.csv", "rb"),
    overwrite=True
)

# List files in volume
for entry in w.files.list_directory_contents("/Volumes/main/default/my_volume/"):
    print(f"{entry.name}: {'dir' if entry.is_directory else 'file'}")

# Download file from volume
response = w.files.download(file_path="/Volumes/main/default/my_volume/data.csv")
with open("downloaded.csv", "wb") as f:
    f.write(response.read())

# Delete file from volume
w.files.delete(file_path="/Volumes/main/default/my_volume/data.csv")
