---
name: databricks-unity-catalog
description: "Unity Catalog governance: manage catalogs/schemas/volumes/functions, grants & permissions, tags & classification, row filters & column masks, Delta Sharing, Lakehouse Federation, system tables, volumes, and data profiling."
---

# Unity Catalog

Comprehensive guidance for Unity Catalog — Databricks' unified governance layer for data, AI, and analytics assets.

## When to Use This Skill

Use this skill when:
- **Creating or managing** catalogs, schemas, volumes, or functions
- **Granting or revoking** permissions on any UC object
- **Tagging** tables or columns for governance, PII classification, or data discovery
- **Applying row filters or column masks** for fine-grained access control
- **Sharing data** across organizations with Delta Sharing
- **Connecting to external databases** via Lakehouse Federation
- **Managing storage credentials** and external locations
- Working with **volumes** (upload, download, list files in `/Volumes/`)
- Querying **system tables** (lineage, audit, billing, compute, jobs, query history)
- Setting up **data profiling** (monitors, drift detection, ML model monitoring)

## MCP Tools

| Tool | Purpose | Reference |
|------|---------|-----------|
| `manage_uc_objects` | CRUD for catalogs, schemas, volumes, functions | [1-objects-and-governance.md](1-objects-and-governance.md) |
| `manage_uc_grants` | Grant, revoke, inspect permissions | [1-objects-and-governance.md](1-objects-and-governance.md) |
| `manage_uc_tags` | Set/unset tags, set comments, query tags | [2-tags-and-classification.md](2-tags-and-classification.md) |
| `manage_uc_security_policies` | Row filters, column masks, security functions | [3-security-policies.md](3-security-policies.md) |
| `manage_uc_sharing` | Delta Sharing: shares, recipients, providers | [4-sharing-and-federation.md](4-sharing-and-federation.md) |
| `manage_uc_connections` | Lakehouse Federation connections | [4-sharing-and-federation.md](4-sharing-and-federation.md) |
| `manage_uc_storage` | Storage credentials and external locations | [4-sharing-and-federation.md](4-sharing-and-federation.md) |
| `manage_uc_monitors` | Data profiling monitors | [7-data-profiling.md](7-data-profiling.md) |
| `list_volume_files` / `upload_to_volume` / `download_from_volume` | Volume file operations | [6-volumes.md](6-volumes.md) |
| `execute_sql` | Query system tables and run DDL | [5-system-tables.md](5-system-tables.md) |

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Objects & Governance | [1-objects-and-governance.md](1-objects-and-governance.md) | Catalog/schema/volume/function CRUD, permissions, common patterns |
| Tags & Classification | [2-tags-and-classification.md](2-tags-and-classification.md) | Tagging tables/columns, PII classification, querying tags |
| Security Policies | [3-security-policies.md](3-security-policies.md) | Row filters, column masks, security functions |
| Sharing & Federation | [4-sharing-and-federation.md](4-sharing-and-federation.md) | Delta Sharing, storage credentials, external locations, Lakehouse Federation |
| System Tables | [5-system-tables.md](5-system-tables.md) | Lineage, audit, billing, compute, jobs, query history |
| Volumes | [6-volumes.md](6-volumes.md) | Volume file operations, permissions, best practices |
| Data Profiling | [7-data-profiling.md](7-data-profiling.md) | Data profiling, drift detection, ML model monitoring |
| Lakehouse Federation | [10-lakehouse-federation.md](10-lakehouse-federation.md) | Foreign connections, foreign catalogs, querying external databases |

## Quick Start

### Create a Catalog and Schema

```python
manage_uc_objects(object_type="catalog", action="create",
                  name="analytics", comment="Production analytics")

manage_uc_objects(object_type="schema", action="create",
                  name="gold", catalog_name="analytics",
                  comment="Gold-layer aggregated tables")
```

### Grant Access

```python
manage_uc_grants(action="grant", securable_type="catalog",
                 full_name="analytics", principal="data-team",
                 privileges=["USE_CATALOG"])

manage_uc_grants(action="grant", securable_type="schema",
                 full_name="analytics.gold", principal="data-team",
                 privileges=["USE_SCHEMA", "SELECT"])
```

### Tag a Table for PII

```python
manage_uc_tags(action="set_tags", object_type="table",
               full_name="analytics.gold.customers",
               tags={"pii": "true", "classification": "confidential"})
```

### Apply a Column Mask

```python
manage_uc_security_policies(
    action="create_security_function",
    function_name="analytics.gold.mask_email",
    parameter_name="email_val", parameter_type="STRING",
    return_type="STRING",
    function_body="RETURN IF(IS_ACCOUNT_GROUP_MEMBER('pii-readers'), email_val, CONCAT(LEFT(email_val, 2), '***@***.com'))"
)

manage_uc_security_policies(
    action="set_column_mask",
    table_name="analytics.gold.customers",
    column_name="email",
    mask_function="analytics.gold.mask_email"
)
```

### Volume File Operations

```python
list_volume_files(volume_path="/Volumes/analytics/bronze/raw_files/")

upload_to_volume(local_path="/tmp/data.csv",
                 volume_path="/Volumes/analytics/bronze/raw_files/data.csv")

download_from_volume(volume_path="/Volumes/analytics/bronze/raw_files/data.csv",
                     local_path="/tmp/downloaded.csv")
```

### Query System Tables

```sql
-- Table lineage: what feeds this table?
SELECT source_table_full_name, source_column_name
FROM system.access.table_lineage
WHERE target_table_full_name = 'catalog.schema.table'
  AND event_date >= current_date() - 7;

-- Audit: recent permission changes
SELECT event_time, user_identity.email, action_name, request_params
FROM system.access.audit
WHERE action_name LIKE '%GRANT%' OR action_name LIKE '%REVOKE%'
ORDER BY event_time DESC LIMIT 100;

-- Billing: DBU usage by workspace
SELECT workspace_id, sku_name, SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
GROUP BY workspace_id, sku_name;
```

## Common Permission Combinations

| Role | Catalog | Schema | Tables | Volumes |
|------|---------|--------|--------|---------|
| **Reader** | `USE_CATALOG` | `USE_SCHEMA` | `SELECT` | `READ_VOLUME` |
| **Writer** | `USE_CATALOG` | `USE_SCHEMA` | `SELECT`, `MODIFY` | `READ_VOLUME`, `WRITE_VOLUME` |
| **Creator** | `USE_CATALOG` | `USE_SCHEMA`, `CREATE_TABLE`, `CREATE_VOLUME` | — | — |
| **Admin** | `ALL_PRIVILEGES` | — | — | — |

## Best Practices

1. **Filter system tables by date** — they are partitioned by date; always use `event_date >= current_date() - N`
2. **Grant least privilege** — start with `USE_CATALOG` + `USE_SCHEMA` + `SELECT`, add more as needed
3. **Tag PII early** — tag tables and columns at creation time; use tags to drive column masks
4. **Use managed volumes** unless you need external storage control
5. **Test security functions** — verify row filters and column masks with a non-admin user before production
6. **Enable system schemas** early in your UC setup for audit and lineage visibility

## Related Skills

- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** — pipelines that write to Unity Catalog tables
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — job execution data visible in system tables
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** — generating data stored in Unity Catalog Volumes
- **[databricks-aibi-dashboards](../databricks-aibi-dashboards/SKILL.md)** — building dashboards on top of Unity Catalog data
- **[databricks-vector-search](../databricks-vector-search/SKILL.md)** — vector indexes on Unity Catalog tables

## Resources

- [Unity Catalog Documentation](https://docs.databricks.com/en/data-governance/unity-catalog/index.html)
- [Unity Catalog System Tables](https://docs.databricks.com/administration-guide/system-tables/)
- [Delta Sharing Documentation](https://docs.databricks.com/en/delta-sharing/index.html)
- [Lakehouse Federation](https://docs.databricks.com/en/query-federation/index.html)
- [Row Filters and Column Masks](https://docs.databricks.com/en/data-governance/unity-catalog/row-and-column-filters.html)
