# Workflow: Analyze with Best Practices

Evaluate the space configuration against the best practices checklist and produce a detailed analysis report.

## Step 3a: Load Checklist

Read `references/best-practices-checklist.md` for the full evaluation criteria.

## Step 3b: Load Schema Reference (if needed)

If you need to understand specific fields in the serialized space JSON, read `references/space-schema.md`.

## Step 3c: Evaluate Each Checklist Item

For each item in the checklist, examine the fetched space configuration and determine:

- **Status**: `pass`, `fail`, `warning`, or `na`
- **Explanation**: Why this assessment was made, referencing specific data from the space
- **Fix** (for fail/warning only): A specific, actionable recommendation

Be concrete — reference actual table names, column names, instruction text, and field values from the space. Don't give generic advice.

Examples of specific fixes:
- "Add a description to column `unit_price` in table `catalog.schema.orders` — e.g., `'Unit price in USD for a single item'`"
- "Add synonyms `['revenue', 'sales amount']` to column `total_sales` in table `catalog.schema.transactions`"
- "Enable `enable_format_assistance: true` (v2) or `get_example_values: true` (v1) on column `region` in table `catalog.schema.stores` — this column appears filterable"
- "Add a join spec between `catalog.schema.orders` and `catalog.schema.customers` on `orders.customer_id = customers.id`"

## Step 3d: Generate Output

Present the analysis in this format:

#### Summary
- Total items evaluated: N
- Pass: X | Fail: Y | Warning: Z | N/A: W

#### Data Sources
| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

#### Instructions
| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

#### Benchmarks
| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

#### Config
| Item | Status | Explanation |
|------|--------|-------------|
| ... | ... | ... |

Fixes:
1. ...

#### Priority Recommendations
List the top 3-5 most impactful fixes, ordered by expected improvement to Genie accuracy.

## Step 3e: Save Report

**Claude Code (local):**
1. Create a `reports/<space_id>/` directory in the user's project root if it doesn't already exist.
2. Save the full analysis markdown (everything from Step 3d) to `reports/<space_id>/config-analysis.md` in the project root.
3. Inform the user of the saved file path.

**Databricks notebook:**
Create a new notebook code cell that renders the analysis as cell output using `displayHTML()` or by printing the markdown string. Do not display the report only in the chat panel.
