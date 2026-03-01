# PowerBI to Databricks Conversion Skill

Convert Power BI semantic models into Databricks metric views, governed by Unity Catalog. This skill automates input scanning, model parsing, ERD/domain generation, schema comparison, KPI definitions, data discovery, query access optimization (materialized views, incremental refresh), report replication, and deployment checklists.

## What This Skill Does

This skill guides an AI agent (or a human developer) through migrating Power BI semantic models to Databricks. It handles:

- **Input scanning and classification** -- reads every file in `input/`, classifies by content, and asks the user how to use each
- **Power BI model parsing** from any format (PBIT, PBIX, BIM, TMDL, or any extension -- detected by content)
- **ERD generation** with Mermaid and text diagrams, PK/FK inference, and relationship visualization
- **Domain inference** from display folders, naming patterns, and table connectivity
- **Catalog resolution** in multi-catalog environments with `fc_` prefix handling
- **Schema extraction** from Databricks Unity Catalog tables *(optional)*
- **CSV schema dump detection** for INFORMATION_SCHEMA-style CSV exports
- **Intermediate mapping layers** extracting Power Query M renames (Scenario D)
- **Column gap analysis** flagging DBX-only columns and discriminators
- **Data discovery queries** for unknown filter values, distributions, and null rates
- **DAX-to-SQL translation** of measures into Databricks metric view YAML
- **Query access optimization** assessing complexity, table size, and grain to choose standard views, materialized views, or gold-layer aggregates
- **Structured KPI definitions** with business context, formulas, and data gaps
- **Sample report analysis** reverse-engineering KPIs from documents/images
- **Report replication** via Databricks-native AI/BI dashboards (Path B)
- **KPI consolidation** and duplicate detection across models and domains
- **Deployment checklists** for going from local artifacts to running reports
- **Performance assessment** and optional gold-layer pipeline generation *(optional)*
- **Power BI reconnection** guidance with best practices (Path A)

## Skill Files

| File | Purpose |
|------|---------|
| [SKILL.md](SKILL.md) | Concise workflow checklist with progressive disclosure |
| [REFERENCE.md](REFERENCE.md) | Detailed patterns for all 12 gaps identified from real-world testing |
| [EXAMPLES.md](EXAMPLES.md) | Input/output examples for key patterns |
| [approach.md](approach.md) | Full 7-step methodology reference |
| [README.md](README.md) | This file -- comprehensive documentation |

## Prerequisites

| Requirement | Details | Required? |
|---|---|---|
| Python | 3.10 or later | Yes |
| Power BI model export | Any format: `.pbit`, `.pbix`, `.bim`, TMDL directory, or JSON with model structure | Yes |
| `databricks-sdk` | `pip install databricks-sdk` | Only for live Databricks schema extraction |
| Databricks CLI | Profile configured with PAT authentication (`~/.databrickscfg`) | Only for live Databricks schema extraction |

## Inputs

All input files go into a single flat `input/` folder. The agent scans and classifies every file by content before proceeding.

| Input | Format | Description |
|---|---|---|
| **Power BI model** | `.pbit`, `.pbix`, `.bim`, TMDL, or JSON | Exported semantic model. Detected by content, not extension. |
| **CSV schema dump** *(optional)* | CSV with `table_name`, `column_name`, `data_type` headers | Schema metadata exported from INFORMATION_SCHEMA queries |
| **Databricks schema** *(optional)* | JSON, SQL DDL, or query output | Schema information from Databricks |
| **Mapping document** *(optional)* | JSON with `mappings` array | Column-level mappings (Scenario C or D) |
| **Sample report** *(optional)* | `.docx`, `.pdf`, `.png`, `.jpg`, `.xlsx`, `.pptx` | Sample report to reverse-engineer KPIs and layout |
| **Databricks config** *(optional)* | YAML with `host`/`token` keys | Workspace URL, PAT, warehouse, catalog, schema |
| **CSV data** *(optional)* | CSV | Headers can inform schema |

### How to Export Power BI Models

**Option 1: PBIT file (recommended)**
1. Open your report in Power BI Desktop.
2. File > Export > Power BI Template (`.pbit`).
3. Place in `input/`.

**Option 2: PBIX file**
The parser extracts the DataModelSchema from `.pbix` files directly. Place in `input/`.

**Option 3: BIM file**
1. Open the model in [Tabular Editor](https://tabulareditor.com/).
2. File > Save As > `model.bim`.
3. Place in `input/`.

**Option 4: TMDL directory**
1. Enable TMDL in Power BI Desktop (Options > Preview Features).
2. File > Save As > TMDL format.
3. Place the directory in `input/`.

**Option 5: Manual description**
Provide table names, column names with types, DAX measures, and relationships.

## Schema Suggestion Queries

When no Databricks schema is available, the agent suggests these queries:

```sql
-- Full column schema (recommended)
SELECT table_name, column_name, data_type, is_nullable, comment
FROM <catalog>.information_schema.columns
WHERE table_schema = '<schema>'
ORDER BY table_name, ordinal_position;

-- Cross-schema comparison
SELECT table_schema, table_name, column_name, data_type
FROM <catalog>.information_schema.columns
WHERE table_schema IN ('<schema_a>', '<schema_b>')
ORDER BY table_schema, table_name, ordinal_position;

-- Per-table detail
DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table_name>;
```

## Project Structure

Run the init script to create the base structure:

```bash
# Minimal base (input/, reference/, temp/)
bash scripts/init_project.sh

# With metric view output folders
bash scripts/init_project.sh --models

# With KPI definitions folder
bash scripts/init_project.sh --kpi

# With report planning folder
bash scripts/init_project.sh --report

# Everything
bash scripts/init_project.sh --all

# In a specific directory
bash scripts/init_project.sh /path/to/project --all
```

Full structure:

```
project-root/
├── input/                             # ALL user-provided files
│   ├── model.pbix                     #   Power BI file (any extension)
│   ├── mapping.json                   #   Optional mapping document
│   ├── schema_dump.sql                #   Optional DDL or DESCRIBE output
│   ├── schema_export.csv              #   Optional CSV schema dump
│   ├── sample_report.pdf              #   Optional sample report
│   └── databricks.yml                 #   Optional Databricks config
├── reference/                         # Generated analysis and documentation
│   ├── input_manifest.json            #   File classification (from scan_inputs.py)
│   ├── pbi_model.json                 #   Parsed Power BI model
│   ├── erd.md                         #   ERD -- Mermaid + text
│   ├── domains.md                     #   Domain groupings
│   ├── catalog_resolution.md          #   Catalog probe results
│   ├── dbx_schema.json                #   Databricks schema (if provided)
│   ├── schema_comparison.md           #   Comparison report
│   ├── column_gap_analysis.md         #   DBX-only columns with discriminator flags
│   ├── data_discovery_queries.sql     #   Generated discovery queries
│   ├── query_optimization_plan.md     #   Serving strategy per domain/KPI
│   ├── report_analysis.md             #   Sample report analysis
│   ├── kpi_duplicates_report.md       #   Duplicate KPI analysis
│   ├── deployment_checklist.md        #   Ordered deployment steps
│   └── model_<name>_analysis.md       #   Per-model analysis
├── kpi/                               # [--kpi] KPI definitions
│   └── kpi_definitions.md             #   Structured KPI definitions by domain
├── models/                            # [--models] Metric view output
│   ├── metric_views/                  #   Metric view SQL by domain
│   ├── mapping_documents/             #   Generated mapping templates
│   └── gold_layer_erd.md              #   Gold-layer ERD (if needed)
├── planreport/                        # [--report] Report planning artifacts
│   ├── report_spec.md                 #   Visual layout, chart specs, narratives
│   ├── email_template.md              #   Distribution specs (recipients, schedule)
│   └── deployment_config.yml          #   Job schedule, warehouse, notifications
├── notebooks/                         # [--gold] Gold-layer pipeline notebooks
├── temp/                              # Working/throwaway files (gitignored)
└── .gitignore
```

### Folder Descriptions

| Folder | Purpose | Created | Persistence |
|---|---|---|---|
| `input/` | All user-provided files | Always | Permanent |
| `reference/` | All analysis outputs, documentation | Always | Permanent |
| `temp/` | Scratch work, intermediate analysis | Always | Disposable |
| `kpi/` | Structured KPI definitions by domain | `--kpi` | Permanent |
| `models/metric_views/` | Final metric view SQL definitions | `--models` | Permanent |
| `models/mapping_documents/` | Generated mapping templates | `--models` | Permanent |
| `planreport/` | Report specs, email templates, deployment config | `--report` | Permanent |
| `notebooks/` | Databricks notebooks for gold-layer pipelines | `--gold` | Permanent |

## Scripts

All scripts live in `scripts/`.

### `init_project.sh`

Scaffolds the project folder structure.

```bash
bash scripts/init_project.sh [project_dir] [FLAGS]
```

Flags: `--models`, `--gold`, `--kpi`, `--report`, `--all`. Without flags, creates `input/`, `reference/`, `temp/`, `.gitignore`.

### `scan_inputs.py`

Scans every file in the `input/` directory and classifies each by content.

```bash
python scripts/scan_inputs.py input/ [-o reference/input_manifest.json]
```

**Dependencies:** None (Python stdlib only).

**Classifications:** `pbi_model`, `csv_schema_dump`, `mapping_json`, `dbx_schema`, `sql_ddl`, `sql_query_output`, `csv_data`, `sample_report`, `databricks_config`, `unknown`.

**Output:** JSON manifest with path, type, format, and details for each file.

### `parse_pbi_model.py`

Parses Power BI model exports into structured JSON. Detects format by content -- not file extension.

```bash
python scripts/parse_pbi_model.py \
  input/model.pbix -o reference/pbi_model.json
```

**Dependencies:** None (Python stdlib only).

**Content detection order:** ZIP archive, JSON structure, TMDL text, TMDL directory.

### `generate_erd.py`

Generates an ERD and domain analysis from the parsed Power BI model JSON.

```bash
python scripts/generate_erd.py \
  reference/pbi_model.json -o reference/
```

**Dependencies:** None (Python stdlib only).

**Outputs:** `reference/erd.md` (Mermaid + text ERD), `reference/domains.md` (domain groupings).

### `extract_dbx_schema.py`

Extracts metadata from Databricks Unity Catalog.

```bash
python scripts/extract_dbx_schema.py \
  my_catalog my_schema -o reference/dbx_schema.json [--profile PROD]
```

**Dependencies:** `databricks-sdk`.

### `compare_schemas.py`

Compares Power BI model against Databricks schema, classifies migration scenario (A, B, C, or D), and produces column gap analysis.

```bash
python scripts/compare_schemas.py \
  reference/pbi_model.json reference/dbx_schema.json \
  -o reference/schema_comparison.md --json \
  --mapping reference/intermediate_mapping.json \
  --gap-analysis reference/column_gap_analysis.md
```

**Dependencies:** None (Python stdlib only).

**New flags:**
- `--mapping <path>`: Intermediate mapping JSON for Scenario D (Power Query M renames)
- `--gap-analysis <path>`: Output path for column gap analysis (defaults to `reference/column_gap_analysis.md`)

**Outputs:**
- `reference/schema_comparison.md` -- Comparison report with scenario classification
- `reference/column_gap_analysis.md` -- DBX-only columns grouped by table with discriminator flagging

## Workflow Summary

```
1. Place all files in input/               # PBI models, DDLs, mappings, configs, reports
                |
2. scan_inputs.py                          # Classify every file (incl. CSV schema, reports)
                |
3. Present to user, ask how to use each    # DO NOT PROCEED without confirmation
                |
4. parse_pbi_model.py                      # Parse -> reference/pbi_model.json
                |
       +--------+--------+
       |                  |
  [If schema avail]   [Always]
       |                  |
5. Catalog resolution  6. generate_erd.py
   + compare_schemas.py      |
   + column_gap_analysis  reference/erd.md
       |               reference/domains.md
       +--------+---------+
                |
7. Build KPI definitions                   # -> kpi/kpi_definitions.md
                |
8. Data discovery queries                  # -> reference/data_discovery_queries.sql
                |
9. Optimize query access layer             # -> reference/query_optimization_plan.md
   (standard view / materialized view /    #    assess size, grain, complexity
    gold-layer aggregate)                  #    create materialized views if needed
                |
10. Build metric views                     # -> models/metric_views/*.sql
                |
11. Analyze sample report (if provided)    # -> reference/report_analysis.md
                |
       +--------+--------+
       |                  |
   [Path A]            [Path B]
       |                  |
12a. PBI reconnection  12b. Databricks-native report
       |                  # -> planreport/
       +--------+---------+
                |
13. Deployment checklist                   # -> reference/deployment_checklist.md
```

## Outputs

| Output | Location | Description | Requires Databricks? |
|---|---|---|---|
| Input manifest | `reference/input_manifest.json` | Classification of all input files | No |
| ERD | `reference/erd.md` | Mermaid + text ER diagram | No |
| Domain definitions | `reference/domains.md` | Business domain groupings | No |
| Catalog resolution | `reference/catalog_resolution.md` | Catalog/schema probe results | Yes |
| Schema comparison | `reference/schema_comparison.md` | Table/column match analysis | Yes |
| Column gap analysis | `reference/column_gap_analysis.md` | DBX-only columns with discriminator flags | Yes |
| Data discovery queries | `reference/data_discovery_queries.sql` | SQL for filter values, distributions | No (uses placeholders) |
| Query optimization plan | `reference/query_optimization_plan.md` | Serving strategy per domain/KPI | No (uses placeholders) |
| Report analysis | `reference/report_analysis.md` | KPIs/layout from sample report | No |
| KPI definitions | `kpi/kpi_definitions.md` | Structured KPI definitions by domain | No |
| Metric view SQL files | `models/metric_views/*.sql` | One file per business domain | No (uses placeholders) |
| KPI duplicates report | `reference/kpi_duplicates_report.md` | Cross-domain duplicate analysis | No |
| Report spec | `planreport/report_spec.md` | Visual layout for native report | No |
| Email template | `planreport/email_template.md` | Distribution specs | No |
| Deployment config | `planreport/deployment_config.yml` | Job schedule, warehouse | No |
| Deployment checklist | `reference/deployment_checklist.md` | Ordered deployment steps | No |
| Mapping documents | `models/mapping_documents/` | Column mapping JSON | Yes |
| Gold-layer ERD | `models/gold_layer_erd.md` | Aggregate table design | Yes |

## Using with Cursor Agent

This skill is automatically available in Cursor. Trigger it by mentioning any of:

- "Power BI", "PBI", "semantic model"
- "DAX to metric view", "migrate Power BI"
- "PBI to Databricks", "convert semantic model"

The agent will:
1. Read SKILL.md and follow the workflow checklist
2. Scan `input/` and classify every file by content
3. Present the classification and ask how each file should be used
4. Parse the PBI model(s), generate ERD/domains, and optionally compare schemas
5. Build KPI definitions, generate data discovery queries
6. Optimize query access (choose standard views, materialized views, or gold-layer aggregates)
7. Build metric views and generate all deliverables
8. Analyze sample reports if provided
9. Generate deployment checklist
10. Always present a plan before making changes

## Reference Articles

- [Adopting Power BI semantic models on Databricks SQL](https://medium.com/dbsql-sme-engineering/adopting-power-bi-semantic-models-on-databricks-sql-6efb4b0f78c9)
- [Parameterizing Databricks SQL Connections in Power BI](https://medium.com/@kyle.hale/parameterizing-your-databricks-sql-connections-in-power-bi-fd7aae20863e)
- [Power BI on Databricks Best Practices Cheat Sheet](https://medium.com/dbsql-sme-engineering/introducing-the-power-bi-on-databricks-best-practices-cheatsheet-a55e0aed9575)
- [Cheat Sheet PDF](https://www.databricks.com/sites/default/files/2025-04/2025-04-power-bi-on-databricks-best-practices-cheat-sheet.pdf)
- [Unity Catalog Metric Views](https://docs.databricks.com/en/metric-views/)
