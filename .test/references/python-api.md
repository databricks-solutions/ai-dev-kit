# Python API Reference

Programmatic usage examples for the skill-test framework.

## CLIContext Setup

The CLIContext provides MCP tool bindings for Databricks execution.

```python
from skill_test.cli import CLIContext, run, regression, init, baseline, mlflow_eval, interactive, review

# For local execution (syntax validation only)
ctx = CLIContext(
    base_path=repo_root / ".test" / "skills"
)

# With MCP tools for Databricks execution
ctx = CLIContext(
    mcp_execute_command=mcp__databricks__execute_databricks_command,
    mcp_execute_sql=mcp__databricks__execute_sql,
    mcp_upload_file=mcp__databricks__upload_file,
    mcp_get_best_warehouse=mcp__databricks__get_best_warehouse,
    mcp_get_best_cluster=mcp__databricks__get_best_cluster,
)
```

## Skill Evaluation

### Basic Evaluation

```python
from skill_test.runners import evaluate_skill

results = evaluate_skill("spark-declarative-pipelines")
# Loads .test/skills/{skill}/ground_truth.yaml, runs scorers, reports to MLflow
```

### Routing Evaluation

```python
from skill_test.runners import evaluate_routing

results = evaluate_routing()
# Tests skill trigger detection from .test/skills/_routing/ground_truth.yaml
```

## Interactive CLI Functions

```python
from skill_test.cli import CLIContext, interactive, run, regression, init, review

# Interactive test generation
result = interactive(
    skill_name="spark-declarative-pipelines",
    prompt="Create a bronze ingestion pipeline",
    response=skill_response,
    ctx=ctx,
    auto_approve_on_success=True
)

# Run evaluation
results = run("spark-declarative-pipelines", ctx)

# Check for regressions
comparison = regression("spark-declarative-pipelines", ctx)

# Review pending candidates (interactive)
result = review("spark-declarative-pipelines", ctx)

# Batch approve candidates with execution_success=True
result = review("spark-declarative-pipelines", ctx, batch=True, filter_success=True)
```

## Generate-Review-Promote Pipeline

The GRP pipeline manages the lifecycle of test cases from generation to promotion.

```python
from skill_test.grp import generate_candidate, save_candidates, promote_approved
from skill_test.grp.reviewer import review_candidates_file
from pathlib import Path

# 1. Generate candidate from skill output
candidate = generate_candidate("spark-declarative-pipelines", prompt, response)

# 2. Save for review
save_candidates([candidate], Path(".test/skills/spark-declarative-pipelines/candidates.yaml"))

# 3. Interactive review
review_candidates_file(Path(".test/skills/spark-declarative-pipelines/candidates.yaml"))

# 4. Promote approved to ground truth
promote_approved(
    Path(".test/skills/spark-declarative-pipelines/candidates.yaml"),
    Path(".test/skills/spark-declarative-pipelines/ground_truth.yaml")
)
```

## Databricks Execution Functions

Functions for executing code on Databricks serverless compute.

```python
from skill_test.grp.executor import (
    DatabricksExecutionConfig,
    execute_python_on_databricks,
    execute_sql_on_databricks,
    execute_code_blocks_on_databricks,
)

# Configure execution (serverless by default)
config = DatabricksExecutionConfig(
    use_serverless=True,  # Default
    catalog="main",
    schema="skill_test",
    timeout=120
)

# Execute SQL on Databricks
result = execute_sql_on_databricks(
    "SELECT * FROM my_table",
    config,
    mcp_execute_sql,
    mcp_get_best_warehouse
)

# Execute all code blocks in a response
result = execute_code_blocks_on_databricks(
    response,
    config,
    mcp_execute_command,
    mcp_execute_sql,
    mcp_get_best_warehouse
)
```

## Test Fixtures

Setting up and tearing down test infrastructure.

```python
from skill_test.fixtures import TestFixtureConfig, setup_fixtures, teardown_fixtures

# Define fixtures
config = TestFixtureConfig(
    catalog="skill_test",
    schema="sdp_tests",
    volume="test_data",
    files=[
        FileMapping("fixtures/sample.json", "raw/sample.json")
    ],
    tables=[
        TableDefinition("source_events", "CREATE TABLE IF NOT EXISTS ...")
    ],
    cleanup_after=True
)

# Set up fixtures
result = setup_fixtures(config, mcp_execute_sql, mcp_upload_file, mcp_get_best_warehouse)

# Tear down when done
teardown_fixtures(config, mcp_execute_sql, mcp_get_best_warehouse)
```

## Execution Modes

| Mode | Description |
|------|-------------|
| **databricks** (default) | Execute on Databricks serverless compute |
| **local** | Syntax validation only (fallback when Databricks unavailable) |
| **dry_run** | Parse and validate without execution |

**Serverless is the default.** The framework only uses a cluster if explicitly specified.
