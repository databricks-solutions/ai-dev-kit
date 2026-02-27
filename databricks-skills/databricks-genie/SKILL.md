---
name: databricks-genie
description: "Create, query, analyze, benchmark, and optimize Databricks Genie Spaces for natural language SQL exploration. Use when building Genie Spaces, asking questions via the Genie Conversation API, or auditing and improving existing spaces."
---

# Databricks Genie

Create and query Databricks Genie Spaces - natural language interfaces for SQL-based data exploration.

## Overview

Genie Spaces allow users to ask natural language questions about structured data in Unity Catalog. The system translates questions into SQL queries, executes them on a SQL warehouse, and presents results conversationally.

For existing spaces, this skill also supports analysis, benchmark testing, and optimization workflows.

## When to Use This Skill

Use this skill when:
- Creating a new Genie Space for data exploration
- Adding sample questions to guide users
- Connecting Unity Catalog tables to a conversational interface
- Asking questions to a Genie Space programmatically (Conversation API)
- Auditing an existing Genie Space against best practices
- Benchmarking and optimizing an existing Genie Space

## MCP Tools

### Space Management

| Tool | Purpose |
|------|---------|
| `create_or_update_genie` | Create or update a Genie Space |
| `get_genie` | Get space details (by ID) or list all spaces (no ID) |
| `delete_genie` | Delete a Genie Space |

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

## Workflow

```
1. Inspect tables    → get_table_details
2. Create space      → create_or_update_genie
3. Query space       → ask_genie (or test in Databricks UI)
4. Curate (optional) → Use Databricks UI to add instructions
5. Optimize (optional) → references/workflow-analyze.md, references/workflow-benchmark.md, references/workflow-optimize.md
```

## Reference Files

- [spaces.md](spaces.md) - Creating and managing Genie Spaces
- [conversation.md](conversation.md) - Asking questions via the Conversation API
- [references/workflow-analyze.md](references/workflow-analyze.md) - Configuration analysis workflow
- [references/workflow-benchmark.md](references/workflow-benchmark.md) - Benchmark analysis workflow
- [references/workflow-optimize.md](references/workflow-optimize.md) - Optimization workflow
- [references/best-practices-checklist.md](references/best-practices-checklist.md) - Genie best-practice checks
- [references/space-schema.md](references/space-schema.md) - Serialized space schema reference

## Prerequisites

Before creating a Genie Space:

1. **Tables in Unity Catalog** - Bronze/silver/gold tables with the data
2. **SQL Warehouse** - A warehouse to execute queries (auto-detected if not specified)

For optimization scripts (`scripts/*.py`):
- `databricks-sdk >= 0.85`
- Databricks auth configured (`databricks configure` or env vars)
- `CAN EDIT` permission on target Genie Space

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
| **Permission denied on optimization scripts** | Ensure user has `CAN EDIT` on target space |

## Related Skills

- **[databricks-agent-bricks](../databricks-agent-bricks/SKILL.md)** - Use Genie Spaces as agents inside Supervisor Agents
- **[databricks-synthetic-data-generation](../databricks-synthetic-data-generation/SKILL.md)** - Generate raw parquet data to populate tables for Genie
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables consumed by Genie Spaces
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - Manage the catalogs, schemas, and tables Genie queries
