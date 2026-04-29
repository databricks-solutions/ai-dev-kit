# DQX Profiling & Rule Generation

## Profile a DataFrame

```python
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.profiler.generator import DQGenerator

ws = WorkspaceClient()
profiler = DQProfiler(ws)
summary_stats, profiles = profiler.profile(spark.read.table("catalog.schema.my_table"))
```

## Profile a Table Directly

```python
from databricks.labs.dqx.config import InputConfig

summary_stats, profiles = profiler.profile_table(
    input_config=InputConfig(location="catalog.schema.my_table"),
    columns=["col1", "col2", "col3"]  # optional
)
```

## Profile Multiple Tables

```python
results = profiler.profile_tables_for_patterns(patterns=["main.data.*"])
results = profiler.profile_tables_for_patterns(
    patterns=["main.*"], exclude_patterns=["*_dq_output", "*_quarantine"]
)
```

## Profiling Options

| Option | Default | Description |
|--------|---------|-------------|
| `sample_fraction` | 0.3 | Fraction of data to sample |
| `sample_seed` | None | Seed for reproducible sampling |
| `limit` | 1000 | Max records to analyze |
| `remove_outliers` | True | Remove outliers before min/max |
| `num_sigmas` | 3 | Std devs for outlier detection |
| `max_null_ratio` | 0.05 | Null ratio threshold for `is_not_null` |
| `trim_strings` | True | Trim whitespace before analysis |
| `max_empty_ratio` | 0.02 | Empty ratio threshold for `is_not_null_or_empty` |
| `distinct_ratio` | 0.01 | Distinct value ratio for `is_in` rule |
| `max_in_count` | 20 | Max items in `is_in_list` rules |
| `round` | True | Round min/max values |
| `filter` | None | SQL filter before profiling |
| `llm_primary_key_detection` | True | Use LLM to detect primary keys |

## Summary Statistics Fields

| Field | Meaning |
|-------|---------|
| `count` | Rows profiled (after sampling/limit) |
| `mean` / `stddev` | Average and standard deviation |
| `min` / `max` | Smallest/largest non-null value |
| `25` / `50` / `75` | Approximate percentiles |
| `count_non_null` / `count_null` | Non-null and null counts |

## Profiler → Check Function Mapping

| Profile Type | Check Function | Column Types | Trigger |
|-------------|---------------|-------------|---------|
| `is_not_null` | `is_not_null` | All | Null ratio <= `max_null_ratio` |
| `is_not_null_or_empty` | `is_not_null_and_not_empty` | String | Null+empty <= thresholds |
| `is_in` | `is_in_list` | String, Int, Long | Distinct ratio <= threshold, count <= max |
| `min_max` | `is_in_range` | Numeric, Date, Timestamp | With outlier removal and rounding |
| `is_unique` | `is_unique` | All | Requires LLM primary key detection |

## Generate Rules from Profiles

```python
generator = DQGenerator(ws)
checks = generator.generate_dq_rules(profiles)
```

## AI-Assisted Rule Generation

Generate quality rules from natural language. Requires `pip install 'databricks-labs-dqx[llm]'`.

```python
generator = DQGenerator(workspace_client=ws, spark=spark)

# Basic
checks = generator.generate_dq_rules_ai_assisted(
    user_input="Username must not start with 's' if age < 18. Valid email required. Age 0-120."
)

# With table schema context
checks = generator.generate_dq_rules_ai_assisted(
    user_input=user_input, input_config=InputConfig(location="catalog.schema.customers")
)

# With profiler summary stats
checks = generator.generate_dq_rules_ai_assisted(
    user_input="Validate sales data for anomalies", summary_stats=summary_stats
)
```

### With Custom Check Functions

```python
@register_rule("row")
def not_ends_with_suffix(column: str, suffix: str):
    return make_condition(F.col(column).endswith(suffix), ...)

generator = DQGenerator(ws, spark=spark, custom_check_functions={"ends_with_suffix": not_ends_with_suffix})
checks = generator.generate_dq_rules_ai_assisted(user_input=user_input)
```

### Custom Model

```python
from databricks.labs.dqx.config import LLMModelConfig

generator = DQGenerator(ws, spark=spark,
    llm_model_config=LLMModelConfig(model_name="databricks/databricks-claude-sonnet-4-5"))
```

### Combine Profiler + AI Rules

```python
all_checks = generator.generate_dq_rules(profiles) + generator.generate_dq_rules_ai_assisted(
    user_input="GDPR compliance: no PII in public fields",
    input_config=InputConfig(location="catalog.schema.customers")
)
```

## Primary Key Detection

```python
result = profiler.detect_primary_keys_with_llm(
    input_config=InputConfig(location="catalog.schema.users")
)
# result: {"primary_key_columns": [...], "confidence": ..., "reasoning": ...}
```

## Data Contract Rules (ODCS)

Requires `pip install 'databricks-labs-dqx[datacontract]'`.

```python
rules = generator.generate_rules_from_contract(
    contract_file="/Workspace/Shared/contracts/customers.yaml"
)
```

### Constraint Mapping

| ODCS Constraint | DQX Rule | Example |
|----------------|----------|---------|
| `required: true` | `is_not_null` | Mandatory fields |
| `unique: true` | `is_unique` | Primary keys |
| `pattern` | `regex_match` | Email validation |
| `minimum` / `maximum` | `is_in_range` or `sql_expression` | Amount limits |
| `minLength` / `maxLength` | `sql_expression` | Length constraints |

### Explicit DQX Rules in Contract

```yaml
quality:
  - type: custom
    engine: dqx
    implementation:
      name: rule_name
      criticality: error
      check:
        function: check_function_name
        arguments:
          column: field_name
```

### Text-Based Rules (LLM-Processed)

```yaml
quality:
  - type: text
    description: |
      Email addresses must be valid and from approved corporate domains only.
```

Requires `pip install 'databricks-labs-dqx[datacontract,llm]'`.

## Lakeflow DLT Expectations Generation

Generate DLT expectations from profiled data:

```python
from databricks.labs.dqx.profiler.dlt_generator import DQDltGenerator

dlt_generator = DQDltGenerator(ws)

sql_rules = dlt_generator.generate_dlt_rules(profiles, language="SQL")
# CONSTRAINT user_id_is_null EXPECT (user_id is not null)

sql_drop = dlt_generator.generate_dlt_rules(profiles, language="SQL", action="drop")
# CONSTRAINT user_id_is_null EXPECT (user_id is not null) ON VIOLATION DROP ROW

python_rules = dlt_generator.generate_dlt_rules(profiles, language="Python")
# @dlt.expect_all({"user_id_is_null": "user_id is not null"})

dict_rules = dlt_generator.generate_dlt_rules(profiles, language="Python_Dict")
```
