# Unity Catalog Objects & Governance

Manage the UC namespace hierarchy (catalogs, schemas, volumes, functions) and permissions.

## Namespace Hierarchy

```
metastore
└── catalog
    └── schema
        ├── table / view / materialized view
        ├── volume (managed or external)
        └── function
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `manage_uc_objects` | CRUD for catalogs, schemas, volumes, functions |
| `manage_uc_grants` | Grant, revoke, and inspect permissions |

---

## Catalog Operations

### Create a Catalog

```python
manage_uc_objects(
    object_type="catalog",
    action="create",
    name="analytics",
    comment="Production analytics catalog"
)
```

With managed storage location (isolates data from metastore default):

```python
manage_uc_objects(
    object_type="catalog",
    action="create",
    name="analytics",
    comment="Production analytics catalog",
    storage_root="s3://my-bucket/analytics/"
)
```

### List / Get / Update / Delete

```python
# List all catalogs
manage_uc_objects(object_type="catalog", action="list")

# Get details
manage_uc_objects(object_type="catalog", action="get", full_name="analytics")

# Update comment or owner
manage_uc_objects(
    object_type="catalog",
    action="update",
    full_name="analytics",
    comment="Updated description",
    owner="data-engineering@company.com"
)

# Delete (force=True to delete non-empty catalogs)
manage_uc_objects(object_type="catalog", action="delete", full_name="analytics", force=True)
```

### Catalog Isolation Mode

```python
# OPEN: all workspace users can see the catalog
# ISOLATED: only explicitly bound workspaces can access
manage_uc_objects(
    object_type="catalog",
    action="update",
    full_name="analytics",
    isolation_mode="ISOLATED"
)
```

---

## Schema Operations

```python
# Create schema
manage_uc_objects(
    object_type="schema",
    action="create",
    name="gold",
    catalog_name="analytics",
    comment="Gold-layer aggregated tables"
)

# List schemas in a catalog
manage_uc_objects(object_type="schema", action="list", catalog_name="analytics")

# Delete schema
manage_uc_objects(object_type="schema", action="delete", full_name="analytics.gold", force=True)
```

---

## Volume Operations

```python
# Create managed volume (data stored in catalog's managed location)
manage_uc_objects(
    object_type="volume",
    action="create",
    name="raw_files",
    catalog_name="analytics",
    schema_name="bronze",
    volume_type="MANAGED",
    comment="Raw ingestion files"
)

# Create external volume (data stays in your cloud storage)
manage_uc_objects(
    object_type="volume",
    action="create",
    name="landing_zone",
    catalog_name="analytics",
    schema_name="bronze",
    volume_type="EXTERNAL",
    storage_location="s3://my-bucket/landing/",
    comment="External landing zone"
)

# List volumes in a schema
manage_uc_objects(
    object_type="volume",
    action="list",
    catalog_name="analytics",
    schema_name="bronze"
)
```

For file operations on volumes (upload, download, list files), see [6-volumes.md](6-volumes.md).

---

## Function Operations

```python
# List functions in a schema
manage_uc_objects(
    object_type="function",
    action="list",
    catalog_name="analytics",
    schema_name="gold"
)

# Get function details
manage_uc_objects(
    object_type="function",
    action="get",
    full_name="analytics.gold.calculate_revenue"
)

# Delete function
manage_uc_objects(
    object_type="function",
    action="delete",
    full_name="analytics.gold.calculate_revenue"
)
```

To **create** functions, use `execute_sql` or `manage_uc_security_policies` (for security functions):

```sql
CREATE FUNCTION analytics.gold.calculate_revenue(quantity INT, price DECIMAL(10,2))
RETURNS DECIMAL(10,2)
RETURN quantity * price;
```

---

## Permissions (Grants)

### Grant Privileges

```python
# Grant catalog-level access
manage_uc_grants(
    action="grant",
    securable_type="catalog",
    full_name="analytics",
    principal="data-analysts",
    privileges=["USE_CATALOG"]
)

# Grant schema-level read access
manage_uc_grants(
    action="grant",
    securable_type="schema",
    full_name="analytics.gold",
    principal="data-analysts",
    privileges=["USE_SCHEMA", "SELECT"]
)

# Grant table-level write access
manage_uc_grants(
    action="grant",
    securable_type="table",
    full_name="analytics.gold.revenue",
    principal="data-engineering",
    privileges=["SELECT", "MODIFY"]
)

# Grant volume access
manage_uc_grants(
    action="grant",
    securable_type="volume",
    full_name="analytics.bronze.raw_files",
    principal="data-engineering",
    privileges=["READ_VOLUME", "WRITE_VOLUME"]
)
```

### Common Privilege Combinations

| Role | Catalog | Schema | Tables | Volumes |
|------|---------|--------|--------|---------|
| **Reader** | `USE_CATALOG` | `USE_SCHEMA` | `SELECT` | `READ_VOLUME` |
| **Writer** | `USE_CATALOG` | `USE_SCHEMA` | `SELECT`, `MODIFY` | `READ_VOLUME`, `WRITE_VOLUME` |
| **Creator** | `USE_CATALOG` | `USE_SCHEMA`, `CREATE_TABLE`, `CREATE_VOLUME` | — | — |
| **Admin** | `ALL_PRIVILEGES` | — | — | — |

### Inspect and Revoke

```python
# Get current grants on an object
manage_uc_grants(
    action="get",
    securable_type="catalog",
    full_name="analytics"
)

# Get effective grants (includes inherited permissions)
manage_uc_grants(
    action="get_effective",
    securable_type="table",
    full_name="analytics.gold.revenue"
)

# Revoke privileges
manage_uc_grants(
    action="revoke",
    securable_type="schema",
    full_name="analytics.gold",
    principal="former-team",
    privileges=["SELECT", "USE_SCHEMA"]
)
```

---

## Common Patterns

### Bootstrap a New Project

```python
# 1. Create catalog
manage_uc_objects(object_type="catalog", action="create", name="my_project",
                  comment="My project data")

# 2. Create medallion schemas
for layer in ["bronze", "silver", "gold"]:
    manage_uc_objects(object_type="schema", action="create",
                      name=layer, catalog_name="my_project",
                      comment=f"{layer.title()} layer")

# 3. Create a volume for raw file ingestion
manage_uc_objects(object_type="volume", action="create",
                  name="raw_files", catalog_name="my_project",
                  schema_name="bronze", volume_type="MANAGED")

# 4. Grant access to the team
manage_uc_grants(action="grant", securable_type="catalog",
                 full_name="my_project", principal="my-team",
                 privileges=["USE_CATALOG", "CREATE_SCHEMA"])
```

### Audit Who Has Access

```python
# Check grants on a sensitive table
grants = manage_uc_grants(
    action="get",
    securable_type="table",
    full_name="analytics.gold.customer_pii"
)
# Review grants["assignments"] for unexpected principals
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **"User does not have USE_CATALOG"** | Grant `USE_CATALOG` on the catalog AND `USE_SCHEMA` on the schema — both are required for access |
| **Cannot create objects** | Need `CREATE_TABLE`/`CREATE_VOLUME` on the schema, plus `USE_SCHEMA` and `USE_CATALOG` |
| **"Catalog not found"** | Check `isolation_mode` — ISOLATED catalogs are only visible to bound workspaces |
| **Cannot delete non-empty catalog** | Use `force=True` or delete child schemas first |
| **External volume creation fails** | Ensure a storage credential and external location exist for the cloud path |
