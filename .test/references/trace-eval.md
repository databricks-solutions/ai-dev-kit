# Trace Evaluation

Trace evaluation analyzes Claude Code session behavior (tool usage, token consumption, etc.) against expectations defined in the manifest.

## Trace Sources

The framework supports two trace sources with automatic fallback:

1. **MLflow** (preferred when configured): Traces logged via `mlflow autolog claude`
2. **Local** (fallback): Session traces at `~/.claude/projects/{hash}/*.jsonl`

```
┌─────────────────────────────────────────────────────────────┐
│                  TRACE SOURCE SELECTION                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Check: mlflow autolog claude --status                   │
│                    │                                        │
│         ┌─────────┴─────────┐                              │
│         │                   │                              │
│         ▼                   ▼                              │
│   ┌──────────┐       ┌──────────────┐                      │
│   │ ENABLED  │       │ NOT ENABLED  │                      │
│   └────┬─────┘       └──────┬───────┘                      │
│        │                    │                              │
│        ▼                    ▼                              │
│  Query MLflow          Use local trace                     │
│  experiment            ~/.claude/projects/                 │
│  for trace             {hash}/{session}.jsonl              │
│        │                    │                              │
│        └────────┬───────────┘                              │
│                 │                                          │
│                 ▼                                          │
│         Run trace scorers                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Setup for MLflow Tracing

```bash
# 1. Set Databricks authentication
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-personal-access-token"

# 2. Configure autolog in your project
mlflow autolog claude -u databricks -n "/Shared/{skill-name}-skill-test-traces"

# 3. Verify setup
mlflow autolog claude --status
```

## Commands

| Command | Description |
|---------|-------------|
| `trace-eval` | Evaluate traces (auto-detects MLflow or local) |
| `trace-eval --local` | Force local trace evaluation |
| `trace-eval --run-id <id>` | Evaluate specific MLflow run (from `mlflow.search_runs`) |
| `trace-eval --trace-id <id>` | Evaluate specific MLflow trace (from `mlflow.get_trace`) |
| `trace-eval --trace <path>` | Evaluate specific local trace file |
| `trace-eval --trace-dir <dir>` | Evaluate all traces in directory |
| `list-traces` | List available traces |
| `list-traces --local` | List only local traces |
| `add --trace` | Add test case with trace evaluation |

### Run ID vs Trace ID

- **Run ID**: Identifies an MLflow run (from `mlflow.search_runs`). The trace is stored as an artifact (e.g., `trace.jsonl`).
- **Trace ID**: Identifies a trace directly in MLflow Tracing (from `mlflow.get_trace`). Format: `tr-{hash}`.

## Trace Scorers

The framework includes 7 trace-based scorers:

| Scorer | Description |
|--------|-------------|
| `tool_count` | Check tool usage against limits |
| `token_budget` | Verify token consumption within budget |
| `required_tools` | Ensure required tools were used |
| `banned_tools` | Verify banned tools were not used |
| `file_existence` | Check expected files were created |
| `tool_sequence` | Verify tools used in expected order |
| `category_limits` | Check tool category limits (bash, mcp_databricks, etc.) |

## Manifest Configuration

Add `trace_expectations` to your `manifest.yaml`:

```yaml
scorers:
  trace_expectations:
    tool_limits:
      Bash: 20
      Read: 50
      Edit: 20
      mcp__databricks__execute_sql: 15
    token_budget:
      max_total: 200000
    required_tools:
      - Read
    banned_tools: []
    category_limits:
      bash: 25
      mcp_databricks: 20
```

## CLI Examples

```bash
# Auto-detect best trace source
uv run python .test/scripts/trace_eval.py databricks-spark-declarative-pipelines

# Force local trace
uv run python .test/scripts/trace_eval.py databricks-spark-declarative-pipelines --local

# Evaluate specific MLflow run (by run ID)
uv run python .test/scripts/trace_eval.py databricks-spark-declarative-pipelines --run-id abc123

# Evaluate specific MLflow trace (by trace ID)
uv run python .test/scripts/trace_eval.py databricks-spark-declarative-pipelines \
  --trace-id tr-d416fccdab46e2dea6bad1d0bd8aaaa8

# Evaluate specific local file
uv run python .test/scripts/trace_eval.py databricks-spark-declarative-pipelines \
  --trace ~/.claude/projects/-Users-name-project/session.jsonl

# List available traces
uv run python .test/scripts/list_traces.py databricks-spark-declarative-pipelines

# Add test case with trace evaluation
uv run python .test/scripts/add.py databricks-spark-declarative-pipelines --trace --prompt "Create pipeline"
```
