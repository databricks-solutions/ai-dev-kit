# Quality Monitors — MCP Tool Reference

Operational reference for the `manage_uc_monitors` MCP tool. For conceptual overview, profile types, and Python SDK examples, see [7-data-profiling.md](7-data-profiling.md).

---

## When to Use Quality Monitors

| Scenario | Monitor Type |
|----------|-------------|
| Track data freshness, completeness, and distribution on any table | **Snapshot** |
| Detect drift over time windows on event/log tables | **TimeSeries** |
| Monitor ML model prediction quality and feature drift | **InferenceLog** |

Quality monitors automatically generate two output Delta tables (profile metrics + drift metrics) and an auto-generated dashboard in the workspace.

---

## MCP Tool: `manage_uc_monitors`

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `action` | string | **Yes** | — | One of: `create`, `get`, `run_refresh`, `list_refreshes`, `delete` |
| `table_name` | string | **Yes** | — | Fully qualified table name (`catalog.schema.table`) |
| `output_schema_name` | string | No | `null` | Schema for output tables (`catalog.schema`). Required for `create`. |
| `schedule_cron` | string | No | `null` | Quartz cron expression (e.g., `0 0 12 * * ?` for daily at noon) |
| `schedule_timezone` | string | No | `"UTC"` | IANA timezone for the schedule |
| `assets_dir` | string | No | `null` | Workspace path for dashboard assets. The MCP tool auto-generates a path if omitted; the REST API requires it. |

### Supported Actions

| Action | Description | Extra Params |
|--------|-------------|-------------|
| `create` | Create a snapshot monitor on a table | `output_schema_name` (required), `schedule_cron`, `schedule_timezone`, `assets_dir` |
| `get` | Get monitor configuration and status | — |
| `run_refresh` | Trigger a manual metric refresh | — |
| `list_refreshes` | List refresh history with states | — |
| `delete` | Delete the monitor (output tables and dashboard are NOT deleted) | — |

> **Limitation:** The MCP tool only creates **snapshot** monitors. For TimeSeries or InferenceLog monitors, use the Python SDK (`w.data_quality.create_monitor`) — see [7-data-profiling.md](7-data-profiling.md).

> **No `list` action:** There is no action to list all monitors across tables. Use `get` on specific tables, or query for `*_profile_metrics` tables to discover monitored tables.

---

## Verified Patterns

All examples below were tested against a live workspace and produce the exact response shapes shown.

### Create a Monitor

```python
manage_uc_monitors(
    action="create",
    table_name="catalog.schema.my_table",
    output_schema_name="catalog.schema",
)
```

**Response:**

```json
{
  "assets_dir": "/Workspace/Users/user@example.com/databricks_lakehouse_monitoring/catalog_schema_my_table",
  "drift_metrics_table_name": "catalog.schema.my_table_drift_metrics",
  "monitor_version": 0,
  "output_schema_name": "catalog.schema",
  "profile_metrics_table_name": "catalog.schema.my_table_profile_metrics",
  "snapshot": {},
  "status": "MONITOR_STATUS_PENDING",
  "table_name": "catalog.schema.my_table"
}
```

The monitor starts as `MONITOR_STATUS_PENDING` and transitions to `MONITOR_STATUS_ACTIVE` once initialized (typically within seconds). A `dashboard_id` is added at that point.

### Create a Monitor with Schedule

```python
manage_uc_monitors(
    action="create",
    table_name="catalog.schema.my_table",
    output_schema_name="catalog.schema",
    schedule_cron="0 0 12 * * ?",
    schedule_timezone="America/Los_Angeles",
)
```

**Response includes schedule block:**

```json
{
  "schedule": {
    "pause_status": "UNPAUSED",
    "quartz_cron_expression": "0 0 12 * * ?",
    "timezone_id": "America/Los_Angeles"
  },
  "status": "MONITOR_STATUS_PENDING",
  ...
}
```

### Common Cron Schedules

| Schedule | Quartz Expression |
|----------|-------------------|
| Daily at midnight | `0 0 0 * * ?` |
| Daily at noon | `0 0 12 * * ?` |
| Every 6 hours | `0 0 */6 * * ?` |
| Weekly on Monday at 8am | `0 0 8 ? * MON` |
| First day of month at midnight | `0 0 0 1 * ?` |

### Get Monitor Status

```python
manage_uc_monitors(
    action="get",
    table_name="catalog.schema.my_table",
)
```

**Response (active monitor):**

```json
{
  "assets_dir": "/Workspace/Users/user@example.com/databricks_lakehouse_monitoring/...",
  "dashboard_id": "01f119fd15e3115cbfd3e9c0218e470e",
  "drift_metrics_table_name": "catalog.schema.my_table_drift_metrics",
  "monitor_version": 0,
  "output_schema_name": "catalog.schema",
  "profile_metrics_table_name": "catalog.schema.my_table_profile_metrics",
  "snapshot": {},
  "status": "MONITOR_STATUS_ACTIVE",
  "table_name": "catalog.schema.my_table"
}
```

**Error (no monitor exists):**

```
Cannot find Monitor with ID: /metastores:<uuid>/tables:<uuid>/
```

### Trigger a Refresh

```python
manage_uc_monitors(
    action="run_refresh",
    table_name="catalog.schema.my_table",
)
```

**Response:**

```json
{
  "refresh_id": 543489905367182,
  "start_time_ms": 1772871772469,
  "state": "PENDING",
  "trigger": "MANUAL"
}
```

### List Refresh History

```python
manage_uc_monitors(
    action="list_refreshes",
    table_name="catalog.schema.my_table",
)
```

**Response:**

```json
{
  "refreshes": [
    {
      "refresh_id": 222263540296352,
      "start_time_ms": 1772871033816,
      "state": "PENDING",
      "trigger": "MANUAL"
    },
    {
      "refresh_id": 896016687173548,
      "start_time_ms": 1772871021738,
      "state": "RUNNING",
      "trigger": "MANUAL"
    }
  ]
}
```

Refresh states: `PENDING` → `RUNNING` → `SUCCESS` or `FAILED`. Completed refreshes also include an `end_time_ms` field.

### Delete a Monitor

```python
manage_uc_monitors(
    action="delete",
    table_name="catalog.schema.my_table",
)
```

**Response:**

```json
{}
```

The REST API returns an empty JSON object on successful deletion. The MCP tool may return a confirmation message wrapping this response.

> **Important:** Deleting a monitor does NOT delete the output tables (`*_profile_metrics`, `*_drift_metrics`) or the dashboard. Clean those up separately if needed.

---

## Querying Monitor Output Tables

### Profile Metrics Table Schema

The `{table_name}_profile_metrics` table contains per-column statistics:

| Column | Type | Description |
|--------|------|-------------|
| `window` | `struct<start:timestamp, end:timestamp>` | Time window for the metrics |
| `log_type` | string | Type of log entry |
| `logging_table_commit_version` | int | Commit version of the logging table |
| `monitor_version` | bigint | Version of the monitor configuration |
| `granularity` | string | Granularity of the metrics |
| `slice_key` | string | Slice key for segmented analysis |
| `slice_value` | string | Slice value for segmented analysis |
| `column_name` | string | Name of the profiled column (`:table` for table-level metrics) |
| `count` | bigint | Total row count |
| `data_type` | string | Data type of the column |
| `num_nulls` | bigint | Number of null values |
| `avg` | double | Mean value (numeric columns) |
| `quantiles` | `array<double>` | Quantile values |
| `min` | double | Minimum value |
| `max` | double | Maximum value |
| `stddev` | double | Standard deviation |
| `num_zeros` | bigint | Number of zero values |
| `num_nan` | bigint | Number of NaN values |
| `min_length` | double | Minimum string length |
| `max_length` | double | Maximum string length |
| `avg_length` | double | Average string length |
| `non_null_columns` | `array<string>` | List of non-null columns (table-level) |
| `frequent_items` | `array<struct<item:string, count:bigint>>` | Most frequent values |
| `median` | double | Median value |
| `distinct_count` | bigint | Number of distinct values |
| `percent_nan` | double | Percentage of NaN values |
| `percent_null` | double | Percentage of nulls |
| `percent_zeros` | double | Percentage of zeros |
| `percent_distinct` | double | Percentage of distinct values |

### Drift Metrics Table Schema

The `{table_name}_drift_metrics` table contains statistical drift tests:

| Column | Type | Description |
|--------|------|-------------|
| `window` | `struct<start:timestamp, end:timestamp>` | Current time window |
| `granularity` | string | Granularity of the metrics |
| `monitor_version` | bigint | Version of the monitor configuration |
| `slice_key` | string | Slice key for segmented analysis |
| `slice_value` | string | Slice value for segmented analysis |
| `column_name` | string | Profiled column |
| `data_type` | string | Data type of the column |
| `window_cmp` | `struct<start:timestamp, end:timestamp>` | Comparison window |
| `drift_type` | string | Type of drift detected (e.g., `CONSECUTIVE`) |
| `count_delta` | bigint | Change in row count |
| `avg_delta` | double | Change in mean |
| `percent_null_delta` | double | Change in null percentage |
| `percent_zeros_delta` | double | Change in zeros percentage |
| `percent_distinct_delta` | double | Change in distinct percentage |
| `non_null_columns_delta` | `struct<added:int, missing:int>` | Changes in non-null columns |
| `js_distance` | double | Jensen-Shannon divergence |
| `ks_test` | `struct<statistic:double, pvalue:double>` | Kolmogorov-Smirnov test |
| `wasserstein_distance` | double | Wasserstein (earth mover's) distance |
| `population_stability_index` | double | PSI score |
| `chi_squared_test` | `struct<statistic:double, pvalue:double>` | Chi-squared test |
| `tv_distance` | double | Total variation distance |
| `l_infinity_distance` | double | L-infinity distance |

> **Note:** Drift metrics require at least 2 refreshes to populate. The first refresh only generates profile metrics.

### Example Queries

```sql
-- Latest profile metrics per column
SELECT
    column_name,
    count,
    num_nulls,
    avg,
    min,
    max,
    stddev,
    distinct_count,
    percent_null,
    window.start AS window_start,
    window.end AS window_end
FROM catalog.schema.my_table_profile_metrics
ORDER BY window.end DESC;

-- Detect columns with high null rates
SELECT column_name, percent_null, count
FROM catalog.schema.my_table_profile_metrics
WHERE percent_null > 0.1
ORDER BY percent_null DESC;

-- Check for significant drift (low KS test p-value)
SELECT
    column_name,
    drift_type,
    ks_test.statistic AS ks_statistic,
    ks_test.pvalue AS ks_pvalue,
    js_distance,
    population_stability_index
FROM catalog.schema.my_table_drift_metrics
WHERE ks_test.pvalue < 0.05
ORDER BY ks_test.pvalue ASC;

-- Monitor data freshness across refreshes
SELECT
    window.start AS window_start,
    window.end AS window_end,
    column_name,
    count
FROM catalog.schema.my_table_profile_metrics
WHERE column_name = ':table'
ORDER BY window.end DESC;
```

### Discovering Monitored Tables

Since there is no `list` action, find monitored tables by querying for output tables:

```sql
SELECT table_catalog, table_schema, table_name
FROM system.information_schema.tables
WHERE table_name LIKE '%_profile_metrics'
ORDER BY table_catalog, table_schema, table_name;
```

---

## Typical Workflow

```
1. Create monitor     →  manage_uc_monitors(action="create", ...)
2. Wait for init      →  manage_uc_monitors(action="get", ...) until MONITOR_STATUS_ACTIVE
3. Trigger refresh    →  manage_uc_monitors(action="run_refresh", ...)
4. Check progress     →  manage_uc_monitors(action="list_refreshes", ...) until state=SUCCESS
5. Query results      →  execute_sql("SELECT ... FROM catalog.schema.table_profile_metrics")
6. (Optional) Delete  →  manage_uc_monitors(action="delete", ...)
```

---

## Common Issues and Troubleshooting

| Issue | Error / Symptom | Solution |
|-------|----------------|----------|
| `list` action fails | `Invalid action: 'list'` | No list action exists. Use `get` per table or query `information_schema` for `*_profile_metrics` tables. |
| Monitor not found | `Cannot find Monitor with ID: /metastores:<uuid>/tables:<uuid>/` | Table has no monitor. Create one first with `action="create"`. |
| Drift metrics empty | Query returns 0 rows | Drift requires at least 2 completed refreshes. Run another refresh and wait for `SUCCESS`. |
| `window_end` column error | `UNRESOLVED_COLUMN` SQL error | The column is `window` (a struct). Use `window.end` or `window.start` to access timestamps. |
| Monitor stuck in PENDING | `status: "MONITOR_STATUS_PENDING"` | Wait a few seconds and re-check with `get`. If persistent, ensure a SQL warehouse is available. |
| Refresh stuck in PENDING/RUNNING | Refresh never reaches `SUCCESS` | Check SQL warehouse availability. Large tables take longer. Use `list_refreshes` to monitor. |
| `FEATURE_NOT_ENABLED` | Feature not enabled on workspace | Contact workspace admin to enable data profiling / Lakehouse Monitoring. |
| `PERMISSION_DENIED` | Missing privileges | Need `USE CATALOG`, `USE SCHEMA`, `SELECT`, and `MANAGE` on the table. |
| Output tables not cleaned up after delete | Tables and dashboard persist | By design. Manually `DROP TABLE` the `*_profile_metrics` and `*_drift_metrics` tables if needed. |
| Snapshot monitor fails on large table | Table exceeds size limit | Snapshot monitors have a 4TB table size limit. Use TimeSeries profile type via SDK instead. |

---

## Resources

- [Data Quality Monitoring Documentation](https://docs.databricks.com/aws/en/data-quality-monitoring/)
- [Data Profiling Conceptual Guide](7-data-profiling.md) — profile types, Python SDK, granularities
- [Data Quality SDK Reference](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/dataquality/data_quality.html)
- [Legacy Lakehouse Monitors SDK Reference](https://databricks-sdk-py.readthedocs.io/en/stable/workspace/catalog/lakehouse_monitors.html)
