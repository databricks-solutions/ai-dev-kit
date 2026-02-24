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

## MCP Tools

### Space Management

| Tool | Purpose |
|------|---------|
| `list_genie` | List all Genie Spaces accessible to you |
| `create_or_update_genie` | Create or update a Genie Space |
| `get_genie` | Get Genie Space details |
| `delete_genie` | Delete a Genie Space |

### Conversation API

| Tool | Purpose |
|------|---------|
| `ask_genie` | Ask a question to a Genie Space, get SQL + results |
| `ask_genie_followup` | Ask follow-up question in existing conversation |

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

## Workflow

```
1. Inspect tables    → get_table_details
2. Create space      → create_or_update_genie
3. Query space       → ask_genie (or test in Databricks UI)
4. Curate (optional) → Use Databricks UI to add instructions
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
1. `databricks-synthetic-data-generation` - Generate raw parquet files
2. `databricks-spark-declarative-pipelines` - Create bronze/silver/gold tables

## Common Issues

| Issue | Solution |
|-------|----------|
| **No warehouse available** | Create a SQL warehouse or provide `warehouse_id` explicitly |
| **Poor query generation** | Add instructions and sample questions that reference actual column names |
| **Slow queries** | Ensure warehouse is running; use OPTIMIZE on tables |

## Related Skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Use Genie Spaces as agents inside Supervisor Agents
- **[databricks-synthetic-data-generation](../databricks-synthetic-data-generation/SKILL.md)** - Generate raw parquet data to populate tables for Genie
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs, schemas, and tables Genie queries

---

## Advanced: Full Genie Configuration via serialized_space

The `create_or_update_genie` tool only sets basic fields (title, description, tables, sample questions). To populate **all** Genie UI sections, use `PATCH /api/2.0/genie/spaces/{id}` with the `serialized_space` field.

### Sections that require serialized_space

| UI Section | serialized_space field |
|---|---|
| General Instructions | `instructions.text_instructions` (max 1 item) |
| SQL queries & functions | `instructions.example_question_sqls` |
| Common SQL Expressions | `instructions.sql_snippets.{filters,expressions,measures}` |
| Benchmarks | `benchmarks.questions` |

### Workflow for full configuration

```
1. create_or_update_genie(...)  → creates space with tables + sample_questions
2. GET /api/2.0/genie/spaces/{id}?include_serialized_space=true  → fetch existing data
3. Build serialized_space dict with all sections
4. PATCH /api/2.0/genie/spaces/{id}  → apply with {"serialized_space": json.dumps(ss)}
```

See [spaces.md](spaces.md#advanced-serialized_space-api) for the complete code example, JSON schema, and constraints.
