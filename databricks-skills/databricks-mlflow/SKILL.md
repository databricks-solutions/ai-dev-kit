---
name: databricks-mlflow
description: "Manage MLflow experiments, runs, traces, artifacts, and model registry on Databricks. Use when listing experiments, searching runs or traces, inspecting model versions, managing aliases, logging assessments, or browsing artifacts."
---

# Databricks MLflow

Manage MLflow experiments, runs, traces, artifacts, and the Unity Catalog model registry in Databricks workspaces.

## Overview

MLflow on Databricks provides experiment tracking, model versioning, trace observability, and artifact management. Experiments organize related runs and traces. The Unity Catalog model registry stores registered models with version aliases for deployment workflows.

## When to Use This Skill

Use this skill when:
- Listing or searching experiments in a workspace
- Creating experiments for new projects (GenAI or ML)
- Searching runs by metrics, parameters, or status
- Tracking how a metric changed over training steps
- Browsing artifacts (models, plots, configs) logged to a run
- Listing registered models in Unity Catalog
- Inspecting model versions and managing aliases
- Searching and inspecting GenAI traces (LLM app observability)
- Logging feedback or expectations on traces for evaluation

## MCP Tools

| Tool | Actions | Purpose |
|------|---------|---------|
| `manage_mlflow_experiment` | create, get, list, search, set_tag, delete | Experiment CRUD and tagging |
| `manage_mlflow_run` | get, search, get_metric_history, list_artifacts | Run inspection and search |
| `manage_mlflow_model` | get, list, search, get_version, list_versions, get_by_alias, set_alias, delete_alias | UC model registry and versions |
| `manage_mlflow_trace` | search, get, set_tag, delete_tag, log_assessment, delete_assessment | Trace observability and assessments |

## Quick Start

### 1. Find Experiments

```python
manage_mlflow_experiment(action="list", max_results=10)

manage_mlflow_experiment(action="search", filter_string="name LIKE '%churn%'")
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
```

## Common Patterns

### Browse Models and Versions

```python
manage_mlflow_model(action="list", catalog_name="main", schema_name="ml")

manage_mlflow_model(action="get_version", full_name="main.ml.churn_model", version=3)

manage_mlflow_model(action="get_by_alias", full_name="main.ml.churn_model", alias="champion")
```

### Promote a Model Version

```python
manage_mlflow_model(action="set_alias", full_name="main.ml.churn_model", alias="champion", version=5)
```

### Search and Inspect Traces

```python
manage_mlflow_trace(action="search", experiment_ids=["123"], filter_string="status = 'OK'", max_results=10)

manage_mlflow_trace(action="get", trace_id="tr-abc123...")
```

### Tag Traces for Evaluation

```python
manage_mlflow_trace(action="set_tag", trace_id="tr-abc123", key="eval_dataset", value="v1")
```

### Log Feedback and Expectations

```python
# Human feedback on trace quality
manage_mlflow_trace(
    action="log_assessment",
    trace_id="tr-abc123",
    assessment_name="quality",
    assessment_value="good",
    rationale="Response was accurate and complete"
)

# Ground-truth expectation for evaluation
manage_mlflow_trace(
    action="log_assessment",
    trace_id="tr-abc123",
    assessment_name="expected_response",
    assessment_value="The answer should mention product availability",
    assessment_type="expectation"
)
```

## Reference Files

| Topic | File | Description |
|-------|------|-------------|
| Experiments & Runs | [experiments-and-runs.md](experiments-and-runs.md) | Experiment paths, run statuses, filter syntax, metric logging |
| Model Registry | [model-registry.md](model-registry.md) | UC models, versions, aliases, legacy vs UC registry |
| Traces & Assessments | [traces-and-assessments.md](traces-and-assessments.md) | Trace structure, assessment types, token usage metadata |

## Common Issues

| Issue | Solution |
|-------|----------|
| **Experiment not found** | Use full path including `/Users/` prefix. Paths are case-sensitive |
| **No runs returned** | Check experiment_ids. Use `manage_mlflow_experiment(action="list")` to find IDs |
| **Filter syntax error** | Use MLflow syntax: `metrics.X > 0.9`, `params.X = 'val'`, `status = 'FINISHED'` |
| **Model not found (UC)** | Use three-level name: `catalog.schema.model`. Check catalog/schema access |
| **Alias not found** | Use `manage_mlflow_model(action="list_versions")` to see all versions |

## Related Skills

- **[databricks-mlflow-evaluation](../databricks-mlflow-evaluation/SKILL.md)** - Evaluate GenAI agents with MLflow scorers
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - Deploy models from MLflow to serving endpoints
- **[databricks-unity-catalog](../databricks-unity-catalog/SKILL.md)** - System tables for MLflow lineage and audit
