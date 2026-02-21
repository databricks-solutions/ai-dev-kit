# Applying Quality Checks

## DQEngine Setup

```python
from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.engine import DQEngine

ws = WorkspaceClient()
dq_engine = DQEngine(ws)

# With Databricks Connect
from databricks.connect import DatabricksSession
spark = DatabricksSession.builder.getOrCreate()
dq_engine = DQEngine(ws, spark)

# With custom result column names
from databricks.labs.dqx.config import ExtraParams
extra_params = ExtraParams(
    result_column_names={"errors": "dq_errors", "warnings": "dq_warnings"}
)
dq_engine = DQEngine(ws, extra_params=extra_params)
```

---

## Applying Checks (DQRule Objects)

### Option 1: Single DataFrame with Result Columns

Returns the original DataFrame with `_error` and `_warning` columns appended:

```python
checked_df = dq_engine.apply_checks(input_df, checks)
# checked_df has all original columns + _error + _warning
```

### Option 2: Split into Valid + Quarantine

```python
valid_df, quarantine_df = dq_engine.apply_checks_and_split(input_df, checks)
# valid_df: rows with no errors (may have warnings)
# quarantine_df: rows with errors
```

### Option 3: End-to-End (Read, Check, Write)

```python
from databricks.labs.dqx.config import InputConfig, OutputConfig

dq_engine.apply_checks_and_save_in_table(
    checks=checks,
    input_config=InputConfig(location="catalog.schema.input_table"),
    output_config=OutputConfig(location="catalog.schema.valid_table", mode="overwrite"),
    quarantine_config=OutputConfig(location="catalog.schema.quarantine_table", mode="overwrite"),
)
```

---

## Applying Checks (Metadata / Dict)

Same three options, using `_by_metadata` variants:

```python
# Option 1: Single DataFrame
checked_df = dq_engine.apply_checks_by_metadata(input_df, checks_metadata)

# Option 2: Split
valid_df, quarantine_df = dq_engine.apply_checks_by_metadata_and_split(input_df, checks_metadata)

# Option 3: End-to-end
dq_engine.apply_checks_by_metadata_and_save_in_table(
    checks=checks_metadata,
    input_config=InputConfig(location="catalog.schema.input_table"),
    output_config=OutputConfig(location="catalog.schema.valid_table", mode="overwrite"),
    quarantine_config=OutputConfig(location="catalog.schema.quarantine_table", mode="overwrite"),
)
```

---

## Filtering Valid / Invalid Rows

After `apply_checks()` returns a single DataFrame:

```python
checked_df = dq_engine.apply_checks(input_df, checks)

valid_df = dq_engine.get_valid(checked_df)       # No errors
invalid_df = dq_engine.get_invalid(checked_df)    # Has errors
```

---

## Saving Results

```python
dq_engine.save_results_in_table(
    output_df=valid_df,
    quarantine_df=quarantine_df,
    output_config=OutputConfig(
        location="catalog.schema.valid_table",
        mode="append",
        options={"mergeSchema": "true"},
    ),
    quarantine_config=OutputConfig(
        location="catalog.schema.quarantine_table",
        mode="append",
    ),
)
```

---

## Multi-Table Processing

### Explicit RunConfig List

```python
from databricks.labs.dqx.config import RunConfig, InputConfig, OutputConfig

dq_engine.apply_checks_and_save_in_tables(run_configs=[
    RunConfig(
        name="orders",
        input_config=InputConfig(location="catalog.schema.orders"),
        output_config=OutputConfig(location="catalog.schema.orders_valid", mode="overwrite"),
        quarantine_config=OutputConfig(location="catalog.schema.orders_quarantine", mode="overwrite"),
        checks_location="catalog.schema.checks_table",
    ),
    RunConfig(
        name="customers",
        input_config=InputConfig(location="catalog.schema.customers"),
        output_config=OutputConfig(location="catalog.schema.customers_valid", mode="overwrite"),
        quarantine_config=OutputConfig(location="catalog.schema.customers_quarantine", mode="overwrite"),
        checks_location="catalog.schema.checks_table",
    ),
])
```

### Wildcard Patterns

Process all tables matching a pattern:

```python
dq_engine.apply_checks_and_save_in_tables_for_patterns(
    patterns=["catalog.schema.*"],
    checks_location="catalog.schema.checks_table",
    exclude_patterns=["*_dq_output", "*_dq_quarantine", "*_checks"],
    output_table_suffix="_dq_output",
    quarantine_table_suffix="_dq_quarantine",
)
```

---

## InputConfig and OutputConfig Reference

### InputConfig

```python
InputConfig(
    location="catalog.schema.table",  # Table or file path
    format="delta",                    # delta, parquet, csv, json
    is_streaming=False,                # True for streaming reads
    schema=None,                       # Optional schema override
    options={},                        # Reader options
)
```

### OutputConfig

```python
OutputConfig(
    location="catalog.schema.output",  # Table or file path
    format="delta",                     # delta, parquet, csv, json
    mode="overwrite",                   # overwrite, append
    options={},                         # Writer options (e.g., mergeSchema)
    trigger=None,                       # Streaming trigger (e.g., {"availableNow": True})
)
```

---

## CLI Commands

```bash
# Apply checks using workspace config
databricks labs dqx apply-checks --timeout-minutes 20

# Apply checks for specific run config
databricks labs dqx apply-checks --run-config default --timeout-minutes 20

# Apply checks with pattern matching
databricks labs dqx apply-checks \
    --run-config "default" \
    --patterns "catalog.schema1.*;catalog.schema2.*" \
    --exclude-patterns "*_dq_output;*_dq_quarantine" \
    --output-table-suffix "_dq_output" \
    --quarantine-table-suffix "_dq_quarantine"

# End-to-end: profile + generate + apply
databricks labs dqx e2e --timeout-minutes 20
databricks labs dqx e2e --run-config default --timeout-minutes 20
```
