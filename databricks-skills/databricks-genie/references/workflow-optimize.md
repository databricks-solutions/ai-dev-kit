# Workflow: Optimize Genie Space

Create a new optimized Genie Space by applying findings from the best practices analysis (Option A) and benchmark analysis (Option B). The original space is preserved — a new copy is created with improvements applied.

## Table of Contents

- [Step 3a: Verify Prerequisites](#step-3a-verify-prerequisites)
- [Step 3b: Load Analysis Results](#step-3b-load-analysis-results)
- [Step 3c: Generate Optimization Plan](#step-3c-generate-optimization-plan)
- [Step 3d: Present Changes for User Review](#step-3d-present-changes-for-user-review)
- [Step 3e: Apply Changes to Config](#step-3e-apply-changes-to-config)
- [Step 3f: Create New Genie Space](#step-3f-create-new-genie-space)
- [Step 3g: Save Report & Present Results](#step-3g-save-report-present-results)

## Step 3a: Verify Prerequisites

Check that both analysis reports exist:

- **Claude Code**: Verify these files exist in the project root:
  - `reports/<space_id>/config-analysis.md`
  - `reports/<space_id>/benchmark-analysis.md`
- **Databricks notebook**: Verify that Option A and Option B analyses are available in previous notebook cell outputs or kernel memory variables.

If either is missing, inform the user which workflow(s) need to run first and offer to start them.

## Step 3b: Load Analysis Results

- **Claude Code**: Read all three files:
  - `reports/<space_id>/config-analysis.md` (best practices findings)
  - `reports/<space_id>/benchmark-analysis.md` (benchmark findings)
  - `reports/<space_id>/space-config.json` (original space configuration)
- **Databricks notebook**: Read previous cell outputs containing the analyses. Use the `space_config` variable from kernel memory for the original configuration.

Also load `references/space-schema.md` as reference for valid field structures and validation rules.

## Step 3c: Generate Optimization Plan

Parse the analysis reports and map findings to specific config changes. Group changes by category:

| Finding Source | Change Category | Config Path |
|---|---|---|
| Best practices: fail/warning on table descriptions | Data source | `data_sources.tables[].description` |
| Best practices: fail/warning on column descriptions | Data source | `data_sources.tables[].column_configs[].description` |
| Best practices: warning on missing synonyms | Data source | `data_sources.tables[].column_configs[].synonyms` |
| Best practices: warning on example values | Data source | `data_sources.tables[].column_configs[].get_example_values` (v1) or `enable_format_assistance` (v2) |
| Best practices: fail on text instructions | Instruction | `instructions.text_instructions` |
| Best practices: fail on example SQLs | Instruction | `instructions.example_question_sqls` |
| Best practices: warning on join specs | Instruction | `instructions.join_specs` |
| Best practices: warning on SQL snippets | Instruction | `instructions.sql_snippets.*` |
| Benchmark: incorrect/partial verdicts | Multiple | Add example SQLs for failing patterns, improve instructions |

**Join spec constraints:** Each `sql` array element must contain a single equality expression.
For multi-column joins, create separate join specs with `comment` and `instruction` fields
that reference each other (e.g., "Always use with the companion YEAR join spec").
Do not combine conditions with AND/OR.

For each change:
1. Reference the specific finding that motivates it (e.g., "config-analysis: fail on column descriptions for `catalog.schema.orders`")
2. Generate the actual new values — not just "add a description" but the actual description text, SQL, synonyms, etc.
3. Use the space's existing data, table names, column names, and business context to produce accurate values

## Step 3d: Present Changes for User Review

Present a structured summary of all proposed changes:

```
## Proposed Optimization: <space_title>

**Changes summary:** X data source changes, Y instruction changes, Z benchmark-driven changes

### Data Source Changes
1. [table: catalog.schema.orders] Add description: "..." (was: missing)
2. [column: orders.unit_price] Add description: "..." (was: missing)
3. [column: orders.region] Add synonyms: ["area", "territory"] (was: none)
4. [column: orders.region] Enable get_example_values (v1) / enable_format_assistance (v2) (was: false)
...

### Instruction Changes
1. Add text instruction: "..."
2. Add example SQL: "What is the monthly revenue trend?" → SELECT ...
3. Add join spec: orders ↔ customers on customer_id (LEFT JOIN)
4. Add filter snippet: "Last 30 Days" → WHERE order_date >= DATE_ADD(CURRENT_DATE(), -30)
...

### Benchmark-Driven Changes
1. Add example SQL for pattern that caused incorrect verdict on Q3: ...
2. Improve column description for `total_amount` (caused partial verdict on Q7): ...
...
```

Wait for user approval. The user may request modifications before proceeding. Apply any requested changes to the plan before continuing.

## Step 3e: Apply Changes to Config

1. Deep copy the original `serialized_space` dict from the space config
2. Apply each approved change to produce the updated config:
   - For new entries (text instructions, example SQLs, join specs, snippets, benchmarks), generate a new 32-char lowercase hex ID for each
   - For modifications (descriptions, synonyms, example values), update the existing entries in place
3. Validate the updated config against the rules in `references/space-schema.md`:
   - All IDs are 32-char lowercase hex
   - Collections with IDs or identifiers are sorted alphabetically
   - Question IDs are unique across `sample_questions` and `benchmarks.questions`
   - Strings do not exceed 25,000 characters
   - Arrays do not exceed 10,000 items

## Step 3f: Create New Genie Space

Read `scripts/create_optimized_space.py` for the implementation, then execute it:

- **Claude Code**:
  1. Save the updated config dict as JSON to `reports/<space_id>/optimized-space-config.json`
  2. Run the creation script via bash:
  ```bash
  python scripts/create_optimized_space.py <original_space_id> reports/<space_id>/optimized-space-config.json
  ```
- **Databricks notebook**: Read the script to understand the implementation. Create a new notebook code cell containing the function definition and a call to it. Replace any `sys.exit()` calls with `raise` statements. The cell should:
  1. Take the updated config dict (from the previous cell)
  2. Call `create_optimized_space(original_space_id, updated_config)` to create the new space
  3. Print the result JSON

  Run the cell and read its output.

If the script fails:
- **`ImportError`**: Prompt user to `pip install "databricks-sdk>=0.85"` (Claude Code only — SDK is pre-installed in Databricks)
- **Auth failure**: Prompt user to run `databricks configure` or check environment variables (Claude Code only — Databricks notebooks auto-authenticate)
- **Permission denied (`403` / `PERMISSION_DENIED`)**: User may not have permission to create Genie Spaces
- **Not found (`404` / `NOT_FOUND`)**: Verify the original space ID

## Step 3g: Save Report & Present Results

**Claude Code (local):**
1. Save a summary report to `reports/<space_id>/optimization-report.md` in the project root.
2. Inform the user of the saved file path.

**Databricks notebook:**
Create a new notebook code cell that renders the optimization report as cell output using `displayHTML()` or by printing the markdown string. Do not display the report only in the chat panel.

The report should include:

```markdown
# Optimization Report: <space_title>

**Original Space ID:** `<original_space_id>`
**New Space ID:** `<new_space_id>`
**New Space URL:** `https://<workspace_host>/spaces/<new_space_id>`
**Date:** <YYYY-MM-DD>

## Changes Applied

### Data Source Changes (X total)
1. ...

### Instruction Changes (Y total)
1. ...

### Benchmark-Driven Changes (Z total)
1. ...

## Next Steps
- Compare the original and optimized spaces side by side
- Run benchmark analysis (Option B) on the new space to measure improvement
- Review and adjust the new space's configuration in the Genie UI
- Share the new space with your team for feedback
```
