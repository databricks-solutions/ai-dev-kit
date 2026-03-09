---
name: databricks-serverless-compute
description: >-
  Run Python code on Databricks serverless compute with no cluster required.
  Use this skill when the user mentions: "serverless", "run code", "no cluster",
  "execute python without cluster", "one-off script", "notebook run", "batch script",
  "run without a cluster", "serverless notebook", "submit code". Also use when the user
  wants to run Python but has no running cluster and does not want to start one.
---

# Databricks Serverless Code Execution

## Overview

Run Python code on Databricks serverless compute via the Jobs API (`runs/submit`). This is the only way to execute Python when no interactive cluster is available and the user doesn't want to start one. No cluster management required — serverless compute spins up automatically.

SQL is also supported (`language="sql"`) but only for DDL/DML operations (CREATE TABLE, INSERT, MERGE). For SQL queries that need result rows, use `execute_sql()` which works with serverless SQL warehouses.

## When to Use This vs Alternatives

| Scenario | Tool | Why |
|----------|------|-----|
| **Run Python, no cluster available** | `run_code_on_serverless` | **Primary use case.** No cluster required; serverless spins up automatically |
| Batch/ETL Python that doesn't need interactivity | `run_code_on_serverless` | Dedicated serverless resources, up to 30 min timeout |
| Interactive, iterative Python (preserving variables) | `execute_databricks_command` | Keeps execution context alive across calls |
| SQL queries that need result rows (SELECT) | `execute_sql` | Works with serverless SQL warehouses; returns result data |
| SQL DDL/DML when no warehouse exists | `run_code_on_serverless` with `language="sql"` | Niche: only when no SQL warehouse is available |
| Long-running production pipelines | Databricks Jobs | Full scheduling, retries, monitoring |

## MCP Tool

**Tool name:** `run_code_on_serverless`

**Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `code` | string | *(required)* | Python or SQL code to execute |
| `language` | string | `"python"` | `"python"` or `"sql"` |
| `timeout` | int | `1800` | Max wait time in seconds (30 min default) |
| `run_name` | string | auto-generated | Optional human-readable run name |

**Returns:** Dictionary with `success`, `output`, `error`, `run_id`, `run_url`, `duration_seconds`, `state`, `message`.

## Output Capture Behavior

- **Python:** Use `dbutils.notebook.exit(value)` to return structured output. The `value` is captured in the `output` field.
- **print() output:** May not be captured reliably. Prefer `dbutils.notebook.exit()` for returning results.
- **SQL:** SELECT query results are **NOT** returned — this is a Jobs API limitation. Only use `language="sql"` for DDL/DML. For SQL queries that need result rows, use `execute_sql()` (works with serverless SQL warehouses).

## Quick Start

### Run a Python script

```python
run_code_on_serverless(
    code="dbutils.notebook.exit('hello from serverless')",
    language="python"
)
```

### Run a SQL DDL statement

```python
run_code_on_serverless(
    code="CREATE TABLE IF NOT EXISTS catalog.schema.my_table (id INT, name STRING)",
    language="sql"
)
```

### Run Python with output capture

```python
run_code_on_serverless(
    code="""
import json
results = {"rows_processed": 42, "status": "complete"}
dbutils.notebook.exit(json.dumps(results))
""",
    language="python",
    timeout=600,
    run_name="data-processing-run"
)
```

## Limitations

| Limitation | Details |
|-----------|---------|
| **Cold start** | ~25-50 seconds for serverless compute to spin up |
| **No interactive state** | Each invocation is a fresh notebook; no variables persist between calls |
| **Languages** | Python and SQL only; no R, Scala, or Java |
| **Default timeout** | 30 minutes (configurable via `timeout` parameter) |
| **SQL SELECT output** | Query results not captured; use `execute_sql()` for SELECT queries |
| **print() output** | Not reliably captured; use `dbutils.notebook.exit()` instead |

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Success (no output)"** for Python | Use `dbutils.notebook.exit(value)` to return output |
| **SQL SELECT returns no data** | Known limitation; use `execute_sql()` for queries needing result rows |
| **Timeout errors** | Increase `timeout` parameter (default 1800s); check run at `run_url` |
| **Cold start feels slow** | Expected ~25-50s; use `execute_databricks_command` with a running cluster for faster iteration |
| **Error message is generic** | Check the `error` field for the full traceback; also check `run_url` in the Databricks UI |

## Related Skills

- **[databricks-jobs](../databricks-jobs/SKILL.md)** - Production job orchestration with scheduling, retries, and multi-task DAGs
- **[databricks-dbsql](../databricks-dbsql/SKILL.md)** - Advanced SQL features, SQL warehouse capabilities, and AI functions
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - Direct Databricks SDK usage for workspace automation
