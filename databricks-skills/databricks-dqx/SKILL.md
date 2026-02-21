---
name: databricks-dqx
description: "Databricks Labs DQX (Data Quality Extensions) framework for defining and enforcing data quality rules on Delta tables using PySpark. Use when building data quality checks, profiling datasets, generating quality rules, quarantining invalid data, integrating quality checks into Lakeflow Declarative Pipelines (DLT), or when the user mentions DQX, data quality, quality checks, data validation, profiling, quarantine, quality rules, or data quality monitoring."
---

# Databricks Labs DQX (Data Quality Extensions)

DQX is a Python framework for defining, applying, and monitoring data quality rules on PySpark DataFrames and Delta tables. It supports both batch and streaming, integrates with Lakeflow Declarative Pipelines (DLT), and provides profiling-based auto-generation of quality rules.

**Repository**: https://github.com/databrickslabs/dqx
**Docs**: https://databrickslabs.github.io/dqx/
**Package**: `databricks-labs-dqx` (PyPI)
**Status**: Databricks Labs project (no formal SLA)

---

## Critical Rules (always follow)

- **MUST** install DQX before use: `%pip install databricks-labs-dqx`
- **MUST** use Unity Catalog 3-layer namespace for table locations
- **MUST** use `WorkspaceClient()` to initialize `DQEngine`
- **PREFER** DQRule classes (programmatic) over metadata dicts for type safety
- **PREFER** profiler-generated rules as a starting point, then customize

## Quick Start

### Minimal Example: Apply Quality Checks to a DataFrame

```python
%pip install databricks-labs-dqx
dbutils.library.restartPython()

from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.engine import DQEngine
from databricks.labs.dqx.rule import DQRowRule, DQDatasetRule
from databricks.labs.dqx import check_funcs

ws = WorkspaceClient()
dq_engine = DQEngine(ws)

# Define checks
checks = [
    DQRowRule(criticality="error", check_func=check_funcs.is_not_null, column="order_id"),
    DQRowRule(criticality="error", check_func=check_funcs.is_not_null_and_not_empty, column="customer_name"),
    DQRowRule(criticality="warn", check_func=check_funcs.is_in_range, column="amount",
              check_func_kwargs={"min_limit": 0, "max_limit": 100000}),
    DQDatasetRule(criticality="error", check_func=check_funcs.is_unique, columns=["order_id"]),
]

# Apply checks - split valid and invalid rows
input_df = spark.table("catalog.schema.orders")
valid_df, quarantine_df = dq_engine.apply_checks_and_split(input_df, checks)

# Save results
valid_df.write.mode("overwrite").saveAsTable("catalog.schema.orders_valid")
quarantine_df.write.mode("overwrite").saveAsTable("catalog.schema.orders_quarantine")
```

### Minimal Example: Auto-Generate Rules with Profiler

```python
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.profiler.generator import DQGenerator

profiler = DQProfiler(ws)
summary_stats, profiles = profiler.profile(input_df)

generator = DQGenerator(ws)
checks = generator.generate_dq_rules(profiles)
# Review and customize generated checks, then apply
```

---

## Quick Reference

| Concept | Details |
|---------|---------|
| **Package** | `pip install databricks-labs-dqx` |
| **Engine** | `DQEngine(WorkspaceClient())` |
| **Rule Types** | `DQRowRule` (per-row), `DQDatasetRule` (across rows), `DQForEachColRule` (multi-column) |
| **Criticality** | `"error"` = quarantine only, `"warn"` = both valid + quarantine |
| **Result Columns** | `_error` and `_warning` appended to output (customizable) |
| **Apply Methods** | `apply_checks()`, `apply_checks_and_split()`, `apply_checks_and_save_in_table()` |
| **Metadata Methods** | `apply_checks_by_metadata()`, `apply_checks_by_metadata_and_split()` |
| **Profiler** | `DQProfiler.profile(df)` + `DQGenerator.generate_dq_rules(profiles)` |
| **Storage** | YAML files, Delta tables, UC Volumes, Lakebase, workspace files |
| **Streaming** | All apply methods work with streaming DataFrames |
| **DLT/Lakeflow** | Apply checks in `@dlt.view`, split to silver + quarantine tables |
| **Extras** | `[llm]` for AI rules, `[pii]` for PII detection, `[datacontract]` for ODCS |

---

## Detailed Guides

**Installation and setup**: See [1-installation-setup.md](1-installation-setup.md) for all installation methods (pip, CLI workspace install, DABs, extras). (Keywords: install, setup, pip, CLI, workspace, extras, llm, pii, datacontract)

**Defining quality rules**: See [2-defining-quality-rules.md](2-defining-quality-rules.md) for rule definition patterns using DQRule classes, YAML metadata, and storage backends. (Keywords: rules, checks, DQRowRule, DQDatasetRule, YAML, metadata, storage, save, load)

**Applying checks**: See [3-applying-checks.md](3-applying-checks.md) for applying checks to DataFrames, splitting valid/invalid rows, and saving results. (Keywords: apply, split, quarantine, valid, invalid, save, DQEngine, batch)

**Profiler and auto-generation**: See [4-profiler-auto-generation.md](4-profiler-auto-generation.md) for profiling datasets and auto-generating quality rules. (Keywords: profile, profiler, auto-generate, DQProfiler, DQGenerator, AI-assisted, data contract)

**Lakeflow/DLT integration**: See [5-lakeflow-integration.md](5-lakeflow-integration.md) for integrating DQX with Lakeflow Declarative Pipelines (DLT). (Keywords: DLT, Lakeflow, pipeline, streaming table, expectations, quarantine)

**Streaming and metrics**: See [6-streaming-metrics.md](6-streaming-metrics.md) for streaming support, quality metrics, and monitoring. (Keywords: streaming, metrics, monitoring, observer, listener, foreachBatch)

**Check functions reference**: See [7-check-functions-reference.md](7-check-functions-reference.md) for the complete list of built-in check functions. (Keywords: is_not_null, is_in_range, is_unique, regex, SQL expression, aggregation, foreign key)

---

## Workflow

1. Determine the task type:

   **Installing DQX?** -> Read [1-installation-setup.md](1-installation-setup.md)
   **Defining quality rules?** -> Read [2-defining-quality-rules.md](2-defining-quality-rules.md)
   **Applying checks to data?** -> Read [3-applying-checks.md](3-applying-checks.md)
   **Profiling data / auto-generating rules?** -> Read [4-profiler-auto-generation.md](4-profiler-auto-generation.md)
   **Integrating with Lakeflow/DLT?** -> Read [5-lakeflow-integration.md](5-lakeflow-integration.md)
   **Streaming or metrics monitoring?** -> Read [6-streaming-metrics.md](6-streaming-metrics.md)
   **Looking up a specific check function?** -> Read [7-check-functions-reference.md](7-check-functions-reference.md)

2. Follow the instructions in the relevant guide

3. Use the profiler as a starting point, then customize rules for your domain

---

## Common Patterns

### Pattern 1: Profile -> Generate -> Review -> Apply

The recommended workflow for new datasets:

```python
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.profiler.generator import DQGenerator
from databricks.labs.dqx.engine import DQEngine
from databricks.sdk import WorkspaceClient

ws = WorkspaceClient()
dq_engine = DQEngine(ws)

# Step 1: Profile
profiler = DQProfiler(ws)
summary_stats, profiles = profiler.profile(spark.table("catalog.schema.my_table"))

# Step 2: Generate rule candidates
generator = DQGenerator(ws)
checks = generator.generate_dq_rules(profiles)

# Step 3: Review and save
from databricks.labs.dqx.config import FileChecksStorageConfig
dq_engine.save_checks(checks, config=FileChecksStorageConfig(location="checks.yml"))

# Step 4: Apply
input_df = spark.table("catalog.schema.my_table")
valid_df, quarantine_df = dq_engine.apply_checks_and_split(input_df, checks)
```

### Pattern 2: End-to-End (Read, Check, Write)

```python
from databricks.labs.dqx.config import InputConfig, OutputConfig

dq_engine.apply_checks_and_save_in_table(
    checks=checks,
    input_config=InputConfig(location="catalog.schema.input_table"),
    output_config=OutputConfig(location="catalog.schema.valid_table", mode="overwrite"),
    quarantine_config=OutputConfig(location="catalog.schema.quarantine_table", mode="overwrite"),
)
```

### Pattern 3: DLT/Lakeflow Pipeline Integration

```python
import dlt
from databricks.labs.dqx.engine import DQEngine
from databricks.sdk import WorkspaceClient

dq_engine = DQEngine(WorkspaceClient())

@dlt.view
def bronze_checked():
    df = dlt.read_stream("bronze_raw")
    return dq_engine.apply_checks(df, checks)

@dlt.table
def silver_valid():
    return dq_engine.get_valid(dlt.read_stream("bronze_checked"))

@dlt.table
def quarantine():
    return dq_engine.get_invalid(dlt.read_stream("bronze_checked"))
```

### Pattern 4: Multi-Table Quality Checks with Wildcards

```python
dq_engine.apply_checks_and_save_in_tables_for_patterns(
    patterns=["catalog.schema.*"],
    checks_location="catalog.schema.checks_table",
    exclude_patterns=["*_dq_output", "*_dq_quarantine"],
    output_table_suffix="_dq_output",
    quarantine_table_suffix="_dq_quarantine",
)
```

---

## MCP Tools

Use Databricks MCP tools (from `databricks-ai-dev-kit` plugin) alongside DQX:

| Tool | Use With DQX |
|------|-------------|
| `execute_sql` | Test queries on input/output tables, verify quarantine data |
| `execute_databricks_command` | Run DQX Python code on clusters |
| `manage_uc_objects` | Create catalogs/schemas/volumes for checks storage |
| `get_table_details` | Inspect table schemas before defining rules |

---

## Official Documentation

- **[DQX Documentation](https://databrickslabs.github.io/dqx/)** - Main docs
- **[DQX GitHub](https://github.com/databrickslabs/dqx)** - Source code and issues
- **[Tutorial](https://databrickslabs.github.io/dqx/tutorial/)** - Getting started tutorial
- **[User Guide](https://databrickslabs.github.io/dqx/user_guide/)** - Detailed user guide
- **[API Reference](https://databrickslabs.github.io/dqx/reference/)** - Full API reference

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **`ModuleNotFoundError: databricks.labs.dqx`** | Run `%pip install databricks-labs-dqx` then `dbutils.library.restartPython()` |
| **`WorkspaceClient` auth fails** | Ensure Databricks auth is configured (profile, env vars, or notebook context) |
| **Profiler slow on large tables** | Use `sample_fraction` (default 0.3) and `limit` (default 1000) options |
| **Rules not catching issues** | Check criticality: `"error"` quarantines, `"warn"` keeps in both outputs |
| **Custom result column names** | Use `ExtraParams(result_column_names={"errors": "my_errors", "warnings": "my_warnings"})` |
| **Streaming checkpoint errors** | Provide `checkpointLocation` in `OutputConfig.options` |
| **DLT integration fails** | Ensure `databricks-labs-dqx` is installed as a pipeline library |

---

## Related Skills

If using the `databricks-ai-dev-kit` plugin, these skills complement DQX:
- **spark-declarative-pipelines** - for building Lakeflow pipelines that use DQX checks
- **databricks-unity-catalog** - for catalog/schema/volume management
- **databricks-jobs** - for scheduling DQX quality check jobs
- **databricks-aibi-dashboards** - for building quality monitoring dashboards
- **synthetic-data-generation** - for generating test data with known quality issues
