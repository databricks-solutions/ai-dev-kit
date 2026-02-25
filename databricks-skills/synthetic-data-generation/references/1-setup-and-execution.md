# Setup and Execution Guide

This guide covers all execution modes for synthetic data generation, organized by Databricks Connect version and Python version.

## Quick Decision Matrix

| Your Environment | Recommended Approach |
|------------------|---------------------|
| Python 3.12+ with databricks-connect >= 16.4 | DatabricksEnv with withDependencies API |
| Python 3.10/3.11 with older databricks-connect | Serverless job with environments parameter |
| Classic compute (fallback only) | Manual cluster setup |

## Option 1: Databricks Connect 16.4+ with Serverless (Recommended)

**Best for:** Python 3.12+, local development with serverless compute

**Install locally:**
```bash
# Preferred
uv pip install "databricks-connect>=16.4,<17.0" faker numpy pandas holidays

# Fallback if uv not available
pip install "databricks-connect>=16.4,<17.0" faker numpy pandas holidays
```

**Configure ~/.databrickscfg:**
```ini
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

**In your script:**
```python
from databricks.connect import DatabricksSession, DatabricksEnv

# Pass dependencies as simple package name strings
env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")

# Create session with managed dependencies
spark = (
    DatabricksSession.builder
    .withEnvironment(env)
    .serverless(True)
    .getOrCreate()
)

# Spark operations now execute on serverless compute with managed dependencies
```

**Version Detection (if needed):**
```python
import importlib.metadata

def get_databricks_connect_version():
    """Get databricks-connect version as (major, minor) tuple."""
    try:
        version_str = importlib.metadata.version('databricks-connect')
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return None

db_version = get_databricks_connect_version()
if db_version and db_version >= (16, 4):
    # Use DatabricksEnv with withDependencies
    pass
```

**Benefits:**
- Instant start, no cluster wait
- Local debugging and fast iteration
- Automatic dependency management
- Edit file, re-run immediately

## Option 2: Older Databricks Connect or Python < 3.12

**Best for:** Python 3.10/3.11, databricks-connect 15.1-16.3

`DatabricksEnv()` and `withEnvironment()` are NOT available in older versions. Use serverless jobs with environments parameter instead.

### Serverless Job Configuration Requirements

**MUST use `"client": "4"` in the Environment Spec:**

```json
{
  "environments": [{
    "environment_key": "datagen_env",
    "spec": {
      "client": "4",
      "dependencies": ["faker", "numpy", "pandas"]
    }
  }]
}
```

> **Note:** Using `"client": "1"` will fail with environment configuration errors.

### Script Deployment

Deploy Python files (.py) to the workspace for serverless jobs:

```bash
databricks workspace import /Users/<user>@databricks.com/scripts/my_script.py \
  --file ./my_script.py --format AUTO

databricks workspace list /Users/<user>@databricks.com/scripts/
```

**Job config must reference the workspace path:**

```json
{
  "spark_python_task": {
    "python_file": "/Users/<user>@databricks.com/scripts/my_script.py"
  },
  "environment_key": "datagen_env"
}
```

**DABs bundle configuration:**
```yaml
# databricks.yml
bundle:
  name: synthetic-data-gen

resources:
  jobs:
    generate_data:
      name: "Generate Synthetic Data"
      tasks:
        - task_key: generate
          spark_python_task:
            python_file: ./src/generate_data.py
          environment_key: default

environments:
  default:
    spec:
      client: "4"
      dependencies:
        - faker
        - numpy
        - pandas
        - holidays
```

## Option 3: Classic Cluster

**Use when:** Serverless unavailable, or specific cluster features needed (GPUs, custom init scripts)

### Step 1: Check Python Version Compatibility

Pandas UDFs require matching Python minor versions between local and cluster.

```bash
# Check local Python
uv run python --version  # or: python --version

# Check cluster DBR version → Python version
# DBR 17.x = Python 3.12
# DBR 15.4 LTS = Python 3.11
# DBR 14.3 LTS = Python 3.10
databricks clusters get <cluster-id> | grep spark_version
```

### Step 2a: If Versions Match → Use Databricks Connect

```bash
# Install matching databricks-connect version (must match DBR major.minor)
uv pip install "databricks-connect==17.3.*" faker numpy pandas holidays
```

```bash
# Install libraries on cluster
`databricks libraries install --json '{"cluster_id": "<cluster_id>", "libraries": [{"pypi": {"package": "faker"}}, {"pypi": {"package": "holidays"}}]}'`

# Wait for INSTALLED status
databricks libraries cluster-status <cluster-id>
```

```python
# Run locally via Databricks Connect
from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.clusterId("<cluster-id>").getOrCreate()
# Your Spark code runs on the cluster
```

### Step 2b: If Versions Don't Match → Submit as Job

**Ask user for approval before submitting.** Example prompt:
> "Your local Python (3.11) doesn't match the cluster (3.12). Pandas UDFs require matching versions. Should I submit this as a job to run directly on the cluster instead?"

```bash
# Upload script to workspace
databricks workspace import /Users/you@company.com/scripts/generate_data.py \
  --file generate_data.py --format AUTO --overwrite

# Submit job to run on cluster
databricks jobs submit --json '{
  "run_name": "Generate Data",
  "tasks": [{
    "task_key": "generate",
    "existing_cluster_id": "<cluster-id>",
    "spark_python_task": {
      "python_file": "/Users/you@company.com/scripts/generate_data.py"
    }
  }]
}'
```

### Classic Cluster Decision Flow

```
Local Python == Cluster Python?
  ├─ YES → Install libs on cluster, run via Databricks Connect
  └─ NO  → Ask user: "Submit as job instead?"
           └─ Upload script + submit job
```

## Required Libraries

Standard libraries for generating realistic synthetic data:

| Library | Purpose | Required For |
|---------|---------|--------------|
| **faker** | Realistic names, addresses, emails, companies | Text data generation |
| **numpy** | Statistical distributions | Non-linear distributions |
| **pandas** | Data manipulation, Pandas UDFs | Spark UDF definitions |
| **holidays** | Country-specific holiday calendars | Time-based patterns |

## Environment Detection Pattern

Use this pattern to auto-detect environment and choose the right session creation:

```python
import os

def is_databricks_runtime():
    """Check if running on Databricks Runtime vs locally."""
    return "DATABRICKS_RUNTIME_VERSION" in os.environ

def get_databricks_connect_version():
    """Get databricks-connect version as (major, minor) tuple or None."""
    try:
        import databricks.connect
        version_str = databricks.connect.__version__
        parts = version_str.split('.')
        return (int(parts[0]), int(parts[1]))
    except (ImportError, AttributeError, ValueError, IndexError):
        return None

on_runtime = is_databricks_runtime()
db_version = get_databricks_connect_version()

# Use DatabricksEnv if: locally + databricks-connect >= 16.4
use_auto_dependencies = (not on_runtime) and db_version and db_version >= (16, 4)

if use_auto_dependencies:
    from databricks.connect import DatabricksSession, DatabricksEnv
    env = DatabricksEnv().withDependencies("faker", "pandas", "numpy", "holidays")
    spark = DatabricksSession.builder.withEnvironment(env).serverless(True).getOrCreate()
else:
    from databricks.connect import DatabricksSession
    spark = DatabricksSession.builder.serverless(True).getOrCreate()
```

## Common Setup Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: faker` | Install dependencies per execution mode above |
| `DatabricksEnv not found` | Upgrade to databricks-connect >= 16.4 or use job with environments |
| `serverless_compute_id` error | Add `serverless_compute_id = auto` to ~/.databrickscfg |
| Classic cluster startup slow | Use serverless instead (instant start) |