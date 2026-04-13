# Creating Genie Spaces

This guide covers creating and managing Genie Spaces for SQL-based data exploration.

## What is a Genie Space?

A Genie Space connects to Unity Catalog tables and translates natural language questions into SQL — understanding schemas, generating queries, executing them on a SQL warehouse, and presenting results conversationally.

## Creation Workflow

### Step 1: Inspect Table Schemas (Required)

**Before creating a Genie Space, you MUST inspect the table schemas** to understand what data is available:

```bash
# Get table details
databricks unity-catalog tables get my_catalog.sales.customers
databricks unity-catalog tables get my_catalog.sales.orders

# Or use discover-schema for multiple tables with statistics
databricks experimental aitools tools discover-schema my_catalog.sales.customers my_catalog.sales.orders
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

```bash
databricks genie create-space --json '{
  "display_name": "Sales Analytics",
  "description": "Explore retail sales data with three related tables:\n- customers: Customer demographics including region, segment, and signup date\n- orders: Transaction history with order_date, total_amount, and status\n- products: Product catalog with category, price, and inventory\n\nTables join on customer_id and product_id.",
  "table_identifiers": [
    "my_catalog.sales.customers",
    "my_catalog.sales.orders",
    "my_catalog.sales.products"
  ]
}'
```

Sample questions can be added via the Databricks UI after creation:
- "What were total sales last month?"
- "Who are our top 10 customers by total_amount?"
- "How many orders were placed in Q4 by region?"
- "What's the average order value by customer segment?"
- "Which product categories have the highest revenue?"
- "Show me customers who haven't ordered in 90 days"

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

Use `databricks genie update-space` to update an existing space by ID.

### Simple field updates

```bash
# Update display name and description
databricks genie update-space SPACE_ID --json '{
  "display_name": "Sales Analytics",
  "description": "Updated description.",
  "table_identifiers": [
    "my_catalog.sales.customers",
    "my_catalog.sales.orders",
    "my_catalog.sales.products"
  ]
}'
```

### Full config update via serialized_space

To push a complete serialized configuration to an existing space (preserves all instructions, SQL examples, join specs, etc.):

```bash
# First export the current config
databricks genie export-space SOURCE_SPACE_ID > config.json

# Modify the serialized_space as needed, then update
databricks genie update-space TARGET_SPACE_ID --json @updated_config.json
```

> **Note:** When using serialized_space, the full config comes from the serialized payload. Top-level overrides (display_name, warehouse_id, description) can still be applied.

## Export, Import & Migration

`databricks genie export-space SPACE_ID` returns a JSON object with these top-level keys:

| Key | Description |
|-----|-------------|
| `space_id` | ID of the exported space |
| `title` | Display name of the space |
| `description` | Description of the space |
| `warehouse_id` | SQL warehouse associated with the space (workspace-specific — do **not** reuse across workspaces) |
| `serialized_space` | JSON-encoded string with the full space configuration (see below) |

This envelope enables cloning, backup, and cross-workspace migration.

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

Use `databricks genie export-space` to export the full configuration (requires CAN EDIT permission):

```bash
databricks genie export-space 01abc123... > exported_space.json
# Returns:
# {
#   "space_id": "01abc123...",
#   "title": "Sales Analytics",
#   "description": "Explore sales data...",
#   "warehouse_id": "abc123def456",
#   "serialized_space": "{\"version\":2,\"data_sources\":{...},\"instructions\":{...}}"
# }
```

### Cloning a Space (Same Workspace)

```bash
# Step 1: Export the source space
databricks genie export-space 01abc123... > source.json

# Step 2: Import as a new space (modify title in JSON if needed)
databricks genie import-space --json @source.json
# Returns: {"space_id": "01def456...", "title": "Sales Analytics", "operation": "imported"}
```

### Migrating Across Workspaces with Catalog Remapping

When migrating between environments (e.g. prod → dev), Unity Catalog names are often different. The `serialized_space` string contains the source catalog name **everywhere** — in table identifiers, SQL queries, join specs, and filter snippets. You must remap it before importing.

**Workflow (3 steps):**

**Step 1 — Export from source workspace:**
```bash
# Use source workspace profile
DATABRICKS_CONFIG_PROFILE=source databricks genie export-space 01f106e1239d14b28d6ab46f9c15e540 > exported.json
```

**Step 2 — Remap catalog name in `serialized_space`:**

Use sed or a script to replace catalog names:
```bash
# Replace source catalog with target catalog in the serialized_space
sed -i '' 's/source_catalog_name/target_catalog_name/g' exported.json
```
This replaces all occurrences — table identifiers, SQL FROM clauses, join specs, and filter snippets.

**Step 3 — Import to target workspace:**
```bash
# Use target workspace profile
DATABRICKS_CONFIG_PROFILE=target databricks genie import-space --json @exported.json
```

### Batch Migration of Multiple Spaces

To migrate several spaces at once, use a shell loop:

```bash
for space_id in id1 id2 id3; do
  # Export
  DATABRICKS_CONFIG_PROFILE=source databricks genie export-space $space_id > ${space_id}.json
  # Remap catalog
  sed -i '' 's/src_catalog/tgt_catalog/g' ${space_id}.json
  # Import
  DATABRICKS_CONFIG_PROFILE=target databricks genie import-space --json @${space_id}.json
done
```

After migration, update `databricks.yml` with the new dev `space_id` values under the `dev` target's `genie_space_ids` variable.

### Updating an Existing Space with New Config

To push a serialized config to an already-existing space (rather than creating a new one), use `databricks genie update-space` with the serialized config. The export → remap → push pattern is identical to the migration steps above; just replace `import-space` with `update-space TARGET_SPACE_ID` as the final call.

### Permissions Required

| Operation | Required Permission |
|-----------|-------------------|
| `databricks genie export-space` | CAN EDIT on source space |
| `databricks genie import-space` | Can create items in target workspace folder |
| `databricks genie update-space` with serialized_space | CAN EDIT on target space |

## Example End-to-End Workflow

1. **Generate synthetic data** using `databricks-synthetic-data-gen` skill:
   - Creates parquet files in `/Volumes/catalog/schema/raw_data/`

2. **Create tables** using `databricks-spark-declarative-pipelines` skill:
   - Creates `catalog.schema.bronze_*` → `catalog.schema.silver_*` → `catalog.schema.gold_*`

3. **Inspect the tables**:
   ```bash
   databricks experimental aitools tools discover-schema catalog.schema.silver_customers catalog.schema.silver_orders
   ```

4. **Create the Genie Space**:
   ```bash
   databricks genie create-space --json '{
     "display_name": "My Data Explorer",
     "table_identifiers": ["catalog.schema.silver_customers", "catalog.schema.silver_orders"]
   }'
   ```

5. **Add sample questions** via the Databricks UI based on actual column names

6. **Test** using conversation.py or the Databricks UI

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

### `databricks genie export-space` returns empty `serialized_space`

Requires at least **CAN EDIT** permission on the space.

### `databricks genie import-space` fails with permission error

Ensure you have CREATE privileges in the target workspace folder.

### Tables not found after migration

Catalog name was not remapped — replace the source catalog name in `serialized_space` before calling `databricks genie import-space`. The catalog appears in table identifiers, SQL FROM clauses, join specs, and filter snippets; a single `sed 's/src_catalog/tgt_catalog/g'` on the whole JSON covers all occurrences.

### CLI targets the wrong workspace

Use `DATABRICKS_CONFIG_PROFILE=profile_name` to specify which workspace profile to use:
```bash
DATABRICKS_CONFIG_PROFILE=dev databricks genie list-spaces
```

### `databricks genie import-space` fails with JSON parse error

The `serialized_space` string may contain multi-line SQL arrays with `\n` escape sequences. Flatten SQL arrays to single-line strings before passing to avoid double-escaping issues.
