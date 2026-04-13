---
name: databricks-genie
description: "Create and query Databricks Genie Spaces for natural language SQL exploration. Use when building Genie Spaces, exporting and importing Genie Spaces, migrating Genie Spaces between workspaces or environments, or asking questions via the Genie Conversation API."
---

# Databricks Genie

Create, manage, and query Databricks Genie Spaces - natural language interfaces for SQL-based data exploration.

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

## CLI Commands

### Space Management

```bash
# List all Genie Spaces
databricks genie list-spaces

# Create a Genie Space
databricks genie create-space --json '{
  "display_name": "Sales Analytics",
  "description": "Explore sales data with natural language",
  "table_identifiers": ["catalog.schema.customers", "catalog.schema.orders"]
}'

# Get space details
databricks genie get-space SPACE_ID

# Update a Genie Space
databricks genie update-space SPACE_ID --json '{
  "display_name": "Updated Name",
  "description": "Updated description"
}'

# Delete (trash) a Genie Space
databricks genie trash-space SPACE_ID
```

### Export & Import (Migration)

```bash
# Export space configuration (returns JSON with serialized_space)
databricks genie export-space SPACE_ID

# Import space from exported config
databricks genie import-space --json '{
  "warehouse_id": "WAREHOUSE_ID",
  "serialized_space": "...",
  "title": "Sales Analytics (Prod)"
}'
```

### Conversation API (Query)

Use the `scripts/conversation.py` script in this skill folder to ask questions:

```bash
# Ask a question to a Genie Space
python scripts/conversation.py ask SPACE_ID "What were total sales last month?"
# Returns: {question, conversation_id, message_id, status, sql, columns, data, row_count}

# Follow-up question in same conversation
python scripts/conversation.py ask SPACE_ID "Break that down by region" --conversation-id CONV_ID

# With custom timeout (default: 60 seconds)
python scripts/conversation.py ask SPACE_ID "Complex analysis query" --timeout 120
```

### Table Inspection

```bash
# Inspect table schemas before creating a space
databricks unity-catalog tables get CATALOG.SCHEMA.TABLE

# Or use the discover-schema tool for multiple tables
databricks experimental aitools tools discover-schema catalog.schema.table1 catalog.schema.table2
```

## Quick Start

### 1. Inspect Your Tables

Before creating a Genie Space, understand your data:

```bash
# Get table details
databricks unity-catalog tables get my_catalog.sales.customers
databricks unity-catalog tables get my_catalog.sales.orders

# Or use discover-schema for multiple tables
databricks experimental aitools tools discover-schema my_catalog.sales.customers my_catalog.sales.orders
```

### 2. Create the Genie Space

```bash
databricks genie create-space --json '{
  "display_name": "Sales Analytics",
  "description": "Explore sales data with natural language",
  "table_identifiers": [
    "my_catalog.sales.customers",
    "my_catalog.sales.orders"
  ]
}'
```

### 3. Ask Questions (Conversation API)

```bash
python scripts/conversation.py ask YOUR_SPACE_ID "What were total sales last month?"
# Returns: SQL, columns, data, row_count
```

### 4. Export & Import (Clone / Migrate)

Export a space (preserves all tables, instructions, SQL examples, and layout):

```bash
databricks genie export-space YOUR_SPACE_ID > exported_space.json
# exported_space.json contains serialized_space with full config
```

Clone to a new space (same catalog):

```bash
# Extract and import
databricks genie import-space --json '{
  "warehouse_id": "WAREHOUSE_ID",
  "serialized_space": "...",
  "title": "Sales Analytics (Clone)"
}'
```

> **Cross-workspace migration:** Use different Databricks CLI profiles for source and target workspaces. Export from source profile, remap catalog names in `serialized_space`, then import via target profile. See [spaces.md §Migration](spaces.md#migrating-across-workspaces-with-catalog-remapping) for the full workflow.

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

See [spaces.md §Troubleshooting](spaces.md#troubleshooting) for a full list of issues and solutions.
## Related Skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Use Genie Spaces as agents inside Supervisor Agents
- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate raw parquet data to populate tables for Genie
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs, schemas, and tables Genie queries
