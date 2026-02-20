# Profiler and Auto-Generation

The DQX profiler analyzes datasets to generate quality rule candidates automatically. This is the recommended starting point for new datasets.

## Profiling a DataFrame

```python
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.profiler.generator import DQGenerator
from databricks.sdk import WorkspaceClient

ws = WorkspaceClient()
profiler = DQProfiler(ws)

# Profile a DataFrame
input_df = spark.table("catalog.schema.my_table")
summary_stats, profiles = profiler.profile(input_df)
```

## Profiling a Table Directly

```python
from databricks.labs.dqx.config import InputConfig

# Profile specific columns
summary_stats, profiles = profiler.profile_table(
    input_config=InputConfig(location="catalog.schema.my_table"),
    columns=["col1", "col2", "col3"],
)
```

## Profiling Multiple Tables (Wildcard Patterns)

```python
results = profiler.profile_tables_for_patterns(
    patterns=["catalog.schema.*"],
    exclude_patterns=["*_dq_output", "*_dq_quarantine"],
)

generator = DQGenerator(ws)
for table_name, (summary_stats, profiles) in results.items():
    checks = generator.generate_dq_rules(profiles)
    dq_engine.save_checks(checks, config=TableChecksStorageConfig(
        location="catalog.schema.checks",
        run_config_name=table_name,
        mode="overwrite",
    ))
```

---

## Profiler Options

```python
custom_options = {
    "sample_fraction": 0.3,       # Sample 30% of data (default)
    "sample_seed": None,          # Random seed for reproducibility
    "limit": 1000,                # Max records to analyze (default)
    "filter": None,               # SQL filter expression (e.g., "status = 'active'")
    "round": True,                # Round min/max values
    "max_in_count": 10,           # Max items for is_in_list rule
    "distinct_ratio": 0.05,       # Generate is_in if distinct ratio < 5%
    "max_null_ratio": 0.01,       # Generate is_not_null if null ratio < 1%
    "remove_outliers": True,      # Enable outlier detection
    "outlier_columns": [],        # Specific columns (empty = all numeric)
    "num_sigmas": 3,              # Standard deviations for outlier detection
    "trim_strings": True,         # Trim whitespace
    "max_empty_ratio": 0.01,      # Generate is_not_null_or_empty if empty ratio < 1%
    "llm_primary_key_detection": True,  # AI-based primary key detection (requires [llm] extra)
}

summary_stats, profiles = profiler.profile(input_df, options=custom_options)
```

---

## Generating Rules from Profiles

```python
generator = DQGenerator(ws)

# Default criticality: "error"
checks = generator.generate_dq_rules(profiles)

# Custom default criticality
checks = generator.generate_dq_rules(profiles, default_criticality="warn")
```

### Profile Types Generated

| Profile Type | Check Function | Applies To |
|-------------|----------------|------------|
| `is_not_null` | `is_not_null` | All types |
| `is_not_null_or_empty` | `is_not_null_and_not_empty` | StringType |
| `is_in` | `is_in_list` | String, Integer, Long |
| `min_max` | `is_in_range` | Numeric, Date, Timestamp |
| `is_unique` | `is_unique` | All (requires `[llm]` extra) |

---

## AI-Assisted Rule Generation

Requires the `[llm]` extra:

```bash
pip install 'databricks-labs-dqx[llm]'
```

### Generate Rules from Natural Language

```python
generator = DQGenerator(ws)
checks = generator.generate_dq_rules_ai_assisted(
    user_input="Ensure all customer emails are valid, ages are between 18 and 120, and order_id is unique",
    input_config=InputConfig(location="catalog.schema.customers"),
)
```

### AI-Assisted Primary Key Detection

```python
profiler = DQProfiler(ws)
primary_keys = profiler.detect_primary_keys_with_llm(
    input_config=InputConfig(location="catalog.schema.my_table"),
    max_retries=3,
)
```

---

## Data Contract Rule Generation

Requires the `[datacontract]` extra:

```bash
pip install 'databricks-labs-dqx[datacontract]'
# Or with AI for text-based expectations
pip install 'databricks-labs-dqx[datacontract,llm]'
```

```python
generator = DQGenerator(ws)
checks = generator.generate_rules_from_contract(
    contract_file="path/to/contract.yaml",
    contract_format="odcs",
    generate_predefined_rules=True,
    process_text_rules=True,           # Requires [llm] extra
    default_criticality="error",
)
```

---

## DLT Expectation Generation

Generate native DLT expectations from profiler results:

```python
from databricks.labs.dqx.profiler.dlt_generator import DQDltGenerator

dlt_generator = DQDltGenerator(ws)

# SQL format
sql_expectations = dlt_generator.generate_dlt_rules(profiles, language="SQL")
# Output: CONSTRAINT user_id_is_null EXPECT (user_id is not null)

# SQL with violation action
sql_with_drop = dlt_generator.generate_dlt_rules(profiles, language="SQL", action="drop")
# Output: CONSTRAINT user_id_is_null EXPECT (user_id is not null) ON VIOLATION DROP ROW

# Python decorator format
python_expectations = dlt_generator.generate_dlt_rules(profiles, language="Python")
# Output: @dlt.expect_all({"user_id_is_null": "user_id is not null", ...})

# Python dict format
dict_expectations = dlt_generator.generate_dlt_rules(profiles, language="Python_Dict")
# Output: {"user_id_is_null": "user_id is not null", ...}
```

---

## CLI Commands for Profiling

```bash
# Profile using workspace config
databricks labs dqx profile --timeout-minutes 20

# Profile specific run config
databricks labs dqx profile --run-config default --timeout-minutes 20

# Profile with patterns
databricks labs dqx profile \
    --run-config "default" \
    --patterns "catalog.schema1.*;catalog.schema2.*" \
    --exclude-patterns "*_output;*_quarantine"

# End-to-end: profile + generate + apply
databricks labs dqx e2e --timeout-minutes 20
```

---

## Complete Workflow Example

```python
from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.engine import DQEngine
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.profiler.generator import DQGenerator
from databricks.labs.dqx.config import (
    InputConfig, OutputConfig, FileChecksStorageConfig
)

ws = WorkspaceClient()
dq_engine = DQEngine(ws)

# 1. Profile the dataset
profiler = DQProfiler(ws)
input_df = spark.table("catalog.schema.orders")
summary_stats, profiles = profiler.profile(input_df)

# 2. Generate rule candidates
generator = DQGenerator(ws)
checks = generator.generate_dq_rules(profiles)

# 3. Review: print generated checks
for check in checks:
    print(check)

# 4. Save checks for future use
dq_engine.save_checks(checks, config=FileChecksStorageConfig(location="order_checks.yml"))

# 5. Apply checks
valid_df, quarantine_df = dq_engine.apply_checks_and_split(input_df, checks)

# 6. Inspect results
print(f"Valid: {valid_df.count()}, Quarantine: {quarantine_df.count()}")
quarantine_df.select("order_id", "_error").show(truncate=False)
```
