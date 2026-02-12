# Databricks Tools Core

High-level, AI-assistant-friendly Python functions for building Databricks projects.

## Overview

The `databricks-tools-core` package provides reusable, opinionated functions for interacting with the Databricks platform. It is designed to be used by AI coding assistants (Claude Code, Cursor, etc.) and developers who want simple, high-level APIs for common Databricks operations.

### Modules

| Module | Description |
|--------|-------------|
| **sql/** | SQL execution, warehouse management, and table statistics |
| **jobs/** | Job management and run operations (serverless by default) |
| **unity_catalog/** | Unity Catalog operations (catalogs, schemas, tables, FGAC policies) |
| **compute/** | Compute and execution context operations |
| **spark_declarative_pipelines/** | Spark Declarative Pipeline management |
| **synthetic_data_generation/** | Test data generation utilities |

## Installation

### Using uv (recommended)

```bash
# Install the package
uv pip install -e .

# Install with dev dependencies
uv pip install -e ".[dev]"
```

### Using pip

```bash
pip install -e .
```

## Authentication

All functions use `get_workspace_client()` from the `auth` module, which supports multiple authentication methods:

### Authentication Priority

1. **Context variables** (for multi-user apps) - Set via `set_databricks_auth()`
2. **Environment variables** - `DATABRICKS_HOST` and `DATABRICKS_TOKEN`
3. **Config profile** - `DATABRICKS_CONFIG_PROFILE` or `~/.databrickscfg`

### Single-User Mode (CLI, Scripts, Notebooks)

```bash
# Option 1: Environment variables
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-token"

# Option 2: Config profile
export DATABRICKS_CONFIG_PROFILE="my-profile"
```

Then use functions directly:

```python
from databricks_tools_core.sql import execute_sql

result = execute_sql("SELECT 1")  # Uses env vars or config
```

### Multi-User Mode (Web Apps, APIs)

For applications serving multiple users, use contextvars to set per-request credentials:

```python
from databricks_tools_core.auth import (
    set_databricks_auth,
    clear_databricks_auth,
    get_workspace_client,
)

# In your request handler
async def handle_request(user_host: str, user_token: str):
    set_databricks_auth(user_host, user_token)
    try:
        # All functions now use this user's credentials
        result = execute_sql("SELECT current_user()")

        # Or get client directly
        client = get_workspace_client()
        warehouses = client.warehouses.list()
    finally:
        clear_databricks_auth()
```

**How it works:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    Authentication Flow                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  set_databricks_auth(host, token)                               │
│         │                                                       │
│         ▼                                                       │
│  ┌─────────────────────────┐                                    │
│  │ contextvars             │  (async-safe, per-request)         │
│  │ _host_ctx = host        │                                    │
│  │ _token_ctx = token      │                                    │
│  └───────────┬─────────────┘                                    │
│              │                                                  │
│              ▼                                                  │
│  get_workspace_client()                                         │
│         │                                                       │
│         ├─── Has context? ──► WorkspaceClient(host, token)      │
│         │                                                       │
│         └─── No context? ───► WorkspaceClient()  (uses env/cfg) │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

This pattern is used by `databricks-mcp-app` to handle per-user authentication when deployed as a Databricks App, where each request includes the user's access token in headers.

## Usage

### SQL Execution

Execute SQL queries on Databricks SQL Warehouses:

```python
from databricks_tools_core.sql import execute_sql, execute_sql_multi

# Simple query (auto-selects warehouse if not specified)
result = execute_sql("SELECT * FROM my_catalog.my_schema.customers LIMIT 10")
# Returns: [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, ...]

# Query with specific warehouse and catalog/schema context
result = execute_sql(
    sql_query="SELECT COUNT(*) as cnt FROM customers",
    warehouse_id="abc123def456",
    catalog="my_catalog",
    schema="my_schema",
)

# Execute multiple statements with dependency-aware parallelism
result = execute_sql_multi(
    sql_content="""
        CREATE TABLE t1 AS SELECT 1 as id;
        CREATE TABLE t2 AS SELECT 2 as id;
        CREATE TABLE t3 AS SELECT * FROM t1 JOIN t2;
    """,
    catalog="my_catalog",
    schema="my_schema",
)
# t1 and t2 run in parallel, t3 waits for both
```

### Warehouse Management

List and select SQL warehouses:

```python
from databricks_tools_core.sql import list_warehouses, get_best_warehouse

# List warehouses (running ones first)
warehouses = list_warehouses(limit=20)
# Returns: [{"id": "...", "name": "...", "state": "RUNNING", ...}, ...]

# Auto-select best available warehouse
warehouse_id = get_best_warehouse()
# Prefers: running shared endpoints > running warehouses > stopped warehouses
```

### Table Statistics

Get detailed table information and column statistics:

```python
from databricks_tools_core.sql import get_table_details, TableStatLevel

# Get all tables in a schema with basic stats
result = get_table_details(
    catalog="my_catalog",
    schema="my_schema",
)

# Get specific tables (faster - no listing required)
result = get_table_details(
    catalog="my_catalog",
    schema="my_schema",
    table_names=["customers", "orders"],
)

# Use glob patterns
result = get_table_details(
    catalog="my_catalog",
    schema="my_schema",
    table_names=["raw_*", "gold_customers"],  # Mix of patterns and exact names
)

# Control stat level
result = get_table_details(
    catalog="my_catalog",
    schema="my_schema",
    table_names=["customers"],
    table_stat_level=TableStatLevel.DETAILED,  # NONE, SIMPLE, or DETAILED
)
```

**TableStatLevel options:**

| Level | Description | Use Case |
|-------|-------------|----------|
| `NONE` | DDL only, no stats | Quick schema lookup |
| `SIMPLE` | Basic stats (samples, min/max, cardinality) | Default, cached |
| `DETAILED` | Full stats (histograms, percentiles, value counts) | Data profiling |

### Jobs

Create, manage, and run Databricks jobs. Uses serverless compute by default for optimal performance and cost.

```python
from databricks_tools_core.jobs import (
    create_job, get_job, list_jobs, update_job, delete_job,
    run_job_now, get_run, list_runs, cancel_run, wait_for_run,
)

# Create a job with notebook task (serverless by default)
tasks = [
    {
        "task_key": "etl_task",
        "notebook_task": {
            "notebook_path": "/Workspace/ETL/process_data",
            "source": "WORKSPACE",
        },
    }
]
job = create_job(name="my_etl_job", tasks=tasks)
print(f"Created job: {job['job_id']}")

# Run the job immediately
run_id = run_job_now(job_id=job["job_id"])

# Wait for completion (with timeout)
result = wait_for_run(run_id=run_id, timeout=3600)
if result.success:
    print(f"Job completed in {result.duration_seconds}s")
else:
    print(f"Job failed: {result.error_message}")

# List recent runs
runs = list_runs(job_id=job["job_id"], limit=10)

# Cancel a running job
cancel_run(run_id=run_id)
```

**Job Functions:**

| Function | Description |
|----------|-------------|
| `create_job()` | Create a new job with tasks and settings |
| `get_job()` | Get detailed job configuration |
| `list_jobs()` | List jobs with optional name filter |
| `find_job_by_name()` | Find job by exact name, returns job ID |
| `update_job()` | Update job configuration |
| `delete_job()` | Delete a job |

**Run Functions:**

| Function | Description |
|----------|-------------|
| `run_job_now()` | Trigger a job run, returns run ID |
| `get_run()` | Get run status and details |
| `get_run_output()` | Get run output and logs |
| `list_runs()` | List runs with filters |
| `cancel_run()` | Cancel a running job |
| `wait_for_run()` | Wait for run completion, returns `JobRunResult` |

**JobRunResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | True if run completed successfully |
| `lifecycle_state` | str | PENDING, RUNNING, TERMINATING, TERMINATED, SKIPPED, INTERNAL_ERROR |
| `result_state` | str | SUCCESS, FAILED, TIMEDOUT, CANCELED |
| `duration_seconds` | float | Total execution time |
| `error_message` | str | Error message if failed |
| `run_page_url` | str | Link to run in Databricks UI |

### Unity Catalog Operations

```python
from databricks_tools_core.unity_catalog import catalogs, schemas, tables

# List catalogs
all_catalogs = catalogs.list_catalogs()

# Create schema
schema = schemas.create_schema(
    catalog_name="main",
    schema_name="my_schema",
    comment="Example schema"
)

# Create table
from databricks.sdk.service.catalog import ColumnInfo, TableType

table = tables.create_table(
    catalog_name="main",
    schema_name="my_schema",
    table_name="my_table",
    columns=[
        ColumnInfo(name="id", type_name="INT"),
        ColumnInfo(name="value", type_name="STRING")
    ],
    table_type=TableType.MANAGED
)
```

## Architecture

```
databricks-tools-core/
├── databricks_tools_core/
│   ├── auth.py                       # Authentication (contextvars + env vars)
│   ├── sql/                          # SQL operations
│   │   ├── sql.py                    # execute_sql, execute_sql_multi
│   │   ├── warehouse.py              # list_warehouses, get_best_warehouse
│   │   ├── table_stats.py            # get_table_details
│   │   └── sql_utils/                # Internal utilities
│   │       ├── executor.py           # SQLExecutor class
│   │       ├── parallel_executor.py  # Multi-statement execution
│   │       ├── dependency_analyzer.py # SQL dependency analysis
│   │       ├── table_stats_collector.py # Stats collection with caching
│   │       └── models.py             # Pydantic models
│   ├── jobs/                         # Job operations
│   │   ├── jobs.py                   # create_job, get_job, list_jobs, etc.
│   │   ├── runs.py                   # run_job_now, get_run, wait_for_run, etc.
│   │   └── models.py                 # JobRunResult, JobError, enums
│   ├── unity_catalog/                # Unity Catalog operations
│   ├── compute/                      # Compute operations
│   ├── spark_declarative_pipelines/  # SDP operations
│   └── client.py                     # REST API client
└── tests/                            # Integration tests
```

This is a **pure Python library** with no MCP protocol dependencies. It can be used standalone in notebooks, scripts, or other Python projects.

For MCP server functionality, see the `databricks-mcp-server` package which wraps these functions as MCP tools.

## Testing

The project includes comprehensive integration tests that run against a real Databricks workspace.

### Prerequisites

- A Databricks workspace with valid authentication configured
- At least one running SQL warehouse
- Permission to create catalogs/schemas/tables

### Running Tests

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run all integration tests
uv run pytest tests/integration/ -v

# Run specific test file
uv run pytest tests/integration/sql/test_sql.py -v

# Run specific test class
uv run pytest tests/integration/sql/test_table_stats.py::TestTableStatLevelDetailed -v

# Run with more verbose output
uv run pytest tests/integration/ -v --tb=long
```

### Test Structure

```
tests/
├── conftest.py                    # Shared fixtures
│   ├── workspace_client           # WorkspaceClient fixture
│   ├── test_catalog               # Creates ai_dev_kit_test catalog
│   ├── test_schema                # Creates fresh test_schema (drops if exists)
│   ├── warehouse_id               # Gets best running warehouse
│   └── test_tables                # Creates sample tables with data
└── integration/
    ├── sql/
    │   ├── test_warehouse.py      # Warehouse listing tests
    │   ├── test_sql.py            # SQL execution tests
    │   └── test_table_stats.py    # Table statistics tests
    └── jobs/
        ├── conftest.py            # Jobs-specific fixtures (test notebook, cleanup)
        ├── test_jobs.py           # Job CRUD tests
        └── test_runs.py           # Run operation tests
```

### Test Coverage

| Test File | Coverage |
|-----------|----------|
| `test_warehouse.py` | `list_warehouses`, `get_best_warehouse` |
| `test_sql.py` | `execute_sql`, `execute_sql_multi`, error handling, parallel execution |
| `test_table_stats.py` | `get_table_details`, all stat levels, glob patterns, caching |
| `test_jobs.py` | `list_jobs`, `find_job_by_name`, `create_job`, `get_job`, `update_job`, `delete_job` |
| `test_runs.py` | `run_job_now`, `get_run`, `cancel_run`, `list_runs`, `wait_for_run` |

### Test Fixtures

The test suite uses session-scoped fixtures to minimize setup overhead:

- **`test_catalog`**: Creates `ai_dev_kit_test` catalog (reuses if exists)
- **`test_schema`**: Drops and recreates `test_schema` for clean state
- **`test_tables`**: Creates `customers`, `orders`, `products` tables with sample data

## Development

```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Format code
uv run black databricks_tools_core/

# Lint code
uv run ruff check databricks_tools_core/
```

## Dependencies

### Core
- `databricks-sdk>=0.20.0` - Official Databricks Python SDK
- `requests>=2.31.0` - HTTP client
- `pydantic>=2.0.0` - Data validation
- `sqlglot>=20.0.0` - SQL parsing
- `sqlfluff>=3.0.0` - SQL linting and formatting

### Development
- `pytest>=7.0.0` - Testing framework
- `pytest-timeout>=2.0.0` - Test timeouts
- `black>=23.0.0` - Code formatting
- `ruff>=0.1.0` - Linting
