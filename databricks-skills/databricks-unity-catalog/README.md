# Databricks Unity Catalog

Unity Catalog system tables, volumes, access controls (ACLs), and FGAC policy governance (column masks, row filters, governed tags).

## Overview

This skill provides guidance for working with Unity Catalog system tables, volumes, access controls, and Fine-Grained Access Control (FGAC) policies. It activates when users query system tables (audit, lineage, billing, compute, jobs, query history), perform volume file operations (upload, download, list files), manage UC permissions (GRANT/REVOKE), or manage FGAC policies (column masks, row filters, governed tags, masking UDFs).

## What's Included

```
databricks-unity-catalog/
├── SKILL.md
├── 5-system-tables.md
├── 6-volumes.md
├── 7-fgac-overview.md
├── 8-fgac-sql-generation.md
├── 9-fgac-sdk-and-tools.md
└── 10-uc-acls.md
```

## Key Topics

- System table schemas: `system.access` (audit, lineage), `system.billing` (usage, cost), `system.compute` (clusters, warehouses), `system.lakeflow` (jobs, pipelines), `system.query` (query history), `system.storage` (storage metrics)
- Enabling system schemas and granting access with SQL
- Table and column-level lineage queries
- Audit log analysis: permission changes, data access tracking
- Billing and DBU consumption monitoring by workspace and SKU
- Volume types: managed vs. external
- Volume file operations: list, upload, download, create directories
- Volume path format: `/Volumes/<catalog>/<schema>/<volume>/<path>`
- Best practices: date filtering on large system tables, minimal access grants, scheduled monitoring reports

## When to Use

- Querying system tables for audit, lineage, billing, or compute metrics
- Uploading, downloading, or listing files in Unity Catalog Volumes
- Analyzing who accessed specific tables or changed permissions
- Monitoring DBU consumption and cost across workspaces
- Tracking table dependencies and column-level lineage
- Reviewing job execution history and query performance
- Setting up governance and access controls for system data
- Managing FGAC policies: column masks, row filters, governed tags
- Analyzing FGAC coverage gaps and policy quotas
- Granting and revoking UC permissions (ACLs)

## Related Skills

- [Spark Declarative Pipelines](../spark-declarative-pipelines/) -- for pipelines that write to Unity Catalog tables
- [Databricks Jobs](../databricks-jobs/) -- for job execution data visible in system tables
- [Synthetic Data Generation](../synthetic-data-generation/) -- for generating data stored in Unity Catalog Volumes
- [AI/BI Dashboards](../aibi-dashboards/) -- for building dashboards on top of Unity Catalog data

## Resources

- [Unity Catalog System Tables](https://docs.databricks.com/administration-guide/system-tables/)
- [Audit Log Reference](https://docs.databricks.com/administration-guide/account-settings/audit-logs.html)
- [Unity Catalog Volumes](https://docs.databricks.com/en/connect/unity-catalog/volumes.html)
