---
name: skill-test
description: Testing framework for evaluating Databricks skills. Use when building test cases for skills, running skill evaluations, comparing skill versions, or creating ground truth datasets with the Generate-Review-Promote (GRP) pipeline. Triggers include "test skill", "evaluate skill", "skill regression", "ground truth", "GRP pipeline", "skill quality", and "skill metrics".
command: skill-test
arguments: "[skill-name] [subcommand]"
---

# Databricks Skills Testing Framework

Offline YAML-first evaluation with human-in-the-loop review and interactive skill improvement.

## /skill-test Command

The `/skill-test` command provides an interactive CLI for testing Databricks skills with real execution on Databricks.

### Basic Usage

```
/skill-test <skill-name> [subcommand]
```

### Subcommands

| Subcommand | Description |
|------------|-------------|
| `run` | Run evaluation against ground truth (default) |
| `regression` | Compare current results against baseline |
| `init` | Initialize test scaffolding for a new skill |
| `add` | Interactive: prompt -> invoke skill -> test -> save |
| `baseline` | Save current results as regression baseline |
| `mlflow` | Run full MLflow evaluation with LLM judges |
| `scorers` | List configured scorers for a skill |
| `scorers update` | Add/remove scorers or update default guidelines |
| `sync` | Sync YAML to Unity Catalog (Phase 2) |

### Examples

```
/skill-test spark-declarative-pipelines
/skill-test spark-declarative-pipelines run
/skill-test spark-declarative-pipelines regression
/skill-test spark-declarative-pipelines baseline
/skill-test spark-declarative-pipelines mlflow
/skill-test spark-declarative-pipelines scorers
/skill-test spark-declarative-pipelines scorers update --add-guideline "Must use CLUSTER BY"
/skill-test my-new-skill init
```

## Execution Instructions

### Environment Setup

The scripts connect to Databricks MLflow via environment variables:
- `DATABRICKS_CONFIG_PROFILE` - Databricks CLI profile (default: "DEFAULT")
- `MLFLOW_TRACKING_URI` - Set to "databricks" for Databricks MLflow
- `MLFLOW_EXPERIMENT_NAME` - Experiment path (e.g., "/Users/{user}/skill-test")

Ensure dependencies are installed:
```bash
uv pip install -e ".test/"
```

### For `mlflow` subcommand

```bash
uv run python .claude/skills/skill-test/scripts/mlflow_eval.py {skill_name}
```

### For `run` subcommand

```bash
uv run python .claude/skills/skill-test/scripts/run_eval.py {skill_name}
```

### For `baseline` subcommand

```bash
uv run python .claude/skills/skill-test/scripts/baseline.py {skill_name}
```

### For `regression` subcommand

```bash
uv run python .claude/skills/skill-test/scripts/regression.py {skill_name}
```

### For `init` subcommand

```bash
uv run python .claude/skills/skill-test/scripts/init_skill.py {skill_name}
```

## Command Handler

When `/skill-test` is invoked, parse arguments and execute the appropriate command.

### Argument Parsing
- `args[0]` = skill_name (required)
- `args[1]` = subcommand (optional, default: "run")

### Subcommand Routing

| Subcommand | Action |
|------------|--------|
| `run` | Execute `run(skill_name, ctx)` and display results |
| `regression` | Execute `regression(skill_name, ctx)` and display comparison |
| `init` | Execute `init(skill_name, ctx)` to create scaffolding |
| `add` | Prompt for test input, invoke skill, run `interactive()` |
| `baseline` | Execute `baseline(skill_name, ctx)` to save as regression baseline |
| `mlflow` | Execute `mlflow_eval(skill_name, ctx)` with MLflow logging |
| `scorers` | Execute `scorers(skill_name, ctx)` to list configured scorers |
| `scorers update` | Execute `scorers_update(skill_name, ctx, ...)` to modify scorers |

### Context Setup

Always create CLIContext with MCP tools before calling any command:

```python
from skill_test.cli import CLIContext, run, regression, init, baseline, mlflow_eval, interactive

ctx = CLIContext(
    mcp_execute_command=mcp__databricks__execute_databricks_command,
    mcp_execute_sql=mcp__databricks__execute_sql,
    mcp_upload_file=mcp__databricks__upload_file,
    mcp_get_best_warehouse=mcp__databricks__get_best_warehouse,
    mcp_get_best_cluster=mcp__databricks__get_best_cluster,
)
```

## Example Workflows

### Running Evaluation (default)
```
User: /skill-test spark-declarative-pipelines run

Claude: [Creates CLIContext with MCP tools]
Claude: [Calls run("spark-declarative-pipelines", ctx)]
Claude: [Displays results table showing passed/failed tests]
```

### Adding a Test Case
```
User: /skill-test spark-declarative-pipelines add

Claude: What prompt would you like to test?
User: Create a bronze ingestion pipeline for CSV files

Claude: [Invokes spark-declarative-pipelines skill with the prompt]
Claude: [Gets response from skill invocation]
Claude: [Calls interactive("spark-declarative-pipelines", prompt, response, ctx)]
Claude: [Reports: "3/3 code blocks passed. Saved to ground_truth.yaml"]
```

### Creating Baseline
```
User: /skill-test spark-declarative-pipelines baseline

Claude: [Creates CLIContext, calls baseline("spark-declarative-pipelines", ctx)]
Claude: [Displays "Baseline saved to baselines/spark-declarative-pipelines/baseline.yaml"]
```

### Checking for Regressions
```
User: /skill-test spark-declarative-pipelines regression

Claude: [Calls regression("spark-declarative-pipelines", ctx)]
Claude: [Compares current pass_rate against baseline]
Claude: [Reports any regressions or improvements]
```

### MLflow Evaluation
```
User: /skill-test spark-declarative-pipelines mlflow

Claude: [Calls mlflow_eval("spark-declarative-pipelines", ctx)]
Claude: [Runs evaluation with LLM judges, logs to MLflow]
Claude: [Displays evaluation metrics and MLflow run link]
```

### Viewing and Updating Scorers
```
User: /skill-test spark-declarative-pipelines scorers

Claude: [Calls scorers("spark-declarative-pipelines", ctx)]
Claude: [Shows enabled scorers, LLM scorers, and default guidelines]

Scorer Configuration for spark-declarative-pipelines:

Enabled (Deterministic):
  - python_syntax
  - sql_syntax
  - pattern_adherence
  - no_hallucinated_apis

LLM Scorers:
  - Safety
  - guidelines_from_expectations

Default Guidelines:
  - Response must address the user's request completely
  - Code examples must follow documented best practices
```

```
User: /skill-test spark-declarative-pipelines scorers update --add-guideline "Must include CLUSTER BY for large tables"

Claude: [Calls scorers_update("spark-declarative-pipelines", ctx, add_guidelines=[...])]
Claude: [Updates manifest.yaml with new guideline]

Updated scorer configuration:
  Changes: Added guideline: Must include CLUSTER BY for large tables...
```

## Interactive Workflow

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

### Execution Modes

| Mode | Description |
|------|-------------|
| **databricks** (default) | Execute on Databricks serverless compute |
| **local** | Syntax validation only (fallback when Databricks unavailable) |
| **dry_run** | Parse and validate without execution |

**Serverless is the default.** The framework only uses a cluster if explicitly specified.

## Python API

### Skill Evaluation

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

### Generate-Review-Promote Pipeline

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

### Interactive CLI Functions

```python
from skill_test.cli import CLIContext, interactive, run, regression, init

# Create context with MCP tools (injected by skill handler)
ctx = CLIContext(
    mcp_execute_command=mcp__databricks__execute_databricks_command,
    mcp_execute_sql=mcp__databricks__execute_sql,
    mcp_upload_file=mcp__databricks__upload_file,
    mcp_get_best_warehouse=mcp__databricks__get_best_warehouse,
)

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
```

### Databricks Execution Functions

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

### Test Fixtures

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

## Quality Gates

| Metric | Threshold |
|--------|-----------|
| syntax_valid/mean | 100% |
| pattern_adherence/mean | 90% |
| no_hallucinated_apis/mean | 100% |
| execution_success/mean | 80% |
| routing_accuracy/mean | 90% |

## Test Case Format

```yaml
test_cases:
  - id: "sdp_bronze_001"
    fixtures:  # Optional: Define test infrastructure
      catalog: "skill_test"
      schema: "sdp_tests"
      volume: "test_data"
      files:
        - local_path: "fixtures/sample_data.json"
          volume_path: "raw/sample_data.json"
      tables:
        - name: "source_events"
          ddl: "CREATE TABLE IF NOT EXISTS ..."
      cleanup_after: true
    inputs:
      prompt: "Create a bronze ingestion pipeline"
    outputs:
      response: |
        ```sql
        CREATE OR REFRESH STREAMING TABLE...
        ```
      execution_success: true
    expectations:
      expected_facts:
        - "STREAMING TABLE"
      expected_patterns:
        - pattern: "CREATE OR REFRESH"
          min_count: 1
      guidelines:
        - "Must use modern SDP syntax"
    metadata:
      category: "happy_path"
      execution_verified:
        mode: "databricks"
        verified_date: "2026-01-26"
```

## File Locations

**Important:** All test files are stored at the **repository root** level, not relative to this skill's directory.

| File Type | Path |
|-----------|------|
| Ground truth | `{repo_root}/.test/skills/{skill-name}/ground_truth.yaml` |
| Candidates | `{repo_root}/.test/skills/{skill-name}/candidates.yaml` |
| Manifest | `{repo_root}/.test/skills/{skill-name}/manifest.yaml` |
| Routing tests | `{repo_root}/.test/skills/_routing/ground_truth.yaml` |
| Baselines | `{repo_root}/.test/baselines/{skill-name}/baseline.yaml` |

For example, to test `spark-declarative-pipelines` in this repository:
```
/Users/.../ai-dev-kit/.test/skills/spark-declarative-pipelines/ground_truth.yaml
```

**Not** relative to the skill definition:
```
/Users/.../ai-dev-kit/.claude/skills/skill-test/skills/...  # WRONG
```

## Directory Structure

```
.test/                          # At REPOSITORY ROOT (not skill directory)
├── pyproject.toml              # Package config (pip install -e ".test/")
├── README.md                   # Contributor documentation
├── SKILL.md                    # Source of truth (synced to .claude/skills/)
├── install_skill_test.sh       # Sync script
├── scripts/                    # Wrapper scripts
│   ├── mlflow_eval.py
│   ├── run_eval.py
│   ├── baseline.py
│   ├── regression.py
│   └── init_skill.py
├── src/
│   └── skill_test/             # Python package
│       ├── __init__.py
│       ├── config.py           # Configuration
│       ├── dataset.py          # YAML/UC data loading
│       ├── cli/                # CLI commands module
│       │   ├── __init__.py     # main() entry point
│       │   └── commands.py     # run, regression, init, interactive
│       ├── fixtures/           # Test fixture setup
│       │   ├── __init__.py
│       │   └── setup.py        # Catalog/schema/volume/table setup
│       ├── scorers/            # Evaluation scorers
│       ├── grp/                # Generate-Review-Promote pipeline
│       │   ├── executor.py     # Local + Databricks execution
│       │   ├── pipeline.py     # GRP workflow
│       │   └── diagnosis.py    # Failure analysis
│       └── runners/            # Evaluation runners
├── skills/                     # Per-skill test definitions
│   ├── _routing/               # Routing test cases
│   └── {skill-name}/           # Skill-specific tests
│       ├── ground_truth.yaml
│       ├── candidates.yaml
│       └── manifest.yaml
├── tests/                      # Unit tests
├── references/                 # Documentation references
└── baselines/                  # Regression baselines
```

## References

- [YAML Schemas](references/yaml-schemas.md) - Manifest and ground truth formats
- [Scorers](references/scorers.md) - Available evaluation scorers
