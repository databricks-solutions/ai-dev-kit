# Genie Space Best Practices Checklist

Evaluate each item against the serialized space JSON. For each item, determine:
- **pass**: Meets the criterion
- **fail**: Does not meet the criterion
- **warning**: Partially meets — improvement recommended
- **na**: Not applicable to this space's configuration

Provide a brief explanation for each assessment and, for any fail/warning, give a specific actionable fix referencing actual table names, column names, or instruction text from the space.

---

## Data Sources

### Tables

**Table Count (1–25, ideally ≤5 initially)**
- Check: `serialized_space.data_sources.tables` array length
- Why: Too many tables increases ambiguity and response latency. Start small and expand as needed.
- Fail if: 0 tables or >25 tables
- Warning if: >10 tables

**Table Descriptions**
- Check: Each table in `data_sources.tables[].description`
- Why: Genie uses table descriptions to decide which tables are relevant to a question. Missing descriptions cause incorrect table selection.
- Fail if: Any table has no description or a generic/empty description
- Good: `"description": "Daily sales transactions with line-item details, one row per product per order"`
- Bad: `"description": ""` or `"description": "sales table"`

**Focused Table Selection**
- Check: Whether tables appear relevant to the space's stated purpose (`title`, `description`)
- Why: Including unnecessary tables adds noise and confuses Genie's table selection.
- Warning if: Tables seem unrelated to the space's purpose

### Columns

**Column Descriptions**
- Check: `data_sources.tables[].column_configs[].description`
- Why: Column descriptions help Genie map user questions to the right columns. Descriptions should provide context beyond what the column name conveys.
- Fail if: Columns with non-obvious names have no description
- Good: `"description": "Total revenue in USD after discounts and before tax"`
- Bad: `"description": "amount"` (just restates the column name)

**Column Synonyms**
- Check: `data_sources.tables[].column_configs[].synonyms` array
- Why: Users use varied terminology. Synonyms map business language to column names.
- Warning if: Key business columns lack synonyms
- Good: Column `total_sales` with `"synonyms": ["revenue", "sales amount", "total revenue"]`

**Example Values Enabled**
- Check: `data_sources.tables[].column_configs[].get_example_values` (v1) or `enable_format_assistance` (v2) depending on space version
- Why: Example values help Genie understand the data distribution and generate correct filter values.
- Warning if: Filterable columns (strings, categoricals) don't have `get_example_values: true` (v1) or `enable_format_assistance: true` (v2)
- Note: v2 spaces reject `get_example_values` — use `enable_format_assistance` instead

**Value Dictionary Enabled**
- Check: `data_sources.tables[].column_configs[].build_value_dictionary` (v1) or `enable_entity_matching` (v2) depending on space version
- Why: For columns with a small set of discrete values (e.g., status, region, category), a value dictionary lets Genie match user terms to exact values.
- Warning if: Low-cardinality categorical columns don't have `build_value_dictionary: true` (v1) or `enable_entity_matching: true` (v2)
- Note: v2 spaces reject `build_value_dictionary` — use `enable_entity_matching` instead

**Irrelevant Columns Hidden**
- Check: Whether columns unrelated to the space's purpose are included
- Why: Extra columns increase ambiguity. Hide columns users won't query.
- Warning if: Columns like internal IDs, audit timestamps, or ETL metadata are exposed

### Metric Views

**Metric View Descriptions**
- Check: `data_sources.metric_views[].description` (if metric_views exist)
- Why: Metric views surface pre-computed metrics. Without descriptions, Genie can't match questions to the right metric.
- Fail if: Metric views exist but lack descriptions
- NA if: No metric views are defined

---

## Instructions

### Text Instructions

**At Least 1 Text Instruction**
- Check: `serialized_space.instructions.text_instructions` array length
- Why: Text instructions provide global context that shapes how Genie interprets questions and writes SQL.
- Fail if: No text instructions exist

**Instructions Are Focused and Minimal**
- Check: Length and content of text instructions
- Why: Overly long or verbose instructions dilute their impact. Instructions should be concise directives, not documentation. SQL examples, metrics, and join logic belong in their respective sections.
- Warning if: Instructions are excessively long (>500 words total) or contain embedded SQL

**Business Jargon Mapped**
- Check: Whether domain-specific terms are defined in instructions
- Why: If users say "churn rate" but the data uses "customer_attrition_pct", instructions should map this.
- Warning if: The space uses specialized terminology without definitions

### Example Question SQLs

**At Least 1 Example SQL**
- Check: `serialized_space.instructions.example_question_sqls` array length
- Why: Example SQLs teach Genie complex query patterns it can't infer from schema alone.
- Fail if: No example SQLs exist

**Examples Cover Complex Patterns**
- Check: Whether example SQLs include multi-table joins, window functions, CTEs, or business logic
- Why: Simple queries (single table SELECT) don't need examples — Genie handles those. Examples should demonstrate patterns Genie would struggle with.
- Warning if: All examples are simple single-table queries

**Examples Are Diverse**
- Check: Whether example SQLs cover different question types and tables
- Why: Redundant examples waste context. Each should teach a distinct pattern.
- Warning if: Multiple examples use nearly identical patterns

**Queries Are Concise**
- Check: Length and complexity of example SQL queries
- Why: Example queries should be as short as possible while remaining complete. Excessive comments or formatting waste tokens.
- Warning if: Queries contain unnecessary verbosity

**Parameters Have Descriptions**
- Check: `instructions.example_question_sqls[].parameters[].description` (if parameters exist)
- Why: Parameter descriptions help Genie understand what values to substitute.
- Fail if: Parameters exist without descriptions
- NA if: No parameters are used

**Complex Examples Have Usage Guidance**
- Check: `instructions.example_question_sqls[].usage_guidance` on complex examples
- Why: Usage guidance tells Genie when to apply a pattern — what keywords or question types should trigger it.
- Warning if: Complex multi-step examples lack usage guidance

### Join Specs

**Join Specs for Multi-Table Relationships**
- Check: `serialized_space.instructions.join_specs` array
- Why: Without explicit join specs, Genie may guess wrong join conditions, especially for self-joins or non-obvious foreign keys.
- Warning if: Multiple tables exist but no join specs are defined
- NA if: Only 1 table is configured
- Note: Multiple join specs between the same table pair is the correct pattern for multi-column joins (not a problem to flag). Each `sql` element must be a single equality expression — compound AND/OR is not supported. Recommend adding `comment` and `instruction` fields to related join specs to ensure they are used together.

**Join Specs Have Comments**
- Check: `instructions.join_specs[].comment`
- Why: Comments explain the business meaning of the relationship, helping Genie choose the right join for a given question.
- Warning if: Join specs exist without comments

### SQL Snippets

**Filter Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.filters` array
- Why: Common filters (time periods, active records, business-specific conditions) reduce errors when Genie needs to filter data.
- Warning if: No filter snippets exist and the space has date/time or status columns

**Expression Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.expressions` array
- Why: Reusable expressions for categorizations, calculations, and business logic ensure consistency across queries.
- Warning if: The space has complex business logic but no expression snippets

**Measure Snippets Defined**
- Check: `serialized_space.instructions.sql_snippets.measures` array
- Why: Measures define standard aggregations (revenue, count, average) that should be computed consistently.
- Warning if: Only 0-1 measures exist and the space has numeric columns that could be aggregated

---

## Benchmarks

**At Least 10 Diverse Q&A Pairs**
- Check: `serialized_space.benchmarks.questions` array length and diversity
- Why: Benchmarks validate that Genie produces correct SQL. Diverse coverage catches regressions across different question types.
- Fail if: Fewer than 10 benchmark questions
- Warning if: Questions cluster around a single topic or table

**Benchmark Coverage**
- Check: Whether benchmarks cover different tables, join patterns, aggregations, and filter types
- Why: Narrow benchmarks miss entire categories of user questions.
- Warning if: Benchmarks only test one type of query pattern

---

## Config

**Sample Questions Present**
- Check: `serialized_space.config.sample_questions` array
- Why: Sample questions appear in the Genie UI as starting points for users. They demonstrate what the space can answer.
- Warning if: No sample questions are defined

**Sample Questions Are Representative**
- Check: Whether sample questions cover the space's key capabilities
- Why: Sample questions should showcase the most valuable query patterns and guide users toward what the space does well.
- Warning if: Sample questions are generic or don't reflect the space's data
