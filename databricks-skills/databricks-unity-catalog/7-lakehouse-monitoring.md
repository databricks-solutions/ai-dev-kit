# Lakehouse Monitoring

Comprehensive reference for Lakehouse Monitoring: create quality monitors on Unity Catalog tables to track data profiles, detect drift, and monitor ML model performance.

## Overview

Lakehouse Monitoring automatically computes statistical profiles and drift metrics for tables over time. When you create a monitor, Databricks generates two output Delta tables (profile metrics + drift metrics) and an optional dashboard.

| Component | Description |
|-----------|-------------|
| **Monitor** | Configuration attached to a UC table |
| **Profile Metrics Table** | Summary statistics computed per column |
| **Drift Metrics Table** | Statistical drift compared to baseline or previous time window |
| **Dashboard** | Auto-generated visualization of metrics |

### Requirements

- Unity Catalog enabled workspace
- Databricks SQL access
- Privileges: `USE CATALOG`, `USE SCHEMA`, `SELECT`, and `MANAGE` on the table
- Only Delta tables supported (managed, external, views, materialized views, streaming tables)

---

## Profile Types

| Type | Use Case | Key Params | Limitations |
|------|----------|------------|-------------|
| **Snapshot** | General-purpose tables without time column | None required | Max 4TB table size |
| **TimeSeries** | Tables with a timestamp column | `timestamp_col`, `granularities` | Last 30 days only |
| **InferenceLog** | ML model monitoring | `timestamp_col`, `granularities`, `model_id_col`, `problem_type`, `prediction_col` | Last 30 days only |

### Granularities (for TimeSeries and InferenceLog)

Supported values: `"5 minutes"`, `"30 minutes"`, `"1 hour"`, `"1 day"`, `"<n> week(s)"`, `"1 month"`, `"1 year"`

---

## MCP Tools

Use the `manage_uc_monitors` tool for all monitor operations:

| Action | Description |
|--------|-------------|
| `create` | Create a quality monitor on a table |
| `get` | Get monitor details and status |
| `run_refresh` | Trigger a metric refresh |
| `list_refreshes` | List refresh history |
| `delete` | Delete the monitor (assets are not deleted) |

### Create a Monitor

> **Note:** The MCP tool currently only creates **snapshot** monitors. For TimeSeries or InferenceLog monitors, use the Python SDK directly (see below).

```python
manage_uc_monitors(
    action="create",
    table_name="catalog.schema.my_table",
    output_schema_name="catalog.schema",
)
```

### Get Monitor Status

```python
manage_uc_monitors(
    action="get",
    table_name="catalog.schema.my_table",
)
```

### Trigger a Refresh

```python
manage_uc_monitors(
    action="run_refresh",
    table_name="catalog.schema.my_table",
)
```

### Delete a Monitor

```python
manage_uc_monitors(
    action="delete",
    table_name="catalog.schema.my_table",
)
```

---

## Python SDK Examples

**Doc:** https://databricks-sdk-py.readthedocs.io/en/stable/workspace/catalog/lakehouse_monitors.html

The SDK provides full control over all profile types via `w.lakehouse_monitors`.

### Create Snapshot Monitor

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.catalog import MonitorSnapshot

w = WorkspaceClient()

monitor = w.lakehouse_monitors.create(
    table_name="catalog.schema.my_table",
    assets_dir="/Workspace/Users/user@example.com/monitoring/my_table",
    output_schema_name="catalog.schema",
    snapshot=MonitorSnapshot(),
)
print(f"Monitor status: {monitor.status}")
```

### Create TimeSeries Monitor

```python
from databricks.sdk.service.catalog import MonitorTimeSeries

monitor = w.lakehouse_monitors.create(
    table_name="catalog.schema.events",
    assets_dir="/Workspace/Users/user@example.com/monitoring/events",
    output_schema_name="catalog.schema",
    time_series=MonitorTimeSeries(
        timestamp_col="event_timestamp",
        granularities=["1 day"],
    ),
)
```

### Create InferenceLog Monitor

```python
from databricks.sdk.service.catalog import MonitorInferenceLog

monitor = w.lakehouse_monitors.create(
    table_name="catalog.schema.model_predictions",
    assets_dir="/Workspace/Users/user@example.com/monitoring/predictions",
    output_schema_name="catalog.schema",
    inference_log=MonitorInferenceLog(
        timestamp_col="prediction_timestamp",
        granularities=["1 hour"],
        model_id_col="model_version",
        problem_type="classification",  # or "regression"
        prediction_col="prediction",
        label_col="label",
    ),
)
```

### Schedule a Monitor

```python
from databricks.sdk.service.catalog import MonitorSnapshot, MonitorCronSchedule

monitor = w.lakehouse_monitors.create(
    table_name="catalog.schema.my_table",
    assets_dir="/Workspace/Users/user@example.com/monitoring/my_table",
    output_schema_name="catalog.schema",
    snapshot=MonitorSnapshot(),
    schedule=MonitorCronSchedule(
        quartz_cron_expression="0 0 12 * * ?",  # Daily at noon
        timezone_id="UTC",
    ),
)
```

### Get, Refresh, and Delete

```python
# Get monitor details
monitor = w.lakehouse_monitors.get(table_name="catalog.schema.my_table")

# Trigger refresh
refresh = w.lakehouse_monitors.run_refresh(table_name="catalog.schema.my_table")

# List refresh history
for r in w.lakehouse_monitors.list_refreshes(table_name="catalog.schema.my_table"):
    print(r)

# Delete monitor (does not delete output tables or dashboard)
w.lakehouse_monitors.delete(table_name="catalog.schema.my_table")
```

---

## Output Tables

When a monitor is created, two metric tables are generated in the specified output schema:

| Table | Naming Convention | Contents |
|-------|-------------------|----------|
| **Profile Metrics** | `{table_name}_profile_metrics` | Per-column statistics (nulls, min, max, mean, distinct count, etc.) |
| **Drift Metrics** | `{table_name}_drift_metrics` | Statistical tests comparing current vs. baseline or previous window |

### Query Output Tables

```sql
-- View latest profile metrics
SELECT *
FROM catalog.schema.my_table_profile_metrics
ORDER BY window_end DESC
LIMIT 100;

-- View latest drift metrics
SELECT *
FROM catalog.schema.my_table_drift_metrics
ORDER BY window_end DESC
LIMIT 100;
```

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `FEATURE_NOT_ENABLED` | Lakehouse Monitoring not enabled on workspace | Contact workspace admin to enable the feature |
| `PERMISSION_DENIED` | Missing `MANAGE` privilege on the table | Grant `MANAGE` on the table to your user/group |
| Monitor refresh stuck in `PENDING` | No SQL warehouse available | Ensure a SQL warehouse is running or set `warehouse_id` |
| Profile metrics table empty | Refresh has not completed yet | Check refresh state with `list_refreshes`; wait for `SUCCESS` |
| Snapshot monitor on large table fails | Table exceeds 4TB limit | Switch to TimeSeries profile type instead |
| TimeSeries shows limited data | Only processes last 30 days | Expected behavior; contact account team to adjust |

---

## Resources

- [Lakehouse Monitors SDK Reference](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/catalog/lakehouse_monitors.html)
