# DQX Storage, Configuration, Metrics & Dashboard

## Checks Storage Backends

| Backend | Config Class | Location Format | Use Case |
|---------|-------------|----------------|----------|
| **Local File** | `FileChecksStorageConfig` | `checks.yml` or `checks.json` | Development, testing |
| **Workspace File** | `WorkspaceFileChecksStorageConfig` | `/Shared/App1/checks.yml` | Shared workspace checks |
| **Unity Catalog Table** | `TableChecksStorageConfig` | `catalog.schema.checks_table` | Production, governed |
| **UC Volume** | `VolumeFileChecksStorageConfig` | `/Volumes/cat/schema/vol/checks.yml` | File-based with UC governance |
| **Lakebase** | `LakebaseChecksStorageConfig` | `dqx.config.checks` | Lakebase-hosted |
| **Installation** | `InstallationChecksStorageConfig` | Auto-managed | CLI workflow default |

### Save and Load

```python
from databricks.labs.dqx.engine import DQEngine
from databricks.labs.dqx.config import (
    FileChecksStorageConfig, WorkspaceFileChecksStorageConfig,
    TableChecksStorageConfig, VolumeFileChecksStorageConfig,
)

dq_engine = DQEngine(WorkspaceClient())

# Local YAML
dq_engine.save_checks(checks, config=FileChecksStorageConfig(location="checks.yml"))

# Workspace file
dq_engine.save_checks(checks, config=WorkspaceFileChecksStorageConfig(location="/Shared/App1/checks.yml"))

# Unity Catalog table (supports append mode and run_config_name)
dq_engine.save_checks(checks, config=TableChecksStorageConfig(
    location="catalog.schema.checks_table", mode="append"
))

# UC Volume
dq_engine.save_checks(checks, config=VolumeFileChecksStorageConfig(
    location="/Volumes/dq/config/checks_volume/App1/checks.yml"
))

# Load from table with run_config_name filter
checks = dq_engine.load_checks(config=TableChecksStorageConfig(
    location="catalog.schema.checks_table", run_config_name="main.default.input_table"
))

# Validate
status = dq_engine.validate_checks(checks)
assert not status.has_errors
```

## Configuration File (config.yml)

Created during `databricks labs install dqx`. Used by CLI workflows.

```yaml
log_level: INFO
version: 1
serverless_clusters: true

run_configs:
  - name: default
    input_config:
      location: catalog.schema.bronze
      format: delta
      is_streaming: false
    output_config:
      location: catalog.schema.silver
      format: delta
      mode: append
    quarantine_config:
      location: catalog.schema.quarantine
      format: delta
      mode: append
    metrics_config:
      format: delta
      location: catalog.schema.dq_metrics
      mode: append
    checks_location: checks.yml
    profiler_config:
      sample_fraction: 0.3
      limit: 1000
      llm_primary_key_detection: false
    warehouse_id: your-warehouse-id
```

### Streaming Configuration

```yaml
run_configs:
  - name: streaming_config
    input_config:
      location: catalog.schema.bronze
      format: delta
      is_streaming: true
    output_config:
      location: catalog.schema.silver
      format: delta
      mode: append
      checkpointLocation: /Volumes/catalog/schema/checkpoint/output
      trigger:
        availableNow: true
    quarantine_config:
      location: catalog.schema.quarantine
      format: delta
      mode: append
      checkpointLocation: /Volumes/catalog/schema/checkpoint/quarantine
      trigger:
        availableNow: true
```

### Custom Check Functions in Config

```yaml
run_configs:
  - name: default
    custom_check_functions:
      my_func: custom_checks/my_funcs.py
      my_other: /Workspace/Shared/MyApp/my_funcs.py
      email_mask: /Volumes/main/dqx_utils/custom/email.py
```

### Reference Tables

```yaml
run_configs:
  - name: default
    reference_tables:
      reference_table_1:
        input_config:
          format: delta
          location: catalog.schema.reference_data
```

## Summary Metrics

DQX auto-computes: `input_row_count`, `error_row_count`, `warning_row_count`, `valid_row_count`.

### Batch Collection

```python
from databricks.labs.dqx.metrics_observer import DQMetricsObserver

observer = DQMetricsObserver(name="dq_metrics")
engine = DQEngine(WorkspaceClient(), observer=observer)
checked_df, observation = engine.apply_checks_by_metadata(df, checks)
checked_df.count()  # trigger Spark action
metrics = observation.get
```

### Write Metrics to Table

```python
engine.apply_checks_and_save_in_table(
    checks=checks,
    input_config=InputConfig(location="catalog.schema.bronze"),
    output_config=OutputConfig(location="catalog.schema.silver"),
    quarantine_config=OutputConfig(location="catalog.schema.quarantine"),
    metrics_config=OutputConfig(location="catalog.schema.dq_metrics", format="delta", mode="append")
)
```

### Streaming Metrics

Use `get_streaming_metrics_listener` or end-to-end methods for automatic streaming metric collection.

### Custom Metrics

```yaml
# In config.yml
custom_metrics:
  - "avg(amount) as average_transaction_amount"
  - "sum(array_size(_errors)) as total_errors"
```

### Metrics Table Schema

| Column | Description |
|--------|-------------|
| `run_id` | Unique run identifier |
| `run_name` | Run configuration name |
| `input_location` / `output_location` / `quarantine_location` | Source, target, quarantine paths |
| `checks_location` | Checks definition location |
| `metric_name` / `metric_value` | Metric name and value (stored as STRING) |
| `run_time` | Timestamp of the run |
| `error_column_name` / `warning_column_name` | Names of result columns |
| `user_metadata` | Custom metadata map |

## Additional Configuration

### Custom Result Column Names

```python
dq_engine = DQEngine(ws, extra_params=ExtraParams(
    result_column_names={"errors": "dq_errors", "warnings": "dq_warnings"}
))
```

### User Metadata

```python
# Engine-level (applies to all checks)
dq_engine = DQEngine(ws, extra_params=ExtraParams(
    user_metadata={"pipeline": "orders", "team": "data-eng"}
))

# Per-check (overrides engine-level for same keys)
DQRowRule(criticality="error", check_func=check_funcs.is_not_null, column="customer_id",
    user_metadata={"check_category": "completeness", "owner": "data-team"})
```

## Quality Dashboard

Built-in Lakeview dashboard with three tabs: **Data Quality Summary**, **Quality by Table (Time Series)**, **Quality by Table (Full Snapshot)**.

```bash
databricks labs dqx open-dashboards
```

Tables must have `_errors`/`_warnings` columns (or custom names). Dashboard is not auto-scheduled; set up a schedule via a Databricks Job. Manual import: `DQX_Dashboard.lvdash.json` from the [DQX GitHub repo](https://github.com/databrickslabs/dqx).

## CLI Reference

```bash
# Installation
databricks labs install dqx                              # Install
databricks labs install dqx@v0.9.3                       # Specific version
databricks labs upgrade dqx                              # Upgrade
databricks labs uninstall dqx                            # Uninstall

# Configuration
databricks labs dqx open-remote-config                   # Open config.yml
databricks labs dqx workflows                            # List workflows

# Profiling
databricks labs dqx profile --run-config "default"
databricks labs dqx profile --patterns "main.data.*"
databricks labs dqx profile --exclude-patterns "*_tmp"

# Quality Checking
databricks labs dqx apply-checks --run-config "default"
databricks labs dqx apply-checks --patterns "main.*"
databricks labs dqx apply-checks --output-table-suffix "_clean"
databricks labs dqx apply-checks --quarantine-table-suffix "_quarantine"

# End-to-End
databricks labs dqx e2e --run-config "default"

# Validation
databricks labs dqx validate-checks --run-config "default"

# Logs & Dashboard
databricks labs dqx logs --workflow profiler
databricks labs dqx logs --workflow quality-checker
databricks labs dqx open-dashboards
```

## Best Practices

### Rule Management

- **Store checks in Delta tables** for production — centralizes management, enables governance and versioning
- **Govern checks storage strictly** — rules directly impact pipeline behavior:
  - Read-only access for business users/data engineers; write restricted to service principals
  - Modify only through CI/CD workflows, not ad-hoc SQL or direct DML
  - Separate tables by domain/team/environment to prevent cross-boundary changes
- **Use `run_config_name`** to share common checks across table groups, layered with table-specific checks
- **Prioritize high-impact fields** — business keys, timestamps, join/aggregation columns, compliance columns, columns with known quality issues, clustering/partition columns
- **Match rule type to purpose:**

| Type | When to Use |
|------|-------------|
| Rule-based | Deterministic validation (default choice) |
| AI-assisted | Translate natural language requirements to rules |
| Anomaly detection | Catch outliers not covered by explicit rules |
| Profiler-generated | Bootstrap initial rule sets from data |

- **Prefer row-level checks** for performance and granularity; use dataset-level to supplement
- **Encapsulate reusable logic** in custom check functions instead of duplicating `sql_expression`
- **Define consumer-specific rules** when downstream applications (reporting, ML, data science) have different quality expectations for the same table

### Profile and Tune Over Time

- Bootstrap rules with the **profiler** for new datasets; re-profile periodically to detect distribution shifts
- Use **AI-assisted generation** to translate business/compliance requirements into rules
- Monitor **pass/fail rates and trends** to reduce false positives while maintaining coverage
- **Add/tune checks immediately** after production incidents to prevent recurrence
- **Retire obsolete rules** as business logic evolves; version rules for traceability

### Pipeline Integration

- **Workflows** (no-code) for post-factum monitoring on persisted data; **embedded** (programmatic) for in-transit validation
- **Apply all checks in one pass** — group row-level + dataset-level + anomaly checks to minimize scans
- **Quarantine** critical bad records (`apply_checks_and_split`); **flag** non-critical records (`apply_checks`)
- **Scale across tables** with `apply_checks_and_save_in_tables` or `apply_checks_and_save_in_tables_for_patterns`
- **Set up SLAs and alerting** for critical quality metrics; use the dashboard and metrics table for trend tracking

### Deployment

- **Version rules in Git**, deploy as Delta tables aligned with pipeline releases (e.g., via Databricks Asset Bundles)
- Use **environment-specific configs** when promoting dev → qa → prod
- Tag rules with version info via `user_metadata` or `run_config_name`:

```yaml
# Per-rule versioning via user_metadata
- criticality: error
  check:
    function: is_not_null
    arguments:
      column: col1
  user_metadata:
    version: v1
    location: catalog.schema.checks_table
```

```python
# Rule-set versioning via run_config_name
dq_engine.save_checks(checks, config=TableChecksStorageConfig(
    location="catalog.schema.checks_table",
    run_config_name="main.default.input_table_v1", mode="overwrite"
))
```

- **Pin DQX version** (`pip install databricks-labs-dqx==0.9.3` / `databricks labs install dqx@v0.9.3`); review breaking changes before upgrading
- **Test in lower environments** with sample/synthetic data before production; automate regression tests for critical checks
- **Use custom installation folders** to isolate DQX dependencies per team
