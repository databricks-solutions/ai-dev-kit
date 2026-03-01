# Mapping Layer & Column Gap Analysis (Steps 6–7)

Steps 6 and 7 of the migration workflow: choose the mapping approach and analyze column gaps.

---

## Step 6: Build Mapping Layer

Choose the appropriate mapping approach based on schema comparison:

- **Direct (A)**: Names match — no mapping needed
- **View layer (B)**: Create aliasing views
- **Mapping document (C)**: Generate JSON mapping from comparison output
- **Intermediate mapping (D)**: Extract Power Query M renames, build two-layer mapping (`pbi_column -> dbx_column`), use three-layer only where applicable (`pbi_column -> m_query_column -> dbx_column`)

```bash
python scripts/compare_schemas.py \
  reference/pbi_model.json reference/dbx_schema.json \
  -o reference/schema_comparison.md --json --mapping reference/intermediate_mapping.json \
  --gap-analysis reference/column_gap_analysis.md
```

---

## Scenario D: Intermediate Mapping Layer

When Power Query M expressions rename columns between the PBI semantic layer and the physical database, a direct name comparison fails. Scenario D handles this by extracting the renames and building a mapping.

### Detection

Look in the PBI model's `partitions[].source.expression` for M code containing:

- `Table.RenameColumns` — explicit column renames
- `Table.SelectColumns` — column selection (implies name preservation)
- Schema parameter patterns — `type table [ColName = type text, ...]`

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
3. Search for `Table.RenameColumns(...)` calls — the argument is a list of `{old, new}` pairs.
4. Search for the `type table [...]` schema definition to find the final column names exposed to the PBI layer.
5. Map backward: PBI column name → M expression column → physical DB column.

### Example M Expression

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

### Mapping JSON Format

**Two-layer (default):**
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

**Three-layer (when M renames are relevant):**
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

When `m_query_column` is absent, the mapping is treated as two-layer.

Pass the intermediate mapping file via the `--mapping` flag:

```bash
python scripts/compare_schemas.py \
  reference/pbi_model.json reference/dbx_schema.json \
  -o reference/schema_comparison.md --json \
  --mapping reference/intermediate_mapping.json
```

---

## Step 7: Column Gap Analysis

After schema comparison, review `reference/column_gap_analysis.md` for DBX-only columns (columns present in Databricks but not referenced in the Power BI model). These may be important for:

- Filters and partitions in reports built outside PBI
- Discriminator columns that determine row subsets
- Audit/metadata columns needed for data governance

### Discriminator Heuristics

A column is flagged as a potential discriminator if its name matches any of:

- Contains `status`, `type`, `category`, `code`, `flag`, `class`, `kind`, `tier`, `level`, `group`
- Starts with `is_`, `has_`, `can_`
- Ends with `_type`, `_status`, `_code`, `_flag`, `_category`, `_class`

### Column Gap Analysis Output

`reference/column_gap_analysis.md` contains:
1. Every DBX-only column grouped by table
2. Discriminator flagging with naming heuristics
3. Suggested actions for each flagged column

```markdown
## Column Gap Analysis

### Table: catalog.schema.sales_fact
| Column | Data Type | Discriminator? | Suggested Action |
|--------|-----------|----------------|------------------|
| result_type | STRING | Yes | May filter report subsets — run data discovery |
| etl_load_date | TIMESTAMP | No | Audit column — likely not needed in reports |

### Table: catalog.schema.customer_dim
| Column | Data Type | Discriminator? | Suggested Action |
|--------|-----------|----------------|------------------|
| customer_status | STRING | Yes | May be essential for active/inactive filtering |
```

Flag discriminator columns for data discovery queries (Step 10) — see [4-erd-kpi-discovery.md](4-erd-kpi-discovery.md).
