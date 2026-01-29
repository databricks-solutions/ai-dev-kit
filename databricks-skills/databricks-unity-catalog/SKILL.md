---
name: databricks-unity-catalog
description: "Comprehensive Unity Catalog governance skill covering object management, access control, storage connections, metadata, system tables, and data sharing. Use when (1) creating, altering, or dropping catalogs, schemas, tables, volumes, or functions, (2) granting or revoking permissions, row-level security, or column masking, (3) configuring storage credentials, external locations, or Lakehouse Federation connections, (4) managing tags, comments, quality monitors, or naming conventions, (5) querying system tables for lineage, audit logs, billing, compute, jobs, or query history, (6) setting up Delta Sharing with shares, recipients, and providers, (7) any Unity Catalog governance, security, or metadata task."
---

# Unity Catalog

Governance, security, and metadata management for Databricks Unity Catalog.

## Reference Files

| Topic | File | Use When |
|-------|------|----------|
| Object Management | [1-object-management.md](1-object-management.md) | Creating/altering/dropping catalogs, schemas, tables, volumes, functions |
| Access Control | [2-access-control.md](2-access-control.md) | Granting permissions, row filters, column masks, service principals |
| Storage & Connections | [3-storage-connections.md](3-storage-connections.md) | Storage credentials, external locations, Lakehouse Federation |
| Governance & Metadata | [4-governance-metadata.md](4-governance-metadata.md) | Tags, comments, quality monitors, naming conventions |
| System Tables | [5-system-tables.md](5-system-tables.md) | Lineage, audit logs, billing, compute, jobs, query history |
| Data Sharing | [6-data-sharing.md](6-data-sharing.md) | Delta Sharing, shares, recipients, providers, clean rooms |

## Quick Start

### Create Catalog + Schema + Table

```sql
-- Catalog
CREATE CATALOG IF NOT EXISTS my_catalog
COMMENT 'Production data catalog';

-- Schema (medallion layers)
CREATE SCHEMA my_catalog.bronze COMMENT 'Raw data';
CREATE SCHEMA my_catalog.silver COMMENT 'Cleaned data';
CREATE SCHEMA my_catalog.gold COMMENT 'Business aggregates';

-- Table
CREATE TABLE my_catalog.bronze.raw_orders (
    order_id BIGINT,
    customer_id BIGINT,
    amount DECIMAL(10, 2),
    order_date DATE
)
USING DELTA
COMMENT 'Raw orders from source';
```

### Grant Access

```sql
GRANT USE CATALOG ON CATALOG my_catalog TO `data_engineers`;
GRANT USE SCHEMA ON SCHEMA my_catalog.bronze TO `data_engineers`;
GRANT SELECT ON ALL TABLES IN SCHEMA my_catalog.gold TO `analysts`;
```

### Query System Tables

```sql
-- Table lineage
SELECT source_table_full_name, target_table_full_name
FROM system.access.table_lineage
WHERE event_date >= current_date() - 7;

-- Audit log
SELECT event_time, user_identity.email, action_name
FROM system.access.audit
WHERE event_date >= current_date() - 7
ORDER BY event_time DESC LIMIT 50;
```

## MCP Tool Integration

Use `mcp__databricks__execute_sql` for UC operations:

```python
# Create catalog
mcp__databricks__execute_sql(sql_query="CREATE CATALOG IF NOT EXISTS my_catalog")

# Grant permissions
mcp__databricks__execute_sql(
    sql_query="GRANT SELECT ON SCHEMA my_catalog.gold TO `analysts`"
)

# Query system tables
mcp__databricks__execute_sql(
    sql_query="SELECT * FROM system.access.audit WHERE event_date >= current_date() - 7 LIMIT 50",
    catalog="system"
)
```

## Best Practices

1. **Three-level namespace**: `catalog.schema.object` for all references
2. **Medallion architecture**: bronze (raw) / silver (cleaned) / gold (aggregated)
3. **Grant hierarchically**: USE CATALOG -> USE SCHEMA -> object privileges
4. **Use groups, not individuals**: Grant to groups, never to personal accounts
5. **Service principals for automation**: Never use personal tokens in pipelines
6. **Always filter system tables by date**: Partition key is `event_date` or `usage_date`
7. **Tags for governance**: Classify PII, confidentiality, and compliance requirements
8. **Liquid Clustering over partitioning**: Use `CLUSTER BY` instead of `PARTITIONED BY` for new tables
