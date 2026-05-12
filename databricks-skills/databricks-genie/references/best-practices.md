# Genie Space Best Practices

Best practices for creating, configuring, and maintaining high-quality Genie spaces. Covers instruction authoring, prompt matching, benchmarks, troubleshooting, and a pre-creation validation checklist.

## Instruction Priority

Instructions help Genie accurately interpret business questions and generate correct SQL. Prioritize SQL-based instructions over text — they are more precise and easier for Genie to apply consistently.

**Priority order (most to least effective):**

1. **SQL Expressions** — for common business terms (metrics, filters, dimensions)
2. **Example SQL Queries** — for complex, multi-part, or hard-to-interpret questions
3. **Text Instructions** — for general guidance that doesn't fit structured SQL definitions

A Genie space supports up to **100 instructions total**, counted as: each example SQL query = 1, each SQL function = 1, the entire text instructions block = 1.

## SQL Expressions

Use SQL expressions to define frequently used business terms as reusable definitions. These are stored in `instructions.sql_snippets` in the `serialized_space` configuration (see [schema.md](schema.md)).

**Three types:**

- **Measures** (`sql_snippets.measures`): KPIs and aggregation metrics
  ```json
  {"id": "...", "alias": "total_revenue", "sql": ["SUM(orders.quantity * orders.unit_price)"]}
  ```
- **Filters** (`sql_snippets.filters`): Common filtering conditions (boolean expression — do **not** include the `WHERE` keyword)
  ```json
  {"id": "...", "display_name": "high value", "sql": ["orders.amount > 1000"]}
  ```
- **Dimensions** (`sql_snippets.expressions`): Attributes for grouping and analysis
  ```json
  {"id": "...", "alias": "order_year", "sql": ["YEAR(orders.order_date)"]}
  ```

**Formatting rules:**
- The `sql` field is a **string array** (`string[]`). Wrap the SQL fragment in an array (e.g., `["SUM(orders.amount)"]`). The API rejects plain strings.
- **All column references must be table-qualified** (`table_name.column_name`). The Genie UI rejects bare column names with "Table name or alias is required for column '...'".
- Filters must **NOT** include the `WHERE` keyword — only the boolean condition.

**Good candidates:** metrics (gross margin, conversion rate), filters ("active customer", "high-value order"), dimensions (fiscal quarter, product category groupings).

## Example SQL Queries

Use complete example SQL queries for hard-to-interpret, multi-part, or complex questions. Good candidates include questions requiring complex joins, multi-step calculations, and domain-specific aggregations.

**Use one question per SQL entry.** Each example SQL query should map to exactly one natural language question. For multiple phrasings of the same question, create separate entries with the same SQL.

**Line-split format for `sql`:** Each SQL clause should be a **separate string element** in the array with `\n` at the end. Never concatenate clauses into one string.

```json
{
  "question": ["What are total sales by product category?"],
  "sql": [
    "SELECT\n",
    "  p.category,\n",
    "  SUM(o.quantity * o.unit_price) as total_sales\n",
    "FROM catalog.schema.orders o\n",
    "JOIN catalog.schema.products p ON o.product_id = p.product_id\n",
    "GROUP BY p.category\n",
    "ORDER BY total_sales DESC"
  ]
}
```

### Parameterized Queries

Add parameters using `:parameter_name` syntax. Parameterized queries become **trusted assets** (labeled "Trusted" in responses). Use for recurring questions where users specify different filter values. Parameter types: String (default), Date, Date and Time, Numeric. Use static queries for questions that don't vary or to teach Genie general patterns.

## Text Instructions

Reserve text instructions for context that doesn't fit SQL definitions. Keep them concise and specific.

**Good text instructions:**
- "Active customer" means a customer with at least one order in the last 90 days
- Revenue should always be calculated as quantity * unit_price * (1 - discount)
- Fiscal year starts April 1st
- All monetary values are in USD unless otherwise specified

**Avoid vague instructions.** Instead of "Ask clarification questions when asked about sales," write:
> "When users ask about sales metrics without specifying product name or sales channel, ask: 'To proceed with sales analysis, please specify your product name and sales channel.'"

Ensure consistency across all instruction types. If text instructions specify rounding decimals to two digits, example SQL queries must also round to two digits.

### Clarification Questions

Structure clarification instructions with: trigger condition ("When users ask about X..."), missing details ("...but don't include Y..."), required action ("...ask a clarification question first..."), and an example question.

### Summary Customization

Add a dedicated section at the end of text instructions with the heading **"Instructions you must follow when providing summaries"** to control how Genie generates natural language summaries alongside query results. Only text instructions affect summary generation.

## Join Specs

Define table relationships in `instructions.join_specs` when foreign keys are not defined in Unity Catalog.

**Critical format requirement:** The `sql` array must contain **two elements**:
1. The join condition using backtick-quoted alias references: `` `orders`.`customer_id` = `customers`.`customer_id` ``
2. A **relationship type annotation** — one of:
   - `"--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_ONE--"`
   - `"--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_MANY--"`
   - `"--rt=FROM_RELATIONSHIP_TYPE_ONE_TO_ONE--"`
   - `"--rt=FROM_RELATIONSHIP_TYPE_MANY_TO_MANY--"`

Without the `--rt=...--` annotation, the API rejects the request with a protobuf parsing error. See [schema.md](schema.md) for the full field reference.

**Priority for defining table relationships:**
1. Define foreign keys in Unity Catalog (most reliable)
2. Define join specs in the `serialized_space` via the API
3. Define join relationships in the Genie space UI (Configure > Knowledge store)
4. Provide example SQL queries with correct joins (effective fallback)
5. Pre-join tables into views (last resort)

## Column Configuration and Prompt Matching

"Prompt matching" is the umbrella term for two features:
- **Format assistance** — provides representative values so Genie understands data types and formatting patterns
- **Entity matching** — maps user terms to actual column values (e.g., "California" → "CA"). Requires `enable_format_assistance: true`.

### API vs UI Behavior

When tables are added via the Genie space UI, both features are auto-enabled for eligible columns. **When creating spaces via the API, prompt matching is OFF by default.** You must explicitly include `column_configs` entries with `enable_format_assistance: true` and `enable_entity_matching: true` for each column that needs it.

After creating a space via API, open it in the UI and verify prompt matching is enabled for key filter columns (Configure > Data > column > Advanced settings).

### Entity Matching Limits

- Up to 120 columns per space
- Up to 1,024 distinct values per column (max 127 characters per value)
- Tables with row filters or column masks are excluded

### When to Disable

Turn off format assistance (and entity matching) on columns that are excluded (`exclude: true`) or on high-cardinality freetext columns where entity matching adds no value.

### Hiding Columns

Set `"exclude": true` in `column_configs` to hide a column from Genie. Use for internal IDs, ETL timestamps, or columns not useful for business questions. **Never hide columns without explicit user approval** — do not infer which columns to hide based on column names.

## Benchmarks

Every new space should include benchmarks in its initial configuration. Target **10-20 benchmark questions**.

### Core Benchmarks (high expected accuracy: 80-100%)

For each example SQL query, include the original question as a smoke test plus 2-3 alternate phrasings. Ground truth SQL = the exact same SQL from the corresponding `example_question_sqls` entry (reuse verbatim).

### Stretch Benchmarks (lower expected accuracy)

New questions covering sample questions or other use cases with no corresponding example SQL. Ground truth SQL is independently written but follows the same conventions.

### Writing Good Benchmarks

- **Questions must be unambiguous.** Include the exact metric, grouping, count, and scope so the ground truth SQL is the only reasonable interpretation. Bad: "Show me the most lethal cancers." Good: "What are the top 5 cancer types ranked by average mortality rate?"
- **Ground truth SQL must be minimal.** Only include columns and clauses directly implied by the question. Extra columns cause benchmark failures.

### Interpreting Results

| Rating | Condition |
|--------|-----------|
| **Good** | Generated SQL or result set matches ground truth (including different sort order or numeric values matching to 4 significant digits) |
| **Bad** | Empty result set, error, extra columns, or different single-cell result |
| **Manual review** | Genie couldn't assess, or no SQL answer was provided |

## Troubleshooting Decision Tree

Use this decision tree when a user reports a specific problem with their Genie space.

### "Genie uses the wrong table or column"
1. Check table/column descriptions — do they match user terminology?
2. Look for overlapping column names across tables
3. Fix: Add example SQL queries showing correct usage, hide confusing columns

### "Genie misunderstands our terminology"
1. Check if the term is defined in text instructions or SQL expressions
2. Check column synonyms in the knowledge store
3. Fix: Add a SQL expression or text instruction mapping the term to the correct data concept

### "Genie filters on wrong values" (e.g., "California" vs "CA")
1. Check if entity matching and format assistance are enabled for the column (Configure > Data > column > Advanced settings)
2. Check if prompt matching data is up to date (kebab menu > Refresh prompt matching)
3. Fix: Enable entity matching (requires format assistance), refresh values if data changed

### "Genie joins tables incorrectly"
1. Check for foreign key constraints in Unity Catalog
2. Check join relationships in the knowledge store
3. Fix: Define join relationships or add example SQL queries with correct joins

### "Metric calculations are wrong"
1. Check if the metric is defined as a SQL expression
2. Check if there's an example SQL query computing it correctly
3. Check for pre-aggregated tables that might be double-counted
4. Fix: Add SQL expressions for metrics, or example SQL for complex calculations

### "Timezone/date calculations are wrong"
1. Check text instructions for timezone guidance
2. Fix: Add explicit instructions like "Time zones are in UTC. Convert using `convert_timezone('UTC', 'America/Los_Angeles', <column>)`."

### "Genie ignores my instructions"
1. Check for conflicting instructions across types
2. Check if the instruction count is high (noise drowns out signal)
3. Fix: Add example SQL (most effective), hide irrelevant columns, simplify instruction set, start a new chat for testing

### "Responses are slow or timing out"
1. Check query history for slow-running queries
2. Fix: Use trusted assets for complex logic, reduce example SQL length, start new chat

## Validation Checklist

Before creating or updating a space, verify:

- [ ] **Title** is a clear, descriptive name (not empty, not generic like "Untitled")
- [ ] **Description** is a one-sentence summary of the space's purpose
- [ ] Space has a **clearly defined purpose** for a specific topic and audience
- [ ] At least one valid Unity Catalog table is specified
- [ ] Tables are **focused** — ideally 5 or fewer, maximum 25
- [ ] Tables exist and user has SELECT permission
- [ ] **Actual column names and values have been inspected** (run `DESCRIBE TABLE` and `SELECT DISTINCT` on key columns)
- [ ] Column names and descriptions are clear and well-annotated in Unity Catalog
- [ ] Warehouse ID is valid and is a pro or serverless SQL warehouse
- [ ] Parent path exists in workspace
- [ ] Sample questions are business-friendly and cover common use cases
- [ ] **SQL expressions** are defined for key metrics, filters, and dimensions, with table-qualified column references
- [ ] **Example SQL queries** are included for complex or multi-step questions
- [ ] **All example SQL queries have been executed** and return valid results
- [ ] **Text instructions** are concise, specific, and non-conflicting
- [ ] Instructions across all types are consistent (same rounding, same date conventions)
- [ ] **`column_configs`** include `enable_format_assistance: true` and `enable_entity_matching: true` for key filter columns (prompt matching is NOT auto-enabled via API)
- [ ] **No columns are excluded** unless the user explicitly approved them
- [ ] **Benchmarks** are included with 10-20 questions and SQL ground truth
- [ ] All IDs are 32-char lowercase hex, unique, and arrays are sorted by `id` / `identifier`
- [ ] `sql` fields are string arrays (not plain strings)
- [ ] Filter snippets do not include the `WHERE` keyword
- [ ] `text_instructions.content` elements end with `\n`

