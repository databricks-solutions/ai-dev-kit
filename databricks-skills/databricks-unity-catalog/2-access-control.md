# Unity Catalog Access Control

Permissions, row-level security, column masking, and service principal setup.

## Privilege Types

| Privilege | Applies To | Description |
|-----------|------------|-------------|
| `USE CATALOG` | Catalog | Required to access anything in the catalog |
| `USE SCHEMA` | Schema | Required to access objects in the schema |
| `SELECT` | Table/View | Read data |
| `MODIFY` | Table | Insert, update, delete, merge |
| `CREATE TABLE` | Schema | Create tables in schema |
| `CREATE SCHEMA` | Catalog | Create schemas in catalog |
| `CREATE CATALOG` | Metastore | Create catalogs (admin) |
| `CREATE VOLUME` | Schema | Create volumes in schema |
| `CREATE FUNCTION` | Schema | Create functions in schema |
| `READ VOLUME` | Volume | Read files from volume |
| `WRITE VOLUME` | Volume | Write files to volume |
| `EXECUTE` | Function | Execute a function |
| `ALL PRIVILEGES` | Any | Full access to object |

---

## Granting Permissions

### Basic GRANT Patterns

**SQL:**
```sql
-- Grant catalog access (required first)
GRANT USE CATALOG ON CATALOG analytics TO `data_engineers`;

-- Grant schema access
GRANT USE SCHEMA ON SCHEMA analytics.bronze TO `data_engineers`;
GRANT CREATE TABLE ON SCHEMA analytics.bronze TO `data_engineers`;

-- Grant table access
GRANT SELECT ON TABLE analytics.gold.customers TO `analysts`;
GRANT SELECT, MODIFY ON TABLE analytics.silver.orders TO `etl_team`;

-- Grant to service principal (use the UUID or application ID)
GRANT ALL PRIVILEGES ON SCHEMA analytics.bronze TO `00000000-0000-0000-0000-000000000000`;

-- Grant to user
GRANT SELECT ON TABLE analytics.gold.report TO `user@company.com`;

-- Grant with all tables in schema
GRANT SELECT ON ALL TABLES IN SCHEMA analytics.gold TO `report_viewers`;

-- Revoke access
REVOKE SELECT ON TABLE analytics.gold.customers FROM `temp_user`;
REVOKE ALL PRIVILEGES ON CATALOG analytics FROM `old_group`;
```

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import PermissionsChange, SecurableType

w = WorkspaceClient()

# Grant permissions
w.grants.update(
    securable_type=SecurableType.CATALOG,
    full_name="analytics",
    changes=[
        PermissionsChange(
            principal="data_engineers",
            add=["USE_CATALOG"]
        )
    ]
)

# Grant multiple privileges
w.grants.update(
    securable_type=SecurableType.SCHEMA,
    full_name="analytics.bronze",
    changes=[
        PermissionsChange(
            principal="data_engineers",
            add=["USE_SCHEMA", "CREATE_TABLE"]
        )
    ]
)

# Grant table access
w.grants.update(
    securable_type=SecurableType.TABLE,
    full_name="analytics.gold.customers",
    changes=[
        PermissionsChange(principal="analysts", add=["SELECT"]),
        PermissionsChange(principal="etl_team", add=["SELECT", "MODIFY"])
    ]
)

# Revoke permissions
w.grants.update(
    securable_type=SecurableType.TABLE,
    full_name="analytics.gold.customers",
    changes=[
        PermissionsChange(principal="temp_user", remove=["SELECT"])
    ]
)

# Get current permissions
grants = w.grants.get(SecurableType.TABLE, "analytics.gold.customers")
for g in grants.privilege_assignments:
    print(f"{g.principal}: {g.privileges}")

# Get effective permissions (includes inherited)
effective = w.grants.get_effective(SecurableType.TABLE, "analytics.gold.customers")
```

**CLI:**
```bash
# Get permissions
databricks grants get TABLE analytics.gold.customers

# Get effective permissions
databricks grants get-effective TABLE analytics.gold.customers

# Update permissions (requires JSON)
databricks grants update TABLE analytics.gold.customers --json '{
    "changes": [
        {"principal": "analysts", "add": ["SELECT"]},
        {"principal": "temp_user", "remove": ["SELECT"]}
    ]
}'
```

---

## Environment Isolation Patterns

### Catalog-per-Environment (Recommended)

```sql
-- DEVELOPMENT: Full access for developers
CREATE CATALOG analytics_dev;
GRANT ALL PRIVILEGES ON CATALOG analytics_dev TO `developers`;
GRANT CREATE CATALOG ON METASTORE TO `developers`;  -- If needed

-- STAGING: CI/CD has write, testers have read
CREATE CATALOG analytics_staging;
GRANT ALL PRIVILEGES ON CATALOG analytics_staging TO `ci_cd_service_principal`;
GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG analytics_staging TO `testers`;

-- PRODUCTION: Strict access control
CREATE CATALOG analytics_prod;
GRANT ALL PRIVILEGES ON CATALOG analytics_prod TO `prod_etl_service_principal`;
GRANT USE CATALOG, USE SCHEMA, SELECT ON CATALOG analytics_prod TO `analysts`;
-- Deny write access explicitly
REVOKE MODIFY ON CATALOG analytics_prod FROM `analysts`;
```

### Schema-per-Environment (Single Catalog)

```sql
CREATE CATALOG analytics;

-- Dev schema
CREATE SCHEMA analytics.dev;
GRANT ALL PRIVILEGES ON SCHEMA analytics.dev TO `developers`;

-- Staging schema
CREATE SCHEMA analytics.staging;
GRANT USE SCHEMA, SELECT ON SCHEMA analytics.staging TO `testers`;

-- Prod schema
CREATE SCHEMA analytics.prod;
GRANT USE SCHEMA, SELECT ON SCHEMA analytics.prod TO `analysts`;
```

---

## Row-Level Security

Row filters restrict which rows users can see.

### Create Row Filter Function

**SQL:**
```sql
-- Region-based filter
CREATE FUNCTION analytics.security.region_filter(region STRING)
RETURNS BOOLEAN
COMMENT 'Filter rows by user region'
RETURN CASE
    WHEN IS_ACCOUNT_GROUP_MEMBER('global_admins') THEN TRUE
    WHEN IS_ACCOUNT_GROUP_MEMBER('us_team') AND region = 'US' THEN TRUE
    WHEN IS_ACCOUNT_GROUP_MEMBER('eu_team') AND region = 'EU' THEN TRUE
    ELSE FALSE
END;

-- Apply to table
ALTER TABLE analytics.gold.sales
SET ROW FILTER analytics.security.region_filter ON (region);

-- Multi-tenant filter (uses group naming convention: tenant_{id})
CREATE FUNCTION analytics.security.tenant_filter(tenant_id STRING)
RETURNS BOOLEAN
RETURN IS_ACCOUNT_GROUP_MEMBER(CONCAT('tenant_', tenant_id))
    OR IS_ACCOUNT_GROUP_MEMBER('super_admins');

ALTER TABLE analytics.gold.customer_data
SET ROW FILTER analytics.security.tenant_filter ON (tenant_id);
```

### Remove Row Filter

```sql
ALTER TABLE analytics.gold.sales
DROP ROW FILTER;
```

### View Current Row Filters

```sql
DESCRIBE TABLE EXTENDED analytics.gold.sales;
-- Look for "Row Filter" in output
```

---

## Column Masking

Column masks transform sensitive data for unauthorized users.

### Create Mask Functions

**SQL:**
```sql
-- Email masking
CREATE FUNCTION analytics.security.mask_email(email STRING)
RETURNS STRING
COMMENT 'Mask email showing only domain'
RETURN CASE
    WHEN IS_ACCOUNT_GROUP_MEMBER('pii_access') THEN email
    ELSE CONCAT('***@', SPLIT(email, '@')[1])
END;

-- SSN masking (show last 4)
CREATE FUNCTION analytics.security.mask_ssn(ssn STRING)
RETURNS STRING
RETURN CASE
    WHEN IS_ACCOUNT_GROUP_MEMBER('pii_access') THEN ssn
    ELSE CONCAT('XXX-XX-', RIGHT(ssn, 4))
END;

-- Credit card masking
CREATE FUNCTION analytics.security.mask_card(card_number STRING)
RETURNS STRING
RETURN CASE
    WHEN IS_ACCOUNT_GROUP_MEMBER('finance_admin') THEN card_number
    ELSE CONCAT('****-****-****-', RIGHT(card_number, 4))
END;

-- Full redaction
CREATE FUNCTION analytics.security.redact_salary(salary DECIMAL(10,2))
RETURNS DECIMAL(10,2)
RETURN CASE
    WHEN IS_ACCOUNT_GROUP_MEMBER('hr_admin') THEN salary
    ELSE NULL
END;
```

### Apply Masks to Columns

```sql
-- Apply single mask
ALTER TABLE analytics.gold.customers
ALTER COLUMN email SET MASK analytics.security.mask_email;

-- Apply multiple masks
ALTER TABLE analytics.gold.employees
ALTER COLUMN ssn SET MASK analytics.security.mask_ssn;

ALTER TABLE analytics.gold.employees
ALTER COLUMN salary SET MASK analytics.security.redact_salary;

-- Remove mask
ALTER TABLE analytics.gold.customers
ALTER COLUMN email DROP MASK;
```

---

## Service Principal Setup

### Create and Configure Service Principal

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# List service principals
for sp in w.service_principals.list():
    print(f"{sp.display_name}: {sp.application_id}")

# Get service principal by application ID
sp = w.service_principals.get(id="00000000-0000-0000-0000-000000000000")
```

**CLI:**
```bash
# List service principals
databricks service-principals list

# Get service principal
databricks service-principals get 00000000-0000-0000-0000-000000000000
```

### Grant Permissions to Service Principal

**SQL:**
```sql
-- Use the service principal's application ID
GRANT USE CATALOG ON CATALOG analytics_prod TO `00000000-0000-0000-0000-000000000000`;
GRANT USE SCHEMA ON SCHEMA analytics_prod.gold TO `00000000-0000-0000-0000-000000000000`;
GRANT SELECT, MODIFY ON ALL TABLES IN SCHEMA analytics_prod.gold TO `00000000-0000-0000-0000-000000000000`;
```

### Use Service Principal in DABs

```yaml
# databricks.yml
targets:
  prod:
    workspace:
      host: https://your-workspace.cloud.databricks.com
    run_as:
      service_principal_name: "00000000-0000-0000-0000-000000000000"
```

---

## Ownership

### Transfer Ownership

**SQL:**
```sql
-- Change catalog owner
ALTER CATALOG analytics SET OWNER TO `admin_group`;

-- Change schema owner
ALTER SCHEMA analytics.gold SET OWNER TO `data_governance_team`;

-- Change table owner
ALTER TABLE analytics.gold.customers SET OWNER TO `data_steward`;

-- Change volume owner
ALTER VOLUME analytics.bronze.raw_files SET OWNER TO `data_engineers`;
```

**Python SDK:**
```python
# Update catalog owner
w.catalogs.update(name="analytics", owner="admin_group")

# Update schema owner
w.schemas.update(full_name="analytics.gold", owner="data_governance_team")
```

---

## Viewing Permissions

### Check Current Permissions

**SQL:**
```sql
-- Show grants on object
SHOW GRANTS ON CATALOG analytics;
SHOW GRANTS ON SCHEMA analytics.gold;
SHOW GRANTS ON TABLE analytics.gold.customers;

-- Show grants for principal
SHOW GRANTS TO `data_engineers`;
SHOW GRANTS TO `user@company.com`;

-- Show grants on all tables in schema
SHOW GRANTS ON ALL TABLES IN SCHEMA analytics.gold;
```

### Query Permissions via System Tables

```sql
-- Get all grants in a catalog
SELECT
    grantee,
    table_catalog,
    table_schema,
    table_name,
    privilege_type
FROM system.information_schema.table_privileges
WHERE table_catalog = 'analytics'
ORDER BY grantee, table_schema, table_name;
```

---

## Best Practices

### Permission Strategy

1. **Always grant hierarchically**: USE_CATALOG → USE_SCHEMA → object privileges
2. **Use groups**: Never grant to individuals, always to groups
3. **Principle of least privilege**: Start minimal, add as needed
4. **Service principals for automation**: Never use personal tokens in production
5. **Regular audits**: Review permissions quarterly

### Security Functions

1. **Name clearly**: `security.mask_*`, `security.filter_*`
2. **Document**: Always add COMMENT explaining the logic
3. **Test thoroughly**: Verify with different group memberships
4. **Keep simple**: Complex logic is hard to audit

### Common Permission Combos

```sql
-- Read-only analyst
GRANT USE CATALOG ON CATALOG analytics TO `analysts`;
GRANT USE SCHEMA ON SCHEMA analytics.gold TO `analysts`;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics.gold TO `analysts`;

-- ETL pipeline
GRANT USE CATALOG ON CATALOG analytics TO `etl_sp`;
GRANT USE SCHEMA ON ALL SCHEMAS IN CATALOG analytics TO `etl_sp`;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics.bronze TO `etl_sp`;
GRANT SELECT, MODIFY ON ALL TABLES IN SCHEMA analytics.silver TO `etl_sp`;
GRANT SELECT, MODIFY ON ALL TABLES IN SCHEMA analytics.gold TO `etl_sp`;

-- Data engineer (full schema access, read-only others)
GRANT USE CATALOG ON CATALOG analytics TO `data_engineers`;
GRANT ALL PRIVILEGES ON SCHEMA analytics.bronze TO `data_engineers`;
GRANT USE SCHEMA, SELECT ON SCHEMA analytics.silver TO `data_engineers`;
GRANT USE SCHEMA, SELECT ON SCHEMA analytics.gold TO `data_engineers`;
```
