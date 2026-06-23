# serialized_space JSON Schema

Complete structure for the `serialized_space` configuration. Include only sections relevant to the user's space.

## Contents
- Example Structure (full JSON)
- Field Reference: config, data_sources, instructions, benchmarks
- Prompt Matching Overview (format assistance, entity matching, limits)
- Important Notes (formatting rules, sorting, common mistakes)
- ID Generation

```json
{
  "version": 2,
  "config": {
    "sample_questions": [
      {
        "id": "a1b2c3d4e5f60000000000000000000a",
        "question": ["What were total sales last month?"]
      }
    ]
  },
  "data_sources": {
    "tables": [
      {
        "identifier": "catalog.schema.orders",
        "description": ["Daily sales transactions with line-item details"],
        "column_configs": [
          {
            "column_name": "region",
            "description": ["Sales region code: AMER, EMEA, APJ, LATAM"],
            "synonyms": ["area", "territory", "sales region"],
            "exclude": false,
            "enable_entity_matching": true,
            "enable_format_assistance": true
          },
          {
            "column_name": "etl_timestamp",
            "exclude": true,
            "enable_entity_matching": false,
            "enable_format_assistance": false
          }
        ]
      },
      {
        "identifier": "catalog.schema.products",
        "column_configs": [
          {
            "column_name": "category",
            "enable_entity_matching": true,
            "enable_format_assistance": true
          }
        ]
      }
    ],
    "metric_views": [
      {
        "identifier": "catalog.schema.revenue_metrics",
        "description": ["Revenue metrics"]
      }
    ]
  },
  "instructions": {
    "text_instructions": [
      {
        "id": "b2c3d4e5f6a70000000000000000000b",
        "content": ["Revenue = quantity * unit_price.\n", "Fiscal year starts April 1st."]
      }
    ],
    "example_question_sqls": [
      {
        "id": "c3d4e5f6a7b80000000000000000000c",
        "question": ["Show top 10 customers by revenue"],
        "sql": ["SELECT\n", "  customer_name,\n", "  SUM(amount) as total\n", "FROM catalog.schema.orders\n", "GROUP BY customer_name\n", "ORDER BY total DESC\n", "LIMIT 10"],
        "usage_guidance": ["Use this pattern for any top-N ranking question by a numeric metric"]
      }
    ],
    "sql_functions": [
      {
        "id": "d4e5f6a7b8c90000000000000000000d",
        "identifier": "catalog.schema.fiscal_quarter",
        "description": "Calculates the fiscal quarter from a date (fiscal year starts April 1)"
      }
    ],
    "join_specs": [
      {
        "id": "e5f6a7b8c9d00000000000000000000e",
        "left": {"identifier": "catalog.schema.orders", "alias": "orders"},
        "right": {"identifier": "catalog.schema.customers", "alias": "customers"},
        "sql": [
          "`orders`.`customer_id` = `customers`.`customer_id`",
          "--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"
        ],
        "comment": ["Join orders to customers on customer_id"],
        "instruction": ["Use this join when relating orders to customer demographics"]
      }
    ],
    "sql_snippets": {
      "filters": [
        {
          "id": "f6a7b8c9d0e10000000000000000000f",
          "display_name": "high value",
          "sql": ["orders.amount > 1000"],
          "synonyms": ["big deal", "large order"],
          "instruction": ["Apply when users ask about high-value or large orders"],
          "comment": ["Threshold aligned with finance team's definition"]
        }
      ],
      "expressions": [
        {
          "id": "a7b8c9d0e1f20000000000000000000a",
          "alias": "order_year",
          "display_name": "Order Year",
          "sql": ["YEAR(orders.order_date)"],
          "synonyms": ["year"],
          "instruction": ["Use for any year-based grouping of orders"],
          "comment": ["Standard date dimension for annual reporting"]
        }
      ],
      "measures": [
        {
          "id": "b8c9d0e1f2a30000000000000000000b",
          "alias": "total_revenue",
          "display_name": "Total Revenue",
          "sql": ["SUM(orders.quantity * orders.unit_price)"],
          "synonyms": ["revenue", "sales", "total sales"],
          "instruction": ["Use for any revenue aggregation"],
          "comment": ["Revenue includes all non-cancelled order line items"]
        }
      ]
    }
  },
  "benchmarks": {
    "questions": [
      {
        "id": "c9d0e1f2a3b40000000000000000000c",
        "question": ["What is average order value?"],
        "answer": [{"format": "SQL", "content": ["SELECT AVG(amount) FROM catalog.schema.orders"]}]
      }
    ]
  }
}
```

---

## Field Reference

### config

| Field | Type | Description |
|-------|------|-------------|
| `config.sample_questions[].id` | string | 32-char lowercase hex ID |
| `config.sample_questions[].question` | string[] | Single question string per entry |

### data_sources

| Field | Type | Description |
|-------|------|-------------|
| `data_sources.tables[].identifier` | string | Fully qualified table name (`catalog.schema.table`) |
| `data_sources.tables[].description` | string[] | Space-scoped description override (optional) |
| `data_sources.tables[].column_configs[]` | array | Per-column configuration (optional — set via API or manage flow) |
| `data_sources.tables[].column_configs[].column_name` | string | Column name |
| `data_sources.tables[].column_configs[].description` | string[] | Contextual description beyond the column name |
| `data_sources.tables[].column_configs[].synonyms` | string[] | Alternative names users might use for this column |
| `data_sources.tables[].column_configs[].exclude` | boolean | Hide this column from Genie (default: false) |
| `data_sources.tables[].column_configs[].enable_format_assistance` | boolean | **(v2 only)** Provide representative values so Genie understands data types and formatting. Auto-enabled via UI but **OFF by default via API** — must be set explicitly. Must be `true` for entity matching to work. |
| `data_sources.tables[].column_configs[].enable_entity_matching` | boolean | **(v2 only)** Match user terms to actual column values (e.g., "California" → "CA"). Auto-enabled via UI but **OFF by default via API** — must be set explicitly. Requires `enable_format_assistance: true`. Supports up to 120 columns, 1,024 distinct values per column (max 127 chars each). |
| `data_sources.metric_views[].identifier` | string | Fully qualified metric view name |
| `data_sources.metric_views[].description` | string[] | What the metric view computes |
| `data_sources.metric_views[].column_configs[]` | array | Per-column configuration (optional — same fields as table column_configs) |

> **v1 vs v2:** Spaces with `"version": 2` reject v1 column_config fields. Use the v2 equivalents instead:
> - `get_example_values` (v1) → `enable_format_assistance` (v2)
> - `build_value_dictionary` (v1) → `enable_entity_matching` (v2)
>
> Including v1 fields in a v2 space will cause API errors. Always use the v2 field names.

> **Prompt matching overview:** "Prompt matching" is the umbrella term for two features that work together:
> - **Format assistance** — provides representative values so Genie understands data types and formatting patterns.
> - **Entity matching** — provides curated lists of distinct values so Genie can map user terms to actual data (e.g., "California" → "CA"). Requires `enable_format_assistance: true` (turning off format assistance automatically disables entity matching).
>
> **UI vs API behavior:** When tables are added via the Genie space UI, both features are auto-enabled for eligible columns. **When creating spaces via the API, prompt matching is OFF by default.** You must explicitly include `column_configs` entries with `enable_format_assistance: true` and `enable_entity_matching: true` for each column that needs it. Columns not listed in `column_configs` will not have prompt matching.
>
> **Post-creation recommendation:** After creating a space via API, open it in the UI and verify that prompt matching is enabled for all key filter columns (Configure > Data > column > Advanced settings). You can also enable it for additional columns at that point.
>
> **Entity matching limits:** Up to 120 columns per space, 1,024 distinct values per column, max 127 characters per value. Tables with row filters or column masks are excluded from prompt matching.
>
> **When to disable:** Turn off format assistance (and entity matching) on columns that are excluded (`exclude: true`) or on high-cardinality freetext columns where entity matching adds no value.

### instructions

| Field | Type | Description |
|-------|------|-------------|
| `instructions.text_instructions[].id` | string | 32-char hex ID |
| `instructions.text_instructions[].content` | string[] | Instruction text segments. Max 1 text instruction per space. **Important:** The API concatenates array elements without separators — each element must end with `\n` or a space to avoid jammed text. |
| `instructions.example_question_sqls[].id` | string | 32-char hex ID |
| `instructions.example_question_sqls[].question` | string[] | Single natural language question |
| `instructions.example_question_sqls[].sql` | string[] | SQL query split by lines with `\n` |
| `instructions.example_question_sqls[].usage_guidance` | string[] | When Genie should apply this pattern (optional but recommended) |
| `instructions.example_question_sqls[].parameters` | array | Parameterized values (optional) |
| `instructions.example_question_sqls[].parameters[].name` | string | Parameter name (matches `:name` in SQL) |
| `instructions.example_question_sqls[].parameters[].description` | string[] | What the parameter represents |
| `instructions.example_question_sqls[].parameters[].type_hint` | string | Data type hint (e.g., `"STRING"`, `"INT"`, `"DATE"`) |
| `instructions.example_question_sqls[].parameters[].default_value` | object | Default value with `values` array (e.g., `{"values": ["month"]}`) |
| `instructions.sql_functions[].id` | string | 32-char hex ID |
| `instructions.sql_functions[].identifier` | string | Fully qualified UDF name |
| `instructions.sql_functions[].description` | string | What the function does (plain string, not array) |
| `instructions.join_specs[].id` | string | 32-char hex ID |
| `instructions.join_specs[].left` | object | Left table: `{"identifier": "catalog.schema.table", "alias": "short_name"}`. `alias` is recommended. |
| `instructions.join_specs[].right` | object | Right table: `{"identifier": "catalog.schema.table", "alias": "short_name"}`. `alias` is recommended. |
| `instructions.join_specs[].sql` | string[] | **Two elements required:** (1) Join condition using backtick-quoted alias references (e.g., `` `orders`.`customer_id` = `customers`.`customer_id` ``), (2) Relationship type annotation (e.g., `"--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"`). |
| `instructions.join_specs[].comment` | string[] | Business context for the relationship (optional) |
| `instructions.join_specs[].instruction` | string[] | Guidance on when to use this join (optional) |

> **Critical `join_specs` format requirement:** The `sql` array must contain **two elements**:
> 1. The join condition — use backtick-quoted alias or table name references: `` "`alias`.`column` = `alias`.`column`" ``
> 2. A **relationship type annotation** — one of:
>    - `"--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"`
>    - `"--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--"`
>    - `"--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--"`
>    - `"--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--"`
>
> **Without the `--rt=...--` annotation, the API rejects the request** with a protobuf parsing error. This annotation is required even though it is not documented in the official API reference.

### sql_snippets (shared fields)

All three snippet types (`filters`, `expressions`, `measures`) support these optional fields in addition to their required ones:

| Field | Type | Description |
|-------|------|-------------|
| `synonyms` | string[] | Alternative terms that trigger this snippet |
| `instruction` | string[] | When Genie should apply this snippet |
| `comment` | string[] | Additional context or notes |
| `display_name` | string | Human-readable name (required for filters, optional for measures/expressions) |

**Type-specific required fields:**

| Type | Required Fields |
|------|----------------|
| `sql_snippets.filters[]` | `id`, `sql` (string[]), `display_name` |
| `sql_snippets.expressions[]` | `id`, `sql` (string[]), `alias` |
| `sql_snippets.measures[]` | `id`, `sql` (string[]), `alias` |

> **Important:** The `sql` field in `sql_snippets` is a **string array** (`string[]`), the same format as `example_question_sqls[].sql`. Wrap the SQL fragment in a single-element array (e.g., `["SUM(orders.amount)"]`). The API rejects plain strings.
>
> **Column references must be table-qualified** (`table_name.column_name`) in all snippet types. The API accepts bare column names, but the Genie UI rejects them with "Table name or alias is required for column '...'". Filters must also omit the `WHERE` keyword — provide only the boolean condition.

### benchmarks

| Field | Type | Description |
|-------|------|-------------|
| `benchmarks.questions[].id` | string | 32-char hex ID (must be unique across `sample_questions` and `benchmarks.questions`) |
| `benchmarks.questions[].question` | string[] | Test question |
| `benchmarks.questions[].answer` | array | Expected answers. Find `format: "SQL"` for SQL benchmarks. |
| `benchmarks.questions[].answer[].format` | string | Answer format (typically `"SQL"`) |
| `benchmarks.questions[].answer[].content` | string[] | Expected SQL query segments |

---

## Important Notes

- `version`: **Required**. Use `2` for new spaces
- `question`: Must be an array with a **single question string** per entry
- `sql` (in `example_question_sqls`): Must be an **array of strings**. Each SQL clause should be a separate element with `\n` at the end:
  - Correct: `["SELECT\n", "  col1,\n", "  col2\n", "FROM table\n", "WHERE col1 > 0"]`
  - Wrong: `["SELECT col1, col2FROM tableWHERE col1 > 0"]`
- `sql` (in `sql_snippets`): Must be a **string array** (`string[]`), same format as `example_question_sqls`. Wrap the SQL fragment in an array:
  - Correct: `["SUM(quantity * unit_price)"]`
  - Wrong: `"SUM(quantity * unit_price)"` (plain string — API rejects this)
- **SQL snippets require table-qualified column references** (`table_name.column`). The API accepts bare column names, but the **UI rejects them** with "Table name or alias is required for column '...'". Always use `table_name.column_name` format in all snippet types (filters, measures, expressions):
  - Correct: `["orders.amount > 1000"]`
  - Wrong: `["amount > 1000"]` (UI rejects bare column names)
- **Filters must NOT include the `WHERE` keyword** — only the boolean condition. Genie adds the `WHERE` clause itself:
  - Correct: `["orders.amount > 1000"]`
  - Wrong: `["WHERE orders.amount > 1000"]`
- **ID Format**: All IDs must be exactly 32 lowercase hexadecimal characters (no hyphens)
- **Sorting**: All arrays of objects with `id` fields must be sorted alphabetically by `id`. Tables must be sorted by `identifier`. `column_configs` must be sorted by `column_name`.
- **Include only what's needed**: Omit sections that don't apply (e.g., skip `metric_views` if none). Note: `benchmarks` is required for new spaces.
- **Join spec format**: The `sql` array requires exactly **two elements**: (1) the join condition using backtick-quoted references, and (2) a `--rt=FROM_RELATIONSHIP_TYPE_...--` annotation. Without the relationship type annotation, the API rejects the request. For multi-column joins, create separate join specs.
- **`text_instructions` content formatting**: The API concatenates `content` array elements without any separator. Each element must end with `\n` or a trailing space to prevent text from being jammed together (e.g., `"Rule one.\n"` not `"Rule one."`)
- **column_configs**: Usually set post-creation via the manage flow or UI. For initial creation, column descriptions and synonyms can be added via `column_configs` in the API, or later through the Genie space UI. Note: `enable_entity_matching` requires `enable_format_assistance` to be `true` — the API will reject configurations where entity matching is enabled but format assistance is not.

---

## ID Generation

Generate unique 32-character hexadecimal IDs (UUID format without hyphens):

```python
import secrets
question_id = secrets.token_hex(16)  # Generates 32-char hex string
```

**Important ID Requirements:**
- Must be exactly 32 characters long
- Must be lowercase hexadecimal (0-9, a-f)
- No hyphens or other separators
- Must be unique within their collection
