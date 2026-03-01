# Catalog Resolution & Schema Extraction (Steps 3–5)

Steps 3, 4, and 5 of the migration workflow: validate catalog accessibility, resolve catalog names, and extract Databricks schema.

---

## Step 3: Validate Catalog Accessibility

**Immediately after parsing**, extract all data source references from the PBI model and cross-reference against:
1. Schema files provided in `input/` (DDL, CSV schema dump, JSON schema)
2. Databricks config in `input/` (host/token/catalog)
3. Live MCP access (test with `execute_sql`)

**If MCP is available**, test accessibility for each referenced catalog:

```sql
SELECT 1 FROM <catalog>.information_schema.tables LIMIT 1;
```

Launch parallel subagents when multiple catalogs need testing — see [9-subagent-patterns.md](9-subagent-patterns.md).

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

Update `reference/catalog_resolution.md` with an accessibility status section:

```markdown
## Catalog Accessibility Status

| Catalog | Schema | Status | Source |
|---------|--------|--------|--------|
| my_catalog | gold | ✅ Accessible | Live MCP query |
| other_catalog | silver | ✅ Covered | input/other_catalog_schema.csv |
| missing_catalog | dbo | ❌ Inaccessible | No schema info — user action required |
```

**Do not proceed past Step 5 without resolving all catalog gaps.** ERD/domain generation (Step 8) can proceed with PBI-only data, but schema comparison and metric view creation require catalog access or schema dumps.

---

## Step 4: Resolve Catalog

First, list all available catalogs:

```sql
SELECT catalog_name FROM system.information_schema.catalogs ORDER BY catalog_name;
```

Then probe schemas within the target catalog:

```sql
SELECT schema_name FROM <catalog>.information_schema.schemata;
```

Then verify table existence:

```sql
SELECT table_name
FROM <catalog>.information_schema.tables
WHERE table_schema = '<schema>';
```

**When multiple candidate catalogs exist** (e.g., `analytics`, `fc_analytics`), launch parallel subagents — one per catalog — to probe concurrently. See [9-subagent-patterns.md](9-subagent-patterns.md) Pattern A.

### Handling fc_ Prefix

Some environments prefix catalog names with `fc_`. The agent should:

1. Try the catalog name as provided
2. If not found, try with `fc_` prefix
3. If not found, try without `fc_` prefix
4. Document both primary and fallback catalog in `reference/catalog_resolution.md`

### Output: catalog_resolution.md

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
| product_dim | fc_my_catalog | gold | ~50K |
```

---

## Step 5: Extract or Ingest Databricks Schema

If no schema was found in `input/`, suggest these queries:

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

Tell the user: *"Paste output in chat, save to input/, or provide catalog.schema for programmatic extraction."*

**Programmatic extraction** via MCP:

```
CallMcpTool:
  server: "user-databricks"
  toolName: "get_table_details"
  arguments: {"catalog": "<catalog>", "schema": "<schema>", "table_stat_level": "SIMPLE"}
```

When extracting from **multiple catalogs or schemas**, launch parallel subagents — one per catalog/schema pair. See [9-subagent-patterns.md](9-subagent-patterns.md) Pattern B.

Also accept DDL files and CSV schema dumps as schema sources.

### CSV Schema Dump as Schema Source

A CSV with INFORMATION_SCHEMA-style headers is treated as equivalent to `extract_dbx_schema.py` output:

```csv
table_name,column_name,data_type,is_nullable,comment
sales_fact,sale_id,BIGINT,NO,Primary key
sales_fact,total_amount,DECIMAL(18,2),YES,Order total
customer_dim,customer_id,BIGINT,NO,Primary key
```

Detection criteria: headers must contain `table_name` + `column_name` (at minimum). `data_type` is strongly expected but not strictly required.

---

## Cross-Schema and Multi-Catalog Environments

### Discover All Schemas in a Catalog

```sql
SELECT schema_name FROM <catalog>.information_schema.schemata;
```

### Discover All Catalogs

```sql
SELECT catalog_name FROM system.information_schema.catalogs;
```

### Cross-Schema Column Comparison

```sql
SELECT table_schema, table_name, column_name, data_type
FROM <catalog>.information_schema.columns
WHERE table_schema IN ('<schema_a>', '<schema_b>')
ORDER BY table_schema, table_name, ordinal_position;
```

### When to Use Cross-Schema Probing

- PBI model references tables from multiple schemas
- Table names exist in multiple schemas (need to disambiguate)
- Migration involves consolidating schemas

---

## Scripts

### extract_dbx_schema.py

```bash
python scripts/extract_dbx_schema.py \
  my_catalog my_schema -o reference/dbx_schema.json [--profile PROD]
```

**Dependencies:** `databricks-sdk`
