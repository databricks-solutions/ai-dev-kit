# Installation and Setup

## Install as a Library (pip)

### In a Databricks Notebook

```python
%pip install databricks-labs-dqx
dbutils.library.restartPython()
```

### Pinned Version (recommended for production)

```python
%pip install databricks-labs-dqx==0.13.0
dbutils.library.restartPython()
```

### Optional Extras

```bash
# AI-assisted rule generation (includes DSPy)
pip install 'databricks-labs-dqx[llm]'

# PII detection (includes Microsoft Presidio)
pip install 'databricks-labs-dqx[pii]'

# Data Contract / ODCS support
pip install 'databricks-labs-dqx[datacontract]'

# Combined
pip install 'databricks-labs-dqx[datacontract,llm]'
```

### In Databricks Asset Bundles (DAB)

Add to your job's task libraries:

```yaml
resources:
  jobs:
    quality_check_job:
      tasks:
        - task_key: run_checks
          libraries:
            - pypi:
                package: databricks-labs-dqx==0.13.0
```

### Enterprise PyPI Mirror

```bash
PIP_INDEX_URL="https://your-company-pypi.internal" pip install databricks-labs-dqx
```

---

## Install as a Workspace Tool (Databricks CLI)

Prerequisites: Python 3.10+, Databricks CLI v0.241+

```bash
# Authenticate
databricks auth login --host <WORKSPACE_HOST>

# Install latest
databricks labs install dqx

# Install pinned version
databricks labs install dqx@v0.13.0

# Force global install (shared across users)
DQX_FORCE_INSTALL=global databricks labs install dqx

# Force user install (default)
DQX_FORCE_INSTALL=user databricks labs install dqx
```

### What Workspace Installation Deploys

- Python wheel file
- `config.yml` configuration file
- Profiler workflow (unscheduled)
- Quality checker workflow (unscheduled)
- End-to-end (e2e) workflow (unscheduled)
- Quality dashboard (unscheduled)

### Installation Locations

| Mode | Path |
|------|------|
| **User (default)** | `/Users/<user>/.dqx` |
| **Global** | `/Applications/dqx` |
| **Custom** | Any workspace folder |

### CLI Lifecycle Commands

```bash
databricks labs install dqx      # Install
databricks labs upgrade dqx      # Upgrade to latest
databricks labs uninstall dqx    # Uninstall

# Open configuration
databricks labs dqx open-remote-config
databricks labs dqx open-remote-config --install-folder "/Workspace/my_folder"

# Open quality dashboard
databricks labs dqx open-dashboards
```

---

## Basic Setup in Code

```python
from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.engine import DQEngine

# Standard setup (uses default auth from notebook context or env)
ws = WorkspaceClient()
dq_engine = DQEngine(ws)

# With Databricks Connect (local development)
from databricks.connect import DatabricksSession
spark = DatabricksSession.builder.getOrCreate()
dq_engine = DQEngine(ws, spark)

# With custom result column names
from databricks.labs.dqx.config import ExtraParams
extra_params = ExtraParams(
    result_column_names={"errors": "dq_errors", "warnings": "dq_warnings"}
)
dq_engine = DQEngine(ws, extra_params=extra_params)
```

---

## Configuration File (config.yml)

For workspace installations, DQX uses a `config.yml`:

```yaml
serverless_clusters: true
profiler_max_parallelism: 4

llm_config:
  model:
    model_name: "databricks/databricks-claude-sonnet-4-5"
    api_key: xxx        # optional: secret_scope/secret_key
    api_base: xxx       # optional: secret_scope/secret_key

extra_params:
  result_column_names:
    errors: dq_errors
    warnings: dq_warnings
  user_metadata:
    team: data-engineering

run_configs:
  - name: default
    checks_location: catalog.schema.checks_table
    input_config:
      format: delta
      location: catalog.schema.input_table
      is_streaming: false
    output_config:
      location: catalog.schema.output_table
      mode: append
    quarantine_config:
      location: catalog.schema.quarantine_table
      mode: append
    profiler_config:
      limit: 1000
      sample_fraction: 0.3
      summary_stats_file: profile_summary_stats.yml
      filter: "status = 'active'"
      llm_primary_key_detection: false
      checks_user_requirements: "business rules description"
```
