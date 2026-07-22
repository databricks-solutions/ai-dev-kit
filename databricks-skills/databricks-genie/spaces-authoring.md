# Authoring a Rich Genie Space

This guide covers building a Genie Space with the full `serialized_space`
surface populated — joins, SQL snippets (filters / expressions / measures),
text instructions, example question SQL, benchmarks, and column configs — not
just the minimal create flow.

The minimal `manage_genie(action="create_or_update", ...)` call takes
`display_name`, `table_identifiers`, `description`, and `sample_questions`
and stops there. For richer spaces you push a fully-populated
`serialized_space` through `manage_genie(action="import")`. This doc walks
through building that payload end-to-end.

See [references/schema.md](references/schema.md) for the full field reference
and [references/best-practices.md](references/best-practices.md) for
authoring conventions (added in PR #473 — cross-reference once merged).

## Where the artifacts live

| Artifact | `serialized_space` path | Purpose |
|---|---|---|
| Tables | `data_sources.tables[]` | UC tables Genie can query directly |
| Metric views | `data_sources.metric_views[]` | UC metric views (semantic layer: dimensions, measures, joins in YAML) |
| Column configs | `data_sources.{tables,metric_views}[].column_configs[]` | Per-column description, synonyms, entity matching, format assistance, exclusion |
| Sample questions | `config.sample_questions[]` | Starter questions shown on the space home page |
| Text instructions | `instructions.text_instructions[]` | Markdown guidance the model reads on every query |
| Example question SQL | `instructions.example_question_sqls[]` | Certified Q&A pairs — strongest steering signal |
| Join specs | `instructions.join_specs[]` | Declared joins the model uses instead of guessing |
| SQL snippets — measures | `instructions.sql_snippets.measures[]` | Named reusable aggregates (`SUM(...)`, `COUNT(DISTINCT ...)`) |
| SQL snippets — filters | `instructions.sql_snippets.filters[]` | Named reusable WHERE clauses |
| SQL snippets — expressions | `instructions.sql_snippets.expressions[]` | Named reusable SELECT expressions (date extracts, CASE bucketing) |
| Benchmarks | `benchmarks.questions[]` | Ground-truth Q&A pairs for quality evaluation |

Dimensions and measures for a Genie Space are **not** fields in
`serialized_space` — they live in Unity Catalog **metric views** (created with
`CREATE VIEW ... WITH METRICS LANGUAGE YAML`), which Genie consumes when you
list them under `data_sources.metric_views[]`. Build the semantic layer in UC,
then reference the metric view by its fully-qualified name.

## The builder

Use `GenieSpaceBuilder` from `databricks_mcp_server.tools.genie_space_builder`
to author payloads without hand-rolling JSON. It provides path constants and
typed `add_*` / `replace_*` / `find_by_id` / `to_json` / `from_json`
helpers, handles ID generation per API spec, and preserves unknown fields on
round-trip.

```python
from databricks_mcp_server.tools.genie_space_builder import GenieSpaceBuilder

builder = GenieSpaceBuilder(
    title="Sales Analytics",
    description="Explore sales data with natural language",
    warehouse_id="abc123",
)
```

All snippets below assume a `builder` in scope.

## The seven-step authoring pipeline

The steps below mirror the pipeline used by
[`sunnysingh-db/ai-genie-space-generator`](https://github.com/sunnysingh-db/ai-genie-space-generator),
a public Databricks Solutions reference implementation. You can run each step
by hand or drive it with an LLM — the builder does not care.

### 1. Scan table metadata

Inspect schemas and sample data before you decide which slots to fill:

```python
get_table_stats_and_schema(
    catalog="my_catalog",
    schema="sales",
    table_stat_level="DEEP",
)
```

Use the output to identify temporal, categorical, and numeric columns,
cardinalities, and plausible join keys.

### 2. Build the semantic layer (dimensions + measures) via metric views

Create a UC metric view per fact table. The YAML body defines dimensions,
measures, and joins in the UC semantic-layer format. Then register the view
with the builder:

```python
execute_sql(
    sql="""
        CREATE OR REPLACE VIEW my_catalog.sales.metrics_orders
        WITH METRICS
        LANGUAGE YAML
        AS $$
        version: 0.1
        source: my_catalog.sales.orders
        dimensions:
          - name: order_date
            expr: order_date
          - name: order_status
            expr: status
        measures:
          - name: total_revenue
            expr: SUM(total_amount)
          - name: order_count
            expr: COUNT(*)
        joins:
          - name: customers
            source: my_catalog.sales.customers
            on: orders.customer_id = customers.customer_id
        $$
    """
)

builder.add_metric_view(
    "my_catalog.sales.metrics_orders",
    description="Order facts with revenue and count measures",
)
```

Raw tables still go under `data_sources.tables` — include them when users
need access to columns that are not covered by the metric view.

### 3. Declare joins

Even when metric views carry join definitions internally, adding explicit
`join_specs` at the space level gives the model reliable cross-table guidance
for ad-hoc queries:

```python
builder.add_join_spec(
    left_identifier="my_catalog.sales.orders",
    right_identifier="my_catalog.sales.customers",
    condition="`o`.`customer_id` = `c`.`customer_id`",
    left_alias="o",
    right_alias="c",
    relationship_type="MANY_TO_ONE",
    comment="Each order is placed by one customer",
)
```

Ground your join columns against the actual column names — do not assume.
`relationship_type` must be one of `ONE_TO_ONE`, `ONE_TO_MANY`,
`MANY_TO_ONE`, `MANY_TO_MANY`. The builder encodes it as a marker inside the
`sql` list (the format the API uses to round-trip the value).

### 4. Add table and column descriptions

Genie reads descriptions when reasoning about schema. Add them at the table
level and at the column level (via `column_configs`) for anything non-obvious:

```python
builder.add_table(
    "my_catalog.sales.orders",
    description=(
        "Order-level fact table. One row per order. "
        "Joined to customers via customer_id."
    ),
)
builder.add_column_config(
    "my_catalog.sales.orders",
    "status",
    description="Order lifecycle state",
    synonyms=["state", "order state"],
    enable_entity_matching=True,
)
builder.add_column_config(
    "my_catalog.sales.orders",
    "_rescued_data",
    exclude=True,
)
```

`enable_entity_matching` on low-cardinality categorical columns lets Genie
resolve "confirmed orders" to `status = 'Confirmed'` even when the user's
phrasing does not match the stored value exactly.

### 5. Write sample questions, with SQL for the important ones

Sample questions appear as clickable tiles on the space home page. Pair each
strategic question with certified SQL via `add_example_sql` — those pairs
anchor the model's generations more strongly than natural language
instructions alone:

```python
builder.add_sample_question("What were total sales last month?")
builder.add_sample_question("Which product categories grew the most this quarter?")
builder.add_sample_question("Who are our top 10 customers by revenue?")

builder.add_example_sql(
    "What were total sales last month?",
    """
    SELECT SUM(total_amount) AS total_sales
    FROM my_catalog.sales.orders
    WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
      AND order_date <  DATE_TRUNC('month', CURRENT_DATE)
    """,
)
```

Write questions in everyday business language — never reference column names,
struct paths, or underscores in the question text itself.

### 6. Add reusable SQL snippets (measures, filters, expressions)

Snippets are named SQL fragments Genie can substitute by name. They reduce
drift between queries and cut down on ad-hoc rewrites:

```python
# Measures — named aggregates (the API field is `alias`, not `name`)
builder.add_sql_measure(
    alias="total_revenue",
    sql="SUM(orders.total_amount)",
    display_name="Total Revenue",
    synonyms=["revenue", "sales"],
    comment="Top-line revenue across all orders.",
)
builder.add_sql_measure(
    alias="cancellation_rate",
    sql="COUNT(CASE WHEN orders.status='Cancelled' THEN 1 END) * 100.0 / COUNT(*)",
    display_name="Cancellation Rate",
)

# Filters — named predicates (no `name` field — uses `display_name`)
builder.add_sql_filter(
    sql="orders.status = 'Confirmed'",
    display_name="Confirmed orders only",
)

# Expressions — named SELECT-list fragments
builder.add_sql_expression(
    alias="order_year",
    sql="YEAR(orders.order_date)",
    display_name="Order year",
)
```

Keep formulas short, valid, and table-prefixed (`table_name.column_name`).
Genie degrades when snippets reference ambiguous bare columns. The builder
stores `sql` and `comment` as single-element lists — the format the Genie
API uses on the wire.

### 7. Add text instructions and benchmarks

Text instructions are free-form markdown the model reads on every query.
Keep them short, actionable, and in business language:

```python
builder.add_text_instruction(
    """
    ## Best Practices
    * Always round percentages to two decimal places in summaries.
    * When users ask about a KPI without specifying a time range,
      ask for the range before answering.
    * Use the `total_revenue` measure for any revenue question.
    """.strip()
)
```

Benchmarks are optional ground-truth Q&A pairs used by the Genie quality
evaluator. Include a handful for the questions you care most about:

```python
builder.add_benchmark(
    "What were total sales last month?",
    """
    SELECT SUM(total_amount)
    FROM my_catalog.sales.orders
    WHERE order_date >= DATE_TRUNC('month', CURRENT_DATE - INTERVAL 1 MONTH)
      AND order_date <  DATE_TRUNC('month', CURRENT_DATE)
    """,
)
```

## Push the payload

Export the envelope and pass it to `manage_genie(action="import")`:

```python
envelope = builder.to_envelope()

manage_genie(
    action="import",
    warehouse_id=envelope["warehouse_id"],
    serialized_space=envelope["serialized_space"],
    title=envelope["title"],
    description=envelope["description"],
)
```

To update an existing space, use `action="create_or_update"` with the same
`serialized_space` argument — the server will merge top-level overrides
(`display_name`, `description`, `warehouse_id`) on top of the serialized
payload.

## Round-tripping an existing space

Fetch an existing space, patch it with the builder, and push it back:

```python
exported = manage_genie(action="export", space_id="space_123")
builder = GenieSpaceBuilder.from_json(exported)

builder.add_example_sql(
    "What's the average order value by segment?",
    "SELECT segment, AVG(total_amount) FROM ... GROUP BY segment",
)
builder.add_sql_measure("avg_order_value", "AVG(orders.total_amount)")

manage_genie(
    action="import",
    **builder.to_envelope(),
)
```

The builder preserves any fields it does not model, so round-trips are safe
against schema additions on the Genie side.

## Auto-populating slots from metadata

The seven-step pipeline maps cleanly to an LLM-driven workflow: scan
metadata, then prompt a model to emit dimensions, measures, joins,
descriptions, sample questions, and snippets. See
[`sunnysingh-db/ai-genie-space-generator`](https://github.com/sunnysingh-db/ai-genie-space-generator)
for a reference implementation that pairs a metadata scanner with a
Databricks Foundation Model API pipeline and writes the output through the
same `serialized_space` contract. The builder in this skill is the authoring
layer you would plug that pipeline into.

## Related skills

- [databricks-unity-catalog](../databricks-unity-catalog/SKILL.md) — create
  the UC metric views that carry the semantic layer
- [databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md) —
  generate tables to populate a Genie Space for demos
- [databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)
  — build bronze/silver/gold tables consumed by Genie
