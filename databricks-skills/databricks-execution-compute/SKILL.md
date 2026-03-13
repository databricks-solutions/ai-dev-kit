---
name: databricks-execution-compute
description: >-
  Execute code on Databricks compute — serverless or classic clusters. Use this
  skill when the user mentions: "run code", "execute", "run on databricks",
  "serverless", "no cluster", "run python", "run scala", "run sql", "run R",
  "run file", "push and run", "notebook run", "batch script", "model training",
  "run script on cluster". Also use when the user wants to run local files on
  Databricks or needs to choose between serverless and cluster compute.
---

# Databricks Execution Compute

Run code on Databricks — either on serverless compute (no cluster required) or on classic clusters (interactive, multi-language). Supports pushing local files to the Databricks workspace and executing them.

## Choosing the Right Tool

| Scenario | Tool | Why |
|----------|------|-----|
| **Run Python, no cluster available** | `run_code_on_serverless` | No cluster needed; serverless spins up automatically |
| **Run local file on a cluster** | `run_file_on_databricks` | Auto-detects language from extension; supports Python, Scala, SQL, R |
| **Interactive iteration (preserve variables)** | `execute_databricks_command` | Keeps execution context alive across calls |
| **SQL queries that need result rows** | `execute_sql` | Works with serverless SQL warehouses; returns data |
| **Batch/ETL Python, no interactivity needed** | `run_code_on_serverless` | Dedicated serverless resources, up to 30 min timeout |
| **Long-running production pipelines** | Databricks Jobs | Full scheduling, retries, monitoring |

## Ephemeral vs Persistent Mode

All execution tools support two modes:

**Ephemeral (default):** Code is executed and no artifact is saved in the workspace. Good for testing, exploration, quick checks.

**Persistent:** Pass `workspace_path` to save the code as a notebook in the Databricks workspace. The notebook stays after execution — visible in the UI, re-runnable, and versionable. Good for:
- Model training scripts
- ETL/data pipeline notebooks
- Any project work the user wants to keep

When the user is working on a project, ask where they want files saved and suggest a path like:
`/Workspace/Users/{username}/{project-name}/`

## MCP Tools

### run_code_on_serverless

Execute code on serverless compute via Jobs API. No cluster required.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | string | *(required)* | Python or SQL code to execute |
| `language` | string | `"python"` | `"python"` or `"sql"` |
| `timeout` | int | `1800` | Max wait time in seconds (30 min) |
| `run_name` | string | auto-generated | Optional human-readable run name |
| `workspace_path` | string | None | Workspace path to persist the notebook. If omitted, uses temp path and cleans up |

**Returns:** `success`, `output`, `error`, `run_id`, `run_url`, `duration_seconds`, `state`, `message`, `workspace_path` (persistent mode).

**Output capture:** Use `dbutils.notebook.exit(value)` to return structured output. `print()` output may not be reliably captured. SQL SELECT results are NOT captured — use `execute_sql()` instead.

### run_file_on_databricks

Read a local file and execute it on a Databricks cluster. Auto-detects language from file extension.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | string | *(required)* | Local path to the file (.py, .scala, .sql, .r) |
| `cluster_id` | string | auto-selected | Cluster to run on; auto-selects if omitted |
| `context_id` | string | None | Reuse an existing execution context |
| `language` | string | auto-detected | Override language detection |
| `timeout` | int | `600` | Max wait time in seconds |
| `destroy_context_on_completion` | bool | `false` | Destroy context after execution |
| `workspace_path` | string | None | Workspace path to also persist the file as a notebook |

**Returns:** `success`, `output`, `error`, `cluster_id`, `context_id`, `context_destroyed`, `message`.

### execute_databricks_command

Execute code interactively on a cluster. Best for iterative work — contexts persist variables and imports across calls.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | string | *(required)* | Code to execute |
| `cluster_id` | string | auto-selected | Cluster to run on |
| `context_id` | string | None | Reuse existing context for speed + state |
| `language` | string | `"python"` | `"python"`, `"scala"`, `"sql"`, or `"r"` |
| `timeout` | int | `120` | Max wait time in seconds |
| `destroy_context_on_completion` | bool | `false` | Destroy context after execution |

**Returns:** `success`, `output`, `error`, `cluster_id`, `context_id`, `context_destroyed`, `message`.

## Cluster Management Helpers

| Tool | Description |
|------|-------------|
| `list_clusters` | List all user-created clusters in the workspace |
| `get_best_cluster` | Auto-select the best running cluster (prefers "shared" > "demo") |
| `start_cluster` | Start a terminated cluster (**always ask user first**) |
| `get_cluster_status` | Poll cluster state after starting |

### When No Cluster Is Available

If `execute_databricks_command` or `run_file_on_databricks` finds no running cluster:
1. The error response includes `startable_clusters` and `suggestions`
2. Ask the user if they want to start a terminated cluster (3-8 min startup)
3. Or suggest `run_code_on_serverless` for Python (no cluster needed)
4. Or suggest `execute_sql` for SQL workloads (uses SQL warehouses)

## Limitations

| Limitation | Applies To | Details |
|-----------|------------|---------|
| Cold start ~25-50s | Serverless | Serverless compute spin-up time |
| No interactive state | Serverless | Each invocation is fresh; no variables persist |
| Python and SQL only | Serverless | No R, Scala, or Java on serverless |
| SQL SELECT not captured | Serverless | Use `execute_sql()` for SELECT queries |
| Cluster must be running | Classic | Use `start_cluster` or switch to serverless |
| print() output unreliable | Serverless | Use `dbutils.notebook.exit()` instead |

## Quick Start Examples

### Run Python on serverless (ephemeral)

```python
run_code_on_serverless(
    code="dbutils.notebook.exit('hello from serverless')"
)
```

### Run Python on serverless (persistent — save to project)

```python
run_code_on_serverless(
    code=training_code,
    workspace_path="/Workspace/Users/user@company.com/ml-project/train",
    run_name="model-training-v1"
)
```

### Run a local file on a cluster

```python
run_file_on_databricks(file_path="/local/path/to/etl.py")
```

### Run a local file and persist it to workspace

```python
run_file_on_databricks(
    file_path="/local/path/to/train.py",
    workspace_path="/Workspace/Users/user@company.com/ml-project/train"
)
```

### Interactive iteration on a cluster

```python
# First call — creates context
result = execute_databricks_command(code="import pandas as pd\ndf = pd.DataFrame({'a': [1,2,3]})")
# Follow-up — reuses context (faster, state preserved)
execute_databricks_command(code="print(df.shape)", context_id=result["context_id"], cluster_id=result["cluster_id"])
```

## Related Skills

- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Production job orchestration with scheduling, retries, and multi-task DAGs
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** — SQL warehouse capabilities and AI functions
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — Direct SDK usage for workspace automation
