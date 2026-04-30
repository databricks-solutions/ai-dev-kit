---
name: databricks-execution-compute
description: >-
  Execute code and manage compute on Databricks. Use this skill when the user
  mentions: "run code", "execute", "run on databricks", "serverless", "no
  cluster", "run python", "run scala", "run sql", "run R", "run file", "push
  and run", "notebook run", "batch script", "model training", "run script on
  cluster", "create cluster", "new cluster", "resize cluster", "modify cluster",
  "delete cluster", "terminate cluster", "create warehouse", "new warehouse",
  "resize warehouse", "delete warehouse", "node types", "runtime versions",
  "DBR versions", "spin up compute", "provision cluster".
---

# Databricks Execution & Compute

Run code on Databricks. Three execution modes—choose based on workload.

> **Path convention:** `<SKILL_ROOT>` in examples below = the directory containing this SKILL.md. Resolve it to the absolute path in your install (e.g. `~/.claude/skills/databricks-execution-compute`). Commands like `python <SKILL_ROOT>/scripts/compute.py ...` work from any cwd.

## Execution Mode Decision Matrix

| Aspect | [Databricks Connect](references/1-databricks-connect.md) ⭐ | [Serverless Job](references/2-serverless-job.md) | [Interactive Cluster](references/3-interactive-cluster.md) |
|--------|-------------------|----------------|---------------------|
| **Use for** | Spark code (ETL, data gen) | Heavy processing (ML) | State across tool calls, Scala/R |
| **Startup** | Instant | ~25-50s cold start | ~5min if stopped |
| **State** | Within Python process | None | Via context_id |
| **Languages** | Python (PySpark) | Python, SQL | Python, Scala, SQL, R |
| **Dependencies** | `withDependencies()` | CLI with environments spec | Install on cluster |

### Decision Flow

Prefer Databricks Connect for all spark-based workload, then serverless.
```
Spark-based code? → Databricks Connect (fastest)
  └─ Python 3.12 missing? → Install it + databricks-connect
  └─ Install fails? → Ask user (don't auto-switch modes)

Heavy/long-running (ML)? → Serverless Job (independent)
Need state across calls? → Interactive Cluster (list and ask which one to use)
Scala/R? → Interactive Cluster (list and ask which one to use)
```


## How to Run Code

**Read the reference file for your chosen mode before proceeding.**

### Databricks Connect (run locally, prefer when it's pure spark code) → [reference](references/1-databricks-connect.md)

```bash
from databricks.connect import DatabricksSession
...
spark = DatabricksSession.builder.profile("my-local-profile").serverless(True).getOrCreate()


python my_spark_script.py
```

### Serverless Job → [reference](references/2-serverless-job.md)

Pure CLI flow: upload a local file as a workspace notebook, fire a one-time run with `databricks jobs submit` (create + run in one call, ephemeral — no Jobs UI entry, no retry), then poll + fetch the result. The local file must be a Databricks source notebook — top line `# Databricks notebook source` (Python) or `-- Databricks notebook source` (SQL).

**1. Upload the local file as a workspace notebook.** `TARGET_PATH` is positional; `--file` is the local path.

`databricks workspace import /Workspace/Users/<user>/.ai_dev_kit/train --file /local/path/to/train.py --format SOURCE --language PYTHON --overwrite`

**2. Submit the run.** Use `--no-wait` to get `{"run_id": N}` back immediately; drop it to block until terminated. **`"client": "4"` is required** for `dependencies` to install (`"1"` silently ignores them).

`databricks jobs submit --no-wait --json @submit.json`

```json
{
  "run_name": "train-run",
  "tasks": [{
    "task_key": "main",
    "notebook_task": {"notebook_path": "/Workspace/Users/<user>/.ai_dev_kit/train"},
    "environment_key": "ml_env"
  }],
  "environments": [{
    "environment_key": "ml_env",
    "spec": {"client": "4", "dependencies": ["scikit-learn==1.5.2", "mlflow==2.22.0"]}
  }]
}
```

**3. Check state / wait for completion.** Life-cycle: `PENDING` → `RUNNING` → `TERMINATED` (or `SKIPPED` / `INTERNAL_ERROR`). Only read `.state.result_state` (`SUCCESS` / `FAILED` / `CANCELED`) once life-cycle is `TERMINATED`.

`databricks jobs get-run <RUN_ID> | jq '{state: .state.life_cycle_state, result: .state.result_state, duration_ms: .execution_duration, url: .run_page_url, task_run_id: .tasks[0].run_id}'`

**4. Fetch the output / error.** **Gotcha:** `get-run-output` takes the **task** run_id (`.tasks[0].run_id`), NOT the parent `run_id` from submit. `notebook_output.result` is the string passed to `dbutils.notebook.exit()`.

`databricks jobs get-run-output <TASK_RUN_ID> | jq '{result: .notebook_output.result, error, error_trace}'`

Always use `dbutils.notebook.exit(<string>)` in the notebook — `print()` is not captured by `get-run-output`. For JSON results: `dbutils.notebook.exit(json.dumps({...}))` then parse `.notebook_output.result` client-side.

**Convenience wrapper.** `scripts/compute.py execute-code` does upload + submit + wait + cleanup in one command and returns a single tidy JSON:

`python <SKILL_ROOT>/scripts/compute.py execute-code --file /local/path/to/train.py --compute-type serverless --timeout 1500 --environments '[{"environment_key":"ml_env","spec":{"client":"4","dependencies":["scikit-learn==1.5.2","mlflow==2.22.0"]}}]' | jq '{success, state, output, error, run_id, run_page_url, execution_duration_ms}'`

### Interactive Cluster → [reference](references/3-interactive-cluster.md)

**Avoid by default — prefer Serverless Job.** Only use an interactive cluster when:
- you have an existing classic cluster already running and available, or
- you need live, stateful execution across multiple calls (debugging via an execution context), or
- the user explicitly asks for it.

Interactive clusters are **slow to start (3-8 min)** and cost money while running. Don't start one implicitly.

## CLI Commands

| Command | Purpose |
|---------|---------|
| `python <SKILL_ROOT>/scripts/compute.py execute-code` | Run code on serverless or an existing cluster |
| `python <SKILL_ROOT>/scripts/compute.py list-compute` | List clusters, node types, Spark versions |
| `python <SKILL_ROOT>/scripts/compute.py manage-cluster` | Create/start/terminate/delete clusters (see [3-interactive-cluster.md](references/3-interactive-cluster.md)) |
| `databricks warehouses create/list` | Manage SQL warehouses |

### SQL Warehouses

All `ID`-taking commands use positional arg (no `--id` flag). Use `databricks warehouses list` to find an ID.

```bash
# Create a serverless SQL warehouse. min_num_clusters + max_num_clusters are REQUIRED
# (the server rejects the default 0). Keep the aidevkit_project tag for resource tracking.
databricks warehouses create --json '{
  "name": "my-warehouse",
  "cluster_size": "Small",
  "enable_serverless_compute": true,
  "auto_stop_mins": 10,
  "min_num_clusters": 1,
  "max_num_clusters": 1,
  "tags": {"custom_tags": [{"key": "aidevkit_project", "value": "ai-dev-kit"}]}
}'

# List / find — trim to id, name, state with jq
databricks warehouses list -o json | jq '.[] | {id, name, state, size: .cluster_size}'

# Find by name
databricks warehouses list -o json | jq '.[] | select(.name == "my-warehouse")'

# Get one warehouse's full config
databricks warehouses get <WAREHOUSE_ID>

# Start / stop (both are LROs; add --no-wait to return immediately)
databricks warehouses start <WAREHOUSE_ID>
databricks warehouses stop  <WAREHOUSE_ID>

# Resize / reconfigure — pass the FULL desired config (omitted fields revert to defaults,
# so always re-state min_num_clusters/max_num_clusters). Use --no-wait if the warehouse
# is STOPPED, otherwise edit blocks trying to reach RUNNING and errors out (the mutation
# itself still applies). When the warehouse is already RUNNING, --no-wait is optional.
databricks warehouses edit <WAREHOUSE_ID> --no-wait --json '{
  "name": "my-warehouse",
  "cluster_size": "Medium",
  "enable_serverless_compute": true,
  "auto_stop_mins": 15,
  "min_num_clusters": 1,
  "max_num_clusters": 1
}'

# Delete (irreversible)
databricks warehouses delete <WAREHOUSE_ID>
```

**Sizes:** `2X-Small`, `X-Small`, `Small`, `Medium`, `Large`, `X-Large`, `2X-Large`, `3X-Large`, `4X-Large`. **Types:** set `"warehouse_type": "PRO"` (default) or `"CLASSIC"` in the JSON body.

## Related Skills

- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** — Data generation using Spark + Faker
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Production job orchestration
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** — SQL warehouse and AI functions
