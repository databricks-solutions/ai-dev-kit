# Creating Genie Spaces

This guide covers creating and managing Genie Spaces for SQL-based data exploration.

## What is a Genie Space?

A Genie Space connects to Unity Catalog tables and translates natural language questions into SQL — understanding schemas, generating queries, executing them on a SQL warehouse, and presenting results conversationally.

## Creation Workflow

### Step 1: Inspect Table Schemas (Required)

**Before creating a Genie Space, you MUST inspect the table schemas** to understand what data is available:

```python
get_table_details(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="SIMPLE"
)
```

This returns:
- Table names and row counts
- Column names and data types
- Sample values and cardinality
- Null counts and statistics

### Step 2: Analyze and Plan

Based on the schema information:

1. **Select relevant tables** - Choose tables that support the user's use case
2. **Identify key columns** - Note date columns, metrics, dimensions, and foreign keys
3. **Understand relationships** - How do tables join together?
4. **Plan sample questions** - What questions can this data answer?

### Step 3: Create the Genie Space

Create the space with content tailored to the actual data:

```python
create_or_update_genie(
    display_name="Sales Analytics",
    table_identifiers=[
        "my_catalog.sales.customers",
        "my_catalog.sales.orders",
        "my_catalog.sales.products"
    ],
    description="""Explore retail sales data with three related tables:
- customers: Customer demographics including region, segment, and signup date
- orders: Transaction history with order_date, total_amount, and status
- products: Product catalog with category, price, and inventory

Tables join on customer_id and product_id.""",
    sample_questions=[
        "What were total sales last month?",
        "Who are our top 10 customers by total_amount?",
        "How many orders were placed in Q4 by region?",
        "What's the average order value by customer segment?",
        "Which product categories have the highest revenue?",
        "Show me customers who haven't ordered in 90 days"
    ]
)
```

## Why This Workflow Matters

**Sample questions that reference actual column names** help Genie:
- Learn the vocabulary of your data
- Generate more accurate SQL queries
- Provide better autocomplete suggestions

**A description that explains table relationships** helps Genie:
- Understand how to join tables correctly
- Know which table contains which information
- Provide more relevant answers

## Auto-Detection of Warehouse

When `warehouse_id` is not specified, the tool:

1. Lists all SQL warehouses in the workspace
2. Prioritizes by:
   - **Running** warehouses first (already available)
   - **Starting** warehouses second
   - **Smaller sizes** preferred (cost-efficient)
3. Returns an error if no warehouses exist

To use a specific warehouse, provide the `warehouse_id` explicitly.

## Table Selection

Choose tables carefully for best results:

| Layer | Recommended | Why |
|-------|-------------|-----|
| Bronze | No | Raw data, may have quality issues |
| Silver | Yes | Cleaned and validated |
| Gold | Yes | Aggregated, optimized for analytics |

### Tips for Table Selection

- **Include related tables**: If users ask about customers and orders, include both
- **Use descriptive column names**: `customer_name` is better than `cust_nm`
- **Add table comments**: Genie uses metadata to understand the data

## Sample Questions

Sample questions help users understand what they can ask:

**Good sample questions:**
- "What were total sales last month?"
- "Who are our top 10 customers by revenue?"
- "How many orders were placed in Q4?"
- "What's the average order value by region?"

These appear in the Genie UI to guide users.

## Best Practices

### Table Design for Genie

1. **Descriptive names**: Use `customer_lifetime_value` not `clv`
2. **Add comments**: `COMMENT ON TABLE sales.customers IS 'Customer master data'`
3. **Primary keys**: Define relationships clearly
4. **Date columns**: Include proper date/timestamp columns for time-based queries

### Description and Context

Provide context in the description:

```
Explore retail sales data from our e-commerce platform. Includes:
- Customers: demographics, segments, and account status
- Orders: transaction history with amounts and dates
- Products: catalog with categories and pricing

Time range: Last 6 months of data
```

### Sample Questions

Write sample questions that:
- Cover common use cases
- Demonstrate the data's capabilities
- Use natural language (not SQL terms)

## Updating a Genie Space

`create_or_update_genie` handles both create and update automatically. There are two ways it locates an existing space to update:

- **By `space_id`** (explicit, preferred): pass `space_id=` to target a specific space.
- **By `display_name`** (implicit fallback): if `space_id` is omitted, the tool searches for a space with a matching name and updates it if found; otherwise it creates a new one.

### Simple field updates (tables, questions, warehouse)

To update metadata without a serialized config:

```python
create_or_update_genie(
    display_name="Sales Analytics",
    space_id="01abc123...",           # omit to match by name instead
    table_identifiers=[               # updated table list
        "my_catalog.sales.customers",
        "my_catalog.sales.orders",
        "my_catalog.sales.products",
    ],
    sample_questions=[                # updated sample questions
        "What were total sales last month?",
        "Who are our top 10 customers by revenue?",
    ],
    warehouse_id="abc123def456",      # omit to keep current / auto-detect
    description="Updated description.",
)
```

### Full config update via `serialized_space`

To push a complete serialized configuration to an existing space (the dict contains all regular table metadata, plus it preserves all instructions, SQL examples, join specs, etc.):

```python
create_or_update_genie(
    display_name="Sales Analytics",   # overrides title embedded in serialized_space
    table_identifiers=[],             # ignored when serialized_space is provided
    space_id="01abc123...",           # target space to overwrite
    warehouse_id="abc123def456",      # overrides warehouse embedded in serialized_space
    description="Updated description.",  # overrides description embedded in serialized_space; omit to keep the one in the payload
    serialized_space=remapped_config, # JSON string from migrate_genie(type="export") (after catalog remap if needed)
)
```

> **Note:** When `serialized_space` is provided, `table_identifiers` and `sample_questions` are ignored — the full config comes from the serialized payload. However, `display_name`, `warehouse_id`, and `description` are still applied as top-level overrides on top of the serialized payload. Omit any of them to keep the values embedded in `serialized_space`.

## Export, Import & Migration

`migrate_genie(type="export")` returns a dictionary with four top-level keys:

| Key | Description |
|-----|-------------|
| `space_id` | ID of the exported space |
| `title` | Display name of the space |
| `description` | Description of the space |
| `warehouse_id` | SQL warehouse associated with the space (workspace-specific — do **not** reuse across workspaces) |
| `serialized_space` | JSON-encoded string with the full space configuration (see below) |

This envelope enables cloning, backup, and cross-workspace migration. Use `migrate_genie(type="export")` and `migrate_genie(type="import")` for all export/import operations — no direct REST calls needed.

### What is `serialized_space`?

`serialized_space` is a JSON string (version 2) embedded inside the export envelope. Its top-level keys are:

| Key | Contents |
|-----|----------|
| `version` | Schema version (currently `2`) |
| `config` | Space-level config: `sample_questions` shown in the UI |
| `data_sources` | `tables` array — each entry has a fully-qualified `identifier` (`catalog.schema.table`) and optional `column_configs` (format assistance, entity matching per column) |
| `instructions` | `example_question_sqls` (certified Q&A pairs), `join_specs` (join relationships between tables), `sql_snippets` (`filters` and `measures` with display names and usage instructions) |
| `benchmarks` | Evaluation Q&A pairs used to measure space quality |

Catalog names appear **everywhere** inside `serialized_space` — in `data_sources.tables[].identifier`, SQL strings in `example_question_sqls`, `join_specs`, and `sql_snippets`. A single `.replace(src_catalog, tgt_catalog)` on the whole string is sufficient for catalog remapping.

Minimum structure:
```json
{"version": 2, "data_sources": {"tables": [{"identifier": "catalog.schema.table"}]}}
```

### Exporting a Space

Use `migrate_genie(type="export")` to export the full configuration (requires CAN EDIT permission):

```python
exported = migrate_genie(type="export", space_id="01abc123...")
# Returns:
# {
#   "space_id": "01abc123...",
#   "title": "Sales Analytics",
#   "description": "Explore sales data...",
#   "warehouse_id": "abc123def456",
#   "serialized_space": "{\"version\":2,\"data_sources\":{...},\"instructions\":{...}}"
# }
```

You can also get `serialized_space` inline via `get_genie`:

```python
details = get_genie(space_id="01abc123...", include_serialized_space=True)
serialized = details["serialized_space"]
```

### Cloning a Space (Same Workspace)

```python
# Step 1: Export the source space
source = migrate_genie(type="export", space_id="01abc123...")

# Step 2: Import as a new space
migrate_genie(
    type="import",
    warehouse_id=source["warehouse_id"],
    serialized_space=source["serialized_space"],
    title=source["title"],  # override title; omit to keep original
    description=source["description"],
)
# Returns: {"space_id": "01def456...", "title": "Sales Analytics (Dev Copy)", "operation": "imported"}
```

### Migrating Across Workspaces with Catalog Remapping

When migrating between environments (e.g. prod → dev), Unity Catalog names are often different. The `serialized_space` string contains the source catalog name **everywhere** — in table identifiers, SQL queries, join specs, and filter snippets. You must remap it before importing.

**Agent workflow (3 steps):**

**Step 1 — Export from source workspace:**
```python
exported = migrate_genie(type="export", space_id="01f106e1239d14b28d6ab46f9c15e540")
# exported keys: warehouse_id, title, description, serialized_space
# exported["serialized_space"] contains all references to source catalog
```

**Step 2 — Remap catalog name in `serialized_space`:**

The agent does this as an inline string substitution between the two MCP calls:
```python
modified_serialized = exported["serialized_space"].replace(
    "source_catalog_name",     # e.g. "healthverity_claims_sample_patient_dataset"
    "target_catalog_name"      # e.g. "healthverity_claims_sample_patient_dataset_dev"
)
```
This replaces all occurrences — table identifiers, SQL FROM clauses, join specs, and filter snippets.

**Step 3 — Import to target workspace:**
```python
migrate_genie(
    type="import",
    warehouse_id="<target_warehouse_id>",   # from list_warehouses() on target
    serialized_space=modified_serialized,
    title=exported["title"],
    description=exported["description"]
)
```

### Batch Migration of Multiple Spaces

To migrate several spaces at once, loop through space IDs. The agent exports, remaps the catalog, then imports each:

```
For each space_id in [id1, id2, id3]:
  1. exported = migrate_genie(type="export", space_id=space_id)
  2. modified  = exported["serialized_space"].replace(src_catalog, tgt_catalog)
  3. result    = migrate_genie(type="import", warehouse_id=wh_id, serialized_space=modified, title=exported["title"], description=exported["description"])
  4. record result["space_id"] for updating databricks.yml
```

After migration, update `databricks.yml` with the new dev `space_id` values under the `dev` target's `genie_space_ids` variable.

### Updating an Existing Space with New Config

To push a serialized config to an already-existing space (rather than creating a new one), use `create_or_update_genie` with `space_id=` and `serialized_space=`. The export → remap → push pattern is identical to the migration steps above; just replace `migrate_genie(type="import")` with `create_or_update_genie(space_id=TARGET_SPACE_ID, ...)` as the final call.

### Permissions Required

| Operation | Required Permission |
|-----------|-------------------|
| `migrate_genie(type="export")` / `get_genie(include_serialized_space=True)` | CAN EDIT on source space |
| `migrate_genie(type="import")` | Can create items in target workspace folder |
| `create_or_update_genie` with `serialized_space` (update) | CAN EDIT on target space |

## Example End-to-End Workflow

1. **Generate synthetic data** using `databricks-synthetic-data-gen` skill:
   - Creates parquet files in `/Volumes/catalog/schema/raw_data/`

2. **Create tables** using `databricks-spark-declarative-pipelines` skill:
   - Creates `catalog.schema.bronze_*` → `catalog.schema.silver_*` → `catalog.schema.gold_*`

3. **Inspect the tables**:
   ```python
   get_table_details(catalog="catalog", schema="schema")
   ```

4. **Create the Genie Space**:
   - `display_name`: "My Data Explorer"
   - `table_identifiers`: `["catalog.schema.silver_customers", "catalog.schema.silver_orders"]`

5. **Add sample questions** based on actual column names

6. **Test** in the Databricks UI

## Troubleshooting

### No warehouse available

- Create a SQL warehouse in the Databricks workspace
- Or provide a specific `warehouse_id`

### Queries are slow

- Ensure the warehouse is running (not stopped)
- Consider using a larger warehouse size
- Check if tables are optimized (OPTIMIZE, Z-ORDER)

### Poor query generation

- Use descriptive column names
- Add table and column comments
- Include sample questions that demonstrate the vocabulary
- Add instructions via the Databricks Genie UI

### `migrate_genie(type="export")` returns empty `serialized_space`

Requires at least **CAN EDIT** permission on the space.

### `migrate_genie(type="import")` fails with permission error

Ensure you have CREATE privileges in the target workspace folder.

### Tables not found after migration

Catalog name was not remapped — replace the source catalog name in `serialized_space` before calling `migrate_genie(type="import")`. The catalog appears in table identifiers, SQL FROM clauses, join specs, and filter snippets; a single `.replace(src_catalog, tgt_catalog)` on the whole string covers all occurrences.

### `migrate_genie` lands in the wrong workspace

Each MCP server is workspace-scoped. Set up two named MCP server entries (one per profile) in your IDE's MCP config instead of switching a single server's profile mid-session.

### MCP server doesn't pick up profile change

The MCP process reads `DATABRICKS_CONFIG_PROFILE` once at startup — editing the config file requires an IDE reload to take effect.

### `migrate_genie(type="import")` fails with JSON parse error

The `serialized_space` string may contain multi-line SQL arrays with `\n` escape sequences. Flatten SQL arrays to single-line strings before passing to avoid double-escaping issues.
