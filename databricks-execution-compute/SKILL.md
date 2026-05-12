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

### Databricks Connect (no MCP tool, run locally) → [reference](references/1-databricks-connect.md)

```bash
python my_spark_script.py
```

### Serverless Job → [reference](references/2-serverless-job.md)

```python
execute_code(file_path="/path/to/script.py")
```

### Interactive Cluster → [reference](references/3-interactive-cluster.md)

```python
# Check for running clusters first (or use the one instructed)
list_compute(resource="clusters")
# Ask the customer which one to use

# Run code, reuse context_id for follow-up MCP call
result = execute_code(code="...", compute_type="cluster", cluster_id="...")
execute_code(code="...", context_id=result["context_id"], cluster_id=result["cluster_id"])
```

## MCP Tools

| Tool | For | Purpose |
|------|-----|---------|
| `execute_code` | Serverless, Interactive | Run code remotely |
| `list_compute` | Interactive | List clusters, check status, auto-select running cluster |
| `manage_cluster` | Interactive | Create, start, terminate, delete. **COSTLY:** `start` takes 3-8 min—ask user |
| `manage_sql_warehouse` | SQL | Create, modify, delete SQL warehouses |

## Related Skills

- **[databricks-synthetic-data-gen](../databricks-synthetic-data-gen/SKILL.md)** — Data generation using Spark + Faker
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Production job orchestration
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** — SQL warehouse and AI functions
