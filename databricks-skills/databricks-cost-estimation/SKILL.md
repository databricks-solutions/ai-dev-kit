---
name: databricks-cost-estimation
description: "Estimate and analyze Databricks costs using system billing tables. Use when the user asks about cost estimation, billing analysis, DBU usage, cost trends, chargeback, or spending breakdowns."
---

# Databricks Cost Estimation

Estimate Databricks costs using `system.billing.usage` and `system.billing.list_prices` system tables. Use when the user asks about DBU consumption, dollar cost estimates, cost trends, chargeback, or billing analysis.

**Trigger phrases:** cost estimation, billing analysis, DBU usage, cost trend, chargeback, how much is this costing, spending breakdown, cost by workspace, cost by job

## Prerequisites

- System tables must be enabled (account-level admin)
- User needs `SELECT` on `system.billing.usage` and `system.billing.list_prices`
- Execute queries via `CallMcpTool(server: "user-databricks", toolName: "execute_sql")`

## Quick Start

### 1. Top SKUs by DBU (last 30 days)

```sql
SELECT
  sku_name,
  billing_origin_product,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY sku_name, billing_origin_product
ORDER BY total_dbus DESC
LIMIT 10
```

### 2. Estimated Dollar Cost by Product

```sql
SELECT
  u.billing_origin_product,
  ROUND(SUM(u.usage_quantity), 2) AS total_dbus,
  ROUND(SUM(u.usage_quantity * COALESCE(p.pricing.effective_list.default, p.pricing.default)), 2) AS estimated_cost_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY u.billing_origin_product
ORDER BY estimated_cost_usd DESC
LIMIT 10
```

## Key Tables

### system.billing.usage

| Column | Type | Description |
|---|---|---|
| `account_id` | STRING | Account ID |
| `workspace_id` | STRING | Workspace ID |
| `record_id` | STRING | Unique usage record ID |
| `sku_name` | STRING | SKU name (e.g. `ENTERPRISE_JOBS_SERVERLESS_COMPUTE_US_EAST_N_VIRGINIA`) |
| `cloud` | STRING | `AWS`, `AZURE`, or `GCP` |
| `usage_start_time` | TIMESTAMP | Start time (UTC) |
| `usage_end_time` | TIMESTAMP | End time (UTC) |
| `usage_date` | DATE | Date of usage (use for fast aggregation) |
| `custom_tags` | MAP\<STRING, STRING\> | User-applied tags (compute resource tags, job tags) |
| `usage_unit` | STRING | Unit of measurement (e.g. `DBU`) |
| `usage_quantity` | DECIMAL(38,18) | Quantity consumed |
| `usage_metadata` | STRUCT | System metadata — access fields with **dot notation**: `usage_metadata.job_id`, `usage_metadata.cluster_id`, etc. |
| `identity_metadata` | STRUCT | Identity info — `identity_metadata.run_as`, `.created_by`, `.owned_by` |
| `record_type` | STRING | `ORIGINAL`, `RETRACTION`, or `RESTATEMENT` |
| `ingestion_date` | DATE | Date record was ingested |
| `billing_origin_product` | STRING | Product that originated usage (see values below) |
| `product_features` | STRUCT | Product feature details — `product_features.is_serverless`, `.jobs_tier`, `.sql_tier`, etc. |
| `usage_type` | STRING | `COMPUTE_TIME`, `STORAGE_SPACE`, `NETWORK_BYTE`, `TOKEN`, `GPU_TIME`, `API_OPERATION`, `STEP`, `ANSWER`, `PROCESSED_GB`, `ACTIVE_TIME`, `JUDGE_REQUEST` |

#### usage_metadata STRUCT fields

Access with dot notation (NOT colon/JSON notation):

- `usage_metadata.cluster_id` — Cluster ID
- `usage_metadata.job_id` — Job ID
- `usage_metadata.job_name` — Job name
- `usage_metadata.job_run_id` — Job run ID
- `usage_metadata.warehouse_id` — SQL warehouse ID
- `usage_metadata.notebook_id` — Notebook ID
- `usage_metadata.notebook_path` — Notebook path
- `usage_metadata.dlt_pipeline_id` — DLT pipeline ID
- `usage_metadata.endpoint_name` — Model serving endpoint name
- `usage_metadata.endpoint_id` — Model serving endpoint ID
- `usage_metadata.instance_pool_id` — Instance pool ID
- `usage_metadata.node_type` — Node type
- `usage_metadata.app_id` — Databricks App ID
- `usage_metadata.app_name` — Databricks App name
- `usage_metadata.metastore_id` — Metastore ID
- `usage_metadata.budget_policy_id` — Budget policy ID

> **CRITICAL:** `usage_metadata` is a STRUCT. Use `usage_metadata.job_id` (dot notation). Do NOT use `usage_metadata:job_id` (colon/JSON notation) — that will error.

#### billing_origin_product values

`AGENT_BRICKS`, `AGENT_EVALUATION`, `AI_FUNCTIONS`, `AI_GATEWAY`, `AI_RUNTIME`, `ALL_PURPOSE`, `APPS`, `BASE_ENVIRONMENTS`, `CLEAN_ROOM`, `DATABASE`, `DATA_CLASSIFICATION`, `DATA_QUALITY_MONITORING`, `DATA_SHARING`, `DEFAULT_STORAGE`, `DLT`, `FINE_GRAINED_ACCESS_CONTROL`, `FOUNDATION_MODEL_TRAINING`, `INTERACTIVE`, `JOBS`, `LAKEBASE`, `LAKEFLOW_CONNECT`, `LAKEHOUSE_MONITORING`, `MODEL_SERVING`, `NETWORKING`, `ONLINE_TABLES`, `PREDICTIVE_OPTIMIZATION`, `SQL`, `SUPERVISOR_AGENT`, `VECTOR_SEARCH`

### system.billing.list_prices

| Column | Type | Description |
|---|---|---|
| `account_id` | STRING | Account ID |
| `price_start_time` | TIMESTAMP | When price became effective (UTC) |
| `price_end_time` | TIMESTAMP | When price stopped being effective (NULL = current) |
| `sku_name` | STRING | SKU name (join key with usage) |
| `cloud` | STRING | `AWS`, `AZURE`, or `GCP` |
| `currency_code` | STRING | Currency (e.g. `USD`) |
| `usage_unit` | STRING | Unit (e.g. `DBU`) |
| `pricing` | STRUCT | Pricing info (see access pattern below) |

#### pricing STRUCT access

The `pricing` column is a STRUCT with nested fields. Access with dot notation:

- `pricing.default` — Published list price (always present, use for long-term estimates)
- `pricing.promotional.default` — Temporary promotional price (may be NULL)
- `pricing.effective_list.default` — Effective list price (resolves list vs promotional)

**Recommended pattern for cost estimation:**

```sql
COALESCE(p.pricing.effective_list.default, p.pricing.default)
```

This uses the effective list price when available, falling back to the default list price.

## Standard Join Pattern

Always join usage to list_prices with these conditions:

```sql
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL   -- current prices only
```

Use `LEFT JOIN` so usage rows without a matching price still appear (with NULL cost).

## Common Patterns

### Top SKUs by Estimated Cost (30 days)

```sql
SELECT
  u.sku_name,
  SUM(u.usage_quantity) AS total_dbus,
  SUM(u.usage_quantity * COALESCE(p.pricing.effective_list.default, p.pricing.default)) AS estimated_cost_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY u.sku_name
ORDER BY estimated_cost_usd DESC
LIMIT 10
```

### Daily Cost Trend

```sql
SELECT
  u.usage_date,
  SUM(u.usage_quantity * COALESCE(p.pricing.effective_list.default, p.pricing.default)) AS daily_cost
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY u.usage_date
ORDER BY u.usage_date
```

### Cost by Workspace

```sql
SELECT
  u.workspace_id,
  SUM(u.usage_quantity) AS total_dbus,
  SUM(u.usage_quantity * COALESCE(p.pricing.effective_list.default, p.pricing.default)) AS estimated_cost_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY u.workspace_id
ORDER BY estimated_cost_usd DESC
LIMIT 10
```

### Cost by Job

```sql
SELECT
  usage_metadata.job_id,
  usage_metadata.job_name,
  SUM(u.usage_quantity) AS total_dbus,
  SUM(u.usage_quantity * COALESCE(p.pricing.effective_list.default, p.pricing.default)) AS estimated_cost_usd
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.billing_origin_product = 'JOBS'
  AND u.usage_metadata.job_id IS NOT NULL
  AND u.usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY usage_metadata.job_id, usage_metadata.job_name
ORDER BY estimated_cost_usd DESC
LIMIT 10
```

### Cost by Model Serving Endpoint

```sql
SELECT
  usage_metadata.endpoint_name,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE billing_origin_product = 'MODEL_SERVING'
  AND usage_metadata.endpoint_name IS NOT NULL
  AND usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
GROUP BY usage_metadata.endpoint_name
ORDER BY total_dbus DESC
LIMIT 10
```

### Week-over-Week Cost Comparison

```sql
SELECT
  DATE_TRUNC('week', u.usage_date) AS week_start,
  SUM(u.usage_quantity * COALESCE(p.pricing.effective_list.default, p.pricing.default)) AS weekly_cost
FROM system.billing.usage u
LEFT JOIN system.billing.list_prices p
  ON u.sku_name = p.sku_name
  AND u.cloud = p.cloud
  AND u.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 8 WEEKS
GROUP BY DATE_TRUNC('week', u.usage_date)
ORDER BY week_start
```

### Tag-Based Chargeback

```sql
WITH tagged_usage AS (
  SELECT
    u.sku_name, u.cloud, u.usage_unit, u.usage_quantity,
    tag.key AS tag_key, tag.value AS tag_value
  FROM system.billing.usage u
  LATERAL VIEW EXPLODE(u.custom_tags) tag
  WHERE u.usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
    AND SIZE(u.custom_tags) > 0
)
SELECT
  t.tag_key,
  t.tag_value,
  SUM(t.usage_quantity * COALESCE(p.pricing.effective_list.default, p.pricing.default)) AS estimated_cost_usd
FROM tagged_usage t
LEFT JOIN system.billing.list_prices p
  ON t.sku_name = p.sku_name
  AND t.cloud = p.cloud
  AND t.usage_unit = p.usage_unit
  AND p.price_end_time IS NULL
GROUP BY t.tag_key, t.tag_value
ORDER BY estimated_cost_usd DESC
LIMIT 20
```

> **Note:** `custom_tags` is a `MAP<STRING, STRING>`. Use `LATERAL VIEW EXPLODE()` in a CTE, then join to list_prices in the outer query. Direct `EXPLODE` in a `SELECT` with `JOIN` causes parse errors.

### Cost by User (identity_metadata)

```sql
SELECT
  identity_metadata.run_as AS user_email,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= CURRENT_DATE() - INTERVAL 30 DAYS
  AND identity_metadata.run_as IS NOT NULL
GROUP BY identity_metadata.run_as
ORDER BY total_dbus DESC
LIMIT 10
```

## Cost Optimization Recommendations

When presenting cost data, suggest these optimizations based on what the data shows:

| Finding | Recommendation |
|---|---|
| High ALL_PURPOSE DBUs | Migrate interactive workloads to Jobs (lower DBU rate) or Serverless |
| High SQL warehouse cost | Right-size warehouse, use Serverless SQL, enable auto-stop |
| Expensive jobs running frequently | Optimize job code, use Photon, consider Serverless Jobs |
| MODEL_SERVING dominates cost | Review endpoint scaling (min instances), use provisioned throughput for steady traffic |
| VECTOR_SEARCH high cost | Evaluate index size and query patterns, consider storage-optimized endpoints |
| No custom_tags | Recommend tagging strategy for chargeback visibility |
| Single workspace dominates | Investigate workloads in that workspace, consider workload isolation |
| Weekend cost same as weekday | Ensure auto-scaling/auto-stop is configured, pause non-production workloads |

## Important Notes

- **List prices are estimates.** Actual invoiced amounts may differ due to committed-use discounts, enterprise agreements, or promotional pricing. These queries use published list prices, not contract prices.
- **`price_end_time IS NULL`** filters to current prices. For historical cost analysis, use `u.usage_start_time BETWEEN p.price_start_time AND COALESCE(p.price_end_time, CURRENT_TIMESTAMP())`.
- **`record_type`** — Filter to `record_type = 'ORIGINAL'` if you want to exclude corrections. By default, include all record types for the most accurate totals (restatements replace retracted records).
- **Latency** — System tables have up to 24-hour ingestion delay. `ingestion_date` shows when data arrived.
- **Unmatched usage rows** — Some usage records (e.g. `usage_unit = 'GB'` for storage) have no matching row in `list_prices`. The `LEFT JOIN` handles this gracefully — those rows appear with NULL cost. Filter to `usage_unit = 'DBU'` if you only want DBU-priced usage.
