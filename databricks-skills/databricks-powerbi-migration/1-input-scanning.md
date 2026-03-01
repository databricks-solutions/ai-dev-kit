# Input Scanning & Model Parsing (Steps 1–2)

Steps 1 and 2 of the migration workflow: classify all input files and parse Power BI models.

---

## Step 1: Scan, Classify, and Confirm All Inputs

**Before doing anything else**, read every file in `input/`. Classify each file by content — not extension.

```bash
python scripts/scan_inputs.py input/ -o reference/input_manifest.json
```

Detects: `pbi_model`, `csv_schema_dump`, `mapping_json`, `dbx_schema`, `sql_ddl`, `sql_query_output`, `csv_data`, `sample_report`, `databricks_config`, `unknown`.

**Present classification to the user and ask:**
1. "I found these files. Here is what each appears to be: [list]. Is this correct?"
2. "How should I use each file?"
3. If no Databricks schema info found: offer schema suggestion queries (Step 5 in [2-catalog-resolution.md](2-catalog-resolution.md)).

**Do not proceed until the user confirms.**

### Input File Types

| Type | Format | Description |
|------|--------|-------------|
| `pbi_model` | `.pbit`, `.pbix`, `.bim`, TMDL directory, or JSON | Exported semantic model — detected by content, not extension |
| `csv_schema_dump` | CSV with `table_name`, `column_name`, `data_type` headers | Schema metadata exported from INFORMATION_SCHEMA |
| `mapping_json` | JSON with `mappings` array | Column-level mappings (Scenario C or D) |
| `dbx_schema` | JSON, SQL DDL, or query output | Schema information from Databricks |
| `sample_report` | `.docx`, `.pdf`, `.png`, `.jpg`, `.xlsx`, `.pptx` | Sample report for KPI reverse-engineering |
| `databricks_config` | YAML with `host`/`token` keys | Workspace URL, PAT, warehouse, catalog, schema |
| `csv_data` | CSV | Headers can inform schema |

### CSV Schema Dump Detection

A CSV file is classified as `csv_schema_dump` when its header row contains columns matching these patterns (case-insensitive):

- `table_name` / `tableName` / `TABLE_NAME`
- `column_name` / `columnName` / `COLUMN_NAME`
- `data_type` / `dataType` / `DATA_TYPE`

At least `table_name` and `column_name` must be present. When a `csv_schema_dump` is detected:

1. Parse the CSV to extract table names, column names, and data types.
2. Build a schema representation equivalent to `extract_dbx_schema.py` output.
3. Use this schema for comparison in Step 6.

---

## Step 2: Parse Power BI Models

```bash
python scripts/parse_pbi_model.py input/<file> -o reference/pbi_model.json
# or batch mode:
python scripts/parse_pbi_model.py input/ -o reference/pbi_model.json
```

The parser handles any file extension — tries ZIP, JSON, and TMDL detection in sequence.

**Content detection order:** ZIP archive → JSON structure → TMDL text → TMDL directory

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

---

## After Parsing: Immediate Catalog Validation

**Immediately after parsing (before proceeding to ERD or KPI steps)**, extract all data source references from the PBI model — server names, database/catalog names, and schema names found in `partitions[].source` (connection strings, M expressions, or `Sql.Database` calls).

Cross-reference these against:
1. Schema files provided in `input/` (DDL, CSV schema dump, JSON schema)
2. Databricks config in `input/` (host/token/catalog)
3. Live MCP access (test with `execute_sql`)

**If a referenced catalog is inaccessible AND no schema dump was provided**, raise a warning immediately:

> "The PBI model references data from `<catalog>.<schema>`, but I have no schema information and cannot access this catalog. Please provide one of:
> 1. A schema dump (CSV, DDL, or JSON) in the `input/` folder
> 2. Databricks credentials with access to this catalog
> 3. Run this query and paste the output: `SELECT table_name, column_name, data_type FROM <catalog>.information_schema.columns WHERE table_schema = '<schema>'`"

**Do not proceed past Step 5 without resolving all catalog gaps.** See [2-catalog-resolution.md](2-catalog-resolution.md) for the full catalog resolution workflow.

### Extracting Data Sources from the Parsed Model

Data source references are in:

1. **Partition source expressions** (`partitions[].source.expression`):
   Look for `Sql.Database("server", "database")` in M code.

   ```
   let Source = Sql.Database("myserver.database.windows.net", "my_catalog"),
       gold = Source{[Schema="gold"]}[Data], ...
   ```

2. **Connection string annotations** (`model.annotations` or `model.dataSources`):
   Some models store explicit connection strings with server, database, catalog, and schema.

3. **Table source metadata** (`tables[].partitions[].source`):
   For DirectQuery tables, the `source` object may contain `schema` and `entity` (table) names.

```python
import re

def extract_data_sources(model: dict) -> list[dict]:
    sources = []
    for table in model.get("tables", []):
        for partition in table.get("partitions", []):
            src = partition.get("source", {})
            expr = src.get("expression", "")
            match = re.search(r'Sql\.Database\("([^"]+)",\s*"([^"]+)"\)', expr)
            if match:
                sources.append({"server": match.group(1), "catalog": match.group(2), "table": table.get("name")})
            schema_match = re.search(r'\[Schema="([^"]+)"\]', expr)
            if schema_match and sources:
                sources[-1]["schema"] = schema_match.group(1)
    return sources
```

---

## Project Structure Reference

```
project-root/
├── input/                             # ALL user-provided files
│   ├── model.pbix
│   ├── mapping.json                   # Optional
│   ├── schema_dump.sql                # Optional
│   ├── schema_export.csv              # Optional
│   ├── sample_report.pdf              # Optional
│   └── databricks.yml                 # Optional
├── reference/
│   ├── input_manifest.json            # Output of scan_inputs.py
│   └── pbi_model.json                 # Output of parse_pbi_model.py
└── temp/                              # Working/throwaway files
```

Initialize with:

```bash
bash scripts/init_project.sh
# With all folders:
bash scripts/init_project.sh --all
```
