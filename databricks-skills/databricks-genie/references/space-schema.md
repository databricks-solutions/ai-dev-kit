# Serialized Space JSON Schema Reference

The `serialized_space` field is a JSON string (parsed into a dict) returned by `client.genie.get_space(space_id, include_serialized_space=True)`. It contains the full Genie Space configuration.

## Table of Contents

- [Top-Level Structure](#top-level-structure)
- [`config`](#config)
- [`data_sources`](#data_sources)
- [Tables](#tables)
- [`instructions`](#instructions)
- [Text Instructions](#text-instructions)
- [Example Question SQLs](#example-question-sqls)
- [Join Specs](#join-specs)
- [SQL Functions](#sql-functions)
- [SQL Snippets](#sql-snippets)
- [`benchmarks`](#benchmarks)
- [Validation Rules](#validation-rules)

## Top-Level Structure

```json
{
  "version": 2,
  "config": { ... },
  "data_sources": { ... },
  "instructions": { ... },
  "benchmarks": { ... }
}
```

---

## `config`

Space-level configuration.

```json
{
  "config": {
    "sample_questions": [
      {
        "id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "question": ["What are the top 10 products by revenue?"]
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sample_questions` | array | Questions shown in the Genie UI as starting points |
| `sample_questions[].id` | string | 32-char lowercase hex identifier |
| `sample_questions[].question` | array of strings | The question text displayed to users |

---

## `data_sources`

Tables, columns, and metric views available to Genie.

### Tables

```json
{
  "data_sources": {
    "tables": [
      {
        "id": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "identifier": "catalog.schema.table_name",
        "description": ["Human-readable table description"],
        "column_configs": [
          {
            "id": "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6a7",
            "column_name": "column_name",
            "description": ["What this column contains"],
            "synonyms": ["alias1", "alias2"],
            // v1 only (rejected by v2 spaces — use v2 equivalents below)
            "get_example_values": true,
            "build_value_dictionary": true,
            "exclude": false,
            // v2 only (replaces v1 fields above)
            "enable_entity_matching": false,
            "enable_format_assistance": false
          }
        ]
      }
    ],
    "metric_views": [
      {
        "id": "c3d4e5f6a7b8c9d0e1f2a3b4c5d6a7b8",
        "identifier": "catalog.schema.metric_view_name",
        "description": ["What this metric view computes"]
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `tables` | array | Unity Catalog tables exposed to Genie |
| `tables[].id` | string | 32-char lowercase hex identifier |
| `tables[].identifier` | string | Fully qualified table name (`catalog.schema.table`) |
| `tables[].description` | array of strings | Human-readable description of the table |
| `tables[].column_configs` | array | Column definitions with metadata |
| `tables[].column_configs[].id` | string | 32-char lowercase hex identifier |
| `tables[].column_configs[].column_name` | string | Column name |
| `tables[].column_configs[].description` | array of strings | Contextual description beyond the column name |
| `tables[].column_configs[].synonyms` | array of strings | Alternative names users might use |
| `tables[].column_configs[].get_example_values` | boolean | (v1 only — use `enable_format_assistance` in v2) Whether Genie fetches sample values for this column |
| `tables[].column_configs[].build_value_dictionary` | boolean | (v1 only — use `enable_entity_matching` in v2) Whether Genie builds a dictionary of discrete values |
| `tables[].column_configs[].exclude` | boolean | Whether to hide this column from Genie |
| `tables[].column_configs[].enable_entity_matching` | boolean | (v2 only — replaces `build_value_dictionary`) Whether Genie matches user terms to column values |
| `tables[].column_configs[].enable_format_assistance` | boolean | (v2 only — replaces `get_example_values`) Whether Genie applies format hints for this column |
| `metric_views` | array | Pre-computed metric views |
| `metric_views[].id` | string | 32-char lowercase hex identifier |
| `metric_views[].identifier` | string | Fully qualified metric view name |
| `metric_views[].description` | array of strings | What the metric view computes |

> **Version Note:** Spaces with `"version": 2` reject v1 fields (`get_example_values`, `build_value_dictionary`). Use their v2 equivalents (`enable_format_assistance`, `enable_entity_matching`) instead. Including v1 fields in a v2 space config will cause API errors.

---

## `instructions`

Guidance that shapes how Genie interprets questions and generates SQL.

### Text Instructions

```json
{
  "instructions": {
    "text_instructions": [
      {
        "id": "d4e5f6a7b8c9d0e1f2a3b4c5d6a7b8c9",
        "content": ["Revenue is calculated as quantity * unit_price.", "Always filter out cancelled orders unless explicitly requested."]
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `text_instructions` | array | Free-text instructions applied globally |
| `text_instructions[].id` | string | 32-char lowercase hex identifier |
| `text_instructions[].content` | array of strings | The instruction text segments |

### Example Question SQLs

```json
{
  "instructions": {
    "example_question_sqls": [
      {
        "id": "e5f6a7b8c9d0e1f2a3b4c5d6a7b8c9d0",
        "question": ["What is the monthly revenue trend for the last year?"],
        "sql": ["SELECT DATE_TRUNC('month', order_date) AS month, ", "SUM(quantity * unit_price) AS revenue ", "FROM catalog.schema.orders ", "WHERE order_date >= DATE_ADD(CURRENT_DATE(), -365) ", "GROUP BY 1 ORDER BY 1"],
        "usage_guidance": ["Use this pattern for any time-series trend question involving revenue or sales amounts"],
        "parameters": [
          {
            "name": "time_period",
            "description": ["The time granularity (day, week, month, quarter, year)"],
            "type_hint": "STRING",
            "default_value": { "values": ["month"] }
          }
        ]
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `example_question_sqls` | array | Question-SQL pairs that teach Genie query patterns |
| `example_question_sqls[].id` | string | 32-char lowercase hex identifier |
| `example_question_sqls[].question` | array of strings | Natural language question segments |
| `example_question_sqls[].sql` | array of strings | The SQL query segments (join to form full query) |
| `example_question_sqls[].usage_guidance` | array of strings | When Genie should apply this pattern |
| `example_question_sqls[].parameters` | array | Parameterized values in the query |
| `example_question_sqls[].parameters[].name` | string | Parameter name |
| `example_question_sqls[].parameters[].description` | array of strings | What the parameter represents |
| `example_question_sqls[].parameters[].type_hint` | string | Data type hint (e.g., `"STRING"`, `"INT"`) |
| `example_question_sqls[].parameters[].default_value` | object | Default value with `values` array |

### Join Specs

```json
{
  "instructions": {
    "join_specs": [
      {
        "id": "f6a7b8c9d0e1f2a3b4c5d6a7b8c9d0e1",
        "left": {
          "identifier": "catalog.schema.orders",
          "alias": "orders"
        },
        "right": {
          "identifier": "catalog.schema.customers",
          "alias": "customers"
        },
        "join_type": "LEFT JOIN",
        "sql": ["orders.customer_id = customers.id"],
        "comment": ["Link orders to customer details; use LEFT JOIN to include orders with unknown customers"],
        "instruction": ["Always use this join when relating orders to customer demographics"]
      }
    ]
  }
}
```

> **Multi-column joins:** Use separate join specs for each condition — compound `AND` expressions are not supported in the `sql` field. Add `comment` and `instruction` fields to both specs indicating they should always be used together.

| Field | Type | Description |
|-------|------|-------------|
| `join_specs` | array | Explicit join definitions for multi-table queries |
| `join_specs[].id` | string | 32-char lowercase hex identifier |
| `join_specs[].left.identifier` | string | Left table fully qualified name |
| `join_specs[].left.alias` | string | Alias for the left table in the join |
| `join_specs[].right.identifier` | string | Right table fully qualified name |
| `join_specs[].right.alias` | string | Alias for the right table in the join |
| `join_specs[].join_type` | string | Join type (INNER JOIN, LEFT JOIN, etc.) |
| `join_specs[].sql` | array of strings | Join condition expression segments. Each element must be a single equality expression (e.g., `"t1.col = t2.col"`). Compound conditions with AND/OR are not supported — use separate join specs for multi-column joins. |
| `join_specs[].comment` | array of strings | Business context for the relationship |
| `join_specs[].instruction` | array of strings | Guidance on when/how to use this join |

### SQL Functions

```json
{
  "instructions": {
    "sql_functions": [
      {
        "id": "a7b8c9d0e1f2a3b4c5d6a7b8c9d0e1f2",
        "identifier": "catalog.schema.calculate_margin",
        "description": "Calculates profit margin percentage from revenue and cost"
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sql_functions` | array | Unity Catalog functions available to Genie |
| `sql_functions[].id` | string | 32-char lowercase hex identifier |
| `sql_functions[].identifier` | string | Fully qualified function name |
| `sql_functions[].description` | string | What the function does |

### SQL Snippets

```json
{
  "instructions": {
    "sql_snippets": {
      "filters": [
        {
          "id": "b8c9d0e1f2a3b4c5d6a7b8c9d0e1f2a3",
          "display_name": "Last 30 Days",
          "sql": "WHERE order_date >= DATE_ADD(CURRENT_DATE(), -30)",
          "synonyms": ["recent", "last month", "past 30 days"],
          "instruction": ["Apply this filter when the user asks about recent data"],
          "comment": ["Standard recency filter for order-based queries"]
        }
      ],
      "expressions": [
        {
          "id": "c9d0e1f2a3b4c5d6a7b8c9d0e1f2a3b4",
          "alias": "customer_segment",
          "display_name": "Customer Segment",
          "sql": "CASE WHEN lifetime_value > 10000 THEN 'Enterprise' WHEN lifetime_value > 1000 THEN 'Mid-Market' ELSE 'SMB' END",
          "synonyms": ["segment", "customer tier", "customer type"],
          "instruction": ["Use this expression when classifying customers by value tier"],
          "comment": ["Segments align with the sales team's tiering model"]
        }
      ],
      "measures": [
        {
          "id": "d0e1f2a3b4c5d6a7b8c9d0e1f2a3b4c5",
          "alias": "total_revenue",
          "display_name": "Total Revenue",
          "sql": "SUM(quantity * unit_price)",
          "synonyms": ["revenue", "sales", "total sales"],
          "instruction": ["Use this measure for any revenue aggregation"],
          "comment": ["Revenue includes all non-cancelled order line items"]
        }
      ]
    }
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sql_snippets` | object | Reusable SQL fragments organized by type |
| `sql_snippets.filters` | array | Common WHERE clause patterns |
| `sql_snippets.expressions` | array | Reusable CASE/calculation expressions |
| `sql_snippets.measures` | array | Standard aggregation definitions |
| `sql_snippets.*[].id` | string | 32-char lowercase hex identifier |
| `sql_snippets.filters[].display_name` | string | Human-readable name for the filter |
| `sql_snippets.filters[].sql` | string | The SQL fragment |
| `sql_snippets.expressions[].alias` | string | Column alias used in generated SQL |
| `sql_snippets.expressions[].display_name` | string | Human-readable name for the expression |
| `sql_snippets.expressions[].sql` | string | The SQL fragment |
| `sql_snippets.measures[].alias` | string | Column alias used in generated SQL |
| `sql_snippets.measures[].display_name` | string | Human-readable name for the measure |
| `sql_snippets.measures[].sql` | string | The SQL fragment |
| `sql_snippets.*[].synonyms` | array of strings | Terms that trigger this snippet |
| `sql_snippets.*[].instruction` | array of strings | Guidance on when to use this snippet |
| `sql_snippets.*[].comment` | array of strings | Additional context or notes |

---

## `benchmarks`

Q&A pairs for validating Genie's SQL generation accuracy.

```json
{
  "benchmarks": {
    "questions": [
      {
        "id": "e1f2a3b4c5d6a7b8c9d0e1f2a3b4c5d6",
        "question": ["What are the top 5 customers by total spend?"],
        "answer": [
          {
            "format": "SQL",
            "content": ["SELECT c.name, SUM(o.amount) AS total_spend ", "FROM catalog.schema.customers c ", "JOIN catalog.schema.orders o ON c.id = o.customer_id ", "GROUP BY 1 ORDER BY 2 DESC LIMIT 5"]
          }
        ]
      }
    ]
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `benchmarks.questions` | array | Benchmark question-answer pairs |
| `benchmarks.questions[].id` | string | 32-char lowercase hex identifier (unique across sample_questions and benchmarks) |
| `benchmarks.questions[].question` | array of strings | The test question segments (join to form full question) |
| `benchmarks.questions[].answer` | array of objects | Expected answers (find the one with `format: "SQL"` for SQL benchmarks) |
| `benchmarks.questions[].answer[].format` | string | Answer format (typically `"SQL"`) |
| `benchmarks.questions[].answer[].content` | array of strings | The expected SQL query segments (join to form full query) |

---

## Validation Rules

| Rule | Details |
|------|---------|
| **IDs** | 32-char lowercase hexadecimal, no hyphens (e.g., `a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6`) |
| **Sorting** | Collections with IDs or identifiers must be sorted alphabetically |
| **String length** | Maximum 25,000 characters per string |
| **Array length** | Maximum 10,000 items per array |
| **ID uniqueness** | Question IDs must be unique across `sample_questions` and `benchmarks.questions` |
