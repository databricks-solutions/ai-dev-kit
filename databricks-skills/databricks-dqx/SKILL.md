---
name: databricks-dqx
description: "Data quality framework for PySpark pipelines using DQX (Databricks Labs). Use when building data quality checks, profiling data, generating quality rules (including AI-assisted), applying validation checks, quarantining bad data, creating quality dashboards, or integrating quality checks into Lakeflow Pipelines (DLT), streaming, or batch workflows. Triggers: 'data quality', 'DQX', 'profiling', 'quality checks', 'data validation', 'quarantine', 'quality rules', 'data contract'."
---

# Databricks DQX — Data Quality Framework

DQX is a Databricks Labs data quality framework for Apache Spark. Define, monitor, and address data quality issues in Python-based data pipelines — batch, streaming, and Lakeflow Pipelines (DLT).

| Capability | Description |
|-----------|-------------|
| **Profiling** | Auto-profile DataFrames/tables and generate rule candidates |
| **AI-Assisted Rules** | Generate checks from natural language using LLMs |
| **Row & Dataset Rules** | Row-level (per-row) and dataset-level (aggregates, uniqueness) checks |
| **Batch & Streaming** | Spark batch, Structured Streaming, and Lakeflow Pipelines |
| **Quarantine** | Split valid/invalid data or annotate rows with error/warning columns |
| **Quality Dashboard** | Track metrics over time with a built-in Lakeview dashboard |
| **Data Contracts** | Generate rules from Open Data Contract Standard (ODCS) YAML |
| **Storage Backends** | YAML, JSON, Delta tables, Workspace files, Volumes, Lakebase |

## Installation

```bash
pip install databricks-labs-dqx                  # Core
pip install 'databricks-labs-dqx[llm]'           # AI-assisted rule generation
pip install 'databricks-labs-dqx[pii]'           # PII detection
pip install 'databricks-labs-dqx[datacontract]'  # Data contract (ODCS) support
databricks labs install dqx                      # Workspace tool (CLI workflows)
```

## Quick Start — Profile → Generate → Apply

```python
from databricks.sdk import WorkspaceClient
from databricks.labs.dqx.profiler.profiler import DQProfiler
from databricks.labs.dqx.profiler.generator import DQGenerator
from databricks.labs.dqx.engine import DQEngine

ws = WorkspaceClient()
input_df = spark.read.table("catalog.schema.my_table")

# Step 1: Profile
profiler = DQProfiler(ws)
summary_stats, profiles = profiler.profile(input_df)

# Step 2: Generate rules from profiles
generator = DQGenerator(ws)
checks = generator.generate_dq_rules(profiles)

# Step 3: Apply checks — split valid and invalid rows
dq_engine = DQEngine(ws)
valid_df, invalid_df = dq_engine.apply_checks_by_metadata_and_split(input_df, checks)

# Write results
valid_df.write.mode("overwrite").saveAsTable("catalog.schema.silver")
invalid_df.write.mode("overwrite").saveAsTable("catalog.schema.quarantine")
```

## Common Patterns

### AI-Assisted Rule Generation

```python
generator = DQGenerator(workspace_client=ws, spark=spark)
checks = generator.generate_dq_rules_ai_assisted(
    user_input="Username must not start with 's' if age < 18. All users need valid email. Age 0-120.",
    input_config=InputConfig(location="catalog.schema.customers")
)
```

Combine profiler + AI rules: `all_checks = profiler_checks + ai_checks`. See [profiling.md](profiling.md) for full options including custom models, summary stats context, and custom check functions.

### Lakeflow Pipelines (DLT) Integration

```python
import dlt
from databricks.labs.dqx.engine import DQEngine

dq_engine = DQEngine(WorkspaceClient())
checks = dq_engine.load_checks(config=...)

@dlt.view
def bronze_dq_check():
    return dq_engine.apply_checks_by_metadata(dlt.read_stream("bronze"), checks)

@dlt.table
def silver():
    return dq_engine.get_valid(dlt.read_stream("bronze_dq_check"))

@dlt.table
def quarantine():
    return dq_engine.get_invalid(dlt.read_stream("bronze_dq_check"))
```

### Structured Streaming (foreachBatch)

```python
# checks defined as DQX classes (DQRowRule, DQDatasetRule)
def validate_and_write(batch_df, batch_id):
    valid_df, invalid_df = dq_engine.apply_checks_and_split(batch_df, checks)
    valid_df.write.format("delta").mode("append").saveAsTable("catalog.schema.output")
    invalid_df.write.format("delta").mode("append").saveAsTable("catalog.schema.quarantine")

(spark.readStream.format("delta").table("catalog.schema.bronze")
    .writeStream.foreachBatch(validate_and_write).start())
```

### End-to-End with Config

```python
dq_engine.apply_checks_by_metadata_and_save_in_table(
    checks=checks,
    input_config=InputConfig(location="catalog.schema.bronze", format="delta"),
    output_config=OutputConfig(location="catalog.schema.silver", format="delta", mode="append"),
    quarantine_config=OutputConfig(location="catalog.schema.quarantine", format="delta", mode="append"),
    metrics_config=OutputConfig(location="catalog.schema.dq_metrics", format="delta", mode="append")
)
```

### Multi-Table Checks

```python
# By explicit table list
dq_engine.apply_checks_and_save_in_tables(run_configs=[RunConfig(...), RunConfig(...)])

# By pattern matching
dq_engine.apply_checks_and_save_in_tables_for_patterns(
    patterns=["catalog.schema.*"], checks_location="catalog.schema.checks_table"
)
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Quality Checks | [quality-checks-reference.md](quality-checks-reference.md) | Built-in row/dataset check functions, YAML format, custom checks |
| Profiling | [profiling.md](profiling.md) | Profiler options, AI-assisted generation, data contracts, primary key detection |
| Storage & Config | [storage-and-config.md](storage-and-config.md) | Storage backends, config.yml, metrics, dashboard, CLI reference, best practices |

## Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: databricks.labs.dqx` | `pip install databricks-labs-dqx` or add to job libraries |
| AI generation fails | `pip install 'databricks-labs-dqx[llm]'` and enable serverless clusters |
| PII detection not available | `pip install 'databricks-labs-dqx[pii]'` |
| Data contract rules missing | `pip install 'databricks-labs-dqx[datacontract]'` |
| Checks validation errors | `dq_engine.validate_checks(checks)` or `databricks labs dqx validate-checks` |
| Custom column name conflicts | `ExtraParams(result_column_names={"errors": "custom_errors", "warnings": "custom_warnings"})` |
| Streaming metrics missing | Use `get_streaming_metrics_listener` or end-to-end methods |
| Dashboard shows no tables | Tables must have `_errors`/`_warnings` columns (or custom names) |
| Profiler too slow | Adjust `sample_fraction` (default 0.3), `limit` (default 1000), or use `filter` |

## Related Skills

- **[databricks-spark-declarative-pipelines](../databricks-spark-declarative-pipelines/SKILL.md)** — Lakeflow Pipelines with DQX quality checks
- **[databricks-spark-structured-streaming](../databricks-spark-structured-streaming/SKILL.md)** — Streaming with foreachBatch quality validation
- **[databricks-aibi-dashboards](../databricks-aibi-dashboards/SKILL.md)** — Custom dashboards for quality metrics
- **[databricks-jobs](../databricks-jobs/SKILL.md)** — Schedule DQX workflows as Databricks Jobs
- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** — Deploy DQX pipelines via Asset Bundles
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** — Manage catalogs, schemas, and tables for quality checks

## Resources

- [DQX Documentation](https://databrickslabs.github.io/dqx/)
- [DQX GitHub Repository](https://github.com/databrickslabs/dqx)
- [DQX Best Practices](https://databrickslabs.github.io/dqx/docs/guide/best_practices/)
