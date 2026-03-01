# ERD, KPI Definitions & Data Discovery (Steps 8–10)

Steps 8, 9, and 10 of the migration workflow: generate ERDs, build structured KPI definitions from DAX, and generate data discovery queries.

---

## Step 8: ERD and Domain Modeling

```bash
python scripts/generate_erd.py reference/pbi_model.json -o reference/
```

Produces `reference/erd.md` (Mermaid + text ERD) and `reference/domains.md` (domain groupings). **Review with user before proceeding.**

This step can proceed with PBI-only data even if no Databricks schema is available.

---

## Step 9: KPI Definitions

Build structured KPI definitions in `kpi/kpi_definitions.md`. Each KPI includes: business context, DAX formula, SQL equivalent, source table, format, data gaps, and domain.

```bash
bash scripts/init_project.sh --kpi
```

### KPI Definition Template

```markdown
### KPI: <KPI Name>
- **Business Context**: <What this KPI measures and why it matters>
- **DAX Formula**: `<original DAX>`
- **SQL Equivalent**: `<translated SQL aggregate>`
- **Source Table**: <catalog.schema.table>
- **Format**: <Currency/Percentage/Integer/Decimal, precision>
- **Data Gaps**: <None identified / Missing values in X column / etc.>
- **Domain**: <Business domain this KPI belongs to>
```

### Organizing KPIs

Group KPIs by domain. Within each domain, order by importance (primary KPIs first, derived KPIs after):

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
```

### DAX-to-SQL Translation Reference

| DAX Function | SQL Equivalent |
|---|---|
| `SUM(Sales[Amount])` | `SUM(total_amount)` |
| `COUNTROWS(Orders)` | `COUNT(1)` |
| `DISTINCTCOUNT(Customer[ID])` | `COUNT(DISTINCT customer_id)` |
| `DIVIDE(SUM(...), SUM(...))` | `SUM(...) / NULLIF(SUM(...), 0)` |
| `CALCULATE(SUM(...), Filter)` | Use metric view `filter` or filtered measure expressions |
| `SAMEPERIODLASTYEAR(...)` | Window function with LAG over year partition |

---

## Step 10: Data Discovery Queries

Auto-generate SQL queries for unknown filter values, value distributions, date ranges, and null rates. Save to `reference/data_discovery_queries.sql`.

**Execute directly** when Databricks access is available:
- **Same catalog** (preferred): Use `execute_sql_multi` to batch all queries (see [9-subagent-patterns.md](9-subagent-patterns.md) Pattern C)
- **Cross-catalog**: Launch parallel shell subagents per catalog (see [9-subagent-patterns.md](9-subagent-patterns.md) Pattern A)

If no Databricks access, present queries to the user to run manually and ingest results back.

### Query Templates

**For low-cardinality / discriminator columns** (flagged in Step 7):

```sql
SELECT DISTINCT <column> FROM <catalog>.<schema>.<table> ORDER BY <column>;
```

**For value distribution:**

```sql
SELECT <column>, COUNT(*) AS cnt
FROM <catalog>.<schema>.<table>
GROUP BY <column>
ORDER BY cnt DESC
LIMIT 50;
```

**For date columns:**

```sql
SELECT MIN(<date_col>) AS min_date, MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>;
```

**For null rate analysis:**

```sql
SELECT
  COUNT(*) AS total_rows,
  COUNT(*) - COUNT(<col>) AS null_count,
  ROUND((COUNT(*) - COUNT(<col>)) * 100.0 / COUNT(*), 2) AS null_pct
FROM <catalog>.<schema>.<table>;
```

### Example Output: reference/data_discovery_queries.sql

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

-- 2. Date range: sales_fact.order_date
SELECT
  MIN(order_date) AS min_date,
  MAX(order_date) AS max_date
FROM catalog.gold.sales_fact;

-- 3. Null rate analysis
SELECT
  COUNT(*) AS total_rows,
  COUNT(*) - COUNT(result_type) AS result_type_nulls,
  COUNT(*) - COUNT(order_status) AS order_status_nulls
FROM catalog.gold.sales_fact;
```
