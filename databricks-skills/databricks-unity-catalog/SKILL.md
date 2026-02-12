---
name: databricks-unity-catalog
description: "Unity Catalog: system tables, volumes, access controls (ACLs), and FGAC governance. Use when querying system tables (audit, lineage, billing), working with volume file operations, managing UC permissions (GRANT/REVOKE), or managing FGAC policies (column masks, row filters, governed tags, masking UDFs)."
---

# Unity Catalog

Guidance for Unity Catalog across four areas: system tables, volumes, access controls, and FGAC policy governance.

## When to Use This Skill

Use this skill when working with any of these four categories:

### System Tables
- Querying **lineage** (table dependencies, column-level lineage)
- Analyzing **audit logs** (who accessed what, permission changes)
- Monitoring **billing and usage** (DBU consumption, cost analysis)
- Tracking **compute resources** (cluster usage, warehouse metrics)
- Reviewing **job execution** (run history, success rates, failures)
- Analyzing **query performance** (slow queries, warehouse utilization)

### Volumes
- Working with **volumes** (upload, download, list files in `/Volumes/`)
- Managing volume **directories** and file operations
- Configuring volume **permissions** (READ VOLUME, WRITE VOLUME)

### UC Access Controls (ACLs)
- **Granting or revoking** privileges on catalogs, schemas, tables, volumes, functions
- Managing **ownership** transfers
- Setting up **role-based access** patterns (data readers, engineers, admins)
- Auditing **current permissions** (SHOW GRANTS)

### FGAC (Fine-Grained Access Control)
- Creating or managing **FGAC policies** (column masks, row filters)
- Working with **governed tags** (creating via UI, applying via SQL)
- Building **masking UDFs** for PII protection (SSN, email, credit card, etc.)
- Implementing **human-in-the-loop governance** workflows
- Managing **policy lifecycle** (create, update, delete, preview)
- Querying **tag assignments** via `information_schema`

---

## Reference Files

### System Tables

| File | Description |
|------|-------------|
| [5-system-tables.md](5-system-tables.md) | Lineage, audit, billing, compute, jobs, query history |

### Volumes

| File | Description |
|------|-------------|
| [6-volumes.md](6-volumes.md) | Volume file operations, permissions, best practices |

### UC Access Controls (ACLs)

| File | Description |
|------|-------------|
| [10-uc-acls.md](10-uc-acls.md) | GRANT/REVOKE, ownership, privilege reference, SDK patterns, common role patterns |

### FGAC (Fine-Grained Access Control)

| File | Description |
|------|-------------|
| [7-fgac-overview.md](7-fgac-overview.md) | FGAC workflow, governed tags, masking UDFs, policy syntax, errors, best practices |
| [8-fgac-sql-generation.md](8-fgac-sql-generation.md) | SET/UNSET TAG, CREATE FUNCTION, CREATE/DROP POLICY, discovery queries |
| [9-fgac-sdk-and-tools.md](9-fgac-sdk-and-tools.md) | Python SDK patterns and 12 MCP tools for policy management |

---

## Quick Start: System Tables

### Enable Access

```sql
-- Grant access to system tables
GRANT USE CATALOG ON CATALOG system TO `data_engineers`;
GRANT USE SCHEMA ON SCHEMA system.access TO `data_engineers`;
GRANT SELECT ON SCHEMA system.access TO `data_engineers`;
```

### Common Queries

```sql
-- Table lineage: What tables feed into this table?
SELECT source_table_full_name, source_column_name
FROM system.access.table_lineage
WHERE target_table_full_name = 'catalog.schema.table'
  AND event_date >= current_date() - 7;

-- Audit: Recent permission changes
SELECT event_time, user_identity.email, action_name, request_params
FROM system.access.audit
WHERE action_name LIKE '%GRANT%' OR action_name LIKE '%REVOKE%'
ORDER BY event_time DESC
LIMIT 100;

-- Billing: DBU usage by workspace
SELECT workspace_id, sku_name, SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
GROUP BY workspace_id, sku_name;
```

### MCP Tool Integration

```python
mcp__databricks__execute_sql(
    sql_query="""
        SELECT source_table_full_name, target_table_full_name
        FROM system.access.table_lineage
        WHERE event_date >= current_date() - 7
    """,
    catalog="system"
)
```

---

## Quick Start: Volumes

```python
# List files in a volume
list_volume_files(volume_path="/Volumes/catalog/schema/volume/folder/")

# Upload file to volume
upload_to_volume(
    local_path="/tmp/data.csv",
    volume_path="/Volumes/catalog/schema/volume/data.csv"
)

# Download file from volume
download_from_volume(
    volume_path="/Volumes/catalog/schema/volume/data.csv",
    local_path="/tmp/downloaded.csv"
)

# Create directory
create_volume_directory(volume_path="/Volumes/catalog/schema/volume/new_folder")
```

See [6-volumes.md](6-volumes.md) for full volume operations, permissions, and troubleshooting.

---

## Quick Start: UC Access Controls (ACLs)

```sql
-- Read-only access pattern
GRANT USE CATALOG ON CATALOG analytics TO `data_readers`;
GRANT USE SCHEMA ON SCHEMA analytics.gold TO `data_readers`;
GRANT SELECT ON SCHEMA analytics.gold TO `data_readers`;

-- Data engineer access pattern
GRANT USE CATALOG ON CATALOG analytics TO `data_engineers`;
GRANT USE SCHEMA ON SCHEMA analytics.silver TO `data_engineers`;
GRANT SELECT ON SCHEMA analytics.silver TO `data_engineers`;
GRANT MODIFY ON SCHEMA analytics.silver TO `data_engineers`;
GRANT CREATE TABLE ON SCHEMA analytics.silver TO `data_engineers`;

-- Show current grants
SHOW GRANTS ON SCHEMA analytics.gold;

-- Transfer ownership
ALTER SCHEMA analytics.gold OWNER TO `new_owner`;
```

See [10-uc-acls.md](10-uc-acls.md) for full privilege reference, SDK patterns, and common role patterns.

---

## Quick Start: FGAC

```sql
-- 1. Apply governed tag to a column (tag must exist in UI first)
SET TAG ON COLUMN catalog.schema.table.ssn_column 'pii_type' = 'ssn';

-- 2. Create a masking UDF
CREATE OR REPLACE FUNCTION catalog.schema.mask_ssn(ssn STRING)
RETURNS STRING
DETERMINISTIC
RETURN CASE
    WHEN ssn IS NULL THEN NULL
    WHEN LENGTH(REGEXP_REPLACE(ssn, '[^0-9]', '')) >= 4
        THEN CONCAT('***-**-', RIGHT(REGEXP_REPLACE(ssn, '[^0-9]', ''), 4))
    ELSE '***-**-****'
END;

-- 3. Create an FGAC column mask policy
CREATE OR REPLACE POLICY mask_pii_ssn
ON SCHEMA catalog.schema
COMMENT 'Mask SSN columns for analysts'
COLUMN MASK catalog.schema.mask_ssn
TO `analysts`
EXCEPT `gov_admin`
FOR TABLES
MATCH COLUMNS hasTagValue('pii_type', 'ssn') AS masked_col
ON COLUMN masked_col;
```

See [7-fgac-overview.md](7-fgac-overview.md) for the full FGAC workflow, policy syntax, and best practices.

---

## Best Practices

### System Tables
1. **Filter by date** — System tables can be large; always use date filters
2. **Use appropriate retention** — Check your workspace's retention settings
3. **Schedule reports** — Create scheduled queries for regular monitoring

### Volumes
4. **Organize by purpose** — Use directory structure within volumes
5. **Grant minimal access** — Use `READ VOLUME` vs `WRITE VOLUME` appropriately

### UC Access Controls (ACLs)
6. **Grant to groups, not users** — Easier to manage and audit
7. **Use least privilege** — Grant only the minimum permissions needed
8. **Leverage inheritance** — Grant at schema level when all tables need the same access
9. **Audit regularly** — Query `system.access.audit` for grant/revoke events

### FGAC
10. **Always include `EXCEPT \`gov_admin\``** in every FGAC policy
11. **Preview before executing** any FGAC policy change
12. **Use governed tags** (not ad-hoc tags) for FGAC policy matching

## Resources

### System Tables & Volumes
- [Unity Catalog System Tables](https://docs.databricks.com/administration-guide/system-tables/)
- [Audit Log Reference](https://docs.databricks.com/administration-guide/account-settings/audit-logs.html)

### UC Access Controls
- [UC Privileges](https://docs.databricks.com/data-governance/unity-catalog/manage-privileges/)

### FGAC
- [FGAC Overview](https://docs.databricks.com/data-governance/unity-catalog/abac/)
- [FGAC Policies](https://docs.databricks.com/data-governance/unity-catalog/abac/policies)
- [FGAC Tutorial](https://docs.databricks.com/data-governance/unity-catalog/abac/tutorial)
- [Governed Tags](https://docs.databricks.com/admin/governed-tags/)
