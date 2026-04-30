# Advanced Pipeline Configuration

By default, pipelines are created with **serverless compute and Unity Catalog**. Use advanced configuration options only when needed.

**CRITICAL: Do NOT set `serverless=false` unless the user explicitly requires:**
- R language support
- Spark RDD APIs
- JAR libraries or Maven coordinates

## When to Use Advanced Configuration

- **Development mode**: Faster iteration with relaxed validation
- **Continuous pipelines**: Real-time streaming instead of triggered runs
- **Event logging**: Custom event log table location
- **Pipeline metadata**: Tags, configuration variables
- **Python dependencies**: Install pip packages for serverless pipelines
- **Classic clusters** (rare): Only if user explicitly needs R, RDD APIs, or JARs

## Pipeline JSON Configuration Reference

These fields can be passed to `databricks pipelines create --json '{...}'` or `databricks pipelines update <id> --json '{...}'`.

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
| `kind` | str | `"BUNDLE"` (DABs) or `"DEFAULT"` |
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

All examples use `databricks pipelines create --json '{...}'`. For updates, use `databricks pipelines update <pipeline_id> --json '{...}'`.

> **Tagging**: By default, add `"tags": {"aidevkit_project": "ai-dev-kit"}` to track resources created with this skill.

### Development Mode Pipeline

```bash
databricks pipelines create --json '{
  "name": "my_dev_pipeline",
  "catalog": "dev_catalog",
  "schema": "dev_schema",
  "serverless": true,
  "development": true,
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}],
  "tags": {"environment": "development", "owner": "data-team"}
}'
```

### Non-Serverless with Dedicated Cluster

```bash
databricks pipelines create --json '{
  "name": "my_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": false,
  "photon": true,
  "edition": "ADVANCED",
  "clusters": [{
    "label": "default",
    "num_workers": 4,
    "node_type_id": "i3.xlarge",
    "custom_tags": {"cost_center": "analytics"}
  }],
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}]
}'
```

### Continuous Streaming Pipeline

```bash
databricks pipelines create --json '{
  "name": "my_streaming_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "continuous": true,
  "configuration": {"spark.sql.shuffle.partitions": "auto"},
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}]
}'
```

### Pipeline with Email Notifications

```bash
databricks pipelines create --json '{
  "name": "my_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}],
  "notifications": [{
    "email_recipients": ["team@example.com", "oncall@example.com"],
    "alerts": ["on-update-failure", "on-update-fatal-failure", "on-flow-failure"]
  }]
}'
```

### Production Pipeline with Autoscaling

```bash
databricks pipelines create --json '{
  "name": "prod_pipeline",
  "catalog": "prod_catalog",
  "schema": "prod_schema",
  "serverless": false,
  "development": false,
  "photon": true,
  "edition": "ADVANCED",
  "clusters": [{
    "label": "default",
    "autoscale": {"min_workers": 2, "max_workers": 8, "mode": "ENHANCED"},
    "node_type_id": "i3.xlarge",
    "spark_conf": {"spark.sql.adaptive.enabled": "true"},
    "custom_tags": {"environment": "production"}
  }],
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}],
  "notifications": [{"email_recipients": ["data-team@example.com"], "alerts": ["on-update-failure"]}]
}'
```

### Serverless with Python Dependencies

```bash
databricks pipelines create --json '{
  "name": "ml_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}],
  "environment": {
    "dependencies": ["scikit-learn==1.3.0", "pandas>=2.0.0", "requests"]
  }
}'
```

### Continuous Pipeline with Restart Window

```bash
databricks pipelines create --json '{
  "name": "realtime_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "continuous": true,
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}],
  "restart_window": {
    "start_hour": 2,
    "days_of_week": ["SATURDAY", "SUNDAY"],
    "time_zone_id": "America/Los_Angeles"
  }
}'
```

### Custom Event Log Location

```bash
databricks pipelines create --json '{
  "name": "my_pipeline",
  "catalog": "my_catalog",
  "schema": "my_schema",
  "serverless": true,
  "libraries": [{"file": {"path": "/Workspace/Users/user@example.com/my_pipeline"}}],
  "event_log": {
    "catalog": "audit_catalog",
    "schema": "pipeline_logs",
    "name": "my_pipeline_events"
  }
}'
```

### Update Existing Pipeline

```bash
# Update pipeline configuration
databricks pipelines update <pipeline_id> --json '{
  "name": "updated_pipeline_name",
  "development": false,
  "notifications": [{"email_recipients": ["team@example.com"], "alerts": ["on-update-failure"]}]
}'

# Then run it
databricks pipelines start-update <pipeline_id> --full-refresh
```

---

## Multi-Schema Patterns

**Recommended: One pipeline writing to multiple schemas** using fully qualified table names. This is simpler than creating multiple pipelines and keeps all dependencies in one place.

For simple cases where all tables go to the same schema, use name prefixes (`bronze_*`, `silver_*`, `gold_*`).

### Option 1: Same Catalog, Separate Schemas

Set pipeline defaults to bronze, use parameters for silver/gold:

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

# Pull variables from pipeline configuration
silver_schema = spark.conf.get("silver_schema")  # e.g., "silver"
gold_schema   = spark.conf.get("gold_schema")    # e.g., "gold"
landing_schema = spark.conf.get("landing_schema")  # e.g., "landing"

# Bronze → uses default catalog/schema (set to bronze in pipeline settings)
@dp.table(name="orders_bronze")
def orders_bronze():
    return spark.readStream.table(f"{landing_schema}.orders_raw")

# Silver → same catalog, schema from parameter
@dp.table(name=f"{silver_schema}.orders_clean")
def orders_clean():
    return spark.read.table("orders_bronze").filter(col("order_id").isNotNull())

# Gold → same catalog, schema from parameter
@dp.materialized_view(name=f"{gold_schema}.orders_by_date")
def orders_by_date():
    return (spark.read.table(f"{silver_schema}.orders_clean")
            .groupBy("order_date").count())
```

### Option 2: Custom Catalog/Schema Per Layer

For cross-catalog scenarios:

```python
from pyspark import pipelines as dp
from pyspark.sql.functions import col

# Pull variables from pipeline configuration
silver_catalog = spark.conf.get("silver_catalog")
silver_schema  = spark.conf.get("silver_schema")
gold_catalog   = spark.conf.get("gold_catalog")
gold_schema    = spark.conf.get("gold_schema")

# Bronze → uses pipeline defaults
@dp.table(name="orders_bronze")
def orders_bronze():
    return spark.readStream.format("cloudFiles").load("/Volumes/...")

# Silver → custom catalog + schema
@dp.table(name=f"{silver_catalog}.{silver_schema}.orders_clean")
def orders_clean():
    return spark.read.table("orders_bronze").filter(col("order_id").isNotNull())

# Gold → custom catalog + schema
@dp.materialized_view(name=f"{gold_catalog}.{gold_schema}.orders_by_date")
def orders_by_date():
    return (spark.read.table(f"{silver_catalog}.{silver_schema}.orders_clean")
            .groupBy("order_date").count())
```

**Key points:**
- Multipart names in `@dp.table(name=...)` let you publish to explicit catalog.schema targets
- Unqualified names use pipeline defaults
- Use fully-qualified names when crossing catalogs
