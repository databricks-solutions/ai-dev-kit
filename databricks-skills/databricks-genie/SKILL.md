---
name: databricks-genie
description: "Create and query Databricks Genie Spaces for natural language SQL exploration. Use when building Genie Spaces, exporting and importing Genie Spaces, migrating Genie Spaces between workspaces or environments, or asking questions via the Genie Conversation API."
---

# Databricks Genie

Create, manage, and query Genie Spaces - natural language interfaces for SQL-based data exploration.

## Overview

Genie Spaces allow users to ask natural language questions about structured data in Unity Catalog. The system translates questions into SQL queries, executes them on a SQL warehouse, and presents results conversationally.

## Creating a Genie Space

### Step 1: Understand the Data

Before creating a Genie Space, explore the available tables to:
- **Select relevant tables** — typically gold layer (aggregated KPIs) and sometimes silver layer (cleaned facts) or metric views
- **Understand the story** — what business questions can this data answer? What insights can users discover?
- **Design meaningful sample questions** — questions should reflect real use cases and lead to actionable insights in the data

Use `discover-schema` as the default — one call returns columns, types, sample rows, null counts, and row count. If you only know the schema, list tables first with `query "SHOW TABLES IN ..."`.

`databricks experimental aitools tools discover-schema catalog.schema.gold_sales catalog.schema.gold_customers`

For Genie, knowing column distribution shapes the sample questions and text instructions. Probe cardinality, ranges, and top categorical values with aggregate SQL through `databricks experimental aitools tools query --warehouse <WH> "..."` so your sample questions reflect what's actually in the data. Both commands auto-pick the default warehouse; set `DATABRICKS_WAREHOUSE_ID` or pass `--warehouse <ID>` to override.

### Step 2: Create the Space

Define your space in a local JSON file (e.g., `genie_space.json`) for version control and easy iteration. See "serialized_space Format" below for the full structure.

```bash
# List all Genie Spaces
databricks genie list-spaces

# Create a Genie Space from a local file
# IMPORTANT: sample_questions require a 32-char hex "id" and "question" must be an array
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Explore sales data\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_space.json | jq -c '.' | jq -Rs '.')
}"

# Get space details (with full config)
databricks genie get-space SPACE_ID --include-serialized-space

# By default, after creation, tag the Genie Space to track resources created with this skill
databricks workspace-entity-tag-assignments create-tag-assignment \
  geniespaces SPACE_ID aidevkit_project --tag-value ai-dev-kit

# Delete a Genie Space
databricks genie trash-space SPACE_ID
```

### Step 3: Test and Iterate

Use `scripts/conversation.py` (see Conversation API section below) to test questions and verify answers are accurate.

If answers are inaccurate or incomplete, improve the space — see "Improving a Genie Space" below.

### Export & Import

```bash
# Export space configuration (extract serialized_space from get-space output)
databricks genie get-space SPACE_ID --include-serialized-space -o json | jq '.serialized_space' > genie_space.json

# Import: Create a new space with the exported serialized_space (then don't forge to tag)
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Migrated space\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_space.json)
}"
```

### Improving a Genie Space

When Genie answers are inaccurate or incomplete, improve the space by updating questions, SQL examples, or instructions:

```bash
# 1. Edit your local genie_space.json (add questions, fix SQL examples, improve instructions)

# 2. Push updates back to the space
databricks genie update-space SPACE_ID --json "{\"serialized_space\": $(cat genie_space.json | jq -c '.' | jq -Rs '.')}"
```

## serialized_space Format

The `serialized_space` field is a JSON string containing the full space configuration.

### Structure

```json
{
  "version": 2,
  "config": {
    "sample_questions": [...]
  },
  "data_sources": {
    "tables": [{"identifier": "catalog.schema.table"}]
  },
  "instructions": {
    "example_question_sqls": [...],
    "text_instructions": [...]
  }
}
```

### Field Format Requirements

**IMPORTANT:** All items in `sample_questions`, `example_question_sqls`, and `text_instructions` require a unique `id` field.

| Field | Format |
|-------|--------|
| `config.sample_questions[]` | `{"id": "32hexchars", "question": ["..."]}` |
| `instructions.example_question_sqls[]` | `{"id": "32hexchars", "question": ["..."], "sql": ["..."]}` |
| `instructions.text_instructions[]` | `{"id": "32hexchars", "content": ["..."]}` |

- **ID format:** 32-character lowercase hex UUID without hyphens.
- **Text fields are arrays:** `question`, `sql`, and `content` are arrays of strings, not plain strings.

### Text Instructions

`text_instructions` make the Genie Space more reliable by explaining:
- **Where to find information** — which tables contain which metrics
- **How to answer specific questions** — when a user asks X, use table Y with filter Z
- **Business context** — definitions, thresholds, and domain knowledge

Well-crafted instructions significantly improve answer accuracy.

### Complete Example

This example shows a properly formatted `serialized_space` with sample questions, SQL examples, and text instructions. Note that every item has a unique 32-char hex `id` and all text fields are arrays:

```json
{
  "version": 2,
  "config": {
    "sample_questions": [
      {"id": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4", "question": ["What is our current on-time performance?"]},...
    ]
  },
  "data_sources": {
    "tables": [
      {"identifier": "catalog.ops.gold_otp_summary"},...
    ]
  },
  "instructions": {
    "example_question_sqls": [
      {
        "id": "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
        "question": ["What is our on-time performance?"],
        "sql": ["SELECT flight_date, ROUND(SUM(on_time_count) * 100.0 / SUM(total_flights), 1) AS otp_pct\n", "FROM catalog.ops.gold_otp_summary\n", "WHERE flight_date >= date_sub(current_date(), 7)\n", "GROUP BY flight_date ORDER BY flight_date"]
      }
    ],
    "text_instructions": [
      {
        "id": "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
        "content": [
          "On-time performance (OTP) questions: Use gold_otp_summary table. OTP target is 85%.\n",
          "Delay analysis questions: Use gold_delay_analysis table. Filter by delay_code for specific delay types.\n",
          "When asked about 'this week' or 'recent': Use flight_date >= date_sub(current_date(), 7).\n",
          "When comparing aircraft: Join with gold_aircraft_reliability on tail_number."
        ]
      }
    ]
  }
}
```


## Cross-Workspace Migration

When migrating between workspaces, catalog names often differ. Export the space, remap with `sed`, then import:

```bash
sed -i '' 's/source_catalog/target_catalog/g' genie_space.json
```

Use `DATABRICKS_CONFIG_PROFILE=profile_name` to target different workspaces.

## Conversation API

Use `scripts/conversation.py` to ask questions programmatically:

```bash
# Ask a question
python scripts/conversation.py ask SPACE_ID "What were total sales last month?"

# Follow-up in same conversation (Genie remembers context)
python scripts/conversation.py ask SPACE_ID "Break down by region" --conversation-id CONV_ID

# With timeout for complex queries
python scripts/conversation.py ask SPACE_ID "Complex query" --timeout 120
```

Start a new conversation for unrelated topics. Use `--conversation-id` only for follow-ups on the same topic.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `sample_question.id must be provided` | Add 32-char hex UUID `id` to each sample question |
| `Expected an array for question` | Use `"question": ["text"]` not `"question": "text"` |
| No warehouse available | Create a SQL warehouse or provide `warehouse_id` |
| Empty `serialized_space` on export | Requires CAN EDIT permission on the space |
| Tables not found after migration | Remap catalog name in `serialized_space` before import |

## Related Skills

- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate data for Genie tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables
