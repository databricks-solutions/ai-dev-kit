# Skill Testing Framework

Test Databricks skills with real execution on serverless compute.

**Note:** This framework is for contributors only and is not distributed via install_skills.sh.

## Setup

```bash
uv pip install -e ".test/[dev]"
.test/install_skill_test.sh
```

Requires a Databricks workspace with serverless SQL/compute enabled.

---

## New Skill Journey

Complete workflow for testing a skill from scratch (e.g., `mlflow`).

### 1. Initialize Test Scaffolding

```
/skill-test <skill-name> init
```

Claude will:
1. Read the skill's SKILL.md documentation
2. Generate `manifest.yaml` with appropriate scorers
3. Create empty `ground_truth.yaml` and `candidates.yaml` templates
4. Recommend test prompts based on documentation

### 2. Add Test Cases

```
/skill-test <skill-name> add
```

Run this with the recommended prompts from init. Claude will:
1. Ask for your test prompt
2. Invoke the skill to generate a response
3. Execute code blocks on Databricks
4. Auto-save passing tests to `ground_truth.yaml`
5. Save failing tests to `candidates.yaml` for review

Repeat for each recommended prompt.

### 3. Review Candidates

```
/skill-test <skill-name> review
```

Review any tests that failed execution and were saved to candidates:
1. Load pending tests from `candidates.yaml`
2. Present each with prompt, response, and execution results
3. Allow you to approve, reject, skip, or edit
4. Promote approved candidates to `ground_truth.yaml`

For batch approval of successful tests:
```
/skill-test <skill-name> review --batch --filter-success
```

### 4. Configure Scorers (Optional)

```
/skill-test <skill-name> scorers
```

View current scorer configuration. To update:

```
/skill-test <skill-name> scorers update --add-guideline "Must use CLUSTER BY"
```

Or edit `.test/skills/<skill-name>/manifest.yaml` directly to:
- Add/remove scorers
- Update default guidelines
- Configure trace expectations

### 5. Run Evaluation

```
/skill-test <skill-name> run
```

Executes code blocks on Databricks or locally (depends on SKILLS, MCP, etc.) and reports pass/fail for each test in `ground_truth.yaml`.

**Note:** Requires test cases in ground_truth.yaml (from steps 2-3).

### 6. MLflow Evaluation (Optional)

```
/skill-test <skill-name> mlflow
```

Runs full evaluation with LLM judges and logs results to MLflow. Provides deeper quality assessment beyond pass/fail execution.

### 7. Save Baseline

```
/skill-test <skill-name> baseline
```

Saves current metrics to `baselines/<skill-name>/baseline.yaml`.

### 8. Check Regressions

After skill changes:
```
/skill-test <skill-name> regression
```

Compares current pass rate against the saved baseline.

---

## Trace Evaluation (In Progress)

Capture Claude Code sessions and evaluate against skill expectations.

### Enable MLflow Tracing

```bash
export DATABRICKS_CONFIG_PROFILE=aws-apps
export MLFLOW_EXPERIMENT_NAME="/Users/<your-email>/Claude Code Skill Traces"

pip install mlflow[databricks]
mlflow autolog claude -u databricks -n "$MLFLOW_EXPERIMENT_NAME" .
```

### Evaluate Traces

**Local trace file:**
```
/skill-test <skill-name> trace-eval --trace ~/.claude/projects/.../session.jsonl
```

**From MLflow run ID** (from `mlflow.search_runs`):
```
/skill-test <skill-name> trace-eval --run-id abc123
```

**From MLflow trace ID** (from `mlflow.get_trace`):
```
/skill-test <skill-name> trace-eval --trace-id tr-d416fccdab46e2dea6bad1d0bd8aaaa8
```

**List available traces:**
```
/skill-test <skill-name> list-traces --local
/skill-test <skill-name> list-traces --experiment "$MLFLOW_EXPERIMENT_NAME"
```

### Configure Expectations

In `manifest.yaml`:
```yaml
scorers:
  trace_expectations:
    tool_limits:
      Bash: 15
      mcp__databricks__execute_sql: 10
    token_budget:
      max_total: 150000
    required_tools:
      - Read
    banned_tools:
      - "DROP DATABASE"
```

---

## Command Reference

| Command | Description |
|---------|-------------|
| `run` | Execute tests against ground truth (default) |
| `init` | Generate test scaffolding from skill docs |
| `add` | Add test cases interactively |
| `review` | Review and promote candidates |
| `baseline` | Save current results as baseline |
| `regression` | Compare against baseline |
| `mlflow` | Full evaluation with LLM judges |
| `trace-eval` | Evaluate session traces |
| `list-traces` | List available traces |
| `scorers` | View/update scorer config |

---

## Files

```
.test/skills/<skill-name>/
├── manifest.yaml       # Scorers, guidelines, trace expectations
├── ground_truth.yaml   # Verified test cases
└── candidates.yaml     # Pending review

.test/baselines/<skill-name>/
└── baseline.yaml       # Regression baseline
```

---

## Test Case Format

```yaml
test_cases:
  - id: "eval_basic_001"
    inputs:
      prompt: "Create a scorer for response length"
    outputs:
      response: |
        ```python
        @scorer
        def response_length(outputs):
            return Feedback(name="length", value=len(outputs["response"]))
        ```
      execution_success: true
    expectations:
      expected_facts: ["@scorer", "Feedback"]
      guidelines: ["Must use mlflow.genai.scorers"]
```

---

## CI/CD

```bash
uv pip install -e ".test/"
uv run pytest .test/tests/
uv run python .test/scripts/regression.py <skill-name>
```
