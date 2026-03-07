# Scorers Reference

All scorers are MLflow-compatible using the `@scorer` decorator from `mlflow.genai.scorers`.

## Tier 1: Deterministic (fast)

Located in `src/scorers/universal.py`.

### python_syntax

AST parsing of Python code blocks in responses.

- **Input**: `outputs.response`
- **Returns**: `yes` if all Python blocks parse, `no` if syntax errors, `skip` if no Python blocks
- **Rationale**: Lists specific syntax errors with line numbers

### sql_syntax

Structural SQL validation (statement recognition, balanced parentheses).

- **Input**: `outputs.response`
- **Returns**: `yes` if all SQL blocks valid, `no` if issues found, `skip` if no SQL blocks
- **Checks**: Recognizable SQL statements (SELECT, CREATE, etc.), balanced parentheses

### pattern_adherence

Regex pattern matching against expected patterns.

- **Input**: `outputs.response`, `expectations.expected_patterns`
- **Returns**: One `Feedback` per pattern with `yes`/`no` based on match count
- **Pattern spec**: Can be string or `{pattern, min_count, max_count, description}`
  - `min_count` (default: 1): Minimum number of matches required
  - `max_count` (optional): Maximum number of matches allowed
  - When `max_count: 0`, validates pattern is absent (useful for negative checks)
- **Example**:
  ```yaml
  expected_patterns:
    - pattern: "notebook_task:"
      min_count: 1
      description: "Uses notebook task"
    - pattern: "new_cluster:"
      max_count: 0
      min_count: 0
      description: "No cluster config for serverless"
  ```

### no_hallucinated_apis

Check for deprecated/incorrect Databricks APIs.

- **Input**: `outputs.response`
- **Returns**: `yes` if clean, `no` if hallucinations found
- **Detects**:
  - `@dlt.table` (should be `@dp.table`)
  - `dlt.read` (should be `spark.read` or `dp.read`)
  - `PARTITION BY` (deprecated, use `CLUSTER BY`)
  - `mlflow.evaluate(` (should be `mlflow.genai.evaluate`)

### expected_facts_present

Check if required facts are mentioned in response.

- **Input**: `outputs.response`, `expectations.expected_facts`
- **Returns**: `yes` if all facts present (case-insensitive), `no` with missing list, `skip` if no facts defined

## Tier 2: Execution-based

### execution_success

Validates via GRP executor that generated code runs successfully.

- **Input**: `outputs.execution_success` (boolean from ground truth)
- **Usage**: Set in ground truth after manual/automated execution verification

## Tier 3: LLM Judge

### Guidelines

Uses `mlflow.genai.scorers.Guidelines` for semantic evaluation.

- **Input**: `expectations.guidelines` (list of guideline strings)
- **Returns**: LLM-judged pass/fail with reasoning
- **Example guidelines**:
  - "Must use modern SDP syntax, not legacy DLT"
  - "Should include metadata columns for lineage"

## Routing Scorers

Located in `src/scorers/routing.py`. Use skill trigger patterns extracted from SKILL.md descriptions.

### skill_routing_accuracy

Primary routing metric - correct skill detection.

- **Input**: `inputs.prompt`, `expectations.expected_skills`, `expectations.is_multi_skill`
- **Returns**: `yes`/`no` based on whether expected skills were detected
- **Handles**: Single-skill, multi-skill, and no-match scenarios

### routing_precision

Avoid false positives (detecting extra skills).

- **Input**: `inputs.prompt`, `expectations.expected_skills`
- **Returns**: Precision score (0.0-1.0) = correct / detected
- **Goal**: Minimize irrelevant skill activation

### routing_recall

Avoid false negatives (missing expected skills).

- **Input**: `inputs.prompt`, `expectations.expected_skills`
- **Returns**: Recall score (0.0-1.0) = correct / expected
- **Goal**: Ensure all relevant skills are triggered

## Quality Gates (Default Thresholds)

| Scorer | Threshold |
|--------|-----------|
| syntax_valid/mean | 100% |
| pattern_adherence/mean | 90% |
| no_hallucinated_apis/mean | 100% |
| execution_success/mean | 80% |
| routing_accuracy/mean | 90% |
