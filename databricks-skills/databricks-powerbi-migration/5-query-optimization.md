# Query Access Optimization (Step 11)

Step 11 of the migration workflow: assess each KPI's query complexity and table characteristics to choose the optimal serving strategy.

Produce `reference/query_optimization_plan.md` before building metric views.

---

## Assessment Dimensions

For each KPI or domain, evaluate:

| Factor | How to Assess | Threshold |
|--------|---------------|-----------|
| **Table size** | `DESCRIBE DETAIL <table>` — check `sizeInBytes` and `numFiles` | < 100 GB = small, 100 GB–1 TB = medium, > 1 TB = large |
| **Row count** | `SELECT COUNT(*) FROM <table>` or estimate from DESCRIBE DETAIL | < 100M = small, 100M–1B = medium, > 1B = large |
| **Join count** | Count the number of tables joined per KPI query | 0–2 = simple, 3–5 = moderate, 6+ = complex |
| **Aggregation complexity** | Window functions, CASE expressions, nested aggregations | Simple SUM/COUNT = low, window/CASE = medium, nested = high |
| **Grain mismatch** | Compare fact table grain to report grain | Same grain = no issue, different grain = pre-aggregation needed |
| **Filter selectivity** | Typical filter narrows result to what % of table? | > 50% = low selectivity, < 10% = high selectivity |
| **Refresh frequency** | How often does the source data change? | Real-time, hourly, daily, weekly |

**Collect table sizing data** using `DESCRIBE DETAIL <table>` for each candidate table. When assessing multiple tables, batch them with `execute_sql_multi` or use parallel subagents — see [9-subagent-patterns.md](9-subagent-patterns.md) Pattern D.

---

## Query Complexity Scoring

Assign a score to determine the serving strategy:

```
Score = table_size_score + join_score + aggregation_score + grain_score

table_size_score: small=0, medium=2, large=4
join_score:       0-2 joins=0, 3-5=1, 6+=2
aggregation_score: simple=0, medium=1, high=2
grain_score:      same=0, different=2
```

| Total Score | Serving Strategy |
|-------------|-----------------|
| 0–2 | Standard metric view (direct on source tables) |
| 3–5 | Materialized view with scheduled refresh |
| 6+ | Gold-layer aggregate table + metric view on top |

---

## Strategy 1: Standard Metric View

For simple KPIs on small/medium tables with few joins. The metric view queries source tables directly at runtime.

```sql
CREATE OR REPLACE VIEW <catalog>.<schema>.sales_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  source: <catalog>.<schema>.sales_fact
  measures:
    - name: Total Sales
      expr: SUM(total_amount)
$$;
```

---

## Strategy 2: Materialized View with Incremental Refresh

For complex KPIs or medium/large tables where pre-computing aggregations significantly reduces query time. Databricks automatically manages incremental refresh.

```sql
CREATE OR REPLACE MATERIALIZED VIEW <catalog>.<schema>.monthly_sales_agg
AS
SELECT
  date_trunc('month', order_date) AS order_month,
  region,
  product_category,
  SUM(total_amount) AS total_sales,
  COUNT(1) AS order_count,
  COUNT(DISTINCT customer_id) AS unique_customers
FROM <catalog>.<schema>.sales_fact
GROUP BY ALL;

ALTER MATERIALIZED VIEW <catalog>.<schema>.monthly_sales_agg
  SCHEDULE CRON '0 2 * * *' AT TIME ZONE 'UTC';
```

Then point the metric view at the materialized view:

```sql
CREATE OR REPLACE VIEW <catalog>.<schema>.sales_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  source: <catalog>.<schema>.monthly_sales_agg
  dimensions:
    - name: Order Month
      expr: order_month
    - name: Region
      expr: region
  measures:
    - name: Total Sales
      expr: SUM(total_sales)
    - name: Avg Order Value
      expr: SUM(total_sales) / NULLIF(SUM(order_count), 0)
$$;
```

---

## Strategy 3: Gold-Layer Aggregate Table

For very large tables (> 1 TB) or when the grain mismatch is severe (e.g., transaction-level fact table but report needs monthly aggregates). Build a dedicated gold-layer table with a pipeline for incremental loads.

```sql
CREATE TABLE <catalog>.<schema>.gold_monthly_sales (
  order_month DATE,
  region STRING,
  product_category STRING,
  total_sales DECIMAL(18,2),
  order_count BIGINT,
  unique_customers BIGINT,
  _etl_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
USING DELTA
CLUSTER BY (order_month, region);
```

Use `spark-declarative-pipelines` skill to maintain incremental refresh, then build metric views on top of the gold table.

---

## Grain Analysis

When the fact table grain is finer than the report grain, pre-aggregation is essential:

| Fact Table Grain | Report Grain | Action |
|-----------------|--------------|--------|
| Transaction-level | Daily | Materialized view with `date_trunc('day', ...)` |
| Transaction-level | Monthly | Gold-layer aggregate or materialized view |
| Daily | Monthly | Materialized view with `date_trunc('month', ...)` |
| Same | Same | Standard metric view (no pre-aggregation) |

---

## Decision Matrix

| Condition | Serving Strategy |
|-----------|-----------------|
| Simple aggregation, table < 100 GB, few joins | Standard metric view |
| Complex joins or expensive aggregation, table 100 GB–1 TB | Materialized view with scheduled refresh |
| Very large table (> 1 TB) or grain mismatch requiring pre-aggregation | Gold-layer aggregate table + metric view on top |
| Mixed: some KPIs simple, some complex | Split across strategies per domain |

---

## Output: reference/query_optimization_plan.md

```markdown
## Query Optimization Plan

### Domain: Sales
| KPI | Score | Strategy | Rationale |
|-----|-------|----------|-----------|
| Total Sales | 2 | Standard metric view | Simple SUM, table < 50 GB |
| Sales YoY Growth | 5 | Materialized view | Window function over 2 years, 200 GB table |
| Customer Lifetime Value | 7 | Gold-layer aggregate | 5-table join, 1.2 TB fact table, transaction-to-monthly grain |

### Materialized Views to Create
1. `monthly_sales_agg` — monthly pre-aggregation for time-series KPIs
   - Schedule: daily at 2:00 AM UTC
   - Source: sales_fact (200 GB)
   - Estimated refresh time: ~15 min

### Gold-Layer Tables to Create
1. `gold_customer_ltv` — customer lifetime value aggregate
   - Pipeline: use spark-declarative-pipelines skill
   - Refresh: daily incremental via SDP
```
