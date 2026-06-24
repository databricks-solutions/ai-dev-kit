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

For Genie, knowing column distribution shapes the sample questions and text instructions. If you don't already know the data, probe cardinality, ranges, and top categorical values with aggregate SQL through `databricks experimental aitools tools query --warehouse <WH> "..."` so your sample questions reflect what's actually in the data. Both commands auto-pick the default warehouse; set `DATABRICKS_WAREHOUSE_ID` or pass `--warehouse <ID>` to override.

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

The `serialized_space` field is a JSON string containing the full space configuration. Six constructs the schema supports, all optional except `version` and `data_sources.tables`:

| Construct | Location | Purpose |
|---|---|---|
| `version` | top-level | Integer **`2`** (not string `"2"`). |
| `data_sources.tables[]` | top-level | UC tables (or metric views) the space queries. Each has `identifier`, plus optional `column_configs[]` for per-column behavior. |
| `config.sample_questions[]` | top-level | Suggested starter questions shown in the UI. |
| `instructions.example_question_sqls[]` | top-level | Trusted question↔SQL pairs ("when asked X, run this SQL"). |
| `instructions.text_instructions[]` | top-level | Free-form rules ("for revenue questions use table Y", domain glossary, defaults). |
| `instructions.sql_functions[]` | top-level | UC SQL functions the space can call as tools (identifier only). |
| `benchmarks.questions[]` | top-level | Evaluation pairs (`question` + `answer` SQL) for accuracy testing. |

### Field-shape rules

- **`version: 2`** — integer, not a string.
- **All text fields are arrays of strings.** `question`, `content`, `sql`, and `answer[].content` are always lists, never bare strings. Single-element arrays are fine; the platform concatenates them.
- **Every item needs a unique `id`** — 32-character lowercase hex. Uniqueness is enforced **across all lists combined** (a duplicate between e.g. `text_instructions` and `example_question_sqls` is rejected). The platform reassigns IDs server-side on create, so exact values don't matter for creation — only that they're present, 32 chars, and unique.
- **Sort order matters:** `data_sources.tables` must be sorted by `identifier`; `example_question_sqls`, `text_instructions`, `sql_functions`, and `benchmarks.questions` must be sorted by `id`. (`sample_questions` is silently re-sorted server-side.)
- **Omit empty sections entirely** rather than including `[]` — both work, but live exports omit them when empty.
- **Author-time ID convention** (optional, recommended): prefix the 32 chars by section to keep them readable and sorted in authoring order — `1…0001` for sample_questions, `2…` for example_question_sqls, `3…` for text_instructions, `4…` for sql_functions, `5…` for benchmarks. The platform doesn't enforce this; it's just convenient.

### Text Instructions

`text_instructions` make the Genie Space more reliable by explaining:
- **Where to find information** — which tables contain which metrics
- **How to answer specific questions** — when a user asks X, use table Y with filter Z
- **Business context** — definitions, thresholds, and domain knowledge

Well-crafted instructions significantly improve answer accuracy.

### Complete example

A populated space exercising every construct (`version`, `data_sources` with `column_configs`, `sample_questions`, `example_question_sqls`, `text_instructions`, `sql_functions`, `benchmarks`):

```json
{
  "version": 2,
  "data_sources": {
    "tables": [
      {
        "identifier": "main.analytics.gold_customers",
        "column_configs": [
          {"column_name": "customer_segment", "enable_format_assistance": true, "enable_entity_matching": true},
          {"column_name": "ltv_usd", "enable_format_assistance": true}
        ]
      },
      {"identifier": "main.analytics.gold_daily_sales"},
      {"identifier": "main.analytics.gold_product_perf"}
    ]
  },
  "config": {
    "sample_questions": [
      {"id": "10000000000000000000000000000001", "question": ["What were total sales last month?"]},
      {"id": "10000000000000000000000000000002", "question": ["Which 5 products had the highest revenue this quarter?"]},
      {"id": "10000000000000000000000000000003", "question": ["Show weekly revenue trend with YoY comparison"]},
      {"id": "10000000000000000000000000000004", "question": ["Which customers churned but had high LTV?"]}
    ]
  },
  "instructions": {
    "example_question_sqls": [
      {
        "id": "20000000000000000000000000000001",
        "question": ["What were total sales last month?"],
        "sql": [
          "SELECT SUM(total_revenue) AS revenue\n",
          "FROM main.analytics.gold_daily_sales\n",
          "WHERE sale_date >= date_trunc('MONTH', add_months(current_date(), -1))\n",
          "  AND sale_date <  date_trunc('MONTH', current_date())"
        ]
      },
      {
        "id": "20000000000000000000000000000002",
        "question": ["Show weekly revenue trend with YoY comparison"],
        "sql": [
          "SELECT date_trunc('WEEK', sale_date) AS week,\n",
          "       SUM(CASE WHEN year(sale_date)=year(current_date())   THEN total_revenue END) AS revenue_this_yr,\n",
          "       SUM(CASE WHEN year(sale_date)=year(current_date())-1 THEN total_revenue END) AS revenue_last_yr\n",
          "FROM main.analytics.gold_daily_sales\n",
          "WHERE sale_date >= add_months(current_date(), -12)\n",
          "GROUP BY 1 ORDER BY 1"
        ]
      }
    ],
    "text_instructions": [
      {
        "id": "30000000000000000000000000000001",
        "content": [
          "Revenue / sales questions: use gold_daily_sales; sale_date is the grain, truncate to WEEK/MONTH/QUARTER as needed.\n",
          "Product-level questions: use gold_product_perf.\n",
          "Customer questions (churn, LTV, segmentation): use gold_customers."
        ]
      },
      {
        "id": "30000000000000000000000000000002",
        "content": [
          "When asked 'last month' / 'this quarter', always anchor on current_date() — never hard-code dates.\n",
          "Default LIMIT 100 on unbounded queries. Default 'top N' to 10 if unspecified.\n",
          "Monetary values are USD. Round percentages to 1 decimal place."
        ]
      }
    ],
    "sql_functions": [
      {"id": "40000000000000000000000000000001", "identifier": "main.analytics.format_currency"}
    ]
  },
  "benchmarks": {
    "questions": [
      {
        "id": "50000000000000000000000000000001",
        "question": ["What was last month's total revenue?"],
        "answer": [{
          "format": "SQL",
          "content": [
            "SELECT SUM(total_revenue) AS revenue FROM main.analytics.gold_daily_sales ",
            "WHERE sale_date >= date_trunc('MONTH', add_months(current_date(), -1)) ",
            "  AND sale_date <  date_trunc('MONTH', current_date())"
          ]
        }]
      }
    ]
  }
}
```

Notes on the example:
- `version` is the integer `2`.
- `data_sources.tables` is sorted by `identifier`. First table shows the `column_configs` extension (per-column toggles for format assistance / entity matching); the other two use the minimal `{"identifier": ...}` form, which is also valid.
- All text payloads (`question`, `content`, `sql`, `answer[].content`) are arrays.
- IDs use the section-prefix scheme (1xxx/2xxx/3xxx/4xxx/5xxx); 32 chars each, unique across all lists.
- `sql_functions[]` references a UC SQL/Python function by `identifier`; the function definition itself lives in UC, not here.
- `benchmarks` is top-level (sibling of `instructions`), not nested under it. Each `answer` is a list of `{format, content}` objects — `"format": "SQL"` is the common case.


## Cross-Workspace Migration

When migrating between workspaces, catalog names often differ. Export the space, remap, then import. Use `jq` to rewrite identifiers — it's portable across macOS/Linux (unlike `sed -i`, whose in-place flag differs between BSD and GNU) and operates on JSON values directly:

```bash
jq --arg src source_catalog --arg dst target_catalog \
   '(.. | strings) |= gsub($src; $dst)' genie_space.json \
   > genie_space.tmp && mv genie_space.tmp genie_space.json
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
