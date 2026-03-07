# Data Profiling (formerly Lakehouse Monitoring)

Comprehensive reference for Data Profiling: create quality monitors on Unity Catalog tables to track data profiles, detect drift, and monitor ML model performance.

## Overview

Data profiling automatically computes statistical profiles and drift metrics for tables over time. When you create a monitor, Databricks generates two output Delta tables (profile metrics + drift metrics) and an optional dashboard.

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
| **TimeSeries** | Tables with a timestamp column | `timestamp_column`, `granularities` | Last 30 days only |
| **InferenceLog** | ML model monitoring | `timestamp_column`, `granularities`, `model_id_column`, `problem_type`, `prediction_column` | Last 30 days only |

### Granularities (for TimeSeries and InferenceLog)

Supported `AggregationGranularity` values: `AGGREGATION_GRANULARITY_5_MINUTES`, `AGGREGATION_GRANULARITY_30_MINUTES`, `AGGREGATION_GRANULARITY_1_HOUR`, `AGGREGATION_GRANULARITY_1_DAY`, `AGGREGATION_GRANULARITY_1_WEEK` – `AGGREGATION_GRANULARITY_4_WEEKS`, `AGGREGATION_GRANULARITY_1_MONTH`, `AGGREGATION_GRANULARITY_1_YEAR`

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

**Doc:** https://databricks-sdk-py.readthedocs.io/en/stable/workspace/dataquality/data_quality.html

The new SDK provides full control over all profile types via `w.data_quality`.

### Create Snapshot Monitor

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, SnapshotConfig,
)

w = WorkspaceClient()

# Look up UUIDs — the new API uses object_id and output_schema_id (both UUIDs)
table_info = w.tables.get("catalog.schema.my_table")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/my_table",
            output_schema_id=schema_info.schema_id,
            snapshot=SnapshotConfig(),
        ),
    ),
)
print(f"Monitor status: {monitor.data_profiling_config.status}")
```

### Create TimeSeries Monitor

```python
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, TimeSeriesConfig, AggregationGranularity,
)

table_info = w.tables.get("catalog.schema.events")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/events",
            output_schema_id=schema_info.schema_id,
            time_series=TimeSeriesConfig(
                timestamp_column="event_timestamp",
                granularities=[AggregationGranularity.AGGREGATION_GRANULARITY_1_DAY],
            ),
        ),
    ),
)
```

### Create InferenceLog Monitor

```python
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, InferenceLogConfig,
    AggregationGranularity, InferenceProblemType,
)

table_info = w.tables.get("catalog.schema.model_predictions")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/predictions",
            output_schema_id=schema_info.schema_id,
            inference_log=InferenceLogConfig(
                timestamp_column="prediction_timestamp",
                granularities=[AggregationGranularity.AGGREGATION_GRANULARITY_1_HOUR],
                model_id_column="model_version",
                problem_type=InferenceProblemType.INFERENCE_PROBLEM_TYPE_CLASSIFICATION,
                prediction_column="prediction",
                label_column="label",
            ),
        ),
    ),
)
```

### Schedule a Monitor

```python
from databricks.sdk.service.dataquality import (
    Monitor, DataProfilingConfig, SnapshotConfig, CronSchedule,
)

table_info = w.tables.get("catalog.schema.my_table")
schema_info = w.schemas.get(f"{table_info.catalog_name}.{table_info.schema_name}")

monitor = w.data_quality.create_monitor(
    monitor=Monitor(
        object_type="table",
        object_id=table_info.table_id,
        data_profiling_config=DataProfilingConfig(
            assets_dir="/Workspace/Users/user@example.com/monitoring/my_table",
            output_schema_id=schema_info.schema_id,
            snapshot=SnapshotConfig(),
            schedule=CronSchedule(
                quartz_cron_expression="0 0 12 * * ?",  # Daily at noon
                timezone_id="UTC",
            ),
        ),
    ),
)
```

### Get, Refresh, and Delete

```python
# Get monitor details
monitor = w.data_quality.get_monitor(
    object_type="table",
    object_id=table_info.table_id,
)

# Trigger refresh
from databricks.sdk.service.dataquality import Refresh

refresh = w.data_quality.create_refresh(
    object_type="table",
    object_id=table_info.table_id,
    refresh=Refresh(
        object_type="table",
        object_id=table_info.table_id,
    ),
)

# Delete monitor (does not delete output tables or dashboard)
w.data_quality.delete_monitor(
    object_type="table",
    object_id=table_info.table_id,
)
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
| `FEATURE_NOT_ENABLED` | Data profiling not enabled on workspace | Contact workspace admin to enable the feature |
| `PERMISSION_DENIED` | Missing `MANAGE` privilege on the table | Grant `MANAGE` on the table to your user/group |
| Monitor refresh stuck in `PENDING` | No SQL warehouse available | Ensure a SQL warehouse is running or set `warehouse_id` |
| Profile metrics table empty | Refresh has not completed yet | Check refresh state with `list_refreshes`; wait for `SUCCESS` |
| Snapshot monitor on large table fails | Table exceeds 4TB limit | Switch to TimeSeries profile type instead |
| TimeSeries shows limited data | Only processes last 30 days | Expected behavior; contact account team to adjust |

---

> **Note:** Data profiling was formerly known as Lakehouse Monitoring. The legacy SDK accessor
> `w.lakehouse_monitors` and the MCP tool `manage_uc_monitors` still use the previous API.

## Resources

- [Data Quality Monitoring Documentation](https://docs.databricks.com/aws/en/data-quality-monitoring/)
- [Data Quality SDK Reference](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/dataquality/data_quality.html)
- [Legacy Lakehouse Monitors SDK Reference](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/catalog/lakehouse_monitors.html)
