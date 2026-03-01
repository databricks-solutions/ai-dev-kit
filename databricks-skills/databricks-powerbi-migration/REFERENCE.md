# Reference: Detailed Patterns

This document provides detailed patterns for each gap identified during real-world testing of the PowerBI-to-Databricks skill. Each section is referenced from [SKILL.md](SKILL.md) workflow steps.

---

## Gap 1: Intermediate Mapping Layer (Scenario D)

When Power Query M expressions rename columns between the PBI semantic layer and the physical database, a direct name comparison fails. Scenario D handles this by extracting the renames and building a mapping.

### Detection

Look in the PBI model's `partitions[].source.expression` for M code containing:

- `Table.RenameColumns` -- explicit column renames
- `Table.SelectColumns` -- column selection (implies name preservation)
- Schema parameter patterns -- `type table [ColName = type text, ...]`

### Mapping Construction

Build the **common two-layer mapping** (`pbi_column -> dbx_column`) by default. Use a **three-layer mapping** only where Power Query M introduces an intermediate rename:

```
Two-layer (default):
  pbi_column  ->  dbx_column

Three-layer (only when M renames are present):
  pbi_column  ->  m_query_column  ->  dbx_column
```

### How to Extract M Renames

1. Parse the PBI model JSON and locate `partitions` on each table.
2. For each partition with `source.type == "m"`, read `source.expression`.
3. Search for `Table.RenameColumns(...)` calls -- the argument is a list of `{old, new}` pairs.
4. Search for the `type table [...]` schema definition to find the final column names exposed to the PBI layer.
5. Map backward: PBI column name -> M expression column -> physical DB column.

### Usage with compare_schemas.py

Pass the intermediate mapping file via the `--mapping` flag:

```bash
python scripts/compare_schemas.py \
  reference/pbi_model.json reference/dbx_schema.json \
  -o reference/schema_comparison.md --json \
  --mapping reference/intermediate_mapping.json
```

The mapping JSON format:

```json
{
  "mappings": [
    {
      "pbi_table": "SalesFact",
      "dbx_table": "catalog.schema.sales_transactions",
      "columns": [
        {
          "pbi_column": "SaleID",
          "m_query_column": "transaction_id",
          "dbx_column": "transaction_id"
        },
        {
          "pbi_column": "TotalAmount",
          "dbx_column": "amount_usd"
        }
      ]
    }
  ]
}
```

When `m_query_column` is absent, the mapping is treated as two-layer.

---

## Gap 2: CSV Schema Dump Detection

CSV files exported from `INFORMATION_SCHEMA` queries or database documentation tools often contain schema metadata. The scanner should detect these and treat them as equivalent to schema query output.

### Detection Criteria

A CSV file is classified as `csv_schema_dump` when its header row contains columns matching these patterns (case-insensitive, allowing underscores, spaces, or camelCase):

- `table_name` / `tableName` / `TABLE_NAME`
- `column_name` / `columnName` / `COLUMN_NAME`
- `data_type` / `dataType` / `DATA_TYPE`

At least `table_name` and `column_name` must be present. `data_type` is strongly expected but not strictly required.

### Agent Behavior

When a `csv_schema_dump` is detected:

1. Parse the CSV to extract table names, column names, and data types.
2. Build a schema representation equivalent to `extract_dbx_schema.py` output.
3. Use this schema for comparison in Step 6.

---

## Gap 3: Databricks-Only Column Gap Detection

After schema comparison, DBX-only columns (columns present in Databricks but not referenced in the Power BI model) may be important for:

- Filters and partitions in reports built outside PBI
- Discriminator columns that determine row subsets
- Audit/metadata columns needed for data governance

### Column Gap Analysis Output

The `compare_schemas.py` script produces `reference/column_gap_analysis.md` with:

1. Every DBX-only column grouped by table
2. Discriminator flagging for columns that appear to be low-cardinality (naming heuristics: `status`, `type`, `category`, `result_type`, `is_*`, `flag_*`, `*_code`)
3. Suggested actions for each flagged column

### Discriminator Heuristics

A column is flagged as a potential discriminator if its name matches any of:

- Contains `status`, `type`, `category`, `code`, `flag`, `class`, `kind`, `tier`, `level`, `group`
- Starts with `is_`, `has_`, `can_`
- Ends with `_type`, `_status`, `_code`, `_flag`, `_category`, `_class`

### Output Format

```markdown
## Column Gap Analysis

### Table: catalog.schema.sales_fact
| Column | Data Type | Discriminator? | Suggested Action |
|--------|-----------|----------------|------------------|
| result_type | STRING | Yes | May filter report subsets -- run data discovery |
| etl_load_date | TIMESTAMP | No | Audit column -- likely not needed in reports |

### Table: catalog.schema.customer_dim
| Column | Data Type | Discriminator? | Suggested Action |
|--------|-----------|----------------|------------------|
| customer_status | STRING | Yes | May be essential for active/inactive filtering |
```

---

## Gap 4: Data Discovery Query Generation

After schema comparison and column gap analysis, auto-generate SQL queries to understand data values, distributions, and ranges.

### Query Templates

For **low-cardinality / discriminator columns**:

```sql
SELECT DISTINCT <column> FROM <catalog>.<schema>.<table> ORDER BY <column>;
```

For **value distribution**:

```sql
SELECT <column>, COUNT(*) AS cnt
FROM <catalog>.<schema>.<table>
GROUP BY <column>
ORDER BY cnt DESC
LIMIT 50;
```

For **date columns**:

```sql
SELECT MIN(<date_col>) AS min_date, MAX(<date_col>) AS max_date
FROM <catalog>.<schema>.<table>;
```

For **null rate analysis**:

```sql
SELECT
  COUNT(*) AS total_rows,
  COUNT(*) - COUNT(<col>) AS null_count,
  ROUND((COUNT(*) - COUNT(<col>)) * 100.0 / COUNT(*), 2) AS null_pct
FROM <catalog>.<schema>.<table>;
```

### Output

Save all generated queries to `reference/data_discovery_queries.sql`. The agent can:

1. Run queries via MCP `execute_sql` if available
2. Present queries to the user to run manually
3. Ingest results back into the analysis

---

## Gap 5: Catalog Resolution Strategy

In multi-catalog environments, the agent must determine which catalog and schema contain the target tables.

### Resolution Steps

1. **Probe available catalogs**:
   ```sql
   SELECT catalog_name FROM system.information_schema.catalogs ORDER BY catalog_name;
   ```

2. **Probe schemas within the target catalog**:
   ```sql
   SELECT schema_name FROM <catalog>.information_schema.schemata;
   ```

3. **Verify table existence**:
   ```sql
   SELECT table_name
   FROM <catalog>.information_schema.tables
   WHERE table_schema = '<schema>';
   ```

### Handling fc_ Prefix

Some environments prefix catalog names with `fc_`. The agent should:

1. Try the catalog name as provided
2. If not found, try with `fc_` prefix
3. If not found, try without `fc_` prefix
4. Document both primary and fallback catalog in `reference/catalog_resolution.md`

### Parallel Probing with Subagents

When the catalog list contains multiple candidates, probe them concurrently using parallel `shell` subagents (see Gap 13 Pattern A). Each subagent calls `execute_sql` via the `user-databricks` MCP server to check table existence in its assigned catalog. This reduces catalog resolution from serial (N sequential queries) to parallel (all catalogs probed at once, max 4 concurrent).

### Output

Produce `reference/catalog_resolution.md`:

```markdown
## Catalog Resolution

- **Primary catalog**: `my_catalog`
- **Fallback catalog**: `fc_my_catalog` (if applicable)
- **Target schema**: `gold`
- **Tables found**: 15 (listed below)
- **Tables missing**: 2 (listed below)

### Table Inventory
| Table | Catalog | Schema | Row Count (est.) |
|-------|---------|--------|------------------|
| sales_fact | my_catalog | gold | ~10M |
```

---

## Gap 6: Report Replication Workflow (Path B)

When the goal is to replace Power BI reports with Databricks-native reports rather than reconnecting PBI:

### Workflow

1. Read the `databricks-aibi-dashboards` skill for dashboard creation patterns
2. Build a report specification from the PBI model's visual layout (pages, visuals, filters)
3. Generate `planreport/report_spec.md` with:
   - Summary tables (KPI scorecards)
   - Trend charts (time series by dimension)
   - Narrative text blocks (dynamic text with metric values)
   - Disclaimers and footnotes
4. Generate `planreport/email_template.md` for distribution specs
5. Use the `databricks-jobs` skill to schedule delivery

### Report Specification Template

```markdown
## Report: <Report Name>

### Page 1: Executive Summary
- **Visual 1**: KPI scorecard (Total Sales, Avg Order Value, Customer Count)
- **Visual 2**: Monthly trend line (Total Sales by Month)
- **Visual 3**: Top 10 table (Products by Revenue)
- **Filters**: Date range, Region, Product Category

### Page 2: Detail View
- **Visual 1**: Table with drill-through (Order details)
- **Filters**: All from Page 1 + Customer Segment
```

---

## Gap 7: KPI Definitions as First-Class Artifact

KPI definitions should be structured, not informal. The agent produces `kpi/kpi_definitions.md` with a standardized template per KPI.

### Template

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

Group KPIs by domain. Within each domain, order by importance (primary KPIs first, derived KPIs after).

```markdown
# KPI Definitions

## Domain: Sales
### KPI: Total Sales
...
### KPI: Avg Order Value
...

## Domain: Finance
### KPI: Gross Margin
...
```

---

## Gap 8: Sample Report / Document Analysis

When `input/` contains sample reports or documents (`.docx`, `.pdf`, `.png`, `.jpg`, `.xlsx`, `.pptx`), the agent should reverse-engineer the report's structure.

### What to Extract

- **KPI names and values** visible in the report
- **Column formatting** (currency symbols, decimal places, date formats)
- **Chart types** (bar, line, pie, table, scorecard)
- **Narrative templates** (dynamic text patterns like "Sales increased by X% compared to...")
- **Disclaimers and footnotes**
- **Branding** (colors, logos, headers/footers)
- **Filter/slicer positions** and default values

### Output

Produce `reference/report_analysis.md`:

```markdown
## Report Analysis: <filename>

### KPIs Identified
| KPI | Value (as shown) | Likely Measure | Format |
|-----|-------------------|----------------|--------|
| Total Revenue | $1.2M | SUM(revenue) | Currency, 1 decimal |

### Visuals
| # | Type | Title | Dimensions | Measures |
|---|------|-------|------------|----------|
| 1 | Scorecard | Key Metrics | - | Total Revenue, Order Count |
| 2 | Line Chart | Monthly Trend | Month | Total Revenue |

### Narrative Templates
- "Revenue for {period} was {Total Revenue}, a {YoY Change}% change from the prior year."

### Disclaimers
- "Data as of {last_refresh_date}. Excludes returns processed after close."
```

---

## Gap 9: Cross-Schema and INFORMATION_SCHEMA Probing

In multi-schema and multi-catalog environments, extend schema queries to cover all relevant schemas.

### Cross-Schema Column Comparison

```sql
SELECT table_schema, table_name, column_name, data_type
FROM <catalog>.information_schema.columns
WHERE table_schema IN ('<schema_a>', '<schema_b>')
ORDER BY table_schema, table_name, ordinal_position;
```

### Discover All Schemas in a Catalog

```sql
SELECT schema_name FROM <catalog>.information_schema.schemata;
```

### Discover All Catalogs

```sql
SELECT catalog_name FROM system.information_schema.catalogs;
```

### When to Use Cross-Schema Probing

- PBI model references tables from multiple schemas
- Table names exist in multiple schemas (need to disambiguate)
- Migration involves consolidating schemas

---

## Gap 10: Report Distribution Artifacts

The `planreport/` folder contains all artifacts needed for Databricks-native report delivery.

### Folder Structure

```
planreport/
├── report_spec.md          # Visual layout, chart specs, narrative blocks
├── email_template.md       # Recipients, schedule, subject, body template
└── deployment_config.yml   # Job schedule, warehouse, notification targets
```

### Email Template

```markdown
## Email Distribution

- **Recipients**: [list of email addresses or groups]
- **Schedule**: Weekly, Monday 8:00 AM UTC
- **Subject**: "{Report Name} - Week of {date}"
- **Body**: See narrative template from report_spec.md
- **Attachments**: PDF export of dashboard
- **Format**: HTML with inline charts
```

### Deployment Configuration

```yaml
report_name: "Sales Weekly Report"
warehouse_id: "<sql_warehouse_id>"
schedule:
  quartz_cron: "0 0 8 ? * MON"
  timezone: "UTC"
notifications:
  on_success:
    - email: "team@company.com"
  on_failure:
    - email: "admin@company.com"
```

---

## Gap 11: Deployment Checklist Generation

The final artifact is an ordered checklist of steps to go from local artifacts to a running, scheduled report.

### Checklist Template

```markdown
## Deployment Checklist

### Pre-Deployment
- [ ] Validate catalog access: `SELECT 1 FROM <catalog>.<schema>.<table> LIMIT 1`
- [ ] Verify all source tables exist and are accessible
- [ ] Confirm SQL warehouse is running and sized appropriately

### Metric View Deployment
- [ ] Deploy metric views: run each SQL file in models/metric_views/
- [ ] Verify metric views: `SELECT MEASURE(...) FROM <view> LIMIT 10`
- [ ] Grant SELECT to required users/groups

### Report Deployment (choose path)
#### Path A: Power BI Reconnection
- [ ] Update Power Query M formulas to use Databricks connector
- [ ] Parameterize ServerHostName and HTTPPath
- [ ] Set DirectQuery for facts, Dual for dimensions
- [ ] Set "Assume Referential Integrity" on relationships
- [ ] Test all report pages for data accuracy
- [ ] Publish to Power BI Service
- [ ] Update stored credentials in Power BI Service

#### Path B: Databricks-Native Report
- [ ] Create AI/BI dashboard from report_spec.md
- [ ] Configure job schedule from deployment_config.yml
- [ ] Set up email distribution from email_template.md
- [ ] Test dashboard rendering and data accuracy

### Post-Deployment
- [ ] Run validation queries against metric views
- [ ] Compare output values with original PBI report
- [ ] Share deployment summary with stakeholders
- [ ] Document any known gaps or deferred items
```

---

## Gap 12: Query Access Optimization

Before constructing metric views, assess query complexity, table size, grain, and access patterns to choose the optimal serving strategy. This prevents building metric views that are too slow for interactive use or unnecessarily expensive.

### Assessment Criteria

For each KPI or domain, evaluate:

| Factor | How to Assess | Threshold |
|--------|---------------|-----------|
| **Table size** | `DESCRIBE DETAIL <table>` -- check `sizeInBytes` and `numFiles` | < 100 GB = small, 100 GB - 1 TB = medium, > 1 TB = large |
| **Row count** | `SELECT COUNT(*) FROM <table>` or estimate from DESCRIBE DETAIL | < 100M = small, 100M - 1B = medium, > 1B = large |
| **Join count** | Count the number of tables joined per KPI query | 0-2 = simple, 3-5 = moderate, 6+ = complex |
| **Aggregation complexity** | Window functions, CASE expressions, nested aggregations | Simple SUM/COUNT = low, window/CASE = medium, nested = high |
| **Grain mismatch** | Compare fact table grain to report grain | Same grain = no issue, different grain = pre-aggregation needed |
| **Filter selectivity** | Typical filter narrows result to what % of table? | > 50% = low selectivity, < 10% = high selectivity |
| **Refresh frequency** | How often does the source data change? | Real-time, hourly, daily, weekly |

### Query Complexity Scoring

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
| 0-2 | Standard metric view (direct on source tables) |
| 3-5 | Materialized view with scheduled refresh |
| 6+ | Gold-layer aggregate table + metric view on top |

### Serving Strategies

#### Strategy 1: Standard Metric View

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

#### Strategy 2: Materialized View with Incremental Refresh

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

#### Strategy 3: Gold-Layer Aggregate Table

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

Use `spark-declarative-pipelines` to maintain incremental refresh, then build metric views on top of the gold table.

### Grain Analysis

When the fact table grain is finer than the report grain, pre-aggregation is essential:

| Fact Table Grain | Report Grain | Action |
|-----------------|--------------|--------|
| Transaction-level | Daily | Materialized view with `date_trunc('day', ...)` |
| Transaction-level | Monthly | Gold-layer aggregate or materialized view |
| Daily | Monthly | Materialized view with `date_trunc('month', ...)` |
| Same | Same | Standard metric view (no pre-aggregation) |

### Output

Produce `reference/query_optimization_plan.md`:

```markdown
## Query Optimization Plan

### Domain: Sales
| KPI | Score | Strategy | Rationale |
|-----|-------|----------|-----------|
| Total Sales | 2 | Standard metric view | Simple SUM, table < 50 GB |
| Sales YoY Growth | 5 | Materialized view | Window function over 2 years, 200 GB table |
| Customer Lifetime Value | 7 | Gold-layer aggregate | 5-table join, 1.2 TB fact table, transaction-to-monthly grain |

### Materialized Views to Create
1. `monthly_sales_agg` -- monthly pre-aggregation for time-series KPIs
   - Schedule: daily at 2:00 AM UTC
   - Source: sales_fact (200 GB)
   - Estimated refresh time: ~15 min

### Gold-Layer Tables to Create
1. `gold_customer_ltv` -- customer lifetime value aggregate
   - Pipeline: notebooks/customer_ltv_pipeline.py
   - Refresh: daily incremental via SDP
```

---

## Gap 13: Subagent Parallelization Patterns

Use `Task` subagents (`subagent_type="shell"`) to parallelize MCP tool calls when work spans multiple catalogs, schemas, or tables. Each subagent runs independently and returns its results. Max 4 concurrent subagents.

### Decision Guide: Subagents vs. `execute_sql_multi`

| Scenario | Best Tool | Why |
|----------|-----------|-----|
| N queries, same catalog | `execute_sql_multi` | Single MCP call, built-in parallelism (up to 4 workers), simpler |
| N queries, different catalogs | Parallel `shell` subagents | Each needs a different catalog context; `execute_sql_multi` takes only one |
| 1 query per catalog for probing | Parallel `shell` subagents | Each subagent probes one catalog independently |
| Sizing N tables in same catalog | `execute_sql_multi` | Combine N `DESCRIBE DETAIL` into one call |
| Sizing tables across catalogs | Parallel `shell` subagents | Different catalog contexts |

### Pattern A: Parallel Catalog Probing

When Step 3 identifies multiple candidate catalogs, launch one subagent per catalog to verify which contains the target tables.

**Subagent prompt template** (one per catalog):

```
Probe catalog "<CATALOG>" for tables in schema "<SCHEMA>" using the Databricks MCP server.

1. Call CallMcpTool with:
   - server: "user-databricks"
   - toolName: "execute_sql"
   - arguments: {"sql_query": "SELECT table_name FROM <CATALOG>.information_schema.tables WHERE table_schema = '<SCHEMA>' ORDER BY table_name"}

2. Return the list of table names found, or state that no tables were found.
```

Launch up to 4 of these concurrently:

```
Task(subagent_type="shell", prompt="<template with catalog=analytics>")
Task(subagent_type="shell", prompt="<template with catalog=fc_analytics>")
Task(subagent_type="shell", prompt="<template with catalog=hive_metastore>")
```

Merge results into `reference/catalog_resolution.md`.

### Pattern B: Parallel Schema Extraction

When Step 4 needs schema from multiple catalogs or schemas, launch one subagent per catalog/schema pair.

**Subagent prompt template**:

```
Extract schema details for catalog "<CATALOG>", schema "<SCHEMA>" using the Databricks MCP server.

1. Call CallMcpTool with:
   - server: "user-databricks"
   - toolName: "get_table_details"
   - arguments: {"catalog": "<CATALOG>", "schema": "<SCHEMA>", "table_stat_level": "SIMPLE"}

2. Return the full result including table names, column definitions, and row counts.
```

### Pattern C: Batch Data Discovery with `execute_sql_multi`

When Step 9 generates discovery queries for tables within a single catalog, execute them all in one MCP call.

**MCP tool call**:

```
CallMcpTool:
  server: "user-databricks"
  toolName: "execute_sql_multi"
  arguments:
    sql_content: |
      SELECT DISTINCT result_type FROM catalog.gold.sales_fact ORDER BY result_type;
      SELECT result_type, COUNT(*) AS cnt FROM catalog.gold.sales_fact GROUP BY result_type ORDER BY cnt DESC LIMIT 50;
      SELECT MIN(order_date) AS min_date, MAX(order_date) AS max_date FROM catalog.gold.sales_fact;
      SELECT DISTINCT customer_status FROM catalog.gold.customer_dim ORDER BY customer_status;
    catalog: "catalog"
    schema: "gold"
    max_workers: 4
```

The tool automatically detects independent queries and runs them in parallel. Results are returned per-statement.

### Pattern D: Parallel Table Sizing

When Step 10 needs `DESCRIBE DETAIL` for many tables, batch them or use subagents.

**Same catalog** -- use `execute_sql_multi`:

```
CallMcpTool:
  server: "user-databricks"
  toolName: "execute_sql_multi"
  arguments:
    sql_content: |
      DESCRIBE DETAIL catalog.gold.sales_fact;
      DESCRIBE DETAIL catalog.gold.customer_dim;
      DESCRIBE DETAIL catalog.gold.product_dim;
      DESCRIBE DETAIL catalog.gold.date_dim;
    catalog: "catalog"
    max_workers: 4
```

**Cross-catalog** -- launch parallel `shell` subagents, each running `execute_sql` with one `DESCRIBE DETAIL` statement against its catalog.

Extract `sizeInBytes` and `numFiles` from results to feed into the query complexity scoring in Gap 12.

---

## Gap 14: Early Catalog Accessibility Validation

After parsing the PBI model (Step 2), immediately extract all data source references and verify that the agent has access to the required catalogs and schemas -- or that schema dumps have been provided. This prevents wasted work in later steps that depend on schema information.

### Extracting Data Source References from the PBI Model

Data source references are embedded in the parsed PBI model JSON in several locations:

1. **Partition source expressions** (`partitions[].source.expression`):
   Look for M code containing `Sql.Database("server", "database")` or `Sql.Databases("server")`. Extract the server name and database/catalog name.

   ```
   // Example M expression:
   let Source = Sql.Database("myserver.database.windows.net", "my_catalog"),
       gold = Source{[Schema="gold"]}[Data],
       ...
   ```

2. **Connection string annotations** (`model.annotations` or `model.dataSources`):
   Some models store explicit connection strings with server, database, catalog, and schema.

3. **Table source metadata** (`tables[].partitions[].source`):
   For DirectQuery tables, the `source` object may contain `schema` and `entity` (table) names.

### Extraction Logic

```python
def extract_data_sources(model: dict) -> list[dict]:
    """Extract catalog/schema references from parsed PBI model."""
    sources = []
    for table in model.get("tables", []):
        for partition in table.get("partitions", []):
            src = partition.get("source", {})
            expr = src.get("expression", "")
            # Look for Sql.Database("server", "database")
            match = re.search(r'Sql\.Database\("([^"]+)",\s*"([^"]+)"\)', expr)
            if match:
                sources.append({
                    "server": match.group(1),
                    "catalog": match.group(2),
                    "table": table.get("name"),
                })
            # Look for schema references: Source{[Schema="xxx"]}
            schema_match = re.search(r'\[Schema="([^"]+)"\]', expr)
            if schema_match:
                sources[-1]["schema"] = schema_match.group(1) if sources else None
    return sources
```

### Accessibility Test

For each unique catalog extracted, test accessibility:

```sql
SELECT 1 FROM <catalog>.information_schema.tables LIMIT 1;
```

When multiple catalogs need testing, launch parallel `shell` subagents (max 4). Each subagent runs `execute_sql` via the `user-databricks` MCP server.

### Cross-Reference Against Provided Inputs

Before running live queries, check whether the `input/` folder already provides schema information for the referenced catalog:

1. Check `reference/input_manifest.json` for files classified as `csv_schema_dump`, `dbx_schema`, or `sql_ddl`
2. Check whether the file's content references the target catalog/schema
3. If schema info is available locally, mark the catalog as "covered by input file" and skip the live accessibility test

### Warning Message Template

If a catalog is referenced but neither accessible nor covered by input files:

```
⚠ Missing catalog access: The PBI model references `<catalog>.<schema>` (used by tables: <table_list>),
but I have no schema information and cannot access this catalog.

Please provide one of:
1. A schema dump (CSV, DDL, or JSON) for `<catalog>.<schema>` in the input/ folder
2. Databricks credentials with access to this catalog
3. Run this query and paste the output:
   SELECT table_name, column_name, data_type, is_nullable, comment
   FROM <catalog>.information_schema.columns
   WHERE table_schema = '<schema>'
   ORDER BY table_name, ordinal_position;
```

### Output

Update `reference/catalog_resolution.md` with an accessibility status section:

```markdown
## Catalog Accessibility Status

| Catalog | Schema | Status | Source |
|---------|--------|--------|--------|
| my_catalog | gold | ✅ Accessible | Live MCP query |
| other_catalog | silver | ✅ Covered | input/other_catalog_schema.csv |
| missing_catalog | dbo | ❌ Inaccessible | No schema info -- user action required |
```

---

## Gap 15: Existing Metric View Detection

Before building new metric views (Step 13), check whether any of the target KPIs already exist in metric views in the target catalog/schema. This avoids duplication and enables incremental updates.

### Discovery: Find Existing Metric Views

Query the catalog's `information_schema` to find views created with the `WITH METRICS` clause:

```sql
SELECT table_name, view_definition
FROM <catalog>.information_schema.views
WHERE table_schema = '<schema>'
  AND view_definition LIKE '%WITH METRICS%';
```

If MCP access is available, execute this via `execute_sql`. If multiple target schemas exist, use `execute_sql_multi` or parallel subagents.

### Inspection: Get Measure Details

For each discovered metric view, use the `manage_metric_views` MCP tool to retrieve its full definition:

```
CallMcpTool:
  server: "user-databricks"
  toolName: "manage_metric_views"
  arguments:
    action: "describe"
    full_name: "<catalog>.<schema>.<view_name>"
```

The result includes `measures` (name + expression) and `dimensions` (name + expression). Extract the measure names and SQL expressions for comparison.

### Comparison Logic

For each KPI from `kpi/kpi_definitions.md`, compare against all measures found in existing metric views:

```
For each kpi in kpi_definitions:
  match = find measure where normalize(measure.name) == normalize(kpi.name)
  if no match:
    classification = "new"
  elif normalize(measure.expr) == normalize(kpi.sql_equivalent):
    classification = "exists"
  else:
    classification = "update"
```

**Normalization** for comparison:
- Lowercase both names
- Strip whitespace
- Remove surrounding quotes
- For expressions: normalize whitespace, remove catalog/schema prefixes for column references

### Classification Actions

| Classification | Description | Action in Step 13 |
|---------------|-------------|-------------------|
| `new` | KPI not found in any existing metric view | `CREATE OR REPLACE VIEW ... WITH METRICS` |
| `update` | KPI name exists but expression differs | `ALTER VIEW` or `manage_metric_views` with `action: "alter"` to update |
| `exists` | KPI name and expression match | Skip -- log as "already deployed" in deployment checklist |

### Output

Produce `reference/existing_metric_views.md`:

```markdown
## Existing Metric View Analysis

### Discovery
Found 3 metric views in `my_catalog.gold`:
- `sales_metrics` (4 measures)
- `finance_metrics` (2 measures)
- `customer_metrics` (3 measures)

### KPI Classification

| KPI Name | Domain | Classification | Existing View | Notes |
|----------|--------|---------------|---------------|-------|
| Total Sales | Sales | exists | sales_metrics | Expression matches |
| Sales YoY Growth | Sales | update | sales_metrics | Expression differs (old: SUM vs new: window) |
| Gross Margin | Finance | new | — | Not found in any existing view |
| Customer Count | Customer | exists | customer_metrics | Expression matches |
| Avg Order Value | Sales | new | — | Not found in any existing view |

### Views to Modify
- **sales_metrics**: ALTER to update `Sales YoY Growth` expression

### New Views to Create
- **finance_metrics_v2**: CREATE with `Gross Margin` measure
  (or add to existing `finance_metrics` if same source table)

### Skipped (Already Deployed)
- Total Sales (in sales_metrics)
- Customer Count (in customer_metrics)
```

### Handling No Access

If Databricks access is not available and no schema description covers the target schema's views, skip this step and treat all KPIs as `new`. Log a note in the deployment checklist: "Manual verification recommended -- could not check for existing metric views."
