---
name: skill-test
description: Testing framework for evaluating Databricks skills. Use when building test cases for skills, running skill evaluations, comparing skill versions, or creating ground truth datasets with the Generate-Review-Promote (GRP) pipeline. Triggers include "test skill", "evaluate skill", "skill regression", "ground truth", "GRP pipeline", "skill quality", and "skill metrics".
command: skill-test
arguments: "[skill-name] [subcommand]"
---

# Databricks Skills Testing Framework

Offline YAML-first evaluation with human-in-the-loop review and interactive skill improvement.

## Quick References

- [Scorers](references/scorers.md) - Available scorers and quality gates
- [YAML Schemas](references/yaml-schemas.md) - Manifest and ground truth formats
- [Python API](references/python-api.md) - Programmatic usage examples
- [Workflows](references/workflows.md) - Detailed example workflows
- [Trace Evaluation](references/trace-eval.md) - Session trace analysis

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
| `add --trace` | Add test case with trace evaluation |
| `review` | Review pending candidates interactively |
| `review --batch` | Batch approve all pending candidates |
| `baseline` | Save current results as regression baseline |
| `mlflow` | Run full MLflow evaluation with LLM judges |
| `trace-eval` | Evaluate traces against skill expectations |
| `list-traces` | List available traces (MLflow or local) |
| `scorers` | List configured scorers for a skill |
| `scorers update` | Add/remove scorers or update default guidelines |
| `sync` | Sync YAML to Unity Catalog (Phase 2) |

### Quick Examples

```
/skill-test databricks-spark-declarative-pipelines run
/skill-test databricks-spark-declarative-pipelines add --trace
/skill-test databricks-spark-declarative-pipelines review --batch --filter-success
/skill-test my-new-skill init
```

See [Workflows](references/workflows.md) for detailed examples of each subcommand.

## Execution Instructions

### Environment Setup

```bash
uv pip install -e .test/
```

Environment variables for Databricks MLflow:
- `DATABRICKS_CONFIG_PROFILE` - Databricks CLI profile (default: "DEFAULT")
- `MLFLOW_TRACKING_URI` - Set to "databricks" for Databricks MLflow
- `MLFLOW_EXPERIMENT_NAME` - Experiment path (e.g., "/Users/{user}/skill-test")

### Running Scripts

All subcommands have corresponding scripts in `.test/scripts/`:

```bash
uv run python .test/scripts/{subcommand}.py {skill_name} [options]
```

| Subcommand | Script |
|------------|--------|
| `run` | `run_eval.py` |
| `regression` | `regression.py` |
| `init` | `init_skill.py` |
| `add` | `add.py` |
| `review` | `review.py` |
| `baseline` | `baseline.py` |
| `mlflow` | `mlflow_eval.py` |
| `scorers` | `scorers.py` |
| `scorers update` | `scorers_update.py` |
| `sync` | `sync.py` |
| `trace-eval` | `trace_eval.py` |
| `list-traces` | `list_traces.py` |
| `_routing mlflow` | `routing_eval.py` |

Use `--help` on any script for available options.

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
| `review` | Execute `review(skill_name, ctx)` to review pending candidates |
| `baseline` | Execute `baseline(skill_name, ctx)` to save as regression baseline |
| `mlflow` | Execute `mlflow_eval(skill_name, ctx)` with MLflow logging |
| `scorers` | Execute `scorers(skill_name, ctx)` to list configured scorers |
| `scorers update` | Execute `scorers_update(skill_name, ctx, ...)` to modify scorers |

### init Behavior

When running `/skill-test <skill-name> init`:

1. Read the skill's SKILL.md to understand its purpose
2. Create `manifest.yaml` with appropriate scorers and trace_expectations
3. Create empty `ground_truth.yaml` and `candidates.yaml` templates
4. Recommend test prompts based on documentation examples

Follow with `/skill-test <skill-name> add` using recommended prompts.

### Context Setup

Create CLIContext with MCP tools before calling any command. See [Python API](references/python-api.md#clicontext-setup) for details.

## File Locations

**Important:** All test files are stored at the **repository root** level, not relative to this skill's directory.

| File Type | Path |
|-----------|------|
| Ground truth | `{repo_root}/.test/skills/{skill-name}/ground_truth.yaml` |
| Candidates | `{repo_root}/.test/skills/{skill-name}/candidates.yaml` |
| Manifest | `{repo_root}/.test/skills/{skill-name}/manifest.yaml` |
| Routing tests | `{repo_root}/.test/skills/_routing/ground_truth.yaml` |
| Baselines | `{repo_root}/.test/baselines/{skill-name}/baseline.yaml` |

For example, to test `databricks-spark-declarative-pipelines` in this repository:
```
/Users/.../ai-dev-kit/.test/skills/databricks-spark-declarative-pipelines/ground_truth.yaml
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
│   ├── _common.py              # Shared utilities
│   ├── run_eval.py
│   ├── regression.py
│   ├── init_skill.py
│   ├── add.py
│   ├── baseline.py
│   ├── mlflow_eval.py
│   ├── routing_eval.py
│   ├── trace_eval.py           # Trace evaluation
│   ├── list_traces.py          # List available traces
│   ├── scorers.py
│   ├── scorers_update.py
│   └── sync.py
├── src/
│   └── skill_test/             # Python package
│       ├── cli/                # CLI commands module
│       ├── fixtures/           # Test fixture setup
│       ├── scorers/            # Evaluation scorers
│       ├── grp/                # Generate-Review-Promote pipeline
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

- [Scorers](references/scorers.md) - Available scorers and quality gates
- [YAML Schemas](references/yaml-schemas.md) - Manifest and ground truth formats
- [Python API](references/python-api.md) - Programmatic usage examples
- [Workflows](references/workflows.md) - Detailed example workflows
- [Trace Evaluation](references/trace-eval.md) - Session trace analysis
