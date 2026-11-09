# Core Library

`databricks-tools-core` is the Python library that powers the MCP server. You can also use it directly in your own projects — with LangChain, OpenAI Agents, FastAPI, or any Python framework.

---

## Install

```bash
pip install databricks-ai-dev-kit
```

## Quick example

```python
from databricks_tools_core.sql import execute_sql
from databricks_tools_core.auth import set_auth

set_auth(profile="DEFAULT")
results = execute_sql("SELECT * FROM main.default.my_table LIMIT 10")
```

## Modules

| Module | Key functions |
|--------|--------------|
| `sql` | `execute_sql`, `execute_sql_multi`, `list_warehouses`, `get_table_details` |
| `jobs` | `create_job`, `run_job_now`, `get_job`, `list_jobs`, `wait_for_run` |
| `unity_catalog` | `list_catalogs`, `list_schemas`, `list_tables` |
| `compute` | `list_clusters`, `execute_command` |
| `spark_declarative_pipelines` | `create_or_update_pipeline`, `run_pipeline`, `get_pipeline` |

## Authentication

```python
from databricks_tools_core.auth import set_auth

# CLI profile (default)
set_auth(profile="DEFAULT")

# Explicit credentials
set_auth(host="https://my-workspace.cloud.databricks.com", token="dapi...")
```

Multi-user safe via Python `contextvars`.

## Framework integration

=== "LangChain"

    ```python
    from langchain.tools import tool
    from databricks_tools_core.sql import execute_sql

    @tool
    def query_databricks(query: str) -> str:
        """Execute a SQL query on Databricks."""
        return execute_sql(query)
    ```

=== "OpenAI Agents"

    ```python
    from agents import function_tool
    from databricks_tools_core.sql import execute_sql

    @function_tool
    def query_databricks(query: str) -> str:
        """Execute a SQL query on Databricks."""
        return execute_sql(query)
    ```

=== "FastAPI"

    ```python
    from fastapi import FastAPI
    from databricks_tools_core.sql import execute_sql

    app = FastAPI()

    @app.get("/query")
    def run_query(sql: str):
        return execute_sql(sql)
    ```

See the full [API documentation](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-tools-core) for details.
