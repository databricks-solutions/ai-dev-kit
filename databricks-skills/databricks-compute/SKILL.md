---
name: databricks-compute
description: "Select, start, and monitor Databricks compute resources (clusters and SQL warehouses) using MCP tools. Covers the full lifecycle: list available resources, pick the best one, start stopped clusters, and poll until ready. Includes serverless vs classic guidance and troubleshooting."
---

# Databricks Compute Management

Manage clusters and SQL warehouses through MCP tools. Use this skill whenever you need compute to run code or SQL queries.

> For workspace connectivity verification, see the `databricks-config` skill.

## Decision: Cluster vs SQL Warehouse

| Need | Use | Why |
|------|-----|-----|
| Run Python/Scala/R code | Cluster | General-purpose compute for notebooks and libraries |
| Run SQL queries | SQL Warehouse | Optimized for SQL; auto-scales and auto-stops |
| Run `execute_databricks_command()` | Cluster | Requires a cluster ID |
| Run `execute_sql()` | SQL Warehouse | Requires a warehouse ID |
| Serverless preferred | SQL Warehouse | Warehouses support serverless with instant start |

## Quick Start — Get Compute and Run

For SQL queries, get the best warehouse:

```python
warehouse_id = mcp__databricks__get_best_warehouse()
# Returns: warehouse ID string (e.g. "d41ad9fd669499ed") or null
mcp__databricks__execute_sql(warehouse_id=warehouse_id, sql_query="SELECT 1")
```

For code execution, get the best cluster:

```python
result = mcp__databricks__get_best_cluster()
# Returns: {"cluster_id": "1203-135841-22k8xamq"} or {"cluster_id": null}
mcp__databricks__execute_databricks_command(cluster_id=result["cluster_id"], code="print('hello')")
```

## MCP Tools Reference

### list_clusters

Lists all clusters in the workspace. No parameters.

```
Tool: mcp__databricks__list_clusters
Args: {}
Returns: [{"cluster_id": "...", "cluster_name": "...", "state": "RUNNING|TERMINATED|PENDING|...", "creator_user_name": "...", "cluster_source": "..."}]
```

### list_warehouses

Lists all SQL warehouses in the workspace. No parameters.

```
Tool: mcp__databricks__list_warehouses
Args: {}
Returns: [{"id": "...", "name": "...", "state": "RUNNING|STOPPED|STARTING|...", "cluster_size": "Small|Medium|...", "auto_stop_mins": 60, "creator_name": "..."}]
```

### get_best_cluster

Selects the best available cluster automatically. No parameters.

Selection logic:
1. Only considers RUNNING clusters
2. Prefers clusters with "shared" in the name (case-insensitive)
3. Then prefers clusters with "demo" in the name
4. Otherwise returns the first running cluster
5. Returns `{"cluster_id": null}` if no running cluster exists

```
Tool: mcp__databricks__get_best_cluster
Args: {}
Returns: {"cluster_id": "1203-135841-22k8xamq"} or {"cluster_id": null}
```

### get_best_warehouse

Selects the best available SQL warehouse automatically. No parameters.

Selection logic:
1. Running warehouse named "Shared endpoint" or "dbdemos-shared-endpoint"
2. Any running warehouse with "shared" in name
3. Any other running warehouse
4. Stopped warehouse with "shared" in name
5. Any other stopped warehouse
6. Within each tier, prefers warehouses owned by the current user
7. Returns null if no warehouses exist

```
Tool: mcp__databricks__get_best_warehouse
Args: {}
Returns: "d41ad9fd669499ed" (warehouse ID string) or null
```

### get_cluster_status

Checks the current state of a specific cluster.

```
Tool: mcp__databricks__get_cluster_status
Args: {"cluster_id": "<cluster-id>"}  # REQUIRED
Returns: {"cluster_id": "...", "cluster_name": "...", "state": "RUNNING|PENDING|TERMINATED|...", "message": "..."}
```

### start_cluster

Starts a terminated cluster. **Always ask the user for confirmation before calling this** — starting a cluster consumes cloud resources and takes 3-8 minutes.

```
Tool: mcp__databricks__start_cluster
Args: {"cluster_id": "<cluster-id>"}  # REQUIRED
Returns (when starting): {"cluster_id": "...", "cluster_name": "...", "state": "PENDING", "previous_state": "TERMINATED", "message": "..."}
Returns (already running): {"cluster_id": "...", "cluster_name": "...", "state": "RUNNING", "message": "..."}
```

## Workflows

### Workflow 1: Run SQL (Preferred Path)

1. Call `get_best_warehouse` — if it returns an ID, use it immediately
2. If null, call `list_warehouses` to show the user what's available
3. Warehouses auto-start on query; no manual start needed

### Workflow 2: Run Code on a Cluster

1. Call `get_best_cluster`
2. If `cluster_id` is not null → use it with `execute_databricks_command`
3. If `cluster_id` is null → no running cluster:
   a. Call `list_clusters` to find terminated clusters
   b. Present the list and ask: "No running clusters. Would you like me to start '<cluster_name>'?"
   c. On approval, call `start_cluster(cluster_id=...)`
   d. Poll `get_cluster_status(cluster_id=...)` every 30-60 seconds until `state` is `RUNNING`
   e. Proceed with `execute_databricks_command`

### Workflow 3: Check Cluster Readiness

Use after calling `start_cluster` to wait for the cluster:

```
loop:
  result = get_cluster_status(cluster_id="...")
  if result.state == "RUNNING" → ready, proceed
  if result.state == "PENDING" → wait 30-60s, retry
  if result.state == "ERROR" or "TERMINATED" → report failure to user
```

## Serverless vs Classic Compute

| Aspect | Serverless | Classic Clusters |
|--------|-----------|-----------------|
| Startup time | Seconds | 3-8 minutes |
| Cost model | Per-query/per-task | Per-minute while running |
| Management | Zero (Databricks-managed) | User-managed (auto-terminate, scaling) |
| Best for | SQL queries, short jobs | Long-running workloads, custom libraries |
| MCP tools | `get_best_warehouse` | `get_best_cluster`, `start_cluster` |

**Prefer serverless SQL warehouses** when the task is SQL-based. They start instantly and stop automatically.

## Common Issues

| Issue | Solution |
|-------|----------|
| `get_best_cluster` returns null | No running clusters. Use `list_clusters` to find terminated ones, then `start_cluster` with user approval |
| `get_best_warehouse` returns null | No warehouses exist. Ask the user to create one in the workspace UI |
| `get_cluster_status` returns "does not exist" | Invalid cluster ID. Re-run `list_clusters` to get valid IDs |
| `start_cluster` returns "does not exist" | Cluster was deleted. Re-run `list_clusters` for current inventory |
| Cluster stuck in PENDING | Normal — startup takes 3-8 minutes. Keep polling. If >10 minutes, suggest the user check the workspace UI for errors |
| Warehouse in STOPPED state | Warehouses auto-start on query submission. Just run the SQL query |

---

## Verified Against Live Workspace

| Tool | Input | Result |
|------|-------|--------|
| `list_clusters` | `{}` | Returned list with fields: cluster_id, cluster_name, state, creator_user_name, cluster_source |
| `list_warehouses` | `{}` | Returned list with fields: id, name, state, cluster_size, auto_stop_mins, creator_name |
| `get_best_cluster` | `{}` | Returned `{"cluster_id": "1203-135841-22k8xamq"}` |
| `get_best_warehouse` | `{}` | Returned `"d41ad9fd669499ed"` (bare string) |
| `get_cluster_status` | `{"cluster_id": "1203-135841-22k8xamq"}` | Returned `{cluster_id, cluster_name, state: "RUNNING", message}` |
| `start_cluster` | `{"cluster_id": "<running-id>"}` | Returned `{cluster_id, cluster_name, state: "RUNNING", message}` (already running) |
| `get_cluster_status` | `{"cluster_id": "invalid-id"}` | Raised `ResourceDoesNotExist` error |
