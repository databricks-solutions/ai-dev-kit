---
name: databricks-genie
description: "Create and query Databricks Genie Spaces for natural language SQL exploration. Use when building Genie Spaces or asking questions via the Genie Conversation API."
---

# Databricks Genie

Create and query Databricks Genie Spaces - natural language interfaces for SQL-based data exploration.

## Overview

Genie Spaces allow users to ask natural language questions about structured data in Unity Catalog. The system translates questions into SQL queries, executes them on a SQL warehouse, and presents results conversationally.

## When to Use This Skill

Use this skill when:
- Creating a new Genie Space for data exploration
- Adding sample questions to guide users
- Connecting Unity Catalog tables to a conversational interface
- Asking questions to a Genie Space programmatically (Conversation API)
- Exporting a Genie Space configuration (serialized_space) for backup or migration
- Importing / cloning a Genie Space from a serialized payload
- Migrating a Genie Space between workspaces or environments (dev → staging → prod)
    - Only supports catalog remapping where catalog names differ across environments
    - Not supported for schema and/or table names that differ across environments
    - Not including migration of tables between environments (only migration of Genie Spaces)

## MCP Tools

### Space Management

| Tool | Purpose |
|------|---------|
| `list_genie` | List all Genie Spaces accessible to you |
| `create_or_update_genie` | Create or update a Genie Space (supports `serialized_space`) |
| `get_genie` |  Get space details (by ID and support `include_serialized_space` parameter) or list all spaces (no ID) |
| `delete_genie` | Delete a Genie Space |
| `export_genie` | Export a Genie Space with full serialized configuration |
| `import_genie` | Import / clone a Genie Space from a serialized payload |

### Conversation API

| Tool | Purpose |
|------|---------|
| `ask_genie` | Ask a question or follow-up (`conversation_id` optional) |

### Supporting Tools

| Tool | Purpose |
|------|---------|
| `get_table_details` | Inspect table schemas before creating a space |
| `execute_sql` | Test SQL queries directly |

## Quick Start

### 1. Inspect Your Tables

Before creating a Genie Space, understand your data:

```python
get_table_details(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="SIMPLE"
)
```

### 2. Create the Genie Space

```python
create_or_update_genie(
    display_name="Sales Analytics",
    table_identifiers=[
        "my_catalog.sales.customers",
        "my_catalog.sales.orders"
    ],
    description="Explore sales data with natural language",
    sample_questions=[
        "What were total sales last month?",
        "Who are our top 10 customers?"
    ]
)
```

### 3. Ask Questions (Conversation API)

```python
ask_genie(
    space_id="your_space_id",
    question="What were total sales last month?"
)
# Returns: SQL, columns, data, row_count
```

### 4. Export & Import (Clone / Migrate)

Export a space (preserves all tables, instructions, SQL examples, and layout):

```python
exported = export_genie(space_id="your_space_id")
# exported["serialized_space"] contains the full config
```

Clone to a new space (same catalog):

```python
import_genie(
    warehouse_id=exported["warehouse_id"],
    serialized_space=exported["serialized_space"],
    title="Sales Analytics (Dev Copy)"
)
```

#### Example: Migrating Genie Spaces from Prod to Dev

When migrating Genie Spaces between environments (e.g., from a `prod` target to a `dev` target defined in your `databricks.yml`), you must update the catalog references within the serialized space. 

**Note:** Genie Space migration assumes that the underlying data assets (schemas and tables) remain structurally identical across environments. The migration of the actual catalogs, schemas, or tables themselves is outside the scope of Genie Space migration skills.

For instance, if your production tables reside in the `healthverity_claims_sample_patient_dataset` catalog, but your development tables are in `healthverity_claims_sample_patient_dataset_dev`, you can perform a string replacement on the exported configuration before importing it into the target workspace:

```python
# 1. Export the Genie Space from the production workspace
exported = export_genie(space_id="<prod_space_id>")

# 2. Remap the catalog name for the development environment
dev_serialized_space = exported["serialized_space"].replace(
    "healthverity_claims_sample_patient_dataset", 
    "healthverity_claims_sample_patient_dataset_dev"
)

# 3. Import the modified space into the dev workspace
import_genie(
    warehouse_id="<dev_warehouse_id>",
    serialized_space=dev_serialized_space,
    title="HealthVerity Claims (Dev)"
)
```

## Workflow

```
1. Inspect tables    → get_table_details
2. Create space      → create_or_update_genie
3. Query space       → ask_genie (or test in Databricks UI)
4. Curate (optional) → Use Databricks UI to add instructions
5. Export/migrate    → export_genie → import_genie
```

## Reference Files

- [spaces.md](spaces.md) - Creating and managing Genie Spaces
- [conversation.md](conversation.md) - Asking questions via the Conversation API

## Prerequisites

Before creating a Genie Space:

1. **Tables in Unity Catalog** - Bronze/silver/gold tables with the data
2. **SQL Warehouse** - A warehouse to execute queries (auto-detected if not specified)

### Creating Tables

Use these skills in sequence:
1. `databricks-synthetic-data-gen` - Generate raw parquet files
2. `databricks-spark-declarative-pipelines` - Create bronze/silver/gold tables

## Common Issues

| Issue | Solution |
|-------|----------|
| **No warehouse available** | Create a SQL warehouse or provide `warehouse_id` explicitly |
| **Poor query generation** | Add instructions and sample questions that reference actual column names |
| **Slow queries** | Ensure warehouse is running; use OPTIMIZE on tables |
| **`export_genie` returns empty `serialized_space`** | Requires at least CAN EDIT permission on the space |
| **`import_genie` fails with permission error** | Ensure you have CREATE privileges in the target workspace folder |
| **Tables not found after migration** | Catalog name was not remapped — replace the source catalog name in `serialized_space` before calling `import_genie` |
| **Catalog name appears in SQL queries too** | `serialized_space` embeds catalog in table identifiers, SQL FROM clauses, join specs, and filters — a single `.replace(src, tgt)` on the whole string covers all occurrences |

## Related Skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Use Genie Spaces as agents inside Supervisor Agents
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate raw parquet data to populate tables for Genie
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs, schemas, and tables Genie queries
