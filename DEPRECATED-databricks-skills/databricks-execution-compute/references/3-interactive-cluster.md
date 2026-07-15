# Interactive Cluster Execution

**Use when:** You have an existing running cluster and need to preserve state across multiple MCP tool calls, or need Scala/R support.

## When to Choose Interactive Cluster

- Multiple sequential commands where variables must persist
- Scala or R code (serverless only supports Python/SQL)
- Existing running cluster available

## Trade-offs

| Pro | Con |
|-----|-----|
| State persists via `context_id` | Cluster startup ~5 min if not running |
| Near-instant follow-up commands | Costs money while running |
| Scala/R/SQL support | Must manage cluster lifecycle |

## Critical: Never Start a Cluster Without Asking

**Starting a cluster takes 3-8 minutes and costs money.** Always check first:

```python
list_compute(resource="clusters")
```

If no cluster is running, ask the user:
> "No running cluster. Options:
> 1. Start 'my-dev-cluster' (~5 min startup, costs money)
> 2. Use serverless (instant, no setup)
> Which do you prefer?"

## Basic Usage

### First Command: Creates Context

```python
result = execute_code(
    code="import pandas as pd\ndf = pd.DataFrame({'a': [1, 2, 3]})",
    compute_type="cluster",
    cluster_id="1234-567890-abcdef"
)
# result contains context_id for reuse
```

### Follow-up Commands: Reuse Context

```python
# Variables from first command still available
execute_code(
    code="print(df.shape)",  # df exists
    context_id=result["context_id"],
    cluster_id=result["cluster_id"]
)
```

### Auto-Select Best Running Cluster

```python
best_cluster = list_compute(resource="clusters", auto_select=True)
execute_code(
    code="spark.range(100).show()",
    compute_type="cluster",
    cluster_id=best_cluster["cluster_id"]
)
```

## Language Support

```python
execute_code(code='println("Hello")', compute_type="cluster", language="scala")
execute_code(code="SELECT * FROM table LIMIT 10", compute_type="cluster", language="sql")
execute_code(code='print("Hello")', compute_type="cluster", language="r")
```

## Installing Libraries

Install pip packages directly in the execution context (pandas/numpy are there by default):

```python
# Install library
execute_code(
    code="""%pip install faker
    dbutils.library.restartPython()""", # Restart Python to pick up new packages (if needed)
    compute_type="cluster",
    cluster_id="...",
    context_id="..."
)
```

## Context Lifecycle

**Keep alive (default):** Context persists until cluster terminates.

**Destroy when done:**
```python
execute_code(
    code="print('Done!')",
    compute_type="cluster",
    destroy_context_on_completion=True
)
```

## Handling No Running Cluster

When no cluster is running, `execute_code` returns:
```json
{
  "success": false,
  "error": "No running cluster available",
  "startable_clusters": [{"cluster_id": "...", "cluster_name": "...", "state": "TERMINATED"}],
  "suggestions": ["Start a terminated cluster", "Use serverless instead"]
}
```

### Starting a Cluster (With User Approval Only)

```python
manage_cluster(action="start", cluster_id="1234-567890-abcdef")
# Poll until running (wait 20sec)
list_compute(resource="clusters", cluster_id="1234-567890-abcdef")
```

## Common Issues

| Issue | Solution |
|-------|----------|
| "No running cluster" | Ask user to start or use serverless |
| Context not found | Context expired; create new one |
| Library not found | `%pip install <library>` then if needed `dbutils.library.restartPython()` |

## When NOT to Use

Switch to **[Databricks Connect](1-databricks-connect.md)** when:
- Developing Spark code with local debugging
- Want instant iteration without cluster concerns

Switch to **[Serverless Job](2-serverless-job.md)** when:
- No cluster running and user doesn't want to wait
- One-off execution without state needs
