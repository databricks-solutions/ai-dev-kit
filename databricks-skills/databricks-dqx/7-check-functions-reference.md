# Check Functions Reference

All functions are in `databricks.labs.dqx.check_funcs`.

```python
from databricks.labs.dqx import check_funcs
```

---

## Row-Level Check Functions

Used with `DQRowRule`. Each operates on a single row and returns a PySpark Column.

### Null and Empty Checks

| Function | Description | Key Args |
|----------|-------------|----------|
| `is_not_null(column)` | Column is not null | `column` |
| `is_null(column)` | Column is null | `column` |
| `is_not_empty(column, trim_strings=False)` | Not empty string (may be null) | `column`, `trim_strings` |
| `is_empty(column, trim_strings=False)` | Is empty string (may be null) | `column`, `trim_strings` |
| `is_not_null_and_not_empty(column, trim_strings=False)` | Not null AND not empty | `column`, `trim_strings` |
| `is_null_or_empty(column, trim_strings=False)` | Null OR empty | `column`, `trim_strings` |
| `is_not_null_and_not_empty_array(column)` | Array not null and not empty | `column` |

### List Membership

| Function | Description | Key Args |
|----------|-------------|----------|
| `is_in_list(column, allowed, case_sensitive=True)` | Value in allowed list (null OK) | `column`, `allowed`, `case_sensitive` |
| `is_not_null_and_is_in_list(column, allowed, case_sensitive=True)` | Not null AND in allowed list | `column`, `allowed`, `case_sensitive` |
| `is_not_in_list(column, forbidden, case_sensitive=True)` | Value not in forbidden list | `column`, `forbidden`, `case_sensitive` |

**Example:**
```python
DQRowRule(
    criticality="error",
    check_func=check_funcs.is_in_list,
    column="status",
    check_func_args=[["active", "inactive", "pending"]],
)
```

### Comparison Checks

| Function | Description | Key Args |
|----------|-------------|----------|
| `is_equal_to(column, value, abs_tolerance, rel_tolerance)` | Equal to value | `column`, `value`, tolerances |
| `is_not_equal_to(column, value, abs_tolerance, rel_tolerance)` | Not equal to value | `column`, `value`, tolerances |
| `is_not_less_than(column, limit)` | Value >= limit | `column`, `limit` |
| `is_not_greater_than(column, limit)` | Value <= limit | `column`, `limit` |
| `is_in_range(column, min_limit, max_limit)` | min <= value <= max | `column`, `min_limit`, `max_limit` |
| `is_not_in_range(column, min_limit, max_limit)` | value < min OR value > max | `column`, `min_limit`, `max_limit` |

**Example:**
```python
DQRowRule(
    criticality="warn",
    check_func=check_funcs.is_in_range,
    column="price",
    check_func_kwargs={"min_limit": 0.01, "max_limit": 99999.99},
)
```

### Pattern Matching

| Function | Description | Key Args |
|----------|-------------|----------|
| `regex_match(column, regex, negate=False)` | Matches regex pattern | `column`, `regex`, `negate` |

**Example:**
```python
DQRowRule(
    name="valid_phone",
    criticality="error",
    check_func=check_funcs.regex_match,
    column="phone",
    check_func_kwargs={"regex": r"^\+?[1-9]\d{1,14}$"},
)
```

### Date and Time Checks

| Function | Description | Key Args |
|----------|-------------|----------|
| `is_valid_date(column, date_format)` | Valid date format | `column`, `date_format` |
| `is_valid_timestamp(column, timestamp_format)` | Valid timestamp format | `column`, `timestamp_format` |
| `is_data_fresh(column, max_age_minutes, base_timestamp)` | Data not stale | `column`, `max_age_minutes` |
| `is_older_than_n_days(column, days, curr_date, negate)` | At least N days old | `column`, `days` |
| `is_older_than_col2_for_n_days(column1, column2, days, negate)` | col1 >= col2 + N days | `column1`, `column2`, `days` |
| `is_not_in_future(column, offset, curr_timestamp)` | Not in the future | `column`, `offset` |
| `is_not_in_near_future(column, offset, curr_timestamp)` | Not in the near future | `column`, `offset` |

**Example:**
```python
DQRowRule(
    criticality="error",
    check_func=check_funcs.is_not_in_future,
    column="order_date",
)
```

### Network Checks

| Function | Description | Key Args |
|----------|-------------|----------|
| `is_valid_ipv4_address(column)` | Valid IPv4 address | `column` |
| `is_ipv4_address_in_cidr(column, cidr_block)` | IPv4 in CIDR range | `column`, `cidr_block` |
| `is_valid_ipv6_address(column)` | Valid IPv6 address | `column` |
| `is_ipv6_address_in_cidr(column, cidr_block)` | IPv6 in CIDR range | `column`, `cidr_block` |

### Custom SQL Expression

| Function | Description | Key Args |
|----------|-------------|----------|
| `sql_expression(expression, msg, name, negate, columns)` | Custom SQL expression | `expression` |

**Example:**
```python
DQRowRule(
    criticality="error",
    check_func=check_funcs.sql_expression,
    check_func_kwargs={
        "expression": "order_total = quantity * unit_price",
        "msg": "Order total does not match quantity * unit_price",
    },
)
```

---

## Dataset-Level Check Functions

Used with `DQDatasetRule`. These operate across groups of rows.

### Uniqueness

| Function | Description | Key Args |
|----------|-------------|----------|
| `is_unique(columns, nulls_distinct=True)` | Values are unique | `columns`, `nulls_distinct` |

**Example:**
```python
# Single column
DQDatasetRule(criticality="error", check_func=check_funcs.is_unique, columns=["order_id"])

# Composite key
DQDatasetRule(criticality="error", check_func=check_funcs.is_unique, columns=["customer_id", "order_date"])
```

### Foreign Key Validation

| Function | Description | Key Args |
|----------|-------------|----------|
| `foreign_key(columns, ref_columns, ref_df_name, ref_table, negate)` | FK constraint check | `columns`, `ref_columns`, `ref_df_name` or `ref_table` |

**Example:**
```python
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

### Outlier Detection

| Function | Description | Key Args |
|----------|-------------|----------|
| `has_no_outliers(column)` | MAD-based outlier detection | `column` |

### Aggregation Checks

| Function | Description | Key Args |
|----------|-------------|----------|
| `is_aggr_not_greater_than(column, limit, aggr_type, group_by, aggr_params)` | Aggregation <= limit | `column`, `limit`, `aggr_type` |
| `is_aggr_not_less_than(column, limit, aggr_type, group_by, aggr_params)` | Aggregation >= limit | `column`, `limit`, `aggr_type` |
| `is_aggr_equal(column, limit, aggr_type, group_by)` | Aggregation == limit | `column`, `limit`, `aggr_type` |
| `is_aggr_not_equal(column, limit, aggr_type, group_by)` | Aggregation != limit | `column`, `limit`, `aggr_type` |

**Supported aggregation types**: `count`, `sum`, `avg`, `min`, `max`, `count_distinct`, `stddev`, `percentile`, and any Databricks built-in aggregate function.

**Example:**
```python
# Max 100 orders per customer
DQDatasetRule(
    criticality="warn",
    check_func=check_funcs.is_aggr_not_greater_than,
    column="order_id",
    check_func_kwargs={
        "aggr_type": "count",
        "group_by": ["customer_id"],
        "limit": 100,
    },
)

# Average order value at least $10
DQDatasetRule(
    criticality="warn",
    check_func=check_funcs.is_aggr_not_less_than,
    column="amount",
    check_func_kwargs={
        "aggr_type": "avg",
        "limit": 10,
    },
)
```

### Custom SQL Query

| Function | Description | Key Args |
|----------|-------------|----------|
| `sql_query(query, merge_columns, msg, name, negate, condition_column, input_placeholder)` | Custom SQL query check | `query`, `merge_columns` |

---

## Helper Function

```python
from databricks.labs.dqx.check_funcs import make_condition

# Create a custom condition for use in custom check functions
condition = make_condition(
    condition=col("amount") > 0,
    message="Amount must be positive",
    alias="positive_amount_check",
)
```

---

## Custom Check Functions

Register custom check functions using the `@register_rule` decorator:

### Row-Level Custom Rule

```python
from databricks.labs.dqx.rule import register_rule
from pyspark.sql import Column
from pyspark.sql.functions import col, when, lit

@register_rule("row")
def is_valid_sku(column: str, prefix: str = "SKU-") -> Column:
    """Check that SKU starts with expected prefix."""
    return when(
        ~col(column).startswith(prefix),
        lit(f"{column} does not start with {prefix}")
    )
```

### Dataset-Level Custom Rule

```python
from databricks.labs.dqx.rule import register_rule
from pyspark.sql import Column
from typing import Callable, Tuple

@register_rule("dataset")
def custom_dataset_check(columns: list[str], threshold: float) -> Tuple[Column, Callable]:
    """Custom dataset-level check."""
    # Return (condition_column, merge_function)
    ...
```
