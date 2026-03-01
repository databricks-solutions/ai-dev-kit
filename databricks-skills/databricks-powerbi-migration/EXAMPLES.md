# Examples: Input/Output Patterns

Concrete examples for key skill workflows. Referenced from [SKILL.md](SKILL.md) and [REFERENCE.md](REFERENCE.md).

---

## EDW-to-CDM Intermediate Mapping (Gap 1)

### Input: Power Query M Expression (from PBI model)

```m
let
    Source = Sql.Database("edw-server", "sales_db"),
    dbo_Transactions = Source{[Schema="dbo",Item="Transactions"]}[Data],
    Renamed = Table.RenameColumns(dbo_Transactions, {
        {"TransactionID", "SaleID"},
        {"AmountUSD", "TotalAmount"},
        {"CreatedAt", "OrderDate"}
    }),
    Selected = Table.SelectColumns(Renamed, {"SaleID", "TotalAmount", "OrderDate", "CustomerID"})
in
    Selected
```

### Output: Two-Layer Mapping (default)

```json
{
  "mappings": [
    {
      "pbi_table": "SalesFact",
      "dbx_table": "catalog.gold.sales_transactions",
      "columns": [
        {"pbi_column": "SaleID", "dbx_column": "transaction_id"},
        {"pbi_column": "TotalAmount", "dbx_column": "amount_usd"},
        {"pbi_column": "OrderDate", "dbx_column": "created_at"},
        {"pbi_column": "CustomerID", "dbx_column": "customer_id"}
      ]
    }
  ]
}
```

### Output: Three-Layer Mapping (when M renames are relevant)

```json
{
  "mappings": [
    {
      "pbi_table": "SalesFact",
      "dbx_table": "catalog.gold.sales_transactions",
      "columns": [
        {"pbi_column": "SaleID", "m_query_column": "TransactionID", "dbx_column": "transaction_id"},
        {"pbi_column": "TotalAmount", "m_query_column": "AmountUSD", "dbx_column": "amount_usd"},
        {"pbi_column": "OrderDate", "m_query_column": "CreatedAt", "dbx_column": "created_at"},
        {"pbi_column": "CustomerID", "m_query_column": "CustomerID", "dbx_column": "customer_id"}
      ]
    }
  ]
}
```

---

## KPI Definition Template (Gap 7)

### Input: Power BI DAX Measures

```dax
Total Sales = SUM(SalesFact[TotalAmount])
Avg Order Value = DIVIDE([Total Sales], COUNTROWS(SalesFact))
Sales YoY Growth = DIVIDE(
    [Total Sales] - CALCULATE([Total Sales], SAMEPERIODLASTYEAR(DateDim[Date])),
    CALCULATE([Total Sales], SAMEPERIODLASTYEAR(DateDim[Date]))
)
Customer Count = DISTINCTCOUNT(SalesFact[CustomerID])
```

### Output: kpi/kpi_definitions.md

```markdown
# KPI Definitions

## Domain: Sales

### KPI: Total Sales
- **Business Context**: Total revenue from all completed sales transactions
- **DAX Formula**: `SUM(SalesFact[TotalAmount])`
- **SQL Equivalent**: `SUM(total_amount)`
- **Source Table**: catalog.gold.sales_fact
- **Format**: Currency, 2 decimals
- **Data Gaps**: None identified
- **Domain**: Sales

### KPI: Avg Order Value
- **Business Context**: Average revenue per sales transaction
- **DAX Formula**: `DIVIDE([Total Sales], COUNTROWS(SalesFact))`
- **SQL Equivalent**: `SUM(total_amount) / NULLIF(COUNT(1), 0)`
- **Source Table**: catalog.gold.sales_fact
- **Format**: Currency, 2 decimals
- **Data Gaps**: None identified
- **Domain**: Sales

### KPI: Sales YoY Growth
- **Business Context**: Year-over-year percentage change in total sales
- **DAX Formula**: `DIVIDE([Total Sales] - CALCULATE([Total Sales], SAMEPERIODLASTYEAR(...)), ...)`
- **SQL Equivalent**: Window function with LAG over year partition (see metric view)
- **Source Table**: catalog.gold.sales_fact
- **Format**: Percentage, 1 decimal
- **Data Gaps**: Requires at least 2 years of data for meaningful comparison
- **Domain**: Sales

### KPI: Customer Count
- **Business Context**: Number of unique customers with at least one transaction
- **DAX Formula**: `DISTINCTCOUNT(SalesFact[CustomerID])`
- **SQL Equivalent**: `COUNT(DISTINCT customer_id)`
- **Source Table**: catalog.gold.sales_fact
- **Format**: Integer
- **Data Gaps**: None identified
- **Domain**: Sales
```

---

## Data Discovery Queries (Gap 4)

### Input: Column Gap Analysis identifies discriminator columns

```
sales_fact.result_type  (flagged as discriminator)
sales_fact.order_status (flagged as discriminator)
sales_fact.order_date   (date column)
customer_dim.customer_status (flagged as discriminator)
```

### Output: reference/data_discovery_queries.sql

```sql
-- =============================================================
-- Data Discovery Queries
-- Generated from column gap analysis
-- =============================================================

-- 1. Discriminator: sales_fact.result_type
SELECT DISTINCT result_type
FROM catalog.gold.sales_fact
ORDER BY result_type;

SELECT result_type, COUNT(*) AS cnt
FROM catalog.gold.sales_fact
GROUP BY result_type
ORDER BY cnt DESC
LIMIT 50;

-- 2. Discriminator: sales_fact.order_status
SELECT DISTINCT order_status
FROM catalog.gold.sales_fact
ORDER BY order_status;

SELECT order_status, COUNT(*) AS cnt
FROM catalog.gold.sales_fact
GROUP BY order_status
ORDER BY cnt DESC
LIMIT 50;

-- 3. Date range: sales_fact.order_date
SELECT
  MIN(order_date) AS min_date,
  MAX(order_date) AS max_date
FROM catalog.gold.sales_fact;

-- 4. Discriminator: customer_dim.customer_status
SELECT DISTINCT customer_status
FROM catalog.gold.customer_dim
ORDER BY customer_status;

SELECT customer_status, COUNT(*) AS cnt
FROM catalog.gold.customer_dim
GROUP BY customer_status
ORDER BY cnt DESC
LIMIT 50;

-- 5. Null rate analysis for all gap columns
SELECT
  COUNT(*) AS total_rows,
  COUNT(*) - COUNT(result_type) AS result_type_nulls,
  COUNT(*) - COUNT(order_status) AS order_status_nulls
FROM catalog.gold.sales_fact;
```

---

## Deployment Checklist (Gap 11)

### Input: Completed project with metric views and Path A chosen

### Output: reference/deployment_checklist.md

```markdown
## Deployment Checklist: Sales Analytics Migration

**Project**: Sales PBI to Databricks
**Date**: 2026-02-26
**Path**: A (PBI Reconnection)

### Pre-Deployment
- [ ] Validate catalog access:
  ```sql
  SELECT 1 FROM analytics_catalog.gold.sales_fact LIMIT 1;
  SELECT 1 FROM analytics_catalog.gold.customer_dim LIMIT 1;
  SELECT 1 FROM analytics_catalog.gold.date_dim LIMIT 1;
  ```
- [ ] Verify SQL warehouse `analytics-wh` is running
- [ ] Confirm user has SELECT on `analytics_catalog.gold`

### Metric View Deployment
- [ ] Run `models/metric_views/sales_metrics.sql`
- [ ] Run `models/metric_views/customer_metrics.sql`
- [ ] Verify:
  ```sql
  SELECT MEASURE(`Total Sales`) FROM analytics_catalog.gold.sales_metrics LIMIT 10;
  SELECT MEASURE(`Customer Count`) FROM analytics_catalog.gold.customer_metrics LIMIT 10;
  ```
- [ ] Grant SELECT to `analysts` group:
  ```sql
  GRANT SELECT ON VIEW analytics_catalog.gold.sales_metrics TO `analysts`;
  ```

### Power BI Reconnection
- [ ] Create parameters: `ServerHostName`, `HTTPPath`, `CatalogName`
- [ ] Update M queries to use `Databricks.Catalogs()` connector
- [ ] Set SalesFact to DirectQuery, CustomerDim/DateDim to Dual
- [ ] Enable "Assume Referential Integrity" on all relationships
- [ ] Test: verify Total Sales matches original report value
- [ ] Publish to Power BI Service
- [ ] Update stored credentials in Power BI Service

### Post-Deployment
- [ ] Compare 5 key KPI values between old and new reports
- [ ] Monitor query performance for 1 week
- [ ] Document any discrepancies in reference/validation_notes.md
- [ ] Share deployment summary with stakeholders
```

---

## CSV Schema Dump (Gap 2)

### Input: CSV file with INFORMATION_SCHEMA-style headers

```csv
table_name,column_name,data_type,is_nullable,comment
sales_fact,sale_id,BIGINT,NO,Primary key
sales_fact,customer_id,BIGINT,NO,FK to customer_dim
sales_fact,order_date,DATE,NO,Date of order
sales_fact,total_amount,DECIMAL(18,2),YES,Order total in USD
customer_dim,customer_id,BIGINT,NO,Primary key
customer_dim,customer_name,STRING,YES,Full name
customer_dim,customer_status,STRING,YES,Active/Inactive
```

### Scanner Output

```json
{
  "path": "input/schema_export.csv",
  "name": "schema_export.csv",
  "type": "csv_schema_dump",
  "details": "Schema dump: 2 tables, 7 columns"
}
```

The agent should parse this CSV and construct a schema representation equivalent to `extract_dbx_schema.py` output for use in schema comparison.

---

## Catalog Resolution (Gap 5)

### Input: User provides catalog name "analytics"

### Agent probes

```sql
SELECT catalog_name FROM system.information_schema.catalogs ORDER BY catalog_name;
-- Result: analytics, fc_analytics, hive_metastore, system
```

### Output: reference/catalog_resolution.md

```markdown
## Catalog Resolution

- **Primary catalog**: `analytics`
- **Fallback catalog**: `fc_analytics`
- **Target schema**: `gold`

### Verification
| Table | Found In | Schema |
|-------|----------|--------|
| sales_fact | analytics | gold |
| customer_dim | analytics | gold |
| date_dim | analytics | gold |
| product_dim | fc_analytics | gold |

**Note**: `product_dim` found only in `fc_analytics`. Verify if this is the correct source.
```

---

## Parallel Catalog Probing with Shell Subagents (Gap 13)

### Input: Catalog list from `system.information_schema.catalogs`

```
analytics, fc_analytics, hive_metastore, system
```

Target schema: `gold`. PBI model references tables: `sales_fact`, `customer_dim`, `date_dim`, `product_dim`.

### Agent launches 3 parallel shell subagents

```
Task(subagent_type="shell", description="Probe analytics catalog",
     prompt='Probe catalog "analytics" for tables in schema "gold" using the Databricks MCP server.
             Call CallMcpTool with server="user-databricks", toolName="execute_sql",
             arguments={"sql_query": "SELECT table_name FROM analytics.information_schema.tables WHERE table_schema = \'gold\' ORDER BY table_name"}.
             Return the list of table names found.')

Task(subagent_type="shell", description="Probe fc_analytics catalog",
     prompt='Probe catalog "fc_analytics" for tables in schema "gold" using the Databricks MCP server.
             Call CallMcpTool with server="user-databricks", toolName="execute_sql",
             arguments={"sql_query": "SELECT table_name FROM fc_analytics.information_schema.tables WHERE table_schema = \'gold\' ORDER BY table_name"}.
             Return the list of table names found.')

Task(subagent_type="shell", description="Probe hive_metastore catalog",
     prompt='Probe catalog "hive_metastore" for tables in schema "gold" using the Databricks MCP server.
             Call CallMcpTool with server="user-databricks", toolName="execute_sql",
             arguments={"sql_query": "SELECT table_name FROM hive_metastore.information_schema.tables WHERE table_schema = \'gold\' ORDER BY table_name"}.
             Return the list of table names found.')
```

### Merged output: reference/catalog_resolution.md

```markdown
## Catalog Resolution

- **Primary catalog**: `analytics`
- **Fallback catalog**: `fc_analytics`
- **Target schema**: `gold`

### Table Inventory
| Table | Catalog | Schema |
|-------|---------|--------|
| sales_fact | analytics | gold |
| customer_dim | analytics | gold |
| date_dim | analytics | gold |
| product_dim | fc_analytics | gold |
```

---

## Batch Data Discovery with execute_sql_multi (Gap 13)

### Input: Data discovery queries from Step 9

All queries target the same catalog (`analytics.gold`).

### Agent calls execute_sql_multi

```
CallMcpTool:
  server: "user-databricks"
  toolName: "execute_sql_multi"
  arguments:
    sql_content: |
      -- Discriminator: sales_fact.result_type
      SELECT DISTINCT result_type FROM analytics.gold.sales_fact ORDER BY result_type;

      -- Distribution: sales_fact.result_type
      SELECT result_type, COUNT(*) AS cnt FROM analytics.gold.sales_fact GROUP BY result_type ORDER BY cnt DESC LIMIT 50;

      -- Date range: sales_fact.order_date
      SELECT MIN(order_date) AS min_date, MAX(order_date) AS max_date FROM analytics.gold.sales_fact;

      -- Discriminator: customer_dim.customer_status
      SELECT DISTINCT customer_status FROM analytics.gold.customer_dim ORDER BY customer_status;

      -- Null rate analysis
      SELECT COUNT(*) AS total_rows, COUNT(*) - COUNT(result_type) AS result_type_nulls, COUNT(*) - COUNT(order_status) AS order_status_nulls FROM analytics.gold.sales_fact;
    catalog: "analytics"
    schema: "gold"
    max_workers: 4
```

### Output: Execution summary

The tool returns results per statement, with an execution summary showing which queries ran in parallel and their individual timings. Results are ingested back into the analysis for column gap resolution and KPI data gap documentation.

---

## Existing Metric View Detection (Gap 15)

### Input: KPIs defined in Step 9

```markdown
## Domain: Sales
- Total Sales: SUM(total_amount)
- Avg Order Value: SUM(total_amount) / NULLIF(COUNT(1), 0)
- Sales YoY Growth: (window function with LAG)
- Customer Count: COUNT(DISTINCT customer_id)

## Domain: Finance
- Gross Margin: (SUM(revenue) - SUM(cost)) / NULLIF(SUM(revenue), 0)
```

### Step 1: Discover existing metric views

```sql
SELECT table_name, view_definition
FROM analytics.information_schema.views
WHERE table_schema = 'gold'
  AND view_definition LIKE '%WITH METRICS%';
```

Result:

| table_name | view_definition |
|-----------|-----------------|
| sales_metrics | CREATE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$ |
| customer_metrics | CREATE VIEW ... WITH METRICS LANGUAGE YAML AS $$ ... $$ |

### Step 2: Inspect each metric view

```
CallMcpTool:
  server: "user-databricks"
  toolName: "manage_metric_views"
  arguments:
    action: "describe"
    full_name: "analytics.gold.sales_metrics"
```

Result shows measures:
- `Total Sales`: `SUM(total_amount)`
- `Order Count`: `COUNT(1)`

```
CallMcpTool:
  server: "user-databricks"
  toolName: "manage_metric_views"
  arguments:
    action: "describe"
    full_name: "analytics.gold.customer_metrics"
```

Result shows measures:
- `Customer Count`: `COUNT(DISTINCT customer_id)`
- `Repeat Customer Rate`: `COUNT(DISTINCT CASE WHEN order_count > 1 THEN customer_id END) / NULLIF(COUNT(DISTINCT customer_id), 0)`

### Step 3: Compare and classify

| KPI Name | Domain | Classification | Existing View | Notes |
|----------|--------|---------------|---------------|-------|
| Total Sales | Sales | exists | sales_metrics | `SUM(total_amount)` matches |
| Avg Order Value | Sales | new | — | Not found in any view |
| Sales YoY Growth | Sales | new | — | Not found in any view |
| Customer Count | Customer | exists | customer_metrics | `COUNT(DISTINCT customer_id)` matches |
| Gross Margin | Finance | new | — | No finance_metrics view found |

### Output: reference/existing_metric_views.md

```markdown
## Existing Metric View Analysis

### Discovery
Found 2 metric views in `analytics.gold`:
- `sales_metrics` (2 measures: Total Sales, Order Count)
- `customer_metrics` (2 measures: Customer Count, Repeat Customer Rate)

### KPI Classification

| KPI Name | Domain | Classification | Existing View | Notes |
|----------|--------|---------------|---------------|-------|
| Total Sales | Sales | exists | sales_metrics | Expression matches |
| Avg Order Value | Sales | new | — | Not in any existing view |
| Sales YoY Growth | Sales | new | — | Not in any existing view |
| Customer Count | Customer | exists | customer_metrics | Expression matches |
| Gross Margin | Finance | new | — | No finance view exists |

### Views to Modify
- None (no `update` classifications in this run)

### New Metric Views to Create
- **sales_metrics**: ALTER to add `Avg Order Value` and `Sales YoY Growth`
  (same source table as existing `Total Sales`, so extend existing view)
- **finance_metrics**: CREATE new view with `Gross Margin`

### Skipped (Already Deployed)
- Total Sales (in sales_metrics)
- Customer Count (in customer_metrics)
```

### Step 13 actions based on classification

```sql
-- Extend existing sales_metrics with new measures
ALTER VIEW analytics.gold.sales_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  source: analytics.gold.sales_fact
  dimensions:
    - name: Order Month
      expr: date_trunc('month', order_date)
    - name: Region
      expr: region
  measures:
    - name: Total Sales
      expr: SUM(total_amount)
      comment: "DAX: SUM(SalesFact[TotalAmount])"
    - name: Avg Order Value
      expr: SUM(total_amount) / NULLIF(COUNT(1), 0)
      comment: "DAX: DIVIDE([Total Sales], COUNTROWS(SalesFact))"
    - name: Sales YoY Growth
      expr: (SUM(total_amount) - LAG(SUM(total_amount)) OVER (ORDER BY date_trunc('month', order_date))) / NULLIF(LAG(SUM(total_amount)) OVER (ORDER BY date_trunc('month', order_date)), 0)
      comment: "DAX: DIVIDE([Total Sales] - CALCULATE([Total Sales], SAMEPERIODLASTYEAR(...)), ...)"
$$;

-- Create new finance_metrics view
CREATE OR REPLACE VIEW analytics.gold.finance_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  source: analytics.gold.revenue_fact
  dimensions:
    - name: Period
      expr: date_trunc('month', revenue_date)
    - name: Business Unit
      expr: business_unit
  measures:
    - name: Gross Margin
      expr: (SUM(revenue) - SUM(cost)) / NULLIF(SUM(revenue), 0)
      comment: "DAX: DIVIDE(SUM(Revenue) - SUM(Cost), SUM(Revenue))"
$$;

-- Customer Count: SKIP (already deployed in customer_metrics with matching expression)
```
