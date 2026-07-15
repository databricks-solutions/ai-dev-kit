# Databricks Connect (Recommended Default)

**Use when:** Running Spark code locally that executes on Databricks serverless compute. This is the fastest, cleanest approach for data generation, ETL, and any Spark workload.

## Why Databricks Connect First?

- **Instant iteration** — Edit file, re-run immediately
- **Local debugging** — IDE debugger, breakpoints work
- **No cold start** — Session stays warm across executions
- **Clean dependencies** — `withDependencies()` installs packages on remote compute

## Requirements

- **Python 3.12** (databricks-connect >= 16.4 requires it)
- **databricks-connect >= 16.4** package
- **~/.databrickscfg** with serverless config

## Setup

**Python 3.12 required.** If not available, install it (uv or other). If install fails, ask user—don't auto-switch modes.

Use default profile, if not setup you can add it `~/.databrickscfg` (never overwrite it without conscent)
```ini
[DEFAULT]
host = https://your-workspace.cloud.databricks.com/
serverless_compute_id = auto
auth_type = databricks-cli
```

## Usage Pattern

```python
from databricks.connect import DatabricksSession, DatabricksEnv

# Declare dependencies installed on serverless compute
# CRITICAL: Include ALL packages used inside UDFs (pandas/numpy are there by default)
env = DatabricksEnv().withDependencies("faker", "holidays")

spark = (
    DatabricksSession.builder
    .profile("my-workspace")  # optional: run on a specific profile from ~/.databrickscfg instead of default
    .withEnvironment(env)
    .serverless(True)
    .getOrCreate()
)

# Spark code now executes on Databricks serverless
df = spark.range(1000)...
df.write.mode('overwrite').saveAsTable("catalog.schema.table")
```

## Common Issues

| Issue | Solution |
|-------|----------|
| `Python 3.12 required` | create venv with correct python version |
| `DatabricksEnv not found` | Upgrade to databricks-connect >= 16.4 |
| `serverless_compute_id` error | Add `serverless_compute_id = auto` to ~/.databrickscfg |
| `ModuleNotFoundError` inside UDF | Add the package to `withDependencies()` |
| `PERSIST TABLE not supported` | Don't use `.cache()` or `.persist()` with serverless |
| `broadcast` is used | Don't broadcast small DF using spark connect, have a small python list instead or join small DF |

## When NOT to Use

Switch to **[Serverless Job](2-serverless-job.md)** when:
- one-off execution
- Heavy ML training that shouldn't depend on local machine staying connected
- Non-Spark Python code (pure sklearn, pytorch, etc.)

Switch to **[Interactive Cluster](3-interactive-cluster.md)** when:
- Need state across multiple separate MCP tool calls
- Need Scala or R support
