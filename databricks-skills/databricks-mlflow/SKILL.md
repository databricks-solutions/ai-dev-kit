---
name: databricks-mlflow
description: "Manage MLflow experiments, runs, and artifacts on Databricks. Use when listing experiments, searching runs by metrics or parameters, inspecting run details, creating experiments, or browsing run artifacts."
---

# Databricks MLflow

Manage MLflow experiments, runs, metrics, and artifacts in Databricks workspaces.

## Overview

MLflow on Databricks provides experiment tracking, model versioning, and artifact management. Experiments organize related runs, each run logs metrics, parameters, and artifacts during training or evaluation. This skill covers the core operations for browsing, searching, and managing these resources.

## When to Use This Skill

Use this skill when:
- Listing or searching experiments in a workspace
- Inspecting experiment details or lifecycle stage
- Creating experiments for new projects
- Searching runs by metrics, parameters, or status
- Viewing a run's metrics, parameters, and tags
- Tracking how a metric changed over training steps
- Browsing artifacts (models, plots, configs) logged to a run
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

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Experiments & Runs | [experiments-and-runs.md](experiments-and-runs.md) | Experiment paths, run statuses, filter syntax, metric logging |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Experiment not found** | Use full path including `/Users/` prefix. Paths are case-sensitive |
| **No runs returned** | Check experiment_ids are correct. Use `list_mlflow_experiments` to find IDs |
| **Filter syntax error** | Use MLflow filter syntax: `metrics.X > 0.9`, `params.X = 'val'`, `status = 'FINISHED'` |
| **Metric history empty** | Metric may have been logged once (no steps). Use `get_mlflow_run` to see latest values |
| **Cannot delete experiment** | Only the experiment creator or workspace admin can delete |

## Related Skills

- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - Evaluate GenAI agents with MLflow scorers
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy models from MLflow to serving endpoints
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - System tables for MLflow lineage and audit
