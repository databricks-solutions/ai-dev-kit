# Defining Quality Rules

DQX supports two approaches for defining quality rules: **programmatic** (DQRule classes) and **declarative** (YAML/dict metadata). Both produce identical behavior at runtime.

## Core Concepts

### Criticality Levels

| Level | Behavior |
|-------|----------|
| `"error"` (default) | Failed rows go ONLY to quarantine DataFrame |
| `"warn"` | Failed rows appear in BOTH valid and quarantine DataFrames |

### Rule Types

| Class | Scope | Use Case |
|-------|-------|----------|
| `DQRowRule` | Per-row | Column-level validation (nulls, ranges, formats) |
| `DQDatasetRule` | Cross-row | Uniqueness, aggregations, foreign keys |
| `DQForEachColRule` | Multi-column | Apply same row-level check to multiple columns |

---

## Method 1: DQRule Classes (Recommended)

### Basic Rules

```python
from databricks.labs.dqx.rule import DQRowRule, DQDatasetRule, DQForEachColRule
from databricks.labs.dqx import check_funcs

checks = [
    # Null check
    DQRowRule(
        criticality="error",
        check_func=check_funcs.is_not_null,
        column="order_id",
    ),
    # Not null and not empty
    DQRowRule(
        criticality="warn",
        check_func=check_funcs.is_not_null_and_not_empty,
        column="customer_name",
    ),
    # Range check with keyword arguments
    DQRowRule(
        criticality="warn",
        check_func=check_funcs.is_in_range,
        column="amount",
        check_func_kwargs={"min_limit": 0, "max_limit": 100000},
    ),
    # List membership with positional arguments
    DQRowRule(
        criticality="error",
        check_func=check_funcs.is_in_list,
        column="status",
        check_func_args=[["pending", "active", "completed", "cancelled"]],
    ),
    # Regex validation
    DQRowRule(
        name="email_format_check",
        criticality="error",
        check_func=check_funcs.regex_match,
        column="email",
        check_func_kwargs={"regex": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"},
    ),
]
```

### Conditional Rules (with filter)

```python
DQRowRule(
    name="premium_amount_check",
    criticality="error",
    filter="customer_tier = 'premium'",  # Only apply to premium customers
    check_func=check_funcs.is_not_less_than,
    column="amount",
    check_func_kwargs={"limit": 100},
)
```

### Multi-Column Rules (DQForEachColRule)

```python
# Apply same check to multiple columns at once
checks = [
    *DQForEachColRule(
        columns=["col1", "col2", "col3"],
        criticality="error",
        check_func=check_funcs.is_not_null,
    ).get_rules(),
]
```

### Dataset-Level Rules

```python
# Uniqueness (single or composite key)
DQDatasetRule(
    criticality="error",
    check_func=check_funcs.is_unique,
    columns=["order_id"],
)

# Composite uniqueness
DQDatasetRule(
    criticality="error",
    check_func=check_funcs.is_unique,
    columns=["customer_id", "order_date"],
)

# Aggregation check
DQDatasetRule(
    criticality="error",
    check_func=check_funcs.is_aggr_not_greater_than,
    column="amount",
    check_func_kwargs={"aggr_type": "count", "group_by": ["customer_id"], "limit": 100},
)

# Foreign key validation (against a table)
DQDatasetRule(
    criticality="error",
    check_func=check_funcs.foreign_key,
    columns=["customer_id"],
    check_func_kwargs={
        "ref_columns": ["id"],
        "ref_table": "catalog.schema.customers",
    },
)
```

### User Metadata

Attach custom metadata to any rule for tracking/reporting:

```python
DQRowRule(
    name="completeness_check",
    criticality="warn",
    check_func=check_funcs.is_not_null_and_not_empty,
    column="address",
    user_metadata={
        "check_category": "completeness",
        "data_steward": "team-data@company.com",
        "sla": "99.5%",
    },
)
```

### Struct Fields and Map Elements

```python
from pyspark.sql import functions as F

# Struct field access
DQRowRule(check_func=check_funcs.is_not_null, column="address.zip_code")

# Map element access
DQRowRule(
    criticality="error",
    check_func=check_funcs.is_not_null,
    column=F.try_element_at("metadata", F.lit("source_system")),
)
```

---

## Method 2: YAML / Dictionary Metadata (Declarative)

Same checks defined declaratively:

```python
import yaml

checks = yaml.safe_load("""
- criticality: error
  check:
    function: is_not_null
    arguments:
      column: order_id

- criticality: warn
  check:
    function: is_not_null_and_not_empty
    arguments:
      column: customer_name

- criticality: warn
  check:
    function: is_in_range
    arguments:
      column: amount
      min_limit: 0
      max_limit: 100000

- criticality: error
  check:
    function: is_in_list
    arguments:
      column: status
      allowed:
        - pending
        - active
        - completed
        - cancelled

- name: email_format_check
  criticality: error
  check:
    function: regex_match
    arguments:
      column: email
      regex: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"

- criticality: error
  check:
    function: is_unique
    arguments:
      columns:
        - order_id

- criticality: error
  check:
    function: is_not_null
    for_each_column:
      - col1
      - col2
      - col3

- criticality: warn
  filter: "customer_tier = 'premium'"
  check:
    function: is_not_less_than
    arguments:
      column: amount
      limit: 100
  user_metadata:
    check_category: business_rule
    data_steward: team@company.com
""")
```

### Dictionary Structure

| Field | Required | Description |
|-------|----------|-------------|
| `criticality` | No | `"error"` (default) or `"warn"` |
| `check.function` | Yes | Check function name (from `check_funcs`) |
| `check.arguments` | Yes | Arguments dict for the check function |
| `check.for_each_column` | No | Apply same check to listed columns |
| `name` | No | Auto-generated if not provided |
| `filter` | No | Spark SQL expression to filter rows |
| `user_metadata` | No | Key-value pairs added to results |

---

## Storing and Loading Checks

### Storage Backends

```python
from databricks.labs.dqx.config import (
    FileChecksStorageConfig,            # Local or workspace file
    WorkspaceFileChecksStorageConfig,   # Workspace file (absolute path)
    TableChecksStorageConfig,           # Delta table
    VolumeFileChecksStorageConfig,      # UC Volume
    LakebaseChecksStorageConfig,        # Lakebase table
    InstallationChecksStorageConfig,    # Installation-managed
)
```

### Saving Checks

```python
from databricks.labs.dqx.config import FileChecksStorageConfig, TableChecksStorageConfig, VolumeFileChecksStorageConfig

# To local YAML file
dq_engine.save_checks(checks, config=FileChecksStorageConfig(location="checks.yml"))

# To workspace file
from databricks.labs.dqx.config import WorkspaceFileChecksStorageConfig
dq_engine.save_checks(checks, config=WorkspaceFileChecksStorageConfig(location="/Shared/App1/checks.yml"))

# To Delta table (with run config name for multi-table support)
dq_engine.save_checks(checks, config=TableChecksStorageConfig(
    location="catalog.schema.checks_table",
    run_config_name="catalog.schema.orders",
    mode="overwrite",
))

# To UC Volume
dq_engine.save_checks(checks, config=VolumeFileChecksStorageConfig(
    location="/Volumes/catalog/schema/volume_name/checks.yml"
))
```

### Loading Checks

```python
# From local file
checks = dq_engine.load_checks(config=FileChecksStorageConfig(location="checks.yml"))

# From workspace file
checks = dq_engine.load_checks(config=WorkspaceFileChecksStorageConfig(location="/Shared/App1/checks.yml"))

# From Delta table
checks = dq_engine.load_checks(config=TableChecksStorageConfig(
    location="catalog.schema.checks_table",
    run_config_name="catalog.schema.orders",
))

# From UC Volume
checks = dq_engine.load_checks(config=VolumeFileChecksStorageConfig(
    location="/Volumes/catalog/schema/volume_name/checks.yml"
))

# From installation
from databricks.labs.dqx.config import InstallationChecksStorageConfig
checks = dq_engine.load_checks(config=InstallationChecksStorageConfig(
    run_config_name="catalog.schema.orders"
))
```

### Delta Table Schema for Checks

When storing checks in a Delta table:

```
name STRING, criticality STRING, check STRUCT<function STRING, for_each_column ARRAY<STRING>, arguments MAP<STRING, STRING>>, filter STRING, run_config_name STRING, user_metadata MAP<STRING, STRING>
```

---

## CLI Commands for Rule Management

```bash
# Validate checks configuration
databricks labs dqx validate-checks
databricks labs dqx validate-checks --run-config default
```
