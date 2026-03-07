# Example Workflows

This reference provides detailed workflow examples for the skill-test framework.

## Initializing a New Skill

```
User: /skill-test databricks-python-sdk init

Claude: [Reads .claude/skills/databricks-python-sdk/SKILL.md]
Claude: [Creates manifest.yaml with scorers based on skill type]
Claude: [Creates empty ground_truth.yaml and candidates.yaml]
Claude: "Created 3 files. Recommended test prompts:
  1. 'List all clusters in my workspace'
  2. 'Get job run status for job ID 123'
Run `/skill-test databricks-python-sdk add` with these prompts."
```

## Running Evaluation (default)

```
User: /skill-test databricks-spark-declarative-pipelines run

Claude: [Creates CLIContext with MCP tools]
Claude: [Calls run("databricks-spark-declarative-pipelines", ctx)]
Claude: [Displays results table showing passed/failed tests]
```

## Adding a Test Case

```
User: /skill-test databricks-spark-declarative-pipelines add

Claude: What prompt would you like to test?
User: Create a bronze ingestion pipeline for CSV files

Claude: [Invokes databricks-spark-declarative-pipelines skill with the prompt]
Claude: [Gets response from skill invocation]
Claude: [Calls interactive("databricks-spark-declarative-pipelines", prompt, response, ctx)]
Claude: [Reports: "3/3 code blocks passed. Saved to ground_truth.yaml"]
```

## Creating Baseline

```
User: /skill-test databricks-spark-declarative-pipelines baseline

Claude: [Creates CLIContext, calls baseline("databricks-spark-declarative-pipelines", ctx)]
Claude: [Displays "Baseline saved to baselines/databricks-spark-declarative-pipelines/baseline.yaml"]
```

## Checking for Regressions

```
User: /skill-test databricks-spark-declarative-pipelines regression

Claude: [Calls regression("databricks-spark-declarative-pipelines", ctx)]
Claude: [Compares current pass_rate against baseline]
Claude: [Reports any regressions or improvements]
```

## MLflow Evaluation

```
User: /skill-test databricks-spark-declarative-pipelines mlflow

Claude: [Calls mlflow_eval("databricks-spark-declarative-pipelines", ctx)]
Claude: [Runs evaluation with LLM judges, logs to MLflow]
Claude: [Displays evaluation metrics and MLflow run link]
```

## Trace Evaluation

```
User: /skill-test databricks-spark-declarative-pipelines trace-eval

Claude: [Checks if MLflow autolog is configured]
Claude: [If MLflow enabled, queries experiment for latest trace]
Claude: [If not, falls back to local ~/.claude/projects/.../*.jsonl]
Claude: [Runs 7 trace scorers against trace_expectations from manifest]
Claude: [Reports violations: tool limits, token budget, required tools, etc.]
```

```
User: /skill-test databricks-spark-declarative-pipelines trace-eval --local

Claude: [Forces use of local session trace, skipping MLflow]
Claude: [Evaluates most recent local trace]
```

```
User: /skill-test databricks-spark-declarative-pipelines add --trace

Claude: [Runs interactive test addition workflow]
Claude: [After execution, also evaluates the session trace]
Claude: [Reports both code execution results and trace metrics]
```

## Viewing and Updating Scorers

```
User: /skill-test databricks-spark-declarative-pipelines scorers

Claude: [Shows enabled scorers, LLM scorers, and default guidelines]
```

```
User: /skill-test databricks-spark-declarative-pipelines scorers update --add-guideline "Must include CLUSTER BY"

Claude: [Updates manifest.yaml with new guideline]
```

## Reviewing Candidates

```
User: /skill-test databricks-spark-declarative-pipelines review

Claude: [Opens interactive review for pending candidates]
Claude: [For each candidate, shows prompt, response, execution results, and diagnosis]
Claude: [User selects: [a]pprove, [r]eject, [s]kip, or [e]dit]
Claude: [Approved candidates are promoted to ground_truth.yaml]
```

```
User: /skill-test databricks-spark-declarative-pipelines review --batch --filter-success

Claude: [Batch approves all candidates with execution_success=True]
Claude: [Reports: "Batch approved 5 candidates, promoted 5 to ground_truth.yaml"]
```

---

## Review Workflow

When test cases fail during `/skill-test add`, they are saved to `candidates.yaml` for review. The review workflow allows you to examine failures, understand issues, and decide what to do with each candidate.

### Diagnosis Output

When a test fails, the system generates diagnosis information:

```yaml
diagnosis:
  error: "AnalysisException: Table or view not found: bronze_orders"
  code_block: "SELECT * FROM bronze_orders"
  suggested_action: "ensure_table_exists"
  relevant_sections:
    - file: "SKILL.md"
      section: "## Table Creation"
      line: 142
      excerpt: "Create streaming tables before querying..."
```

### Interactive Review Options

When reviewing interactively, you have four options for each candidate:

| Option | Key | Action |
|--------|-----|--------|
| **Approve** | `a` | Mark as approved, will be promoted to ground_truth.yaml |
| **Reject** | `r` | Discard the candidate (with required reason) |
| **Skip** | `s` | Keep as pending for later review |
| **Edit** | `e` | Modify expectations before approving |

### Candidate Lifecycle

```
[add] --> candidates.yaml (status: pending)
                |
         [review]
                |
      +----+----+----+
      |    |    |    |
   approve reject skip edit
      |    |    |    |
      v    v    |    v
 (approved) (removed) (pending) (approved+edited)
      |              |    |
      +--------------+----+
                |
         [promote]
                |
                v
        ground_truth.yaml
```

### Batch Approval

For CI/automation, use batch mode to approve candidates programmatically:

```bash
# Approve all pending candidates
uv run python .test/scripts/review.py my-skill --batch

# Only approve candidates that executed successfully
uv run python .test/scripts/review.py my-skill --batch --filter-success
```

Batch approval is useful for:
- Automated pipelines where human review isn't practical
- Bulk-approving candidates that passed execution validation
- Seeding initial ground truth from successful test runs

---

## Interactive Workflow (7-Phase)

When running `/skill-test <skill-name>`, the framework follows this workflow:

1. **Prompt Phase**: User provides a test prompt interactively
2. **Generate Phase**: Invoke the skill to generate a response
3. **Fixture Phase** (if test requires infrastructure):
   - Create catalog/schema via `mcp__databricks__execute_sql`
   - Create volume and upload test files via `mcp__databricks__upload_file`
   - Create any required source tables
4. **Execute Phase**:
   - Extract code blocks from response
   - Execute Python blocks via serverless compute (default) or specified cluster
   - Execute SQL blocks via `mcp__databricks__execute_sql` (auto-detected warehouse)
5. **Review Phase**:
   - If ALL blocks pass -> Auto-approve, save to `ground_truth.yaml`
   - If ANY block fails -> Save to `candidates.yaml`, enter GRP review
6. **Cleanup Phase** (if configured):
   - Teardown test infrastructure
7. **Report Phase**: Display execution summary
