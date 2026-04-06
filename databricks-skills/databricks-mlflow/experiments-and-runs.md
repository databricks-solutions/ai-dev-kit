# MLflow Experiments and Runs Reference

## Experiment Paths

MLflow experiments use workspace-style paths:

| Pattern | Example | Description |
|---------|---------|-------------|
| User experiments | `/Users/user@example.com/my-experiment` | Personal experiments |
| Shared experiments | `/Shared/team/experiment-name` | Team-shared experiments |
| Notebook experiments | Auto-created when running a notebook | Tied to notebook path |

Notebook experiments are created automatically with `mlflow.experimentType: NOTEBOOK` tag. Standalone experiments use `MLFLOW_EXPERIMENT`.

## Experiment Kind (UI Type)

The `mlflow.experimentKind` tag controls how the experiment appears in the Databricks UI:

| `experiment_kind` param | `mlflow.experimentKind` value | UI Display |
|------------------------|------------------------------|------------|
| `"genai"` | `genai_development` | **GenAI apps & agents** (traces, LLM evaluation) |
| `"ml"` | `custom_model_development` | **Machine learning** (training runs, metrics) |
| None (default) | not set | Defaults to GenAI view |

Set this when creating an experiment:
```python
create_mlflow_experiment("/Users/me/my-agent", experiment_kind="genai")
create_mlflow_experiment("/Users/me/churn-model", experiment_kind="ml")
```

Or change it later:
```python
set_mlflow_experiment_tag("123", "mlflow.experimentKind", "custom_model_development")
```

## Experiment Lifecycle

| Stage | Description |
|-------|-------------|
| `active` | Normal state, visible in UI |
| `deleted` | Soft-deleted, can be restored from UI or API |

Deleting an experiment soft-deletes all its runs too. Restoring the experiment restores the runs.

## Run Statuses

| Status | Description |
|--------|-------------|
| `RUNNING` | Run is in progress |
| `SCHEDULED` | Run is scheduled but not started |
| `FINISHED` | Run completed successfully |
| `FAILED` | Run failed with an error |
| `KILLED` | Run was manually stopped |

## Filter Syntax

MLflow uses a SQL-like filter syntax for searching experiments and runs.

### Experiment Filters

```
name = '/Users/me/experiment'
name LIKE '%churn%'
tags.team = 'ml-eng'
tags.`mlflow.experimentType` = 'MLFLOW_EXPERIMENT'
```

### Run Filters

```
# By metrics
metrics.accuracy > 0.9
metrics.loss < 0.1
metrics.val_f1_score >= 0.85

# By parameters
params.model_type = 'xgboost'
params.learning_rate = '0.01'

# By status
status = 'FINISHED'
status != 'FAILED'

# By tags
tags.mlflow.runName LIKE '%best%'
tags.environment = 'production'

# Combined
metrics.accuracy > 0.9 AND params.model_type = 'xgboost' AND status = 'FINISHED'
```

### Order By

Sort results by metrics, params, or built-in fields:

```
["metrics.accuracy DESC"]
["start_time DESC"]
["metrics.val_f1_score DESC", "start_time DESC"]
```

## Metric Logging

Metrics can be logged at different granularities:

| Method | Description | History |
|--------|-------------|---------|
| Single value | `log_metric("accuracy", 0.95)` | One data point |
| Per step | `log_metric("loss", 0.5, step=0)` | Full training curve |
| Per epoch | `log_metric("val_loss", 0.3, step=10)` | Validation curve |

Use `get_mlflow_metric_history` to retrieve the full step-by-step history. Use `get_mlflow_run` to get only the latest value for each metric.

## Parameters vs Metrics vs Tags

| Field | Type | Use For | Searchable |
|-------|------|---------|------------|
| **Parameters** | String key-value | Hyperparameters, config values | `params.key = 'value'` |
| **Metrics** | Float key-value with history | Training/evaluation scores | `metrics.key > 0.9` |
| **Tags** | String key-value | Metadata, labels, notes | `tags.key = 'value'` |

Parameters and tags are logged once (or overwritten). Metrics can have a history of values over steps.

## Artifacts

Artifacts are files logged during a run. Common types:

| Artifact | Description |
|----------|-------------|
| `model/` | Serialized model (MLflow model format) |
| `*.png` | Plots (confusion matrix, ROC curve, etc.) |
| `*.json` | Metric summaries, configs |
| `*.html` | HTML reports (e.g., estimator visualizations) |
| `notebooks/` | Auto-generated trial notebooks (AutoML) |

Use `list_mlflow_run_artifacts` to browse, optionally drilling into subdirectories with the `path` parameter.

## Common Tag Prefixes

| Prefix | Source | Examples |
|--------|--------|----------|
| `mlflow.*` | MLflow system | `mlflow.runName`, `mlflow.source.type`, `mlflow.log-model.history` |
| `_databricks_automl.*` | AutoML | `_databricks_automl.problem_type`, `_databricks_automl.state` |
| Custom | User-defined | `team`, `environment`, `model_version` |
