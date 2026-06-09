# Authoring a High-Quality Genie Space

The Quick Start in [SKILL.md](SKILL.md) creates a *basic* space: a display name, a
table list, a description, and a handful of sample questions. That works, but it
leaves Genie to infer everything else. The spaces that answer accurately are the
ones that ship **curation** — column synonyms, structured instructions, certified
example SQL, join specs, reusable measures/filters, and benchmarks.

All of that lives in the `serialized_space` payload (see
[spaces.md §What is serialized_space?](spaces.md#what-is-serialized_space)). You do
not need the Databricks UI to set it. Build the `serialized_space` JSON yourself and
pass it to `manage_genie(action="create_or_update", serialized_space=...)`.

This guide is the playbook for doing that well. Follow it whenever the goal is a
production-grade space, not a throwaway.

## The golden rule: ground everything in real data

The single biggest quality lever is **never inventing values**. Genie answers badly
when example SQL filters on `status = 'ACTIVE'` but the column actually contains
`'active'`, `'Active'`, and `'A'`. Before generating any SQL, instructions, or
filters, pull the **actual** distinct values from the data and use only those.

> IMPORTANT — Use ONLY real values from the data in SQL, filters, and instructions.
> Do NOT invent status values, tier names, category labels, or date formats.

## Workflow

### 1. Inspect deeply (not just the schema)

Start with the schema, then profile the columns you intend to filter or group on.

```
# MCP Tool: get_table_stats_and_schema
get_table_stats_and_schema(catalog="my_catalog", schema="sales", table_stat_level="SIMPLE")
# Returns: table + column names, types, row counts, sample values, cardinality
```

For categorical columns (low/medium cardinality) you plan to reference, pull the real
distinct values so you can ground filters and instructions:

```
# MCP Tool: execute_sql
execute_sql(query="SELECT DISTINCT status FROM my_catalog.sales.orders LIMIT 50")
execute_sql(query="SELECT MIN(order_date), MAX(order_date) FROM my_catalog.sales.orders")
```

Note for each table: the date/timestamp columns, the numeric metrics, the categorical
dimensions, the foreign keys, and any ETL/metadata columns to exclude (e.g.
`_ingested_at`, `_rescued_data`, surrogate hashes).

### 2. Build each config layer

A strong space populates **all** of the following. Counts below are good defaults for
a 1–5 table space; scale sample questions and example SQL up modestly for larger ones.

| Layer | What to generate | Default count |
|---|---|---|
| Table & column descriptions + **synonyms** | A 1–2 sentence description per table; a short description for every column; `synonyms` for abbreviated/technical names | all columns |
| **Sample questions** | Natural-language questions a business user would ask | exactly 5 |
| **Text instructions** | Domain knowledge under canonical GSL headers (see below) | 1 block, < 2,000 chars |
| **Example question→SQL** | Question + SQL pairs that teach query patterns, with `usage_guidance` and parameters | ~12 |
| **Measures** | Reusable aggregation expressions (COUNT/SUM/AVG) | 5 |
| **Filters** | Reusable WHERE-clause snippets (date ranges, status/category) | 5 |
| **Expressions** | Computed dimension columns (date parts, CASE labels) | 3 |
| **Join specs** | One per table relationship | required if 2+ tables |
| **Benchmarks** | Ground-truth question + expected-SQL pairs for quality scoring | 10 |

#### Table & column descriptions + synonyms

- If a table comment is empty or vague, write a clear 1–2 sentence description.
- Add a brief description for **every** column. Even obvious names benefit from
  context (`order_date` → "Date the order was placed").
- Add `synonyms` for columns with abbreviated or technical names users refer to
  differently: `cust_id` → `["customer ID", "account number"]`,
  `txn_amt` → `["transaction amount", "payment amount"]`. Skip columns with clear,
  unambiguous names.
- Mark ETL/metadata columns as excluded so Genie ignores them.

#### Text instructions: the canonical GSL section vocabulary

`text_instructions` is a **last resort** layer — it is for natural-language guidance
Genie cannot infer from the structured config. Keep SQL, metric definitions, joins,
and column docs **out** of it (those go in the layers below). Use these five canonical
headers, in this order, omitting any that are empty:

| Header | What goes here |
|---|---|
| `## PURPOSE` | One or two bullets: the space's scope and audience. |
| `## DISAMBIGUATION` | Clarification triggers ("When the user asks about 'customer performance' without a time range, ask them to clarify the period") and term-resolution rules ("'Q1' means calendar Q1 unless the user says 'fiscal Q1'"). |
| `## DATA QUALITY NOTES` | NULL handling, known bad rows, column semantics not in the column description. |
| `## CONSTRAINTS` | Hard guardrails: what never to show (PII columns, secrets), what not to do. |
| `## Instructions you must follow when providing summaries` | Summary behavior: rounding rules, mandatory caveats, date-range statements. **Use this exact heading — it is Databricks's blessed string. Do not paraphrase it.** |

Rules:
- Markdown `## Header` per section; dash bullets, one idea per bullet; blank line between sections.
- **No SQL** inside bullets — SQL belongs in `sql_snippets` / `example_question_sqls` / `join_specs`.
- Keep the **total under 2,000 characters**. Long instructions push higher-value SQL context out of Genie's prompt window.
- Every bullet should reference a concrete asset (table, column, user phrase) or be a specific behavioral rule. Vague guidance ("be helpful", "follow best practices") is an anti-pattern.

Example block:

```markdown
## PURPOSE
- Answer questions about order revenue for FY2024 US retail orders.
- Users are merchandising managers — assume retail/e-commerce fluency.

## DISAMBIGUATION
- When the user asks about "customer performance" without a time range, ask them to clarify the period.
- "Q1" means calendar Q1 unless the user says "fiscal Q1".

## DATA QUALITY NOTES
- orders.order_amount is NULL for cancelled rows — filter with is_cancelled = false.

## CONSTRAINTS
- Never show PII columns (customer_email, customer_phone).

## Instructions you must follow when providing summaries
- Round percentages to two decimal places.
- Always state the date range used in the summary.
```

#### Example question→SQL pairs

Generate ~12 question+SQL pairs that teach Genie how to write correct queries.

- Use fully-qualified table names (`catalog.schema.table`).
- Use parameterized SQL (`:param_name`) when the question involves user-supplied values.
- Each parameter needs `name`, `type_hint` (STRING/INTEGER/DOUBLE/DECIMAL/DATE/BOOLEAN), a real `default_value` from the data, and a `description`.
- The question should be concrete (use the default value, not a placeholder).
- Mix ~4 hardcoded patterns + ~8 parameterized queries.
- Cover diverse patterns: aggregation, filtering, grouping, joins, date ranges, top-N.
- Include a `usage_guidance` sentence for each — when Genie should use this pattern ("Use for any top-N ranking question", "Use when filtering by date range").
- Only use filter values that appear in the data.

#### Measures, filters, expressions (reusable SQL snippets)

These are always applicable — generate them even for a single table.

- **measures** (5): reusable aggregation expressions. `{alias, sql, display_name}`. Include COUNT, SUM, AVG on numeric/date columns.
- **filters** (5): reusable WHERE conditions (without the `WHERE` keyword). `{display_name, sql}`. Date ranges, status/category filters, common lookups.
- **expressions** (3): computed dimension columns. `{alias, sql, display_name}`. Date parts (YEAR/MONTH), CASE labels, concatenations.

Use fully-qualified `catalog.schema.table.column` names in all snippet SQL.

#### Join specs

Required when 2+ tables. One entry per relationship, one direction only
(orders→customers, not both). Each: left table/column, right table/column, and a
relationship of `MANY_TO_ONE`, `ONE_TO_MANY`, or `MANY_TO_MANY`.

#### Benchmarks

Generate 10 question + expected-SQL pairs used to score the space's quality.

- Hardcoded literal values only — **no** `:param_name` placeholders.
- Cover aggregation, filtering, grouping, and join patterns; mix single- and multi-table.
- The expected SQL must be the **most direct, natural** answer. Do NOT add extra WHERE clauses the question didn't ask for, unnecessary JOINs, or defensive NULL filters. It should be what a skilled analyst writes to answer exactly that question — otherwise a simpler-but-correct Genie answer gets scored wrong.

### 3. Validate every generated SQL before embedding it

Generated SQL that doesn't run is worse than no SQL. Test each example query and
benchmark with `execute_sql` (substitute parameter default values for any `:param`),
and fix or drop anything that errors or returns zero rows for a question that should
return data.

```
# MCP Tool: execute_sql
execute_sql(query="SELECT region, SUM(total_amount) AS revenue FROM my_catalog.sales.orders WHERE region = 'North America' GROUP BY region")
```

### 4. Create the space with the full config

Assemble the `serialized_space` JSON (shapes below) and create:

```python
manage_genie(
    action="create_or_update",
    display_name="Sales Analytics",
    warehouse_id="abc123def456",          # omit to auto-detect
    description="Order revenue analytics for FY2024 US retail.",
    serialized_space=json.dumps(config),  # the assembled config
)
```

## serialized_space field shapes

Version 2. Every item carries a 32-character lowercase-hex `id`. Within each array,
**sort items by `id`** (and `column_configs` by `column_name`, `tables`/`metric_views`
by `identifier`). String-valued content fields are **arrays of strings** (SQL is split
into lines, each line keeping its trailing `\n` except the last).

```json
{
  "version": 2,
  "config": {
    "sample_questions": [
      { "id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6", "question": ["What were total sales last month?"] }
    ]
  },
  "data_sources": {
    "tables": [
      {
        "identifier": "my_catalog.sales.orders",
        "description": ["Transaction history: one row per order."],
        "column_configs": [
          {
            "column_name": "cust_id",
            "description": ["Foreign key to customers."],
            "synonyms": ["customer ID", "account number"],
            "enable_format_assistance": true,
            "enable_entity_matching": true
          },
          {
            "column_name": "_ingested_at",
            "exclude": true,
            "enable_format_assistance": false,
            "enable_entity_matching": false
          }
        ]
      }
    ]
  },
  "instructions": {
    "text_instructions": [
      { "id": "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7",
        "content": ["## PURPOSE\n- Answer order-revenue questions for FY2024 US retail.\n", "## CONSTRAINTS\n- Never show PII columns (customer_email).\n"] }
    ],
    "example_question_sqls": [
      {
        "id": "c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",
        "question": ["Show revenue for North America"],
        "sql": ["SELECT region, SUM(total_amount) AS revenue\n", "FROM my_catalog.sales.orders\n", "WHERE region = :region_name\n", "GROUP BY region"],
        "usage_guidance": ["Use for revenue aggregation filtered by region."],
        "parameters": [
          { "name": "region_name", "type_hint": "STRING",
            "description": ["Sales region. Values: North America, EMEA, APJ, LATAM"],
            "default_value": { "values": ["North America"] } }
        ]
      }
    ],
    "sql_snippets": {
      "measures": [
        { "id": "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9", "alias": "total_revenue", "sql": ["SUM(my_catalog.sales.orders.total_amount)"], "display_name": "Total Revenue" }
      ],
      "filters": [
        { "id": "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0", "display_name": "Last 30 days", "sql": ["my_catalog.sales.orders.order_date >= current_date() - INTERVAL 30 DAYS"] }
      ],
      "expressions": [
        { "id": "f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1", "alias": "order_year", "sql": ["YEAR(my_catalog.sales.orders.order_date)"], "display_name": "Order Year" }
      ]
    },
    "join_specs": [
      {
        "id": "a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2",
        "left": { "identifier": "my_catalog.sales.orders", "alias": "orders" },
        "right": { "identifier": "my_catalog.sales.customers", "alias": "customers" },
        "sql": ["`orders`.`cust_id` = `customers`.`customer_id`", "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"]
      }
    ]
  },
  "benchmarks": {
    "questions": [
      {
        "id": "b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3",
        "question": ["What was total revenue in North America?"],
        "answer": [{ "format": "SQL", "content": ["SELECT SUM(total_amount) FROM my_catalog.sales.orders\n", "WHERE region = 'North America'"] }]
      }
    ]
  }
}
```

Notes on specific fields:

- **Join `sql`** is a two-element array: the backtick-quoted equality condition using
  the table aliases, followed by a relationship tag
  `--rt=FROM_RELATIONSHIP_TYPE_<REL>--` where `<REL>` is `MANY_TO_ONE`, `ONE_TO_MANY`,
  or `MANY_TO_MANY`.
- **Filter `sql`** is the condition **without** the leading `WHERE`.
- **Parameter `type_hint`** must be one of `STRING`, `INTEGER`, `DOUBLE`, `DECIMAL`,
  `DATE`, `BOOLEAN` (normalize `NUMBER`/`INT` → `INTEGER`, `FLOAT` → `DOUBLE`).
- **Excluded columns** set `exclude: true` and turn off `enable_format_assistance` and
  `enable_entity_matching`.

## API constraints to respect

The Genie API rejects payloads that break these. Enforce them while assembling:

| Constraint | Limit |
|---|---|
| `instructions.text_instructions` | **At most 1** object (put all sections in its one `content` array) |
| Per-string length | ≤ 25,000 characters |
| Tables | ≤ 30 |
| Total serialized size | ≤ 3.5 MB |
| IDs | 32-char lowercase hex, **unique** across all instruction scopes and across `sample_questions` + `benchmarks.questions` |
| Array ordering | sorted (by `id`; `column_configs` by `column_name`; `tables`/`metric_views` by `identifier`) |
| Empty `sql` snippets | remove any measure/filter/expression with empty SQL |
| Join specs | must have both `left` and `right`; drop otherwise |

If a benchmark or example SQL fails validation in step 3 and can't be repaired, drop
it rather than shipping broken SQL.

## Worked end-to-end sequence

1. `get_table_stats_and_schema(...)` for each schema → schema, sample values, cardinality.
2. `execute_sql("SELECT DISTINCT <categorical_col> ...")` for the columns you'll filter/group on → real values.
3. Draft each layer (descriptions+synonyms, 5 sample questions, GSL text instructions, ~12 example SQLs, 5 measures / 5 filters / 3 expressions, join specs, 10 benchmarks) — grounded in the real values from steps 1–2.
4. `execute_sql(...)` to validate every example SQL and benchmark; fix or drop failures.
5. Assemble `serialized_space` per the shapes above, respecting the constraints.
6. `manage_genie(action="create_or_update", display_name=..., warehouse_id=..., serialized_space=json.dumps(config))`.
7. `ask_genie(space_id=..., question=...)` to smoke-test a few sample questions.

## References

- [SKILL.md](SKILL.md) — tool reference and Quick Start
- [spaces.md](spaces.md) — space management, export/import, migration, troubleshooting
- [conversation.md](conversation.md) — querying via the Conversation API
- Databricks Genie best practices: <https://docs.databricks.com/aws/en/genie/best-practices>
- `serialized_space` schema: <https://docs.databricks.com/aws/en/genie/conversation-api#understanding-the-serialized_space-field>
- Validation rules (ID format, sorting, size limits): <https://docs.databricks.com/aws/en/genie/conversation-api#validation-rules-for-serialized_space>
