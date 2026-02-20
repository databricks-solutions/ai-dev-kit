# Lakeflow / DLT Integration

DQX integrates with Lakeflow Declarative Pipelines (DLT) to apply quality checks within pipeline stages.

**Important**: Install `databricks-labs-dqx` as a pipeline library before using DQX in DLT.

---

## Pattern 1: Apply Checks with Quarantine

Split data into valid (silver) and quarantine tables:

```python
import dlt
from databricks.labs.dqx.engine import DQEngine
from databricks.labs.dqx.rule import DQRowRule
from databricks.labs.dqx import check_funcs
from databricks.sdk import WorkspaceClient

dq_engine = DQEngine(WorkspaceClient())

checks = [
    DQRowRule(criticality="error", check_func=check_funcs.is_not_null, column="order_id"),
    DQRowRule(criticality="warn", check_func=check_funcs.is_in_range, column="amount",
              check_func_kwargs={"min_limit": 0, "max_limit": 100000}),
]

@dlt.view
def bronze_dq_check():
    """Apply quality checks to bronze data."""
    df = dlt.read_stream("bronze_orders")
    return dq_engine.apply_checks(df, checks)

@dlt.table
def silver_orders():
    """Valid rows only."""
    return dq_engine.get_valid(dlt.read_stream("bronze_dq_check"))

@dlt.table
def quarantine_orders():
    """Invalid rows for investigation."""
    return dq_engine.get_invalid(dlt.read_stream("bronze_dq_check"))
```

### With Metadata-Based Checks

```python
import yaml

checks_metadata = yaml.safe_load("""
- criticality: error
  check:
    function: is_not_null
    arguments:
      column: order_id
- criticality: warn
  check:
    function: is_in_range
    arguments:
      column: amount
      min_limit: 0
      max_limit: 100000
""")

@dlt.view
def bronze_dq_check():
    df = dlt.read_stream("bronze_orders")
    return dq_engine.apply_checks_by_metadata(df, checks_metadata)

@dlt.table
def silver_orders():
    return dq_engine.get_valid(dlt.read_stream("bronze_dq_check"))

@dlt.table
def quarantine_orders():
    return dq_engine.get_invalid(dlt.read_stream("bronze_dq_check"))
```

---

## Pattern 2: Report Only (No Quarantine)

Keep all rows but add quality annotations:

```python
@dlt.view
def bronze_dq_check():
    df = dlt.read_stream("bronze_orders")
    return dq_engine.apply_checks(df, checks)

@dlt.table
def silver_orders():
    """All rows pass through with _error/_warning columns for monitoring."""
    return dlt.read_stream("bronze_dq_check")
```

---

## Pattern 3: Load Checks from External Storage

Load checks from a Delta table or UC Volume instead of hardcoding:

```python
from databricks.labs.dqx.config import TableChecksStorageConfig

@dlt.view
def bronze_dq_check():
    # Load checks from Delta table at pipeline start
    checks = dq_engine.load_checks(config=TableChecksStorageConfig(
        location="catalog.schema.quality_checks",
        run_config_name="bronze_orders",
    ))
    df = dlt.read_stream("bronze_orders")
    return dq_engine.apply_checks_by_metadata(df, checks)
```

---

## Pattern 4: Generate DLT Native Expectations from Profiler

Use the profiler to generate native DLT `EXPECT` constraints:

```python
from databricks.labs.dqx.profiler.dlt_generator import DQDltGenerator

dlt_generator = DQDltGenerator(ws)

# SQL format (for SQL DLT pipelines)
sql_expectations = dlt_generator.generate_dlt_rules(profiles, language="SQL")
# CONSTRAINT user_id_is_null EXPECT (user_id is not null)

# SQL with action
sql_with_action = dlt_generator.generate_dlt_rules(profiles, language="SQL", action="drop")
# CONSTRAINT user_id_is_null EXPECT (user_id is not null) ON VIOLATION DROP ROW

# Python dict format (for Python DLT pipelines)
expectations_dict = dlt_generator.generate_dlt_rules(profiles, language="Python_Dict")
# {"user_id_is_null": "user_id is not null", ...}

# Use in DLT
@dlt.table
@dlt.expect_all(expectations_dict)
def silver_orders():
    return dlt.read_stream("bronze_orders")
```

---

## DQX vs Native DLT Expectations

| Feature | DQX in DLT | Native DLT Expectations |
|---------|-----------|------------------------|
| **Quarantine routing** | Yes (split valid/invalid) | Drop or fail only |
| **Row-level error details** | Yes (_error/_warning columns) | No |
| **Dataset-level checks** | Yes (uniqueness, aggregation) | No |
| **External rule storage** | Yes (tables, volumes, files) | Inline only |
| **Profiler auto-generation** | Yes | No |
| **User metadata** | Yes | No |
| **Criticality levels** | Yes (error/warn) | Yes (expect/expect_all/expect_or_drop/expect_or_fail) |

**Recommendation**: Use DQX when you need quarantine routing, detailed error information, or centralized rule management. Use native DLT expectations for simple pass/fail constraints.

---

## Pipeline Library Configuration

### In Pipeline Settings (UI or API)

Add `databricks-labs-dqx` as a PyPI library in your pipeline configuration.

### In Asset Bundles (databricks.yml)

```yaml
resources:
  pipelines:
    my_pipeline:
      libraries:
        - notebook:
            path: ./src/transformations/
        - pypi:
            package: databricks-labs-dqx==0.13.0
```

### Via MCP Tool

When using `create_or_update_pipeline`, include in the libraries list:

```python
libraries = [
    {"notebook": {"path": "/path/to/transformations/"}},
    {"pypi": {"package": "databricks-labs-dqx==0.13.0"}},
]
```
