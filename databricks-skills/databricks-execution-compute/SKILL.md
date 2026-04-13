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

## Execution Mode Decision Matrix

| Aspect | [Databricks Connect](references/1-databricks-connect.md) ⭐ | [Serverless Job](references/2-serverless-job.md) | [Interactive Cluster](references/3-interactive-cluster.md) |
|--------|-------------------|----------------|---------------------|
| **Use for** | Spark code (ETL, data gen) | Heavy processing (ML) | State across tool calls, Scala/R |
| **Startup** | Instant | ~25-50s cold start | ~5min if stopped |
| **State** | Within Python process | None | Via context_id |
| **Languages** | Python (PySpark) | Python, SQL | Python, Scala, SQL, R |
| **Dependencies** | `withDependencies()` | CLI with environments spec | Install on cluster |

### Decision Flow

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

### Databricks Connect (run locally) → [reference](references/1-databricks-connect.md)

```bash
python my_spark_script.py
```

### Serverless Job → [reference](references/2-serverless-job.md)

```bash
# Create and run a job with serverless compute
databricks jobs create --json '{
  "name": "my-script-job",
  "tasks": [{
    "task_key": "main",
    "spark_python_task": {"python_file": "/Workspace/Users/me/script.py"},
    "environment_key": "default"
  }],
  "environments": [{"environment_key": "default", "spec": {"client": "4"}}]
}'

# Run the job
databricks jobs run-now --job-id JOB_ID
```

### Interactive Cluster → [reference](references/3-interactive-cluster.md)

```bash
# List running clusters
databricks clusters list --output json | jq '.[] | select(.state == "RUNNING")'

# Run a notebook or script on a cluster
databricks workspace import /Workspace/Users/me/script.py --file ./script.py
databricks jobs create --json '{
  "name": "cluster-job",
  "tasks": [{
    "task_key": "main",
    "existing_cluster_id": "CLUSTER_ID",
    "spark_python_task": {"python_file": "/Workspace/Users/me/script.py"}
  }]
}'
```

## CLI Commands

| Command | For | Purpose |
|---------|-----|---------|
| `databricks jobs create/run-now` | Serverless, Cluster | Run code remotely |
| `databricks clusters list` | Interactive | List clusters, check status |
| `databricks clusters create/start/delete` | Interactive | Manage clusters. **COSTLY:** `start` takes 3-8 min |
| `databricks sql warehouses create/list` | SQL | Manage SQL warehouses |

## Related Skills

- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** — Data generation using Spark + Faker
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Production job orchestration
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** — SQL warehouse and AI functions
