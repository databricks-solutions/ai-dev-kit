# Workflow: Analyze with Benchmarks

Run the space's benchmark questions against Genie via the SDK, compare generated SQL to expected SQL, and produce a detailed accuracy report.

## Step 3a: Extract Benchmark Questions

From the fetched space configuration, read `serialized_space.benchmarks.questions`.

Parse the benchmark data format:
- `question` is an **array of strings** — join them to get the full question text
- `answer` is a **list of objects** — find the one with `format: "SQL"`
- `answer[].content` is an **array of strings** — join them to get the full expected SQL

If the space has no benchmarks (empty or missing `benchmarks.questions`), inform the user:
> "This Genie Space has no benchmark questions configured. Benchmarks are question-answer pairs that let you test Genie's SQL generation accuracy. Would you like to run the best practices analysis instead?"

## Step 3b: Present Benchmarks for Selection

Display the benchmark questions as a numbered list:

```
Found N benchmark questions:
  1. What are the top 5 customers by total spend?
  2. What is the monthly revenue trend?
  3. ...

Which benchmarks would you like to run? Enter numbers (e.g., "1,3,5"), a range (e.g., "1-5"), or "all".
```

Wait for the user's selection before proceeding.

## Step 3c: Run Selected Benchmarks

Read `scripts/run_benchmark.py` for the implementation, then execute each selected benchmark question **sequentially**:

- **Claude Code**: Run via bash:
  ```bash
  python scripts/run_benchmark.py <space_id> "<question_text>"
  ```
- **Databricks notebook**: Read the script to understand the implementation. For each selected question, create a new notebook code cell containing the function definition and a call to it. Replace any `sys.exit()` calls with `raise` statements. Run the cell and read its output before proceeding to the next question. Report progress in the chat after each cell completes.

After each question completes, report progress:
```
[1/5] "What are the top 5 customers by total spend?" — SQL generated
[2/5] "What is the monthly revenue trend?" — failed: <error message>
[3/5] "Show cancelled orders from last quarter" — timed out
```

**Error handling:**
- **Exit code 1 / `RuntimeError`** (script-level error: auth failure, space not found) → halt all remaining benchmarks and report the error to the user
- **`status: "FAILED"`, `"TIMEOUT"`, or `"ERROR"`** in the result → record the result and continue to the next question

## Step 3d: Analyze Each Result

For each benchmark that produced SQL (`status: "COMPLETED"` with `generated_sql` present), compare the generated SQL against the expected SQL across these dimensions:

| Dimension | What to compare |
|-----------|----------------|
| Tables referenced | Same tables used (ignoring alias differences)? |
| Join conditions | Same joins with equivalent conditions? |
| WHERE clauses | Same filters applied (accounting for equivalent expressions)? |
| Aggregations | Same aggregate functions on same columns? |
| GROUP BY | Same grouping columns? |
| ORDER BY | Same ordering columns and direction? |
| LIMIT | Same row limit? |
| Column selection | Same output columns (ignoring aliases)? |
| Expressions | Same calculations and transformations? |

Assign a verdict to each question:
- **correct**: Generated SQL is semantically equivalent to expected SQL (may differ in formatting, aliases, or expression order)
- **partial**: Right general approach but with meaningful differences (e.g., missing a filter, different aggregation)
- **incorrect**: Wrong logic (wrong tables, wrong joins, wrong calculations)
- **error**: Genie could not generate SQL (failed, timed out, or returned a text response instead)

## Step 3e: Generate Benchmark Report

Produce the report in this markdown format:

```markdown
# Benchmark Analysis: <space_title>

**Space ID:** `<space_id>`
**Date:** <YYYY-MM-DD>
**Questions tested:** X of Y total benchmarks

## Summary

| Verdict | Count |
|---------|-------|
| Correct | X |
| Partial | X |
| Incorrect | X |
| Error | X |
| **Score** | **X/Y (Z%)** |

Score counts correct as 1, partial as 0.5, incorrect and error as 0.

## Detailed Results

### 1. <question text>

**Verdict:** correct | partial | incorrect | error

**Expected SQL:**
```sql
<expected SQL>
```

**Generated SQL:**
```sql
<generated SQL or "N/A — <reason>">
```

**Analysis:**
<dimensional comparison — which aspects matched, which differed, and why it matters>

---

### 2. <next question>
...

## Patterns & Recommendations

<Identify recurring issues across the benchmark results. For example:>
- If multiple questions missed a specific join, recommend adding a join spec
- If aggregations are consistently wrong, recommend adding example SQLs
- If certain tables are never used correctly, recommend improving table/column descriptions
- Link recommendations to specific Genie Space configuration changes
```

## Step 3f: Save Report

**Claude Code (local):**
1. Create a `reports/<space_id>/` directory in the user's project root if it doesn't already exist.
2. Save the full report markdown to `reports/<space_id>/benchmark-analysis.md` in the project root.
3. Inform the user of the saved file path.

**Databricks notebook:**
Create a new notebook code cell that renders the benchmark report as cell output using `displayHTML()` or by printing the markdown string. Do not display the report only in the chat panel.
