---
name: databricks-unity-catalog
description: "Unity Catalog system tables and volumes. Use when querying system tables (audit, lineage, billing) or working with volume file operations (upload, download, list files in /Volumes/)."
---

# Unity Catalog

Guidance for Unity Catalog system tables, volumes, and governance.

## When to Use This Skill

Use this skill when:
- Working with **volumes** (upload, download, list files in `/Volumes/`)
- Querying **lineage** (table dependencies, column-level lineage)
- Analyzing **audit logs** (who accessed what, permission changes)
- Monitoring **billing and usage** (DBU consumption, cost analysis)
- Tracking **compute resources** (cluster usage, warehouse metrics)
- Reviewing **job execution** (run history, success rates, failures)
- Analyzing **query performance** (slow queries, warehouse utilization)

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| System Tables | [5-system-tables.md](5-system-tables.md) | Lineage, audit, billing, compute, jobs, query history |
| Volumes | [6-volumes.md](6-volumes.md) | Volume file operations, permissions, best practices |

## Quick Start

### Volume File Operations (MCP Tools)

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

### Enable System Tables Access

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

## MCP Tool Integration

Use `mcp__databricks__execute_sql` for system table queries:

```python
# Query lineage
mcp__databricks__execute_sql(
    sql_query="""
        SELECT source_table_full_name, target_table_full_name
        FROM system.access.table_lineage
        WHERE event_date >= current_date() - 7
    """,
    catalog="system"
)
```

## Best Practices

1. **Filter by date** - System tables can be large; always use date filters
2. **Use appropriate retention** - Check your workspace's retention settings
3. **Grant minimal access** - System tables contain sensitive metadata
4. **Schedule reports** - Create scheduled queries for regular monitoring

## Resources

- [Unity Catalog System Tables](https://docs.databricks.com/administration-guide/system-tables/)
- [Audit Log Reference](https://docs.databricks.com/administration-guide/account-settings/audit-logs.html)
