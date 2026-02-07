# Advanced Pipeline Configuration (`extra_settings`)

By default, pipelines are created with **serverless compute and Unity Catalog**. Use the `extra_settings` parameter only for advanced use cases.

**CRITICAL: Do NOT use `extra_settings` to set `serverless=false` unless the user explicitly requires:**
- R language support
- Spark RDD APIs
- JAR libraries or Maven coordinates

## When to Use `extra_settings`

- **Development mode**: Faster iteration with relaxed validation
- **Continuous pipelines**: Real-time streaming instead of triggered runs
- **Event logging**: Custom event log table location
- **Pipeline metadata**: Tags, configuration variables
- **Python dependencies**: Install pip packages for serverless pipelines
- **Classic clusters** (rare): Only if user explicitly needs R, RDD APIs, or JARs

## `extra_settings` Parameter Reference

### Top-Level Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `serverless` | bool | `true` | Use serverless compute. Set `false` for dedicated clusters. |
| `continuous` | bool | `false` | `true` = always running (real-time), `false` = triggered runs |
| `development` | bool | `false` | Development mode: faster startup, relaxed validation, no retries |
| `photon` | bool | `false` | Enable Photon vectorized query engine |
| `edition` | str | `"CORE"` | `"CORE"`, `"PRO"`, or `"ADVANCED"`. Advanced required for CDC. |
| `channel` | str | `"CURRENT"` | `"CURRENT"` (stable) or `"PREVIEW"` (latest features) |
| `clusters` | list | `[]` | Cluster configs (required if `serverless=false`) |
| `configuration` | dict | `{}` | Spark config key-value pairs (all values must be strings) |
| `tags` | dict | `{}` | Pipeline metadata tags (max 25 tags) |
| `event_log` | dict | auto | Custom event log table location |
| `notifications` | list | `[]` | Email/webhook alerts on pipeline events |
| `id` | str | - | Force update of specific pipeline ID |
| `allow_duplicate_names` | bool | `false` | Allow multiple pipelines with same name |
| `budget_policy_id` | str | - | Budget policy ID for cost tracking |
| `storage` | str | - | DBFS root directory for checkpoints/tables (legacy, use Unity Catalog instead) |
| `target` | str | - | **Deprecated**: Use `schema` parameter instead |
| `dry_run` | bool | `false` | Validate pipeline without creating (create only) |
| `run_as` | dict | - | Run pipeline as specific user/service principal |
| `restart_window` | dict | - | Maintenance window for continuous pipeline restarts |
| `filters` | dict | - | Include/exclude specific paths from pipeline |
| `trigger` | dict | - | **Deprecated**: Use `continuous` instead |
| `deployment` | dict | - | Deployment method (BUNDLE or DEFAULT) |
| `environment` | dict | - | Python pip dependencies for serverless |
| `gateway_definition` | dict | - | CDC gateway pipeline configuration |
| `ingestion_definition` | dict | - | Managed ingestion settings (Salesforce, Workday, etc.) |
| `usage_policy_id` | str | - | Usage policy ID |

### `clusters` Array - Cluster Configuration

Each cluster object supports these fields:

| Field | Type | Description |
|-------|------|-------------|
| `label` | str | **Required**. `"default"` for main cluster, `"maintenance"` for maintenance tasks |
| `num_workers` | int | Fixed number of workers (use this OR autoscale, not both) |
| `autoscale` | dict | `{"min_workers": 1, "max_workers": 4, "mode": "ENHANCED"}` |
| `node_type_id` | str | Instance type, e.g., `"i3.xlarge"`, `"Standard_DS3_v2"` |
| `driver_node_type_id` | str | Driver instance type (defaults to node_type_id) |
| `instance_pool_id` | str | Use instances from this pool (faster startup) |
| `driver_instance_pool_id` | str | Pool for driver node |
| `spark_conf` | dict | Spark configuration for this cluster |
| `spark_env_vars` | dict | Environment variables |
| `custom_tags` | dict | Tags applied to cloud resources |
| `init_scripts` | list | Init script locations |
| `aws_attributes` | dict | AWS-specific: `{"availability": "SPOT", "zone_id": "us-west-2a"}` |
| `azure_attributes` | dict | Azure-specific: `{"availability": "SPOT_AZURE"}` |
| `gcp_attributes` | dict | GCP-specific settings |

**Autoscale modes**: `"LEGACY"` or `"ENHANCED"` (recommended, optimizes for DLT workloads)

### `event_log` Object - Custom Event Log Location

| Field | Type | Description |
|-------|------|-------------|
| `catalog` | str | Unity Catalog name for event log table |
| `schema` | str | Schema name for event log table |
| `name` | str | Table name for event logs |

### `notifications` Array - Alert Configuration

Each notification object:

| Field | Type | Description |
|-------|------|-------------|
| `email_recipients` | list | List of email addresses |
| `alerts` | list | Events to alert on: `"on-update-success"`, `"on-update-failure"`, `"on-update-fatal-failure"`, `"on-flow-failure"` |

### `configuration` Dict - Spark/Pipeline Config

Common configuration keys (all values must be strings):

| Key | Description |
|-----|-------------|
| `spark.sql.shuffle.partitions` | Number of shuffle partitions (`"auto"` recommended) |
| `pipelines.numRetries` | Number of retries on transient failures |
| `pipelines.trigger.interval` | Trigger interval for continuous pipelines, e.g., `"1 hour"` |
| `spark.databricks.delta.preview.enabled` | Enable Delta preview features (`"true"`) |

### `run_as` Object - Pipeline Execution Identity

Specify which user or service principal runs the pipeline:

| Field | Type | Description |
|-------|------|-------------|
| `user_name` | str | Email of workspace user (can only set to your own email) |
| `service_principal_name` | str | Application ID of service principal (requires servicePrincipal/user role) |

**Note**: Only one of `user_name` or `service_principal_name` can be set.

### `restart_window` Object - Continuous Pipeline Restart Schedule

For continuous pipelines, define when restarts can occur:

| Field | Type | Description |
|-------|------|-------------|
| `start_hour` | int | **Required**. Hour (0-23) when 5-hour restart window begins |
| `days_of_week` | list | Days allowed: `"MONDAY"`, `"TUESDAY"`, etc. (default: all days) |
| `time_zone_id` | str | Timezone, e.g., `"America/Los_Angeles"` (default: UTC) |

### `filters` Object - Path Filtering

Include or exclude specific paths from the pipeline:

| Field | Type | Description |
|-------|------|-------------|
| `include` | list | List of paths to include |
| `exclude` | list | List of paths to exclude |

### `environment` Object - Python Dependencies (Serverless)

Install pip dependencies for serverless pipelines:

| Field | Type | Description |
|-------|------|-------------|
| `dependencies` | list | List of pip requirements (e.g., `["pandas==2.0.0", "requests"]`) |

### `deployment` Object - Deployment Method

| Field | Type | Description |
|-------|------|-------------|
| `kind` | str | `"BUNDLE"` (Databricks Asset Bundles) or `"DEFAULT"` |
| `metadata_file_path` | str | Path to deployment metadata file |

### Edition Comparison

| Feature | CORE | PRO | ADVANCED |
|---------|------|-----|----------|
| Streaming tables | Yes | Yes | Yes |
| Materialized views | Yes | Yes | Yes |
| Expectations (data quality) | Yes | Yes | Yes |
| Change Data Capture (CDC) | No | No | Yes |
| SCD Type 1/2 | No | No | Yes |

## Configuration Examples

### Development Mode Pipeline

Use `create_or_update_pipeline` tool with:
- `name`: "my_dev_pipeline"
- `root_path`: "/Workspace/Users/user@example.com/my_pipeline"
- `catalog`: "dev_catalog"
- `schema`: "dev_schema"
- `workspace_file_paths`: [...]
- `start_run`: true
- `extra_settings`:
```json
{
    "development": true,
    "tags": {"environment": "development", "owner": "data-team"}
}
```

### Non-Serverless with Dedicated Cluster

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "serverless": false,
    "clusters": [{
        "label": "default",
        "num_workers": 4,
        "node_type_id": "i3.xlarge",
        "custom_tags": {"cost_center": "analytics"}
    }],
    "photon": true,
    "edition": "ADVANCED"
}
```

### Continuous Streaming Pipeline

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "continuous": true,
    "configuration": {
        "spark.sql.shuffle.partitions": "auto"
    }
}
```

### Using Instance Pool

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "serverless": false,
    "clusters": [{
        "label": "default",
        "instance_pool_id": "0727-104344-hauls13-pool-xyz",
        "num_workers": 2,
        "custom_tags": {"project": "analytics"}
    }]
}
```

### Custom Event Log Location

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "event_log": {
        "catalog": "audit_catalog",
        "schema": "pipeline_logs",
        "name": "my_pipeline_events"
    }
}
```

### Pipeline with Email Notifications

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "notifications": [{
        "email_recipients": ["team@example.com", "oncall@example.com"],
        "alerts": ["on-update-failure", "on-update-fatal-failure", "on-flow-failure"]
    }]
}
```

### Production Pipeline with Autoscaling

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "serverless": false,
    "development": false,
    "photon": true,
    "edition": "ADVANCED",
    "clusters": [{
        "label": "default",
        "autoscale": {
            "min_workers": 2,
            "max_workers": 8,
            "mode": "ENHANCED"
        },
        "node_type_id": "i3.xlarge",
        "spark_conf": {
            "spark.sql.adaptive.enabled": "true"
        },
        "custom_tags": {"environment": "production"}
    }],
    "notifications": [{
        "email_recipients": ["data-team@example.com"],
        "alerts": ["on-update-failure"]
    }]
}
```

### Run as Service Principal

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "run_as": {
        "service_principal_name": "00000000-0000-0000-0000-000000000000"
    }
}
```

### Continuous Pipeline with Restart Window

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "continuous": true,
    "restart_window": {
        "start_hour": 2,
        "days_of_week": ["SATURDAY", "SUNDAY"],
        "time_zone_id": "America/Los_Angeles"
    }
}
```

### Serverless with Python Dependencies

Use `create_or_update_pipeline` tool with `extra_settings`:
```json
{
    "serverless": true,
    "environment": {
        "dependencies": [
            "scikit-learn==1.3.0",
            "pandas>=2.0.0",
            "requests"
        ]
    }
}
```

### Update Existing Pipeline by ID

If you have a pipeline ID from the Databricks UI, you can force an update by including `id` in `extra_settings`:
```json
{
    "id": "554f4497-4807-4182-bff0-ffac4bb4f0ce"
}
```

### Full JSON Export from Databricks UI

You can copy pipeline settings from the Databricks UI (Pipeline Settings > JSON) and pass them directly as `extra_settings`. Invalid fields like `pipeline_type` are automatically filtered:

```json
{
    "id": "554f4497-4807-4182-bff0-ffac4bb4f0ce",
    "pipeline_type": "WORKSPACE",
    "continuous": false,
    "development": true,
    "photon": false,
    "edition": "ADVANCED",
    "channel": "CURRENT",
    "clusters": [{
        "label": "default",
        "num_workers": 1,
        "instance_pool_id": "0727-104344-pool-xyz"
    }],
    "configuration": {
        "catalog": "main",
        "schema": "my_schema"
    }
}
```

**Note**: Explicit tool parameters (`name`, `root_path`, `catalog`, `schema`, `workspace_file_paths`) always take precedence over values in `extra_settings`.
