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

| Tool | Actions | Purpose |
|------|---------|---------|
| `manage_mlflow_experiment` | create, get, list, search, set_tag, delete | Experiment CRUD and tagging |
| `manage_mlflow_run` | get, search, get_metric_history, list_artifacts | Run inspection and search |

## Quick Start

### 1. Find Experiments

```python
# List recent experiments
manage_mlflow_experiment(action="list", max_results=10)

# Search by name pattern
manage_mlflow_experiment(action="search", filter_string="name LIKE '%churn%'")

# Search by tag
manage_mlflow_experiment(action="search", filter_string="tags.team = 'ml-eng'")
```

### 2. Search Runs

```python
# Find the best runs by accuracy
manage_mlflow_run(
    action="search",
    experiment_ids=["123456789"],
    filter_string="metrics.accuracy > 0.9 AND status = 'FINISHED'",
    order_by=["metrics.accuracy DESC"],
    max_results=5
)
```

### 3. Inspect a Run

```python
# Get full run details
manage_mlflow_run(action="get", run_id="abc123def456")

# View training loss curve
manage_mlflow_run(action="get_metric_history", run_id="abc123def456", metric_key="loss")

# Browse logged artifacts
manage_mlflow_run(action="list_artifacts", run_id="abc123def456")
```

### 4. Create an Experiment

```python
# GenAI agent experiment (shows as "GenAI apps & agents" in UI)
manage_mlflow_experiment(
    action="create",
    name="/Users/user@example.com/my-agent",
    experiment_kind="genai",
    tags={"team": "ml-eng"}
)

# Traditional ML experiment (shows as "Machine learning" in UI)
manage_mlflow_experiment(
    action="create",
    name="/Users/user@example.com/churn-model",
    experiment_kind="ml",
    tags={"project": "churn-prediction"}
)
```

## Common Patterns

### Compare Runs Across Experiments

```python
# Find all finished runs across multiple experiments
manage_mlflow_run(
    action="search",
    experiment_ids=["111", "222", "333"],
    filter_string="status = 'FINISHED'",
    order_by=["metrics.val_f1_score DESC"],
    max_results=10
)
```

### Filter by Model Type

```python
manage_mlflow_run(
    action="search",
    experiment_ids=["123"],
    filter_string="params.model_type = 'xgboost' AND metrics.accuracy > 0.85"
)
```

### Check Training Convergence

```python
# Get loss over training steps
manage_mlflow_run(action="get_metric_history", run_id="abc123", metric_key="loss")

# Compare with validation loss
manage_mlflow_run(action="get_metric_history", run_id="abc123", metric_key="val_loss")
```

### Explore Run Artifacts

```python
# List root artifacts
manage_mlflow_run(action="list_artifacts", run_id="abc123")

# Drill into a subdirectory
manage_mlflow_run(action="list_artifacts", run_id="abc123", path="model")
```

### Experiment Lifecycle Management

```python
# Create for a new project
manage_mlflow_experiment(action="create", name="/Users/me/project-v2", tags={"version": "2"})

# Soft-delete when done (can be restored)
manage_mlflow_experiment(action="delete", experiment_id="123")

# View deleted experiments
manage_mlflow_experiment(action="list", view_type="DELETED_ONLY")
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Experiments & Runs | [experiments-and-runs.md](experiments-and-runs.md) | Experiment paths, run statuses, filter syntax, metric logging |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Experiment not found** | Use full path including `/Users/` prefix. Paths are case-sensitive |
| **No runs returned** | Check experiment_ids are correct. Use `manage_mlflow_experiment(action="list")` to find IDs |
| **Filter syntax error** | Use MLflow filter syntax: `metrics.X > 0.9`, `params.X = 'val'`, `status = 'FINISHED'` |
| **Metric history empty** | Metric may have been logged once (no steps). Use `manage_mlflow_run(action="get")` to see latest values |
| **Cannot delete experiment** | Only the experiment creator or workspace admin can delete |

## Related Skills

- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - Evaluate GenAI agents with MLflow scorers
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy models from MLflow to serving endpoints
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - System tables for MLflow lineage and audit
