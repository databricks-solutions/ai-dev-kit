---
name: databricks-powerbi-migration
description: "Converts Power BI semantic models to Databricks metric views. Handles schema assessment, ERD/domain generation, intermediate mapping layers, DAX-to-SQL translation, query access optimization (materialized views, incremental refresh), KPI definitions, data discovery, report replication, and deployment checklists. Use when migrating Power BI to Databricks, converting DAX to metric views, building metric views from semantic models, or when the user mentions Power BI, PBI, semantic model, DAX migration, or PBI-to-Databricks."
---

# PowerBI to Databricks Conversion

Convert Power BI semantic models into Databricks metric views, Delta tables, and associated assets.

**Always run in Plan mode.** Prompt the user for direction when uncertain.

## Prerequisites

- Python 3.10+
- *(Optional)* Databricks CLI profile configured with PAT authentication
- *(Optional)* `databricks-sdk` installed (`pip install databricks-sdk`)

## Quick Start

```bash
bash scripts/init_project.sh
# Place all files in input/ (PBI models, DDLs, mappings, schema dumps, sample reports, configs)
python scripts/scan_inputs.py input/ -o reference/input_manifest.json
# Present results to user, confirm usage, then follow the checklist below
```

## Migration Scenarios

Determined by `scripts/compare_schemas.py` when Databricks schema information is available:

- **Scenario A** (names match): Repoint Power BI connection directly to Databricks
- **Scenario B** (names differ, model same): Create aliasing views in Databricks, then repoint
- **Scenario C** (names and model differ): Generate views from a JSON mapping document
- **Scenario D** (intermediate mapping layer): PBI semantic layer -> mapping (Power Query M renames) -> Databricks physical layer. See [REFERENCE.md](REFERENCE.md) Gap 1.

If no Databricks schema is available, skip comparison and proceed to ERD/domain generation.

## Workflow Checklist

Copy this checklist and check off steps as you complete them:

```
Task Progress:
- [ ] 1. Scan and classify all files in input/
- [ ] 2. Parse Power BI model(s)
- [ ] 3. Validate catalog accessibility (raise early warnings for missing catalogs)
- [ ] 4. Resolve catalog (probe available catalogs)
- [ ] 5. Extract or ingest Databricks schema (suggest queries if missing)
- [ ] 6. Build mapping layer (direct, view, translation docs, or mapping doc)
- [ ] 7. Compare schemas and detect column gaps (DBX-only columns)
- [ ] 8. Generate ERD and domain model
- [ ] 9. Build KPI definitions file (kpi/kpi_definitions.md)
- [ ] 10. Generate data discovery queries for unknown filter values
- [ ] 11. Optimize query access layer (materialized views, grain, complexity)
- [ ] 12. Check existing metric views (detect duplicates, propose update vs create)
- [ ] 13. Build or update metric views by domain
- [ ] 14. Analyze sample report (if provided) and choose output path
- [ ] 15. Output Path A: PBI reconnection  --OR--  Path B: Databricks-native report
- [ ] 16. Generate deployment checklist
```

### Step 1: Scan, Classify, and Confirm All Inputs

**Before doing anything else**, read every file in `input/`. Classify each file by content -- not extension.

```bash
python scripts/scan_inputs.py input/ -o reference/input_manifest.json
```

Detects: `pbi_model`, `csv_schema_dump`, `mapping_json`, `dbx_schema`, `sql_ddl`, `sql_query_output`, `csv_data`, `sample_report`, `databricks_config`, `unknown`.

**Present classification to the user and ask:**
1. "I found these files. Here is what each appears to be: [list]. Is this correct?"
2. "How should I use each file?"
3. If no Databricks schema info found: offer schema suggestion queries (Step 5).

**Do not proceed until the user confirms.**

### Step 2: Parse Power BI Models

```bash
python scripts/parse_pbi_model.py input/<file> -o reference/pbi_model.json
# or batch mode:
python scripts/parse_pbi_model.py input/ -o reference/pbi_model.json
```

The parser handles any file extension -- tries ZIP, JSON, and TMDL detection in sequence.

### Step 3: Validate Catalog Accessibility

**Immediately after parsing**, extract all data source references from the PBI model -- server names, database/catalog names, and schema names found in `partitions[].source` (connection strings, M expressions, or `Sql.Database` calls).

Cross-reference these against what is available:

1. Schema files provided in `input/` (DDL, CSV schema dump, JSON schema)
2. Databricks config in `input/` (host/token/catalog)
3. Live MCP access (test with `execute_sql`)

**If MCP is available**, test accessibility for each referenced catalog:

```sql
SELECT 1 FROM <catalog>.information_schema.tables LIMIT 1;
```

Launch parallel `shell` subagents when multiple catalogs need testing. See [REFERENCE.md](REFERENCE.md) Gap 14.

**If a referenced catalog is inaccessible AND no schema dump was provided**, raise a warning to the user immediately:

> "The PBI model references data from `<catalog>.<schema>`, but I have no schema information and cannot access this catalog. Please provide one of:
> 1. A schema dump (CSV, DDL, or JSON) in the `input/` folder
> 2. Databricks credentials with access to this catalog
> 3. Run this query and paste the output: `SELECT table_name, column_name, data_type FROM <catalog>.information_schema.columns WHERE table_schema = '<schema>'`"

**Do not proceed past Step 5 without resolving all catalog gaps.** ERD/domain generation (Step 8) can proceed with PBI-only data, but schema comparison and metric view creation require catalog access or schema dumps.

Update `reference/catalog_resolution.md` with accessibility status for each referenced catalog.

Probe available catalogs before schema extraction. See [REFERENCE.md](REFERENCE.md) Gap 5 for detailed strategy.

First, list all catalogs:

```sql
SELECT catalog_name FROM system.information_schema.catalogs ORDER BY catalog_name;
```

Then verify table existence. **When multiple candidate catalogs exist** (e.g., `analytics`, `fc_analytics`), launch parallel `shell` subagents -- one per catalog -- to probe concurrently:

```
-- Each subagent runs this against its assigned catalog:
SELECT table_name FROM <catalog>.information_schema.tables WHERE table_schema = '<schema>';
```

Use `CallMcpTool` with `execute_sql` on the `user-databricks` MCP server. See [REFERENCE.md](REFERENCE.md) Gap 13 Pattern A for the subagent prompt template.

Produce `reference/catalog_resolution.md` documenting primary catalog, fallback catalog, and table locations.

### Step 5: Extract or Ingest Databricks Schema

If no schema was found in `input/`, suggest these queries:

```sql
SELECT table_name, column_name, data_type, is_nullable, comment
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
ORDER BY table_name, ordinal_position;
```

**Programmatic extraction**: Use `CallMcpTool` with `get_table_details` on the `user-databricks` server (`catalog`, `schema` required). When extracting from **multiple catalogs or schemas**, launch parallel `shell` subagents -- one per catalog/schema pair. See [REFERENCE.md](REFERENCE.md) Gap 13 Pattern B.

For cross-schema environments, see [REFERENCE.md](REFERENCE.md) Gap 9.

Tell the user: *"Paste output in chat, save to input/, or provide catalog.schema for programmatic extraction."*

Also accept DDL files and CSV schema dumps as schema sources.

### Step 6: Build Mapping Layer

Choose the appropriate mapping approach based on schema comparison:

- **Direct (A)**: Names match -- no mapping needed
- **View layer (B)**: Create aliasing views
- **Mapping document (C)**: Generate JSON mapping from comparison output
- **Intermediate mapping (D)**: Extract Power Query M renames, build two-layer mapping (`pbi_column -> dbx_column`), use three-layer only where applicable (`pbi_column -> m_query_column -> dbx_column`). See [REFERENCE.md](REFERENCE.md) Gap 1.

```bash
python scripts/compare_schemas.py \
  reference/pbi_model.json reference/dbx_schema.json \
  -o reference/schema_comparison.md --json --mapping reference/intermediate_mapping.json
```

### Step 7: Column Gap Analysis

After schema comparison, review `reference/column_gap_analysis.md` for DBX-only columns. Flag potential discriminators (low-cardinality columns like `status`, `category`, `result_type`). See [REFERENCE.md](REFERENCE.md) Gap 3.

### Step 8: ERD and Domain Modeling

```bash
python scripts/generate_erd.py reference/pbi_model.json -o reference/
```

Produces `reference/erd.md` and `reference/domains.md`. Review with user before proceeding.

### Step 9: KPI Definitions

Build structured KPI definitions in `kpi/kpi_definitions.md`. See [REFERENCE.md](REFERENCE.md) Gap 7 for template. Each KPI includes: business context, DAX formula, SQL equivalent, source table, format, data gaps, and domain.

```bash
bash scripts/init_project.sh --kpi
```

### Step 10: Data Discovery Queries

Auto-generate SQL queries for unknown filter values, value distributions, date ranges, and null rates. Save to `reference/data_discovery_queries.sql`. See [REFERENCE.md](REFERENCE.md) Gap 4.

**Execute directly** using MCP tools when Databricks access is available:

- **Same catalog** (preferred): Use `execute_sql_multi` to run all discovery queries in a single batched call with automatic parallelism (up to 4 workers). See [REFERENCE.md](REFERENCE.md) Gap 13 Pattern C.
- **Cross-catalog**: Launch parallel `shell` subagents, each running `execute_sql` against its catalog.

If no Databricks access, present queries to the user to run manually and ingest results back.

### Step 11: Optimize Query Access Layer

Before building metric views, assess each KPI's query complexity and the underlying table characteristics to decide the optimal serving strategy. Produce `reference/query_optimization_plan.md`. See [REFERENCE.md](REFERENCE.md) Gap 12 for detailed criteria.

**Assess each KPI / domain along these dimensions:**

| Factor | What to Check |
|--------|---------------|
| Table size | Row count and data size from `DESCRIBE DETAIL` or schema metadata |
| Query complexity | Number of joins, subqueries, window functions, or CASE expressions |
| Grain mismatch | Fact table grain vs. report grain (e.g., transaction-level vs. monthly) |
| Filter patterns | High-selectivity filters (date range, region) vs. full-table scans |
| Refresh frequency | Real-time vs. daily/hourly vs. weekly |

**Decision matrix:**

| Condition | Serving Strategy |
|-----------|-----------------|
| Simple aggregation, table < 100 GB, few joins | Standard metric view |
| Complex joins or expensive aggregation, table 100 GB - 1 TB | Materialized view with scheduled refresh |
| Very large table (> 1 TB) or grain mismatch requiring pre-aggregation | Gold-layer aggregate table + metric view on top |
| Mixed: some KPIs simple, some complex | Split across strategies per domain |

**Materialized view pattern with incremental refresh:**

```sql
CREATE OR REPLACE MATERIALIZED VIEW <catalog>.<schema>.monthly_sales_agg
AS
SELECT
  date_trunc('month', order_date) AS order_month,
  region,
  SUM(total_amount) AS total_sales,
  COUNT(1) AS order_count
FROM <catalog>.<schema>.sales_fact
GROUP BY ALL;

ALTER MATERIALIZED VIEW <catalog>.<schema>.monthly_sales_agg
  SCHEDULE CRON '0 2 * * *' AT TIME ZONE 'UTC';
```

The metric view then references the materialized view instead of the raw fact table, reducing query cost and latency.

**Collect table sizing data** using `DESCRIBE DETAIL <table>` for each candidate table. When assessing multiple tables, launch parallel `shell` subagents to run `DESCRIBE DETAIL` concurrently via the `execute_sql` MCP tool. See [REFERENCE.md](REFERENCE.md) Gap 13 Pattern D.

**Output:** `reference/query_optimization_plan.md` documenting the chosen strategy per domain/KPI with rationale.

### Step 12: Check Existing Metric Views

**Before building metric views**, check whether any KPIs already exist in metric views in the target catalog/schema. This prevents duplication and enables incremental updates. See [REFERENCE.md](REFERENCE.md) Gap 15.

**If Databricks access is available**, discover existing metric views:

```sql
SELECT table_name, view_definition
FROM <catalog>.information_schema.views
WHERE table_schema = '<schema>'
  AND view_definition LIKE '%WITH METRICS%';
```

For each discovered metric view, use `manage_metric_views` MCP tool to inspect its measures:

```
CallMcpTool: server="user-databricks", toolName="manage_metric_views"
Arguments: {"action": "describe", "full_name": "<catalog>.<schema>.<view_name>"}
```

**Compare** existing measures against KPI definitions from Step 9. For each KPI, classify as:

| Classification | Condition | Action |
|---------------|-----------|--------|
| `new` | Measure name not found in any existing metric view | CREATE new metric view |
| `update` | Measure name exists but SQL expression differs | ALTER existing metric view |
| `exists` | Measure name and expression match | Skip -- already deployed |

**Output:** `reference/existing_metric_views.md` documenting the classification per KPI and listing any existing views that will be modified.

**If no Databricks access**, skip this step and treat all KPIs as `new`.

### Step 13: Build or Update Metric Views

Based on the classification from Step 12, handle each domain's metric views:

- **New KPIs**: Create metric views with `CREATE OR REPLACE VIEW ... WITH METRICS`
- **Updated KPIs**: Use `ALTER VIEW` or `manage_metric_views` with `action: "alter"` to update existing definitions
- **Existing KPIs**: Skip -- log in deployment checklist as "already deployed"

```sql
CREATE OR REPLACE VIEW <catalog>.<schema>.domain_metrics
WITH METRICS LANGUAGE YAML AS $$
  version: 1.1
  source: <catalog>.<schema>.fact_table
  dimensions:
    - name: Dimension Name
      expr: column_expression
  measures:
    - name: Measure Name
      expr: AGG_FUNC(column)
      comment: "DAX: ORIGINAL_FORMULA"
$$;
```

Create folders on demand: `bash scripts/init_project.sh --models`

Use the `databricks-metric-views` skill for YAML syntax details.

### Step 14: Sample Report Analysis

If `input/` contains `.docx`, `.pdf`, `.png`, `.jpg`, `.xlsx`, or `.pptx` files, analyze them to extract KPI names, formatting, chart types, narrative templates, and disclaimers. Produce `reference/report_analysis.md`. See [REFERENCE.md](REFERENCE.md) Gap 8.

### Step 15: Output Path

**Path A: PBI Reconnection** -- Update Power Query M formulas to use `Databricks.Catalogs()`. Use DirectQuery for facts, Dual for dimensions. Parameterize `ServerHostName`/`HTTPPath`.

**Path B: Databricks-Native Report** -- Read `databricks-aibi-dashboards` skill. Build report spec and email template in `planreport/`. See [REFERENCE.md](REFERENCE.md) Gaps 6 and 10.

```bash
bash scripts/init_project.sh --report
```

### Step 16: Deployment Checklist

Generate `reference/deployment_checklist.md` with ordered steps from local artifacts to running report. See [REFERENCE.md](REFERENCE.md) Gap 11.

## Auxiliary Steps (run as needed)

- **Multi-Model Handling** (Step 5 in old workflow): Process each model/schema pair separately. Track shared dimensions.
- **Duplicate KPI Report**: After all models analyzed, identify duplicates. Save to `reference/kpi_duplicates_report.md`.
- **Performance Assessment** (requires DBX schema): Flag tables >100 GB or >1B rows. Consider materialized metric views.
- **Gold Layer**: Define ERD in `models/gold_layer_erd.md`. Use `spark-declarative-pipelines` and `databricks-jobs` skills.

## Related Skills

The agent should discover and leverage these skills as needed throughout the workflow:

- **`databricks-metric-views`** -- YAML syntax, MCP `manage_metric_views` tool
- **`databricks-dbsql`** -- Advanced SQL, pipe syntax, AI functions
- **`databricks-unity-catalog`** -- System tables, volume operations
- **`databricks-aibi-dashboards`** -- AI/BI dashboard creation
- **`databricks-genie`** / **`genie-space-curation`** -- Genie Spaces
- **`spark-declarative-pipelines`** -- Gold-layer pipelines
- **`databricks-jobs`** -- Job scheduling
- **`databricks-asset-bundles`** -- Multi-environment deployment
- **`databricks-config`** -- Workspace authentication
- **`databricks-python-sdk`** -- SDK and REST API
- **`databricks-docs`** -- Documentation lookup

Also check for MCP tools (e.g., `execute_sql`, `execute_sql_multi`, `manage_metric_views`, `get_table_details`).

## Subagent Parallelization

Use `Task` subagents to parallelize work when multiple catalogs, schemas, or tables must be probed independently. This accelerates Steps 3, 4, 5, 10, and 11.

### When to Use Subagents vs. `execute_sql_multi`

| Scenario | Approach |
|----------|----------|
| Multiple queries within **one catalog** | `execute_sql_multi` MCP tool (built-in parallelism, up to 4 workers) |
| Probing **across catalogs** (each needs its own catalog context) | Launch parallel `shell` subagents (max 4 concurrent) |
| Mixed: some cross-catalog, some same-catalog | Combine both -- subagents for cross-catalog, `execute_sql_multi` within each |

### Pattern: Parallel Shell Subagents

Launch up to 4 concurrent `Task` calls with `subagent_type="shell"`. Each subagent executes `CallMcpTool` against the `user-databricks` MCP server.

Example prompt for a catalog-probing subagent:

```
Use the CallMcpTool to call the "execute_sql" tool on the "user-databricks" server.
Arguments: {"sql_query": "SELECT table_name FROM <catalog>.information_schema.tables WHERE table_schema = '<schema>'"}
Return the full result set.
```

### Pattern: Batch SQL with `execute_sql_multi`

For multiple independent queries within the same catalog, use the `execute_sql_multi` MCP tool in a single call. It automatically parallelizes independent statements (up to `max_workers` default 4).

```
CallMcpTool: server="user-databricks", toolName="execute_sql_multi"
Arguments: {
  "sql_content": "<all queries separated by ;>",
  "catalog": "<catalog>",
  "schema": "<schema>",
  "max_workers": 4
}
```

### Where Subagents Are Used in This Workflow

- **Step 3** -- Test catalog accessibility across multiple catalogs in parallel
- **Step 4** -- Probe multiple candidate catalogs in parallel
- **Step 5** -- Extract schema from multiple catalogs/schemas in parallel
- **Step 10** -- Run data discovery queries (prefer `execute_sql_multi` for same-catalog batch)
- **Step 11** -- Run `DESCRIBE DETAIL` on multiple tables in parallel for sizing

## Common Issues

| Issue | Resolution |
|-------|------------|
| No Databricks schema available | Suggest INFORMATION_SCHEMA queries (Step 5) or accept DDL/CSV |
| Column names differ between PBI and DBX | Use Scenario B (views) or D (intermediate mapping) |
| DBX-only columns not in PBI model | Check column_gap_analysis.md for discriminators |
| Multiple catalogs/schemas | Use catalog resolution (Step 4) and cross-schema probing |
| Power Query M renames columns | Extract from `partitions[].source.expression`, build intermediate mapping |
| Sample report provided but no PBI model | Reverse-engineer KPIs from report analysis |
| fc_ prefix on catalog names | Try both with and without prefix during catalog resolution |
| Slow metric view queries on large tables | Use materialized views with scheduled refresh (Step 11) |
| Grain mismatch between fact table and report | Pre-aggregate into gold-layer table, point metric view at aggregate |
| KPIs already exist in metric views | Step 12 detects existing measures -- propose ALTER instead of CREATE |
| PBI references catalog with no access or schema | Step 3 raises early warning -- provide schema dump or credentials |

## Detailed Reference

- For detailed patterns for all gaps, see [REFERENCE.md](REFERENCE.md)
- For input/output examples, see [EXAMPLES.md](EXAMPLES.md)
- For the full 7-step methodology, see [approach.md](approach.md)
