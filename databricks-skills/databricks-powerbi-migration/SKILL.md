---
name: databricks-powerbi-migration
description: "Converts Power BI semantic models to Databricks metric views. Handles schema assessment, ERD/domain generation, intermediate mapping layers, DAX-to-SQL translation, query access optimization (materialized views, incremental refresh), KPI definitions, data discovery, report replication, and deployment checklists. Use when migrating Power BI to Databricks, converting DAX to metric views, building metric views from semantic models, or when the user mentions Power BI, PBI, semantic model, DAX migration, or PBI-to-Databricks."
---

# PowerBI to Databricks Conversion

Convert Power BI semantic models into Databricks metric views, Delta tables, and associated assets.

**Always run in Plan mode.** Prompt the user for direction when uncertain.

---

## Critical Rules (always follow)

- **MUST** run in Plan mode — present a plan before making changes
- **MUST** scan and confirm all inputs with the user before proceeding past Step 2
- **MUST** raise early catalog access warnings — do not silently skip missing catalogs
- **MUST** check for existing metric views before creating new ones (Step 12)

---

## Prerequisites

- Python 3.10+
- *(Optional)* Databricks CLI profile configured with PAT authentication
- *(Optional)* `databricks-sdk` installed (`pip install databricks-sdk`)

---

## Quick Start

```bash
bash scripts/init_project.sh
# Place all files in input/ (PBI models, DDLs, mappings, schema dumps, sample reports, configs)
python scripts/scan_inputs.py input/ -o reference/input_manifest.json
# Present results to user, confirm usage, then follow the checklist below
```

---

## Required Steps

Copy this checklist and verify each item:

```
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

---

## Migration Scenarios

Determined by `scripts/compare_schemas.py` when Databricks schema information is available:

- **Scenario A** (names match): Repoint Power BI connection directly to Databricks
- **Scenario B** (names differ, model same): Create aliasing views in Databricks, then repoint
- **Scenario C** (names and model differ): Generate views from a JSON mapping document
- **Scenario D** (intermediate mapping layer): PBI semantic layer → mapping (Power Query M renames) → Databricks physical layer. See [3-mapping-layer.md](3-mapping-layer.md).

If no Databricks schema is available, skip comparison and proceed to ERD/domain generation.

---

## Detailed Guides

**Input scanning & model parsing**: Use [1-input-scanning.md](1-input-scanning.md) for scanning, classifying, and parsing all input files including PBI models in any format. (Keywords: scan_inputs, parse_pbi_model, TMDL, PBIX, PBIT, BIM, file classification, csv_schema_dump)

**Catalog resolution & schema extraction**: See [2-catalog-resolution.md](2-catalog-resolution.md) for validating catalog access, probing catalogs, resolving fc_ prefixes, and extracting Databricks schemas. (Keywords: catalog validation, INFORMATION_SCHEMA, schema dump, DDL, fc_ prefix, cross-schema, early warning, accessibility)

**Mapping layer & column gap analysis**: See [3-mapping-layer.md](3-mapping-layer.md) for choosing between direct/view/mapping-doc/intermediate-mapping approaches and analyzing DBX-only columns. (Keywords: compare_schemas, column gap, Power Query M renames, aliasing views, Scenario A/B/C/D, discriminator columns, intermediate mapping)

**ERD, KPI definitions & data discovery**: See [4-erd-kpi-discovery.md](4-erd-kpi-discovery.md) for generating ERDs, building structured KPI definitions from DAX, and generating data discovery queries. (Keywords: generate_erd, domains, DAX translation, kpi_definitions, data discovery, null rate, discriminator, SAMEPERIODLASTYEAR)

**Query access optimization**: Use [5-query-optimization.md](5-query-optimization.md) for assessing table size, join complexity, and grain mismatch to choose standard views, materialized views, or gold-layer aggregates. (Keywords: materialized view, incremental refresh, grain mismatch, table size, query complexity score, serving strategy, DESCRIBE DETAIL)

**Metric views — check & build**: See [6-metric-views.md](6-metric-views.md) for detecting existing metric views, classifying KPIs as new/update/exists, and creating or altering metric views. (Keywords: manage_metric_views, WITH METRICS, CREATE OR REPLACE VIEW, ALTER VIEW, KPI classification, existing metric views)

**Report analysis & output paths**: See [7-report-output.md](7-report-output.md) for analyzing sample reports and choosing between PBI reconnection (Path A) or Databricks-native dashboards (Path B). (Keywords: report analysis, Path A, Path B, PBI reconnection, Databricks.Catalogs, AI/BI dashboard, report spec, email template, DirectQuery)

**Deployment checklist**: Use [8-deployment.md](8-deployment.md) for generating the ordered deployment checklist from local artifacts to a running report. (Keywords: deployment checklist, pre-deployment, post-deployment, grant SELECT, validate metric views)

**Subagent parallelization**: See [9-subagent-patterns.md](9-subagent-patterns.md) for patterns to parallelize catalog probing, schema extraction, and data discovery using shell subagents and execute_sql_multi. (Keywords: parallel subagents, execute_sql_multi, catalog probing, cross-catalog, parallel schema extraction, Task subagent)

---

## Workflow

1. Determine the task type:

   **Starting a new migration?** → Start with [1-input-scanning.md](1-input-scanning.md)
   **Catalog inaccessible or names need resolving?** → Read [2-catalog-resolution.md](2-catalog-resolution.md)
   **Column names differ between PBI and DBX?** → Read [3-mapping-layer.md](3-mapping-layer.md)
   **Building KPI definitions or ERD?** → Read [4-erd-kpi-discovery.md](4-erd-kpi-discovery.md)
   **Large tables or slow queries?** → Read [5-query-optimization.md](5-query-optimization.md)
   **Creating or updating metric views?** → Read [6-metric-views.md](6-metric-views.md)
   **Analyzing sample report or choosing output path?** → Read [7-report-output.md](7-report-output.md)
   **Ready to deploy?** → Read [8-deployment.md](8-deployment.md)
   **Need to probe multiple catalogs in parallel?** → Read [9-subagent-patterns.md](9-subagent-patterns.md)

2. Follow the instructions in the relevant guide

3. Repeat for next task type

---

## Common Issues

| Issue | Resolution |
|-------|------------|
| No Databricks schema available | Suggest INFORMATION_SCHEMA queries or accept DDL/CSV — see [2-catalog-resolution.md](2-catalog-resolution.md) |
| Column names differ between PBI and DBX | Use Scenario B (views) or D (intermediate mapping) — see [3-mapping-layer.md](3-mapping-layer.md) |
| DBX-only columns not in PBI model | Check column_gap_analysis.md for discriminators — see [3-mapping-layer.md](3-mapping-layer.md) |
| Multiple catalogs/schemas | Use catalog resolution and parallel probing — see [2-catalog-resolution.md](2-catalog-resolution.md) |
| Power Query M renames columns | Extract renames, build intermediate mapping — see [3-mapping-layer.md](3-mapping-layer.md) |
| Sample report but no PBI model | Reverse-engineer KPIs from report analysis — see [7-report-output.md](7-report-output.md) |
| fc_ prefix on catalog names | Try with and without prefix during resolution — see [2-catalog-resolution.md](2-catalog-resolution.md) |
| Slow metric view queries on large tables | Use materialized views with scheduled refresh — see [5-query-optimization.md](5-query-optimization.md) |
| Grain mismatch between fact table and report | Pre-aggregate into gold-layer table — see [5-query-optimization.md](5-query-optimization.md) |
| KPIs already exist in metric views | Detect before creating, propose ALTER — see [6-metric-views.md](6-metric-views.md) |
| PBI references catalog with no access or schema | Raise early warning, request schema dump — see [2-catalog-resolution.md](2-catalog-resolution.md) |

---

## Related Skills

- **`databricks-metric-views`** — YAML syntax, MCP `manage_metric_views` tool
- **`databricks-dbsql`** — Advanced SQL, pipe syntax, AI functions
- **`databricks-unity-catalog`** — System tables, volume operations
- **`databricks-aibi-dashboards`** — AI/BI dashboard creation
- **`databricks-genie`** / **`genie-space-curation`** — Genie Spaces
- **`spark-declarative-pipelines`** — Gold-layer pipelines
- **`databricks-jobs`** — Job scheduling
- **`databricks-asset-bundles`** — Multi-environment deployment
- **`databricks-config`** — Workspace authentication
- **`databricks-python-sdk`** — SDK and REST API
- **`databricks-docs`** — Documentation lookup

Also check for MCP tools (e.g., `execute_sql`, `execute_sql_multi`, `manage_metric_views`, `get_table_details`).

---

## Official Documentation

- **[Unity Catalog Metric Views](https://docs.databricks.com/en/metric-views/)** — YAML syntax, joins, materialization, MEASURE() function
- **[Adopting Power BI semantic models on Databricks SQL](https://medium.com/dbsql-sme-engineering/adopting-power-bi-semantic-models-on-databricks-sql-6efb4b0f78c9)** — Migration walkthrough
- **[Power BI on Databricks Best Practices Cheat Sheet](https://www.databricks.com/sites/default/files/2025-04/2025-04-power-bi-on-databricks-best-practices-cheat-sheet.pdf)** — Best practices reference
- **[Parameterizing Databricks SQL Connections in Power BI](https://medium.com/@kyle.hale/parameterizing-your-databricks-sql-connections-in-power-bi-fd7aae20863e)** — ServerHostName/HTTPPath parameterization
