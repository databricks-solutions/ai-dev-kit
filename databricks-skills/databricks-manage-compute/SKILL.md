---
name: databricks-manage-compute
description: >-
  Create, modify, and delete Databricks compute resources (clusters and SQL
  warehouses). Use this skill when the user mentions: "create cluster", "new
  cluster", "resize cluster", "modify cluster", "delete cluster", "terminate
  cluster", "create warehouse", "new warehouse", "resize warehouse", "delete
  warehouse", "node types", "runtime versions", "DBR versions", "spin up
  compute", "provision cluster".
---

# Databricks Manage Compute

Create, modify, and delete Databricks compute resources — classic clusters and SQL warehouses. Provides opinionated defaults so simple operations just work, with full override for power users.

## Decision Matrix

| User Intent | Tool | Notes |
|-------------|------|-------|
| **Create a new cluster** | `create_cluster` | Just needs name + num_workers; defaults handle the rest |
| **Resize or reconfigure a cluster** | `modify_cluster` | Change workers, DBR, node type, spark conf |
| **Stop a cluster (save costs)** | `terminate_cluster` | Reversible — can restart with `start_cluster` |
| **Permanently remove a cluster** | `delete_cluster` | DESTRUCTIVE — always confirm with user first |
| **Choose a node type** | `list_node_types` | Browse available VM types before creating |
| **Choose a DBR version** | `list_spark_versions` | Browse runtimes; filter for "LTS" |
| **Create a SQL warehouse** | `create_sql_warehouse` | Serverless Pro by default |
| **Resize a SQL warehouse** | `modify_sql_warehouse` | Change size, scaling, auto-stop |
| **Permanently remove a warehouse** | `delete_sql_warehouse` | DESTRUCTIVE — always confirm with user first |

## MCP Tools — Clusters

### create_cluster

Create a new Databricks cluster with sensible defaults.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | *(required)* | Human-readable cluster name |
| `num_workers` | int | `1` | Fixed worker count (ignored if autoscale is set) |
| `spark_version` | string | latest LTS | DBR version key (e.g. "15.4.x-scala2.12") |
| `node_type_id` | string | auto-picked | Worker node type (e.g. "i3.xlarge") |
| `autotermination_minutes` | int | `120` | Minutes of inactivity before auto-stop |
| `data_security_mode` | string | `"SINGLE_USER"` | Security mode |
| `spark_conf` | string (JSON) | None | Spark config overrides as JSON |
| `autoscale_min_workers` | int | None | Min workers for autoscaling |
| `autoscale_max_workers` | int | None | Max workers for autoscaling |

**Returns:** `cluster_id`, `cluster_name`, `state`, `spark_version`, `node_type_id`, `message`.

### modify_cluster

Modify an existing cluster. Only specified parameters change; the rest stay as-is. Running clusters will restart.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cluster_id` | string | *(required)* | Cluster to modify |
| `name` | string | unchanged | New cluster name |
| `num_workers` | int | unchanged | New worker count |
| `spark_version` | string | unchanged | New DBR version |
| `node_type_id` | string | unchanged | New node type |
| `autotermination_minutes` | int | unchanged | New auto-termination |
| `spark_conf` | string (JSON) | unchanged | New Spark config |
| `autoscale_min_workers` | int | unchanged | Enable/modify autoscaling |
| `autoscale_max_workers` | int | unchanged | Enable/modify autoscaling |

**Returns:** `cluster_id`, `cluster_name`, `state`, `message`.

### terminate_cluster

Stop a running cluster (reversible). The cluster can be restarted later with `start_cluster`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cluster_id` | string | *(required)* | Cluster to terminate |

**Returns:** `cluster_id`, `cluster_name`, `state`, `message`.

### delete_cluster

**DESTRUCTIVE** — Permanently delete a cluster. Always confirm with the user before calling.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `cluster_id` | string | *(required)* | Cluster to permanently delete |

**Returns:** `cluster_id`, `cluster_name`, `state`, `message` (includes warning).

### list_node_types

List available VM/node types for the workspace. Use this to help users choose a `node_type_id` for `create_cluster`.

**Returns:** List of `node_type_id`, `memory_mb`, `num_cores`, `num_gpus`, `description`, `is_deprecated`.

### list_spark_versions

List available Databricks Runtime versions. Filter for "LTS" in the name for long-term support versions.

**Returns:** List of `key`, `name`.

## MCP Tools — SQL Warehouses

### create_sql_warehouse

Create a new SQL warehouse. Defaults to serverless Pro with 120-minute auto-stop.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | string | *(required)* | Warehouse name |
| `size` | string | `"Small"` | T-shirt size (2X-Small through 4X-Large) |
| `min_num_clusters` | int | `1` | Minimum clusters |
| `max_num_clusters` | int | `1` | Maximum clusters for scaling |
| `auto_stop_mins` | int | `120` | Auto-stop after inactivity |
| `warehouse_type` | string | `"PRO"` | PRO or CLASSIC |
| `enable_serverless` | bool | `true` | Enable serverless compute |

**Returns:** `warehouse_id`, `name`, `size`, `state`, `message`.

### modify_sql_warehouse

Modify an existing SQL warehouse. Only specified parameters change.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `warehouse_id` | string | *(required)* | Warehouse to modify |
| `name` | string | unchanged | New warehouse name |
| `size` | string | unchanged | New T-shirt size |
| `min_num_clusters` | int | unchanged | New min clusters |
| `max_num_clusters` | int | unchanged | New max clusters |
| `auto_stop_mins` | int | unchanged | New auto-stop timeout |

**Returns:** `warehouse_id`, `name`, `state`, `message`.

### delete_sql_warehouse

**DESTRUCTIVE** — Permanently delete a SQL warehouse. Always confirm with the user before calling.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `warehouse_id` | string | *(required)* | Warehouse to permanently delete |

**Returns:** `warehouse_id`, `name`, `state`, `message` (includes warning).

## Destructive Actions

`delete_cluster` and `delete_sql_warehouse` are permanent and irreversible. Before calling either:

1. Tell the user the action is permanent
2. Ask for explicit confirmation
3. Only proceed if the user confirms

`terminate_cluster` is safe and reversible — the cluster can be restarted.

## Quick Start Examples

### Create a simple cluster (all defaults)

```python
create_cluster(name="my-dev-cluster", num_workers=1)
```

### Create an autoscaling cluster

```python
create_cluster(
    name="my-scaling-cluster",
    autoscale_min_workers=1,
    autoscale_max_workers=8,
    autotermination_minutes=60
)
```

### Resize a cluster

```python
modify_cluster(cluster_id="1234-567890-abcdef", num_workers=4)
```

### Create a SQL warehouse

```python
create_sql_warehouse(name="analytics-warehouse", size="Medium")
```

### Stop a cluster to save costs

```python
terminate_cluster(cluster_id="1234-567890-abcdef")
```

## Related Skills

- **[databricks-execution-compute](../databricks-execution-compute/SKILL.md)** — Execute code on clusters and serverless compute
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** — SQL warehouse query capabilities
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** — Direct SDK usage for workspace automation
