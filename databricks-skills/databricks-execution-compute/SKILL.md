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

Run code on Databricks and manage compute resources — all through 4 consolidated MCP tools.

## MCP Tools

### execute_code

Single entry point for all code execution on Databricks.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | string | None | Code to execute. Required unless `file_path` is set |
| `file_path` | string | None | Local file to execute (.py, .scala, .sql, .r). Language auto-detected |
| `compute_type` | string | `"auto"` | `"serverless"`, `"cluster"`, or `"auto"` |
| `cluster_id` | string | auto-selected | Cluster to run on (cluster compute) |
| `context_id` | string | None | Reuse execution context for state preservation (cluster compute) |
| `language` | string | `"python"` | `"python"`, `"scala"`, `"sql"`, or `"r"` |
| `timeout` | int | varies | Max wait seconds. Defaults: serverless=1800, cluster=120, file=600 |
| `destroy_context_on_completion` | bool | `false` | Destroy context after execution (cluster compute) |
| `workspace_path` | string | None | Persist notebook at this workspace path |
| `run_name` | string | auto-generated | Human-readable run name (serverless only) |

**compute_type resolution ("auto" mode):**
- Has `cluster_id` or `context_id` → cluster
- Language is scala/r → cluster
- Otherwise → serverless

**When to use each compute_type:**

| Scenario | compute_type | Why |
|----------|-------------|-----|
| Run Python, no cluster available | `"serverless"` | No cluster needed; serverless spins up automatically |
| Run local file on a cluster | `"cluster"` + `file_path` | Auto-detects language; supports Python, Scala, SQL, R |
| Interactive iteration (preserve variables) | `"cluster"` | Keep context alive across calls via `context_id` |
| SQL queries that need result rows | Use `execute_sql` tool | Works with SQL warehouses; returns data |
| Batch/ETL Python | `"serverless"` | Dedicated resources, up to 30 min timeout |

### manage_cluster

Create, modify, start, terminate, or delete clusters.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | string | *(required)* | `"create"`, `"modify"`, `"start"`, `"terminate"`, or `"delete"` |
| `cluster_id` | string | None | Required for modify, start, terminate, delete |
| `name` | string | None | Required for create, optional for modify |
| `num_workers` | int | `1` | Fixed worker count (ignored if autoscale is set) |
| `spark_version` | string | latest LTS | DBR version key |
| `node_type_id` | string | auto-picked | Worker node type |
| `autotermination_minutes` | int | `120` | Minutes of inactivity before auto-stop |
| `data_security_mode` | string | `"SINGLE_USER"` | Security mode |
| `spark_conf` | string (JSON) | None | Spark config overrides |
| `autoscale_min_workers` | int | None | Min workers for autoscaling |
| `autoscale_max_workers` | int | None | Max workers for autoscaling |

**DESTRUCTIVE:** `"delete"` is permanent and irreversible — always confirm with user.
**COSTLY:** `"start"` consumes cloud resources (3-8 min startup) — always ask user first.

### manage_sql_warehouse

Create, modify, or delete SQL warehouses.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | string | *(required)* | `"create"`, `"modify"`, or `"delete"` |
| `warehouse_id` | string | None | Required for modify and delete |
| `name` | string | None | Required for create |
| `size` | string | `"Small"` | T-shirt size (2X-Small through 4X-Large) |
| `min_num_clusters` | int | `1` | Minimum clusters |
| `max_num_clusters` | int | `1` | Maximum clusters for scaling |
| `auto_stop_mins` | int | `120` | Auto-stop after inactivity |
| `warehouse_type` | string | `"PRO"` | PRO or CLASSIC |
| `enable_serverless` | bool | `true` | Enable serverless compute |

**DESTRUCTIVE:** `"delete"` is permanent — always confirm with user.

For listing warehouses, use the `list_warehouses` tool (SQL tools).

### list_compute

List and inspect compute resources.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `resource` | string | `"clusters"` | `"clusters"`, `"node_types"`, or `"spark_versions"` |
| `cluster_id` | string | None | Get status for a specific cluster (poll after starting) |
| `auto_select` | bool | `false` | Return the best running cluster (prefers "shared" > "demo") |

## Ephemeral vs Persistent Mode

All execution supports two modes:

**Ephemeral (default):** Code is executed and no artifact is saved. Good for testing, exploration.

**Persistent:** Pass `workspace_path` to save as a notebook in Databricks workspace. Good for model training, ETL, project work. Suggest paths like:
`/Workspace/Users/{username}/{project-name}/`

## When No Cluster Is Available

If cluster execution finds no running cluster:
1. The error response includes `startable_clusters` and `suggestions`
2. Ask the user if they want to start a terminated cluster (3-8 min startup)
3. Or suggest `compute_type="serverless"` for Python (no cluster needed)
4. Or suggest `execute_sql` for SQL workloads (uses SQL warehouses)

## Limitations

| Limitation | Applies To | Details |
|-----------|------------|---------|
| Cold start ~25-50s | Serverless | Serverless compute spin-up time |
| No interactive state | Serverless | Each invocation is fresh; no variables persist |
| Python and SQL only | Serverless | No R, Scala, or Java on serverless |
| SQL SELECT not captured | Serverless | Use `execute_sql` for SELECT queries |
| Cluster must be running | Cluster | Use manage_cluster start or switch to serverless |
| print() output unreliable | Serverless | Use `dbutils.notebook.exit()` instead |

## Quick Start Examples

### Run Python on serverless

```python
execute_code(code="dbutils.notebook.exit('hello from serverless')")
```

### Run Python on serverless (persistent)

```python
execute_code(
    code=training_code,
    workspace_path="/Workspace/Users/user@company.com/ml-project/train",
    run_name="model-training-v1"
)
```

### Run a local file on a cluster

```python
execute_code(file_path="/local/path/to/etl.py", compute_type="cluster")
```

### Interactive iteration on a cluster

```python
# First call — creates context
result = execute_code(code="import pandas as pd\ndf = pd.DataFrame({'a': [1,2,3]})", compute_type="cluster")
# Follow-up — reuses context
execute_code(code="print(df.shape)", context_id=result["context_id"], cluster_id=result["cluster_id"])
```

### Create a cluster

```python
manage_cluster(action="create", name="my-dev-cluster", num_workers=2)
```

### Create an autoscaling cluster

```python
manage_cluster(action="create", name="scaling-cluster", autoscale_min_workers=1, autoscale_max_workers=8)
```

### Start a terminated cluster

```python
manage_cluster(action="start", cluster_id="1234-567890-abcdef")
# Poll until running
list_compute(resource="clusters", cluster_id="1234-567890-abcdef")
```

### Create a SQL warehouse

```python
manage_sql_warehouse(action="create", name="analytics-wh", size="Medium")
```

## Related Skills

- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Production job orchestration with scheduling, retries, and multi-task DAGs
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** — SQL warehouse capabilities and AI functions
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — Direct SDK usage for workspace automation
