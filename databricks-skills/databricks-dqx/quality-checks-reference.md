# DQX Quality Checks Reference

## Row-Level Checks

Row-level checks validate individual rows, adding error/warning annotations per row.

### Null and Empty

| Function | Description | Arguments |
|----------|-------------|-----------|
| `is_not_null` | Not null | `column` |
| `is_null` | Is null | `column` |
| `is_not_empty` | String not empty | `column`, `trim_strings` (opt) |
| `is_empty` | String is empty | `column`, `trim_strings` (opt) |
| `is_not_null_and_not_empty` | Not null and not empty | `column`, `trim_strings` (opt) |
| `is_null_or_empty` | Null or empty | `column`, `trim_strings` (opt) |
| `is_not_null_and_not_empty_array` | Array not null/empty | `column` |

### Value

| Function | Description | Arguments |
|----------|-------------|-----------|
| `is_in_list` | In allowed list | `column`, `allowed`, `case_sensitive` (opt) |
| `is_not_in_list` | Not in forbidden list | `column`, `forbidden`, `case_sensitive` (opt) |
| `is_not_null_and_is_in_list` | Not null and in list | `column`, `allowed`, `case_sensitive` (opt) |
| `is_in_range` | Within range (inclusive) | `column`, `min_limit`, `max_limit` |
| `is_not_in_range` | Outside range | `column`, `min_limit`, `max_limit` |
| `is_equal_to` | Equals expected | `column`, `value`, `abs_tolerance` (opt), `rel_tolerance` (opt) |
| `is_not_equal_to` | Not equal to expected | `column`, `value`, `abs_tolerance` (opt), `rel_tolerance` (opt) |
| `is_not_less_than` | >= threshold | `column`, `limit` |
| `is_not_greater_than` | <= threshold | `column`, `limit` |

### Format

| Function | Description | Arguments |
|----------|-------------|-----------|
| `is_valid_date` | Valid date string | `column`, `date_format` (opt) |
| `is_valid_timestamp` | Valid timestamp | `column`, `timestamp_format` (opt) |
| `is_valid_json` | Valid JSON | `column` |
| `has_json_keys` | JSON has required keys | `column`, `keys`, `require_all` (opt) |
| `has_valid_json_schema` | JSON matches schema | `column`, `schema` (DDL string or StructType) |
| `is_valid_ipv4_address` | Valid IPv4 | `column` |
| `is_ipv4_address_in_cidr` | IPv4 in CIDR | `column`, `cidr_block` |
| `is_valid_ipv6_address` | Valid IPv6 | `column` |
| `is_ipv6_address_in_cidr` | IPv6 in CIDR | `column`, `cidr_block` |
| `regex_match` | Matches regex | `column`, `regex`, `negate` (opt) |

### Temporal

| Function | Description | Arguments |
|----------|-------------|-----------|
| `is_not_in_future` | Not in future | `column`, `offset` (opt), `curr_timestamp` (opt) |
| `is_not_in_near_future` | Not in near future | `column`, `offset` (opt), `curr_timestamp` (opt) |
| `is_older_than_n_days` | Older than N days | `column`, `days`, `curr_date` (opt), `negate` (opt) |
| `is_older_than_col2_for_n_days` | col1 older than col2 by N days | `column1`, `column2`, `days`, `negate` (opt) |
| `is_data_fresh` | Data freshness | `column`, `max_age_minutes`, `base_timestamp` (opt) |

### Geographic

| Function | Description |
|----------|-------------|
| `is_latitude` / `is_longitude` | Valid lat (-90..90) / lon (-180..180) |
| `is_geometry` / `is_geography` | Valid geometry/geography type |
| `is_point` / `is_linestring` / `is_polygon` | Specific geometry types |
| `is_multipoint` / `is_multilinestring` / `is_multipolygon` | Multi-geometry types |
| `is_geometrycollection` | Geometry collection |
| `is_ogc_valid` | OGC-valid geometry |
| `is_non_empty_geometry` | Non-empty geometry |
| `is_not_null_island` | Not NULL island (POINT(0 0)) |
| `has_dimension` | Expected dimensionality |
| `has_x_coordinate_between` / `has_y_coordinate_between` | Coordinate in range |
| `is_area_not_less_than` / `is_area_not_greater_than` | Area constraints |
| `is_area_equal_to` / `is_area_not_equal_to` | Area equality |
| `is_num_points_not_less_than` / `is_num_points_not_greater_than` | Point count bounds |
| `is_num_points_equal_to` / `is_num_points_not_equal_to` | Point count equality |

### Security

| Function | Description | Arguments |
|----------|-------------|-----------|
| `does_not_contain_pii` | No PII detected (requires `[pii]` extra) | `column`, `threshold` (opt), `language` (opt), `entities` (opt) |

### Custom SQL

| Function | Description | Arguments |
|----------|-------------|-----------|
| `sql_expression` | Custom SQL boolean expression | `expression`, `msg` (opt), `name` (opt), `negate` (opt), `columns` (opt) |

```python
DQRowRule(criticality="error", check_func=check_funcs.sql_expression,
    check_func_kwargs={"expression": "amount > 0 AND currency IN ('USD', 'EUR')"})
```

## Dataset-Level Checks

Validate the entire dataset — aggregates, uniqueness, schema, cross-dataset comparisons.

| Function | Description | Key Arguments |
|----------|-------------|---------------|
| `is_unique` | Unique column(s) | `columns`, `nulls_distinct` (opt, default True) |
| `is_aggr_not_greater_than` | Aggregate <= limit | `column`, `aggr_type`, `limit`, `group_by` (opt), `aggr_params` (opt) |
| `is_aggr_not_less_than` | Aggregate >= limit | `column`, `aggr_type`, `limit`, `group_by` (opt), `aggr_params` (opt) |
| `is_aggr_equal` | Aggregate equals value | `column`, `aggr_type`, `limit`, `group_by` (opt), `abs_tolerance` (opt) |
| `is_aggr_not_equal` | Aggregate != value | `column`, `aggr_type`, `limit`, `group_by` (opt), `abs_tolerance` (opt) |
| `foreign_key` | Values exist in reference | `columns`, `ref_columns`, `ref_df_name` or `ref_table`, `negate` (opt) |
| `sql_query` | Custom SQL returns no violations | `query`, `merge_columns` (opt), `condition_column` (opt) |
| `compare_datasets` | Compare with reference | `columns`, `ref_columns`, `ref_df_name` or `ref_table` |
| `is_data_fresh_per_time_window` | Freshness in time window | `column`, `window_minutes`, `min_records_per_window`, `lookback_windows` (opt) |
| `has_valid_schema` | Schema matches expected | `expected_schema` or `ref_df_name`/`ref_table` |
| `has_no_outliers` | No statistical outliers (MAD) | `column` |

Supported `aggr_type` values: `count`, `count_distinct`, `approx_count_distinct`, `sum`, `avg`, `min`, `max`, `stddev`, `stddev_pop`, `variance`, `var_pop`, `median`, `mode`, `skewness`, `kurtosis`, `percentile`, `approx_percentile`

Use `aggr_params` for percentile/accuracy settings (e.g., `{"accuracy": 100}` for `percentile`).

```python
from databricks.labs.dqx.rule import DQDatasetRule
from databricks.labs.dqx import check_funcs

# Composite uniqueness
DQDatasetRule(criticality="error", check_func=check_funcs.is_unique,
    columns=["order_id", "line_item_id"])

# Aggregate with group by
DQDatasetRule(criticality="error", check_func=check_funcs.is_aggr_not_greater_than,
    column="amount", check_func_kwargs={"aggr_type": "count", "group_by": ["customer_id"], "limit": 100})

# Foreign key
DQDatasetRule(criticality="error", check_func=check_funcs.foreign_key,
    columns=["product_id"], check_func_kwargs={"ref_df_name": "products_ref", "ref_columns": ["id"]})
```

## Multi-Column Shorthand

```python
from databricks.labs.dqx.rule import DQForEachColRule
from databricks.labs.dqx import check_funcs

checks = DQForEachColRule(
    columns=["col1", "col2", "col3"], criticality="error", check_func=check_funcs.is_not_null
).get_rules()
```

## YAML/JSON Check Format

```yaml
- criticality: error          # "error" or "warn" (default: "error")
  check:
    function: is_not_null      # Built-in or custom function name
    arguments:
      column: customer_id
  name: custom_name            # Optional: override auto-generated name
  filter: "status = 'active'"  # Optional: SQL filter for conditional checks
  user_metadata:               # Optional: custom metadata
    check_category: completeness

# Multi-column shorthand
- criticality: error
  check:
    function: is_not_null
    for_each_column: [col1, col2, col3]
```

Note: In metadata format (YAML/JSON/dict), use `__decimal__: "0.01"` for decimal values.

## Complex Types

```python
# Struct field (dot notation)
DQRowRule(check_func=check_funcs.is_not_null, column="address.zip_code")
# Map key
DQRowRule(check_func=check_funcs.is_not_null, column=F.try_element_at("metadata", F.lit("key1")))
# Array element
DQRowRule(check_func=check_funcs.is_not_null, column=F.try_element_at("tags", F.lit(1)))
```

## Custom Check Functions

```python
from databricks.labs.dqx.rule import register_rule, make_condition
import pyspark.sql.functions as F

@register_rule("row")
def not_ends_with_suffix(column: str, suffix: str):
    return make_condition(
        F.col(column).endswith(suffix),
        f"{column} should not end with '{suffix}'",
        f"{column}_ends_with_{suffix}"
    )
```
