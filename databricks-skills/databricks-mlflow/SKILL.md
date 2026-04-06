---
name: databricks-mlflow
description: "Manage MLflow experiments, runs, traces, artifacts, and model registry on Databricks. Use when listing experiments, searching runs or traces, inspecting model versions, managing aliases, logging assessments, or browsing artifacts."
---

# Databricks MLflow

Manage MLflow experiments, runs, artifacts, and the Unity Catalog model registry in Databricks workspaces.

## Overview

MLflow on Databricks provides experiment tracking, model versioning, and artifact management. Experiments organize related runs, each run logs metrics, parameters, and artifacts during training or evaluation. The Unity Catalog model registry stores registered models and versions with aliases for deployment workflows.

## When to Use This Skill

Use this skill when:
- Listing or searching experiments in a workspace
- Inspecting experiment details or lifecycle stage
- Creating experiments for new projects
- Searching runs by metrics, parameters, or status
- Viewing a run's metrics, parameters, and tags
- Tracking how a metric changed over training steps
- Browsing artifacts (models, plots, configs) logged to a run
- Listing registered models in Unity Catalog
- Inspecting model versions and their source runs
- Managing model aliases (champion, challenger, etc.)
- Searching and inspecting GenAI traces (LLM app observability)
- Logging feedback or expectations on traces for evaluation
- Tagging traces for dataset building
- Cleaning up old or unused experiments

## MCP Tools

### Experiment Management

| Tool | Purpose |
|------|---------|
| `get_mlflow_experiment` | Get experiment by ID or name |
| `list_mlflow_experiments` | List experiments (active, deleted, or all) |
| `search_mlflow_experiments` | Search with filters (name, tags) |
| `create_mlflow_experiment` | Create experiment with optional kind ("genai" or "ml") |
| `set_mlflow_experiment_tag` | Set a tag on an experiment (metadata, kind, etc.) |
| `delete_mlflow_experiment` | Soft-delete an experiment (can be restored) |

### Run Operations

| Tool | Purpose |
|------|---------|
| `get_mlflow_run` | Get run details (metrics, params, tags, status) |
| `search_mlflow_runs` | Search runs across experiments by metrics/params/status |
| `get_mlflow_metric_history` | Get metric values over training steps |
| `list_mlflow_run_artifacts` | List files logged to a run (models, plots, etc.) |

### Traces & Assessments

| Tool | Purpose |
|------|---------|
| `search_mlflow_traces` | Search traces across experiments by status/time |
| `get_mlflow_trace` | Full trace detail with spans, tags, metadata, assessments |
| `set_mlflow_trace_tag` | Tag a trace for filtering or labeling |
| `delete_mlflow_trace_tag` | Remove a trace tag |
| `log_mlflow_assessment` | Log feedback or expectation on a trace |
| `delete_mlflow_assessment` | Remove an assessment |

### Model Registry (Unity Catalog)

| Tool | Purpose |
|------|---------|
| `get_mlflow_model` | Get registered model by full name (catalog.schema.model) |
| `list_mlflow_models` | List models, optionally filtered by catalog/schema |
| `search_mlflow_models` | Search legacy workspace registry by name/tags |
| `get_mlflow_model_version` | Get a specific model version |
| `list_mlflow_model_versions` | List all versions of a model |
| `get_mlflow_model_version_by_alias` | Resolve alias to version (e.g. "champion") |
| `set_mlflow_model_alias` | Point alias to a version |
| `delete_mlflow_model_alias` | Remove an alias |

## Quick Start

### 1. Find Experiments

```python
# List recent experiments
list_mlflow_experiments(max_results=10)

# Search by name pattern
search_mlflow_experiments(filter_string="name LIKE '%churn%'")

# Search by tag
search_mlflow_experiments(filter_string="tags.team = 'ml-eng'")
```

### 2. Search Runs

```python
# Find the best runs by accuracy
search_mlflow_runs(
    experiment_ids=["123456789"],
    filter_string="metrics.accuracy > 0.9 AND status = 'FINISHED'",
    order_by=["metrics.accuracy DESC"],
    max_results=5
)
```

### 3. Inspect a Run

```python
# Get full run details
get_mlflow_run(run_id="abc123def456")
# Returns: run_id, status, metrics dict, params dict, tags dict

# View training loss curve
get_mlflow_metric_history(run_id="abc123def456", metric_key="loss")
# Returns: history with value, timestamp, step for each data point

# Browse logged artifacts
list_mlflow_run_artifacts(run_id="abc123def456")
# Returns: model/, metrics.json, plots/, etc.
```

### 4. Create an Experiment

```python
# GenAI agent experiment (shows as "GenAI apps & agents" in UI)
create_mlflow_experiment(
    name="/Users/user@example.com/my-agent",
    experiment_kind="genai",
    tags={"team": "ml-eng"}
)

# Traditional ML experiment (shows as "Machine learning" in UI)
create_mlflow_experiment(
    name="/Users/user@example.com/churn-model",
    experiment_kind="ml",
    tags={"project": "churn-prediction"}
)
```

## Common Patterns

### Compare Runs Across Experiments

```python
# Find all finished runs across multiple experiments
search_mlflow_runs(
    experiment_ids=["111", "222", "333"],
    filter_string="status = 'FINISHED'",
    order_by=["metrics.val_f1_score DESC"],
    max_results=10
)
```

### Filter by Model Type

```python
search_mlflow_runs(
    experiment_ids=["123"],
    filter_string="params.model_type = 'xgboost' AND metrics.accuracy > 0.85"
)
```

### Check Training Convergence

```python
# Get loss over training steps
history = get_mlflow_metric_history(run_id="abc123", metric_key="loss")
# Look at history values to verify loss is decreasing

# Compare with validation loss
val_history = get_mlflow_metric_history(run_id="abc123", metric_key="val_loss")
```

### Explore Run Artifacts

```python
# List root artifacts
list_mlflow_run_artifacts(run_id="abc123")

# Drill into a subdirectory
list_mlflow_run_artifacts(run_id="abc123", path="model")
```

### Experiment Lifecycle Management

```python
# Create for a new project
create_mlflow_experiment("/Users/me/project-v2", tags={"version": "2"})

# Soft-delete when done (can be restored)
delete_mlflow_experiment(experiment_id="123")

# View deleted experiments
list_mlflow_experiments(view_type="DELETED_ONLY")
```

### Browse Models in Unity Catalog

```python
# List models in a specific catalog/schema
list_mlflow_models(catalog_name="main", schema_name="ml")

# Get model details with aliases
get_mlflow_model("main.ml.churn_model")
```

### Inspect Model Versions

```python
# List all versions
list_mlflow_model_versions("main.ml.churn_model")

# Get specific version details (source run, status)
get_mlflow_model_version("main.ml.churn_model", version=3)

# Resolve which version "champion" points to
get_mlflow_model_version_by_alias("main.ml.churn_model", "champion")
```

### Promote a Model Version

```python
# Set the "champion" alias to version 5
set_mlflow_model_alias("main.ml.churn_model", alias="champion", version_num=5)

# Remove old alias
delete_mlflow_model_alias("main.ml.churn_model", alias="challenger")
```

### Search and Inspect Traces

```python
# Find traces in a GenAI experiment
search_mlflow_traces(experiment_ids=["123"], filter_string="status = 'OK'", max_results=10)

# Get full trace detail (spans, metadata, assessments)
get_mlflow_trace("tr-abc123...")
```

### Tag Traces for Evaluation

```python
# Mark traces for inclusion in eval datasets
set_mlflow_trace_tag("tr-abc123", "eval_dataset", "v1")
set_mlflow_trace_tag("tr-abc123", "quality", "good")
```

### Log Feedback and Expectations

```python
# Human feedback on trace quality
log_mlflow_assessment("tr-abc123", "quality", "good",
    rationale="Response was accurate and complete")

# Ground-truth expectation for evaluation
log_mlflow_assessment("tr-abc123", "expected_response",
    "The answer should mention product availability",
    assessment_type="expectation")
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Experiments & Runs | [experiments-and-runs.md](experiments-and-runs.md) | Experiment paths, run statuses, filter syntax, metric logging |
| Traces & Assessments | [traces-and-assessments.md](traces-and-assessments.md) | Trace structure, assessment types, token usage metadata |
| Model Registry | [model-registry.md](model-registry.md) | UC models, versions, aliases, legacy vs UC registry |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Experiment not found** | Use full path including `/Users/` prefix. Paths are case-sensitive |
| **No runs returned** | Check experiment_ids are correct. Use `list_mlflow_experiments` to find IDs |
| **Filter syntax error** | Use MLflow filter syntax: `metrics.X > 0.9`, `params.X = 'val'`, `status = 'FINISHED'` |
| **Metric history empty** | Metric may have been logged once (no steps). Use `get_mlflow_run` to see latest values |
| **Cannot delete experiment** | Only the experiment creator or workspace admin can delete |
| **Model not found (UC)** | Use three-level name: `catalog.schema.model`. Check catalog/schema access |
| **Legacy vs UC models** | Use `list_mlflow_models` for UC, `search_mlflow_models` for legacy workspace registry |
| **Alias not found** | Alias may not be set yet. Use `list_mlflow_model_versions` to see all versions |

## Related Skills

- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - Evaluate GenAI agents with MLflow scorers
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy models from MLflow to serving endpoints
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - System tables for MLflow lineage and audit
