# Streaming Support and Quality Metrics

## Streaming DataFrames

All DQX `apply_checks` methods work with both batch and streaming DataFrames. No code changes needed for the check logic itself.

### End-to-End Streaming

```python
from databricks.labs.dqx.config import InputConfig, OutputConfig

dq_engine.apply_checks_and_save_in_table(
    checks=checks,
    input_config=InputConfig(
        location="catalog.schema.input_stream",
        is_streaming=True,
    ),
    output_config=OutputConfig(
        location="catalog.schema.valid_stream",
        mode="append",
        trigger={"availableNow": True},
        options={
            "checkpointLocation": "/Volumes/catalog/schema/vol/checkpoint_output",
            "mergeSchema": "true",
        },
    ),
    quarantine_config=OutputConfig(
        location="catalog.schema.quarantine_stream",
        mode="append",
        trigger={"availableNow": True},
        options={
            "checkpointLocation": "/Volumes/catalog/schema/vol/checkpoint_quarantine",
        },
    ),
)
```

### foreachBatch Pattern

For fine-grained control over micro-batch processing:

```python
from unittest.mock import MagicMock
from databricks.labs.dqx.engine import DQEngine
from databricks.sdk import WorkspaceClient

def validate_and_write_micro_batch(batch_df, batch_id):
    mock_ws = MagicMock(spec=WorkspaceClient)
    dq_engine = DQEngine(mock_ws)

    valid_df, quarantine_df = dq_engine.apply_checks_and_split(batch_df, checks)

    valid_df.write.format("delta").mode("append").saveAsTable("catalog.schema.valid")
    quarantine_df.write.format("delta").mode("append").saveAsTable("catalog.schema.quarantine")

input_stream = spark.readStream.table("catalog.schema.source")
input_stream.writeStream.foreachBatch(validate_and_write_micro_batch).start()
```

---

## Quality Metrics

DQX captures quality metrics lazily (triggered after count/display/write actions).

### Batch Metrics via Observation

```python
from databricks.labs.dqx.metrics_observer import DQMetricsObserver
from databricks.labs.dqx.config import OutputConfig

observer = DQMetricsObserver()
dq_engine = DQEngine(ws, observer=observer)

# Apply checks (metrics collected lazily)
checked_df = dq_engine.apply_checks(input_df, checks)

# Trigger an action (count, write, display) to collect metrics
checked_df.write.mode("overwrite").saveAsTable("catalog.schema.output")

# Save metrics to a Delta table
dq_engine.save_summary_metrics(
    observed_metrics=observer.get,
    metrics_config=OutputConfig(location="catalog.schema.quality_metrics"),
)
```

### Streaming Metrics via Listener

```python
listener = dq_engine.get_streaming_metrics_listener(
    metrics_config=OutputConfig(location="catalog.schema.quality_metrics")
)
spark.streams.addListener(listener)
```

### Default Metrics Captured

| Metric | Description |
|--------|-------------|
| `input_count` | Total rows in input |
| `error_count` | Rows with errors |
| `warning_count` | Rows with warnings |
| `valid_count` | Rows passing all error checks |

### Custom Quality Metrics

You can extend the default metrics with custom aggregations by adding user metadata to your checks and querying the metrics table.

---

## Monitoring Dashboard

DQX workspace installation includes a quality dashboard:

```bash
# Open the dashboard
databricks labs dqx open-dashboards
```

You can also build custom AI/BI dashboards on the metrics Delta table using the `databricks-aibi-dashboards` skill.

---

## Workflow Orchestration

### CLI Workflows

```bash
# List available workflows
databricks labs dqx workflows

# View workflow logs
databricks labs dqx logs --workflow quality-checker
```

### Scheduling with Databricks Jobs

Use the `databricks-jobs` skill to schedule periodic quality checks:

```python
# Example: Schedule DQX quality checks as a job task
# See databricks-jobs skill for full details
```
