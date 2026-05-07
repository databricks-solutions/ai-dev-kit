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

For Genie, knowing column distribution shapes the sample questions and text instructions. If you don't already know the data, probe cardinality, ranges, and top categorical values with aggregate SQL through `databricks experimental aitools tools query "..."` so your sample questions reflect what's actually in the data. Both commands auto-pick the default warehouse; set `DATABRICKS_WAREHOUSE_ID` to override.

Fan out independent probes (state ∈ `PENDING|RUNNING|SUCCEEDED|FAILED|CANCELED|CLOSED`):

```bash
submit() { databricks api post /api/2.0/sql/statements --json "$(jq -nc --arg w "$1" --arg s "$2" '{warehouse_id:$w,statement:$s,wait_timeout:"0s",on_wait_timeout:"CONTINUE"}')" | jq -r .statement_id; }
SIDS=(); for q in "$@"; do SIDS+=( "$(submit "$WH" "$q")" ); done
for s in "${SIDS[@]}"; do databricks api get "/api/2.0/sql/statements/$s" | jq '{state:.status.state, rows:.result.data_array}'; done
# cancel: databricks api post "/api/2.0/sql/statements/$SID/cancel"
```

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

Use the Conversation API (section below) to ask questions and verify answers. If answers are inaccurate or incomplete, improve the space — see "Improving a Genie Space" below.

### Export & Import

**Convention:** `genie_space.json` always holds the **parsed** space object (not a JSON-string-encoded blob), so it's readable and editable. At each use site we stringify it with `jq -c '.' | jq -Rs '.'` — same pattern as Step 2 Create and "Improving a Genie Space" below. `jq -r '.serialized_space | fromjson'` on export strips the outer quoting so the file is already a parsed object.

```bash
# Export: extract serialized_space AND unwrap it to a parsed object on disk
databricks genie get-space SPACE_ID --include-serialized-space -o json \
  | jq '.serialized_space | fromjson' > genie_space.json

# Import: same stringify pattern as Step 2 (Create)
databricks genie create-space --json "{
  \"warehouse_id\": \"WAREHOUSE_ID\",
  \"title\": \"Sales Analytics\",
  \"description\": \"Migrated space\",
  \"parent_path\": \"/Workspace/Users/you@company.com/genie_spaces\",
  \"serialized_space\": $(cat genie_space.json | jq -c '.' | jq -Rs '.')
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

### Field Format Requirements

**IMPORTANT:** All items in `sample_questions`, `example_question_sqls`, and `text_instructions` require a unique `id` field.

| Field | Format |
|-------|--------|
| `config.sample_questions[]` | `{"id": "32hexchars", "question": ["..."]}` |
| `instructions.example_question_sqls[]` | `{"id": "32hexchars", "question": ["..."], "sql": ["..."]}` |
| `instructions.text_instructions[]` | `{"id": "32hexchars", "content": ["..."]}` |

- **ID format:** 32-character lowercase hex, unique across **all three lists combined** (a duplicate between e.g. `text_instructions` and `example_question_sqls` is rejected).
- **Text fields are arrays:** `question`, `sql`, and `content` are arrays of strings, not plain strings.
- **Sort order matters:** `data_sources.tables` must be sorted by `identifier`; `example_question_sqls` and `text_instructions` must be sorted by `id`. (`sample_questions` is silently re-sorted server-side.)
- **Simple ID scheme that satisfies both rules:** prefix per list + monotonic counter, total 32 hex chars — `1…0001`, `1…0002` for `sample_questions`; `2…0001`, `2…0002` for `example_question_sqls`; `3…0001` for `text_instructions`. Authoring order = sort order, no collisions.

### Text Instructions

`text_instructions` make the Genie Space more reliable by explaining:
- **Where to find information** — which tables contain which metrics
- **How to answer specific questions** — when a user asks X, use table Y with filter Z
- **Business context** — definitions, thresholds, and domain knowledge

Well-crafted instructions significantly improve answer accuracy.

### Example

Top-level keys are `version`, `config`, `data_sources`, `instructions`. Every item in `sample_questions`, `example_question_sqls`, and `text_instructions` needs a unique 32-char hex `id` and all text fields are arrays:

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

Ask questions via three CLI primitives: `start-conversation`, `create-message` (follow-ups), and `get-message` (state + SQL + text). `--no-wait` on `start-conversation` / `create-message` returns immediately with `{conversation_id, message_id}`; poll `get-message` until `.status` is `COMPLETED`, `FAILED`, or `CANCELLED`. Intermediate states you'll see: `SUBMITTED`, `FILTERING_CONTEXT`, `ASKING_AI`, `EXECUTING_QUERY`.

```bash
# Start a new conversation (async — get IDs back immediately)
databricks genie start-conversation --no-wait SPACE_ID "What were total sales last month?"
# → {"conversation_id": "...", "message_id": "..."}

# Poll state
databricks genie get-message SPACE_ID CONV_ID MSG_ID | jq '{status, error}'

# When COMPLETED, pull the generated SQL and any text reply
databricks genie get-message SPACE_ID CONV_ID MSG_ID \
  | jq '.attachments[] | {sql: .query.query, description: .query.description, text: .text.content}'

# Fetch the query result rows (columns + data_array)
databricks genie get-message-attachment-query-result SPACE_ID CONV_ID MSG_ID ATTACHMENT_ID \
  | jq '{columns: .statement_response.manifest.schema.columns | map({name, type: .type_name}),
         rows: .statement_response.result.data_array}'

# Follow-up in the same conversation (Genie remembers context)
databricks genie create-message --no-wait SPACE_ID CONV_ID "Break that down by region"
```

Start a new conversation for unrelated topics. Use `create-message` (same `CONV_ID`) only for follow-ups on the same topic.

On `FAILED`, `get-message` populates `.error.error` with the underlying error string (e.g. `[INSUFFICIENT_PERMISSIONS] ...`) and `.error.type` (e.g. `SQL_EXECUTION_EXCEPTION`). Attachments may still include `suggested_questions` even when the primary query failed.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `sample_question.id must be provided` | Add 32-char hex UUID `id` to each sample question |
| `Expected an array for question` | Use `"question": ["text"]` not `"question": "text"` |
| No warehouse available | Create a SQL warehouse or provide `warehouse_id` |
| Empty `serialized_space` on export | Requires CAN EDIT permission on the space |
| Tables not found after migration | Remap catalog name in `serialized_space` before import |
| Slow answers / query timeouts | Size up the warehouse attached to the space; simplify or pre-aggregate tall source tables |
| Wrong or empty answers | Add `example_question_sqls` and `text_instructions` — see "Improving a Genie Space" |

## Related Skills

- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** - Generate data for Genie tables
- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** - Build bronze/silver/gold tables
