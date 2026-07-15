# System Tables

Comprehensive reference for Unity Catalog system tables: lineage, audit, billing, compute, jobs, and metadata.

## Overview

System tables are read-only tables in the `system` catalog providing operational data about your Databricks account.

| Schema | Purpose |
|--------|---------|
| `system.access` | Audit logs, lineage tracking |
| `system.billing` | Usage and cost data |
| `system.compute` | Clusters, warehouses, node metrics |
| `system.lakeflow` | Jobs and pipelines |
| `system.query` | Query history and performance |
| `system.storage` | Storage metrics and predictive IO |
| `system.information_schema` | Metadata about UC objects |

---

## Enable System Schemas

System schemas must be enabled before querying.

**SQL:**
```sql
-- Check available system schemas
SELECT * FROM system.information_schema.schemata
WHERE catalog_name = 'system';
```

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

# List system schemas and their state
for schema in w.system_schemas.list(metastore_id="your-metastore-id"):
    print(f"{schema.schema}: {schema.state}")

# Enable a system schema
w.system_schemas.enable(
    metastore_id="your-metastore-id",
    schema_name="access"
)
```

**CLI:**
```bash
# List system schemas
databricks system-schemas list --metastore-id your-metastore-id

# Enable system schema
databricks system-schemas enable --metastore-id your-metastore-id \
    --schema-name access
```

---

## Access Schema (Audit & Lineage)

### system.access.audit

Audit logs for all Unity Catalog operations.

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `event_date` | DATE | Partition key - always filter on this |
| `event_time` | TIMESTAMP | When the event occurred |
| `workspace_id` | BIGINT | Workspace where event occurred |
| `user_identity` | STRUCT | User email, IP, session info |
| `action_name` | STRING | Operation performed |
| `request_params` | MAP | Request parameters |
| `response` | STRUCT | Response status and error |
| `source_ip_address` | STRING | Client IP address |

**Common Queries:**

```sql
-- Recent table access events
SELECT
    event_time,
    user_identity.email AS user_email,
    action_name,
    request_params.full_name_arg AS table_name,
    response.status_code
FROM system.access.audit
WHERE event_date >= current_date() - 7
  AND action_name IN ('getTable', 'createTable', 'deleteTable')
ORDER BY event_time DESC
LIMIT 100;

-- Permission changes in last 30 days
SELECT
    event_time,
    user_identity.email AS changed_by,
    action_name,
    request_params.securable_type AS object_type,
    request_params.securable_full_name AS object_name,
    request_params.changes AS permission_changes
FROM system.access.audit
WHERE event_date >= current_date() - 30
  AND action_name IN ('updatePermissions', 'grantPermission', 'revokePermission')
ORDER BY event_time DESC;

-- Failed access attempts (security monitoring)
SELECT
    event_time,
    user_identity.email AS user_email,
    source_ip_address,
    action_name,
    request_params.full_name_arg AS resource,
    response.error_message
FROM system.access.audit
WHERE event_date >= current_date() - 7
  AND response.status_code != '200'
ORDER BY event_time DESC;

-- Most active users by query count
SELECT
    user_identity.email AS user_email,
    COUNT(*) AS query_count,
    COUNT(DISTINCT DATE(event_time)) AS active_days
FROM system.access.audit
WHERE event_date >= current_date() - 30
  AND action_name = 'commandSubmit'
GROUP BY user_identity.email
ORDER BY query_count DESC
LIMIT 20;

-- Catalog/schema creation events
SELECT
    event_time,
    user_identity.email AS created_by,
    action_name,
    request_params.name AS object_name,
    request_params.catalog_name
FROM system.access.audit
WHERE event_date >= current_date() - 30
  AND action_name IN ('createCatalog', 'createSchema', 'deleteCatalog', 'deleteSchema')
ORDER BY event_time DESC;

-- Who created a specific table?
SELECT
    event_time,
    user_identity.email AS created_by,
    request_params
FROM system.access.audit
WHERE action_name = 'createTable'
  AND request_params.full_name_arg = 'analytics.gold.customer_360'
ORDER BY event_time DESC
LIMIT 1;

-- What tables did a user access?
SELECT DISTINCT
    request_params.full_name_arg AS table_name,
    MIN(event_time) AS first_access,
    MAX(event_time) AS last_access,
    COUNT(*) AS access_count
FROM system.access.audit
WHERE user_identity.email = 'analyst@company.com'
  AND action_name = 'getTable'
  AND event_date >= current_date() - 30
GROUP BY request_params.full_name_arg
ORDER BY access_count DESC;

-- Track sensitive table access
SELECT
    event_time,
    user_identity.email AS user_email,
    source_ip_address,
    action_name
FROM system.access.audit
WHERE event_date >= current_date() - 7
  AND request_params.full_name_arg IN (
      'analytics.gold.customers',
      'analytics.gold.financial_data'
  )
ORDER BY event_time DESC;
```

### system.access.table_lineage

Track data flow between tables.

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `source_table_full_name` | STRING | Source table (catalog.schema.table) |
| `source_type` | STRING | TABLE, VIEW, PATH |
| `target_table_full_name` | STRING | Target table |
| `target_type` | STRING | TABLE, VIEW |
| `created_by` | STRING | User who created the lineage |
| `event_time` | TIMESTAMP | When lineage was captured |

**Common Queries:**

```sql
-- Find upstream tables (what feeds this table)
SELECT DISTINCT
    source_table_full_name,
    source_type,
    MAX(event_time) AS last_updated
FROM system.access.table_lineage
WHERE target_table_full_name = 'analytics.gold.customer_360'
GROUP BY source_table_full_name, source_type
ORDER BY last_updated DESC;

-- Find downstream tables (what this table feeds)
SELECT DISTINCT
    target_table_full_name,
    target_type,
    MAX(event_time) AS last_updated
FROM system.access.table_lineage
WHERE source_table_full_name = 'analytics.bronze.raw_orders'
GROUP BY target_table_full_name, target_type
ORDER BY last_updated DESC;

-- Full lineage chain (recursive)
WITH RECURSIVE lineage AS (
    SELECT
        source_table_full_name,
        target_table_full_name,
        1 AS depth
    FROM system.access.table_lineage
    WHERE target_table_full_name = 'analytics.gold.customer_360'

    UNION ALL

    SELECT
        t.source_table_full_name,
        t.target_table_full_name,
        l.depth + 1
    FROM system.access.table_lineage t
    JOIN lineage l ON t.target_table_full_name = l.source_table_full_name
    WHERE l.depth < 10
)
SELECT DISTINCT * FROM lineage ORDER BY depth;

-- Tables with most dependencies
SELECT
    target_table_full_name,
    COUNT(DISTINCT source_table_full_name) AS upstream_count
FROM system.access.table_lineage
WHERE event_time >= current_date() - 90
GROUP BY target_table_full_name
ORDER BY upstream_count DESC
LIMIT 20;

-- Lineage with entity types
SELECT
    source_table_full_name,
    source_type,
    target_table_full_name,
    target_type,
    created_by,
    event_time
FROM system.access.table_lineage
WHERE target_table_full_name LIKE 'analytics.gold.%'
  AND event_time >= current_date() - 30;
```

### system.access.column_lineage

Column-level lineage tracking.

**Common Queries:**

```sql
-- Find column origins
SELECT
    source_table_full_name,
    source_column_name,
    target_table_full_name,
    target_column_name
FROM system.access.column_lineage
WHERE target_table_full_name = 'analytics.gold.customer_360'
  AND target_column_name = 'total_orders'
ORDER BY event_time DESC;

-- Impact analysis: what uses this column?
SELECT DISTINCT
    target_table_full_name,
    target_column_name
FROM system.access.column_lineage
WHERE source_table_full_name = 'analytics.bronze.raw_customers'
  AND source_column_name = 'email';

-- PII column tracking
SELECT
    source_table_full_name,
    source_column_name,
    target_table_full_name,
    target_column_name
FROM system.access.column_lineage
WHERE source_column_name IN ('email', 'ssn', 'phone', 'address')
ORDER BY event_time DESC;

-- Find all transformations for a column
SELECT
    source_table_full_name,
    source_column_name,
    target_table_full_name,
    target_column_name
FROM system.access.column_lineage
WHERE target_column_name = 'customer_ltv'
ORDER BY event_time DESC;
```

---

## Billing Schema

### system.billing.usage

Detailed usage records for cost analysis.

**Schema:**
| Column | Type | Description |
|--------|------|-------------|
| `usage_date` | DATE | Date of usage |
| `workspace_id` | BIGINT | Workspace ID |
| `sku_name` | STRING | Product SKU |
| `usage_quantity` | DECIMAL | Amount consumed |
| `usage_unit` | STRING | Unit of measure (DBU) |
| `cloud` | STRING | Cloud provider |
| `usage_metadata` | MAP | Additional metadata |

**Common Queries:**

```sql
-- Daily DBU consumption by SKU
SELECT
    usage_date,
    sku_name,
    SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
GROUP BY usage_date, sku_name
ORDER BY usage_date DESC, total_dbus DESC;

-- Compute vs SQL Warehouse usage
SELECT
    CASE
        WHEN sku_name LIKE '%ALL_PURPOSE%' THEN 'All-Purpose Compute'
        WHEN sku_name LIKE '%JOBS%' THEN 'Jobs Compute'
        WHEN sku_name LIKE '%SQL%' THEN 'SQL Warehouse'
        WHEN sku_name LIKE '%SERVERLESS%' THEN 'Serverless'
        ELSE 'Other'
    END AS compute_type,
    SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
GROUP BY 1
ORDER BY total_dbus DESC;

-- Daily trend with 7-day moving average
SELECT
    usage_date,
    SUM(usage_quantity) AS daily_dbus,
    AVG(SUM(usage_quantity)) OVER (
        ORDER BY usage_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d
FROM system.billing.usage
WHERE usage_date >= current_date() - 60
GROUP BY usage_date
ORDER BY usage_date;

-- Top cost drivers by cluster
SELECT
    usage_metadata.cluster_id,
    usage_metadata.cluster_name,
    SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= current_date() - 30
  AND usage_metadata.cluster_id IS NOT NULL
GROUP BY usage_metadata.cluster_id, usage_metadata.cluster_name
ORDER BY total_dbus DESC
LIMIT 20;

-- Cost by workspace with list prices
SELECT
    workspace_id,
    u.sku_name,
    SUM(usage_quantity) AS total_dbus,
    SUM(usage_quantity * p.pricing.default) AS estimated_cost
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
    ON u.sku_name = p.sku_name AND u.cloud = p.cloud
WHERE usage_date >= current_date() - 30
  AND p.price_end_time IS NULL
GROUP BY workspace_id, u.sku_name
ORDER BY estimated_cost DESC;
```

### system.billing.list_prices

Reference prices for SKUs.

```sql
-- Get current list prices
SELECT
    sku_name,
    cloud,
    currency_code,
    pricing.default AS price_per_dbu
FROM system.billing.list_prices
WHERE price_end_time IS NULL
ORDER BY sku_name;
```

---

## Compute Schema

### system.compute.clusters

Cluster configurations and metadata (historical definitions, not live state).

```sql
-- Clusters by source type
SELECT
    cluster_source,
    COUNT(*) AS cluster_count
FROM system.compute.clusters
WHERE delete_time IS NULL
GROUP BY cluster_source;

-- Clusters by Databricks Runtime version
SELECT
    dbr_version,
    COUNT(*) AS cluster_count
FROM system.compute.clusters
WHERE delete_time IS NULL
GROUP BY dbr_version
ORDER BY cluster_count DESC;

-- Recently created clusters
SELECT
    cluster_id,
    cluster_name,
    owned_by,
    dbr_version,
    cluster_source,
    create_time
FROM system.compute.clusters
WHERE delete_time IS NULL
  AND create_time >= current_date() - 30
ORDER BY create_time DESC
LIMIT 20;

-- Clusters by node type
SELECT
    worker_node_type,
    COUNT(*) AS cluster_count
FROM system.compute.clusters
WHERE delete_time IS NULL
GROUP BY worker_node_type
ORDER BY cluster_count DESC;
```

### system.compute.warehouse_events

SQL Warehouse scaling and state events.

```sql
-- Warehouse uptime analysis
SELECT
    warehouse_id,
    event_type,
    COUNT(*) AS event_count
FROM system.compute.warehouse_events
WHERE event_time >= current_date() - 7
GROUP BY warehouse_id, event_type
ORDER BY warehouse_id, event_count DESC;

-- Warehouse scaling patterns by hour
SELECT
    DATE(event_time) AS event_date,
    HOUR(event_time) AS event_hour,
    COUNT(*) AS scale_events
FROM system.compute.warehouse_events
WHERE event_type IN ('SCALED_UP', 'SCALED_DOWN')
  AND event_time >= current_date() - 30
GROUP BY DATE(event_time), HOUR(event_time)
ORDER BY event_date, event_hour;
```

---

## Lakeflow Schema (Jobs & Pipelines)

### system.lakeflow.jobs

Job definitions and configurations.

```sql
-- Jobs by trigger type
SELECT
    CASE
        WHEN trigger.schedule IS NOT NULL THEN 'Scheduled'
        WHEN trigger.file_arrival IS NOT NULL THEN 'File Arrival'
        WHEN trigger.continuous IS NOT NULL THEN 'Continuous'
        WHEN trigger.table_update IS NOT NULL THEN 'Table Update'
        ELSE 'Manual/API'
    END AS job_trigger_type,
    COUNT(*) AS job_count
FROM system.lakeflow.jobs
WHERE delete_time IS NULL
GROUP BY 1;

-- Jobs with no recent runs (potentially stale)
SELECT
    j.job_id,
    j.name,
    j.creator_user_name,
    MAX(r.period_start_time) AS last_run
FROM system.lakeflow.jobs j
LEFT JOIN system.lakeflow.job_run_timeline r
    ON j.job_id = r.job_id
WHERE j.delete_time IS NULL
GROUP BY j.job_id, j.name, j.creator_user_name
HAVING MAX(r.period_start_time) < current_date() - 30
    OR MAX(r.period_start_time) IS NULL;
```

### system.lakeflow.job_run_timeline

Job run history and performance.

```sql
-- Job success rate
SELECT
    job_id,
    COUNT(*) AS total_runs,
    SUM(CASE WHEN result_state = 'SUCCESS' THEN 1 ELSE 0 END) AS successful_runs,
    ROUND(100.0 * SUM(CASE WHEN result_state = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 2) AS success_rate
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_date() - 30
GROUP BY job_id
HAVING COUNT(*) >= 5
ORDER BY success_rate ASC;

-- Average job duration by day
SELECT
    DATE(period_start_time) AS run_date,
    job_id,
    AVG(run_duration_seconds / 60) AS avg_duration_minutes
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_date() - 30
  AND run_duration_seconds IS NOT NULL
GROUP BY DATE(period_start_time), job_id
ORDER BY run_date DESC;

-- Failed jobs in last 24 hours
SELECT
    job_id,
    run_id,
    period_start_time,
    result_state,
    termination_code
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_timestamp() - INTERVAL 24 HOURS
  AND result_state IN ('FAILED', 'TIMEDOUT', 'CANCELED')
ORDER BY period_start_time DESC;

-- Job run duration percentiles
SELECT
    job_id,
    PERCENTILE(run_duration_seconds / 60, 0.5) AS p50_minutes,
    PERCENTILE(run_duration_seconds / 60, 0.9) AS p90_minutes,
    PERCENTILE(run_duration_seconds / 60, 0.99) AS p99_minutes
FROM system.lakeflow.job_run_timeline
WHERE period_start_time >= current_date() - 30
  AND run_duration_seconds IS NOT NULL
GROUP BY job_id;
```

### system.lakeflow.pipeline_events

DLT/SDP pipeline execution events.

```sql
-- Pipeline success rate
SELECT
    pipeline_id,
    COUNT(*) AS total_updates,
    SUM(CASE WHEN event_type = 'update_success' THEN 1 ELSE 0 END) AS successful,
    ROUND(100.0 * SUM(CASE WHEN event_type = 'update_success' THEN 1 ELSE 0 END) / COUNT(*), 2) AS success_rate
FROM system.lakeflow.pipeline_events
WHERE timestamp >= current_date() - 30
  AND event_type IN ('update_success', 'update_failed')
GROUP BY pipeline_id;

-- Recent pipeline failures
SELECT
    pipeline_id,
    pipeline_name,
    timestamp,
    event_type,
    details
FROM system.lakeflow.pipeline_events
WHERE timestamp >= current_date() - 7
  AND event_type = 'update_failed'
ORDER BY timestamp DESC;
```

---

## Query Schema

### system.query.history

Query execution history and performance.

```sql
-- Slowest queries in last 7 days
SELECT
    statement_id,
    executed_by,
    compute.warehouse_id AS warehouse_id,
    total_duration_ms / 1000 AS duration_seconds,
    produced_rows,
    LEFT(statement_text, 100) AS query_preview
FROM system.query.history
WHERE start_time >= current_date() - 7
  AND execution_status = 'FINISHED'
ORDER BY total_duration_ms DESC
LIMIT 20;

-- Query volume by hour
SELECT
    DATE(start_time) AS query_date,
    HOUR(start_time) AS query_hour,
    COUNT(*) AS query_count,
    AVG(total_duration_ms / 1000) AS avg_duration_seconds
FROM system.query.history
WHERE start_time >= current_date() - 7
GROUP BY DATE(start_time), HOUR(start_time)
ORDER BY query_date DESC, query_hour;

-- Most active query users
SELECT
    executed_by,
    COUNT(*) AS query_count,
    SUM(total_duration_ms) / 1000 / 60 AS total_minutes,
    AVG(total_duration_ms) / 1000 AS avg_seconds
FROM system.query.history
WHERE start_time >= current_date() - 30
GROUP BY executed_by
ORDER BY query_count DESC
LIMIT 20;

-- Failed queries analysis
SELECT
    executed_by,
    error_message,
    COUNT(*) AS failure_count
FROM system.query.history
WHERE start_time >= current_date() - 7
  AND execution_status = 'FAILED'
GROUP BY executed_by, error_message
ORDER BY failure_count DESC
LIMIT 20;

-- Queries by statement type
SELECT
    statement_type,
    COUNT(*) AS query_count,
    AVG(total_duration_ms / 1000) AS avg_duration_seconds,
    SUM(produced_rows) AS total_rows
FROM system.query.history
WHERE start_time >= current_date() - 7
GROUP BY statement_type
ORDER BY query_count DESC;
```

---

## Information Schema

Metadata about Unity Catalog objects.

```sql
-- List all catalogs
SELECT catalog_name, catalog_owner, comment, created, created_by
FROM system.information_schema.catalogs
ORDER BY catalog_name;

-- List all schemas in a catalog
SELECT schema_name, schema_owner, comment, created
FROM system.information_schema.schemata
WHERE catalog_name = 'analytics'
ORDER BY schema_name;

-- List all tables
SELECT
    table_catalog,
    table_schema,
    table_name,
    table_type,
    comment
FROM system.information_schema.tables
WHERE table_catalog = 'analytics'
  AND table_schema = 'gold'
ORDER BY table_name;

-- Column details for a table
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default,
    comment
FROM system.information_schema.columns
WHERE table_catalog = 'analytics'
  AND table_schema = 'gold'
  AND table_name = 'customers'
ORDER BY ordinal_position;

-- Find tables by column name (data discovery)
SELECT DISTINCT
    table_catalog,
    table_schema,
    table_name
FROM system.information_schema.columns
WHERE column_name LIKE '%email%'
   OR column_name LIKE '%customer_id%';

-- Tables without comments (governance gap)
SELECT
    table_catalog,
    table_schema,
    table_name
FROM system.information_schema.tables
WHERE comment IS NULL
  AND table_catalog NOT IN ('system', 'hive_metastore')
ORDER BY table_catalog, table_schema, table_name;

-- Permission audit: who has access to what
SELECT
    grantee,
    table_catalog,
    table_schema,
    table_name,
    privilege_type
FROM system.information_schema.table_privileges
WHERE table_catalog = 'analytics'
ORDER BY table_schema, table_name, grantee;

-- Schema privileges
SELECT
    grantee,
    catalog_name,
    schema_name,
    privilege_type
FROM system.information_schema.schema_privileges
WHERE catalog_name = 'analytics'
ORDER BY schema_name, grantee;

-- Find all volumes
SELECT
    volume_catalog,
    volume_schema,
    volume_name,
    volume_type,
    storage_location,
    comment
FROM system.information_schema.volumes
WHERE volume_catalog = 'analytics';

-- Find all functions
SELECT
    routine_catalog,
    routine_schema,
    routine_name,
    routine_type,
    data_type AS return_type
FROM system.information_schema.routines
WHERE routine_catalog = 'analytics';

-- Share details
SELECT * FROM system.information_schema.shares;

-- Share objects
SELECT
    share_name,
    name AS object_name,
    data_object_type,
    shared_as
FROM system.information_schema.shared_data_objects
WHERE share_name = 'customer_insights';

-- Recipient grants
SELECT
    share_name,
    recipient_name,
    privilege
FROM system.information_schema.share_recipients;
```

---

## External Lineage

Track lineage to external systems.

**Python SDK:**
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import (
    CreateRequestExternalLineage,
    ExternalLineageObject,
    LineageDirection
)

w = WorkspaceClient()

# Create external lineage relationship
w.external_lineage.create_external_lineage_relationship(
    external_lineage_relationship=CreateRequestExternalLineage(
        target=ExternalLineageObject(
            table_full_name="analytics.bronze.raw_orders"
        ),
        source=ExternalLineageObject(
            external_system="salesforce",
            external_object="Account"
        )
    )
)

# List external lineage
lineage = w.external_lineage.list_external_lineage_relationships(
    object_info=ExternalLineageObject(
        table_full_name="analytics.bronze.raw_orders"
    ),
    lineage_direction=LineageDirection.UPSTREAM
)
for rel in lineage:
    print(f"Source: {rel.source}")
```

**CLI:**
```bash
# Create external lineage
databricks external-lineage create-external-lineage-relationship --json '{
    "source": {
        "external_system": "salesforce",
        "external_object": "Account"
    },
    "target": {
        "table_full_name": "analytics.bronze.raw_orders"
    }
}'

# List external lineage
databricks external-lineage list-external-lineage-relationships --json '{
    "object_info": {
        "table_full_name": "analytics.bronze.raw_orders"
    },
    "lineage_direction": "UPSTREAM"
}'
```

---

## Best Practices

### Query Performance

1. **Always filter by date partitions** - System tables are partitioned by date
```sql
WHERE event_date >= current_date() - 30  -- Good
WHERE event_time >= '2024-01-01'         -- Slower (scans all partitions)
```

2. **Use LIMIT for exploration** - System tables can be very large
```sql
LIMIT 100  -- Always add for exploratory queries
```

3. **Create views for common queries** - Avoid repeating complex logic
```sql
CREATE VIEW analytics.governance.daily_audit_summary AS
SELECT ...
```

4. **Schedule aggregation jobs** - Pre-aggregate for dashboards
```sql
CREATE TABLE analytics.monitoring.daily_usage_summary AS
SELECT usage_date, sku_name, SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
GROUP BY usage_date, sku_name;
```

### Retention Periods

| System Table | Retention |
|--------------|-----------|
| Audit logs | 365 days |
| Billing usage | 365 days |
| Query history | 30 days |
| Lineage | 365 days |
| Compute events | 30 days |

### Access Control

```sql
-- Grant access to monitoring team
GRANT SELECT ON SCHEMA system.access TO `monitoring_team`;
GRANT SELECT ON SCHEMA system.billing TO `finance_team`;
GRANT SELECT ON SCHEMA system.query TO `platform_team`;
```

### Governance Tips

1. **Enable system tables early** in your UC setup
2. **Use column lineage** for sensitive data tracking
3. **Register external sources** for complete visibility
4. **Retain audit logs** for compliance (typically 1-7 years)
5. **Monitor failed access** for security threats
6. **Automate alerts** for sensitive operations
