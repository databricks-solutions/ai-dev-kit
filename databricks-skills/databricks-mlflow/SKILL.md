---
name: databricks-mlflow
description: "Manage MLflow experiments, runs, artifacts, and model registry on Databricks. Use when listing experiments, searching runs, inspecting model versions, managing aliases, or browsing artifacts."
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
- Cleaning up old or unused experiments

## MCP Tools

| Tool | Actions | Purpose |
|------|---------|---------|
| `manage_mlflow_experiment` | create, get, list, search, set_tag, delete | Experiment CRUD and tagging |
| `manage_mlflow_run` | get, search, get_metric_history, list_artifacts | Run inspection and search |
| `manage_mlflow_model` | get, list, search, get_version, list_versions, get_by_alias, set_alias, delete_alias | UC model registry and versions |

## Quick Start

### 1. Find Experiments

```python
manage_mlflow_experiment(action="list", max_results=10)

manage_mlflow_experiment(action="search", filter_string="name LIKE '%churn%'")

manage_mlflow_experiment(action="search", filter_string="tags.team = 'ml-eng'")
```

### 2. Search Runs

```python
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
manage_mlflow_run(action="get", run_id="abc123def456")

manage_mlflow_run(action="get_metric_history", run_id="abc123def456", metric_key="loss")

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
manage_mlflow_run(
    action="search",
    experiment_ids=["111", "222", "333"],
    filter_string="status = 'FINISHED'",
    order_by=["metrics.val_f1_score DESC"],
    max_results=10
)
```

### Check Training Convergence

```python
manage_mlflow_run(action="get_metric_history", run_id="abc123", metric_key="loss")
manage_mlflow_run(action="get_metric_history", run_id="abc123", metric_key="val_loss")
```

### Browse Models in Unity Catalog

```python
manage_mlflow_model(action="list", catalog_name="main", schema_name="ml")

manage_mlflow_model(action="get", full_name="main.ml.churn_model")
```

### Inspect Model Versions

```python
manage_mlflow_model(action="list_versions", full_name="main.ml.churn_model")

manage_mlflow_model(action="get_version", full_name="main.ml.churn_model", version=3)

manage_mlflow_model(action="get_by_alias", full_name="main.ml.churn_model", alias="champion")
```

### Promote a Model Version

```python
manage_mlflow_model(action="set_alias", full_name="main.ml.churn_model", alias="champion", version=5)

manage_mlflow_model(action="delete_alias", full_name="main.ml.churn_model", alias="challenger")
```

### Experiment Lifecycle

```python
manage_mlflow_experiment(action="create", name="/Users/me/project-v2", tags={"version": "2"})

manage_mlflow_experiment(action="delete", experiment_id="123")

manage_mlflow_experiment(action="list", view_type="DELETED_ONLY")
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Experiments & Runs | [experiments-and-runs.md](experiments-and-runs.md) | Experiment paths, run statuses, filter syntax, metric logging |
| Model Registry | [model-registry.md](model-registry.md) | UC models, versions, aliases, legacy vs UC registry |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Experiment not found** | Use full path including `/Users/` prefix. Paths are case-sensitive |
| **No runs returned** | Check experiment_ids are correct. Use `manage_mlflow_experiment(action="list")` to find IDs |
| **Filter syntax error** | Use MLflow filter syntax: `metrics.X > 0.9`, `params.X = 'val'`, `status = 'FINISHED'` |
| **Metric history empty** | Metric may have been logged once (no steps). Use `manage_mlflow_run(action="get")` for latest values |
| **Cannot delete experiment** | Only the experiment creator or workspace admin can delete |
| **Model not found (UC)** | Use three-level name: `catalog.schema.model`. Check catalog/schema access |
| **Legacy vs UC models** | Use `action="list"` for UC, `action="search"` for legacy workspace registry |
| **Alias not found** | Alias may not be set. Use `manage_mlflow_model(action="list_versions")` to see all versions |

## Related Skills

- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - Evaluate GenAI agents with MLflow scorers
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy models from MLflow to serving endpoints
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - System tables for MLflow lineage and audit
