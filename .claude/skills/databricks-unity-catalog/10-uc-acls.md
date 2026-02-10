# Unity Catalog Access Controls (ACLs)

Comprehensive reference for Unity Catalog privilege management: GRANT/REVOKE, ownership, and permission patterns across securables.

## Securable Hierarchy

```
METASTORE
  └── CATALOG
        └── SCHEMA
              ├── TABLE / VIEW / MATERIALIZED VIEW
              ├── VOLUME
              ├── FUNCTION
              └── MODEL
```

Privileges **inherit** down the hierarchy. Granting `USE CATALOG` on a catalog grants access to all schemas within it (but not data access — that requires `SELECT`, `MODIFY`, etc.).

## Privilege Reference

### Catalog-Level

| Privilege | Description |
|-----------|-------------|
| `USE CATALOG` | Required to access any object within the catalog |
| `CREATE SCHEMA` | Create schemas within the catalog |
| `ALL PRIVILEGES` | All catalog-level privileges |

### Schema-Level

| Privilege | Description |
|-----------|-------------|
| `USE SCHEMA` | Required to access any object within the schema |
| `CREATE TABLE` | Create tables and views |
| `CREATE VOLUME` | Create volumes |
| `CREATE FUNCTION` | Create functions |
| `CREATE MODEL` | Create registered models |
| `ALL PRIVILEGES` | All schema-level privileges |

### Table/View-Level

| Privilege | Description |
|-----------|-------------|
| `SELECT` | Read data from the table or view |
| `MODIFY` | Insert, update, delete data |
| `ALL PRIVILEGES` | All table-level privileges |

### Volume-Level

| Privilege | Description |
|-----------|-------------|
| `READ VOLUME` | Read files from the volume |
| `WRITE VOLUME` | Write files to the volume |
| `ALL PRIVILEGES` | All volume-level privileges |

### Function-Level

| Privilege | Description |
|-----------|-------------|
| `EXECUTE` | Execute the function |
| `ALL PRIVILEGES` | All function-level privileges |

## SQL Syntax

### GRANT

```sql
-- Catalog access
GRANT USE CATALOG ON CATALOG my_catalog TO `group_name`;
GRANT CREATE SCHEMA ON CATALOG my_catalog TO `group_name`;

-- Schema access
GRANT USE SCHEMA ON SCHEMA my_catalog.my_schema TO `group_name`;
GRANT CREATE TABLE ON SCHEMA my_catalog.my_schema TO `group_name`;
GRANT CREATE VOLUME ON SCHEMA my_catalog.my_schema TO `group_name`;
GRANT CREATE FUNCTION ON SCHEMA my_catalog.my_schema TO `group_name`;

-- Table/View access
GRANT SELECT ON TABLE my_catalog.my_schema.my_table TO `group_name`;
GRANT MODIFY ON TABLE my_catalog.my_schema.my_table TO `group_name`;

-- Volume access
GRANT READ VOLUME ON VOLUME my_catalog.my_schema.my_volume TO `group_name`;
GRANT WRITE VOLUME ON VOLUME my_catalog.my_schema.my_volume TO `group_name`;

-- Function access
GRANT EXECUTE ON FUNCTION my_catalog.my_schema.my_function TO `group_name`;

-- All privileges shorthand
GRANT ALL PRIVILEGES ON SCHEMA my_catalog.my_schema TO `admin_group`;
```

### REVOKE

```sql
REVOKE SELECT ON TABLE my_catalog.my_schema.my_table FROM `group_name`;
REVOKE MODIFY ON TABLE my_catalog.my_schema.my_table FROM `group_name`;
REVOKE ALL PRIVILEGES ON SCHEMA my_catalog.my_schema FROM `group_name`;
```

### Show Grants

```sql
-- Show all grants on a securable
SHOW GRANTS ON CATALOG my_catalog;
SHOW GRANTS ON SCHEMA my_catalog.my_schema;
SHOW GRANTS ON TABLE my_catalog.my_schema.my_table;
SHOW GRANTS ON VOLUME my_catalog.my_schema.my_volume;

-- Show grants for a specific principal
SHOW GRANTS `group_name` ON CATALOG my_catalog;
SHOW GRANTS `user@example.com` ON SCHEMA my_catalog.my_schema;
```

## Ownership

Every securable has exactly one **owner**. The owner has all privileges on the object and can grant/revoke privileges to others.

```sql
-- Transfer ownership
ALTER CATALOG my_catalog OWNER TO `new_owner`;
ALTER SCHEMA my_catalog.my_schema OWNER TO `new_owner`;
ALTER TABLE my_catalog.my_schema.my_table OWNER TO `new_owner`;
ALTER VOLUME my_catalog.my_schema.my_volume OWNER TO `new_owner`;
```

## Python SDK Patterns

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# Grant privileges
w.grants.update(
    securable_type="TABLE",
    full_name="my_catalog.my_schema.my_table",
    changes=[{
        "principal": "data_readers",
        "add": ["SELECT"],
    }]
)

# Revoke privileges
w.grants.update(
    securable_type="TABLE",
    full_name="my_catalog.my_schema.my_table",
    changes=[{
        "principal": "data_readers",
        "remove": ["SELECT"],
    }]
)

# Get current grants
grants = w.grants.get(
    securable_type="TABLE",
    full_name="my_catalog.my_schema.my_table"
)
for assignment in grants.privilege_assignments:
    print(f"{assignment.principal}: {assignment.privileges}")

# Get effective grants (includes inherited)
effective = w.grants.get_effective(
    securable_type="TABLE",
    full_name="my_catalog.my_schema.my_table",
    principal="data_readers"
)
```

## Common Patterns

### Read-Only Data Consumer

```sql
-- Minimal access for data readers
GRANT USE CATALOG ON CATALOG analytics TO `data_readers`;
GRANT USE SCHEMA ON SCHEMA analytics.gold TO `data_readers`;
GRANT SELECT ON SCHEMA analytics.gold TO `data_readers`;
```

### Data Engineer (Read + Write)

```sql
GRANT USE CATALOG ON CATALOG analytics TO `data_engineers`;
GRANT USE SCHEMA ON SCHEMA analytics.silver TO `data_engineers`;
GRANT SELECT ON SCHEMA analytics.silver TO `data_engineers`;
GRANT MODIFY ON SCHEMA analytics.silver TO `data_engineers`;
GRANT CREATE TABLE ON SCHEMA analytics.silver TO `data_engineers`;
```

### Schema Admin

```sql
GRANT USE CATALOG ON CATALOG analytics TO `schema_admins`;
GRANT ALL PRIVILEGES ON SCHEMA analytics.gold TO `schema_admins`;
```

### ML Engineer (Models + Functions)

```sql
GRANT USE CATALOG ON CATALOG ml TO `ml_engineers`;
GRANT USE SCHEMA ON SCHEMA ml.models TO `ml_engineers`;
GRANT CREATE MODEL ON SCHEMA ml.models TO `ml_engineers`;
GRANT CREATE FUNCTION ON SCHEMA ml.models TO `ml_engineers`;
GRANT SELECT ON SCHEMA ml.features TO `ml_engineers`;
```

## MCP Tool

Use `mcp__databricks__manage_uc_grants` for grant operations, or `mcp__databricks__execute_sql` for SQL-based grant management.

## Best Practices

1. **Grant to groups, not users** — Easier to manage and audit
2. **Use least privilege** — Grant only the minimum permissions needed
3. **Leverage inheritance** — Grant at schema level when all tables need the same access
4. **Audit regularly** — Query `system.access.audit` for grant/revoke events
5. **Prefer `USE CATALOG` + `USE SCHEMA` + `SELECT`** over `ALL PRIVILEGES`
6. **Document ownership** — Keep track of who owns each catalog/schema
