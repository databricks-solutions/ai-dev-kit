# MLflow Model Registry Reference

## Unity Catalog vs Legacy Registry

Databricks has two model registries:

| Feature | Unity Catalog (recommended) | Legacy Workspace |
|---------|---------------------------|-----------------|
| Naming | `catalog.schema.model` (3-level) | Flat name (e.g. "my-model") |
| Versioning | Numeric versions (1, 2, 3...) | Numeric versions |
| Promotion | **Aliases** (champion, challenger) | **Stages** (Staging, Production) |
| Governance | UC permissions (GRANT/REVOKE) | Workspace ACLs |
| MCP tools | `get/list_mlflow_model*` | `search_mlflow_models` |

Use Unity Catalog for new models. The legacy registry is available for backward compatibility.

## Model Aliases (UC)

Aliases are mutable references to specific model versions. They replace the legacy stage-based promotion.

| Alias Convention | Purpose |
|-----------------|---------|
| `champion` | Current production model |
| `challenger` | Candidate for A/B testing against champion |
| `baseline` | Reference model for comparison |

### Alias Workflow

```python
# 1. Train and register a new version (happens in notebook/job)
# Version 5 is created automatically

# 2. Set as challenger for testing
set_mlflow_model_alias("main.ml.churn_model", "challenger", 5)

# 3. After validation, promote to champion
set_mlflow_model_alias("main.ml.churn_model", "champion", 5)

# 4. Clean up old challenger alias
delete_mlflow_model_alias("main.ml.churn_model", "challenger")
```

### Serving with Aliases

Model serving endpoints can reference aliases instead of version numbers:

```python
# Endpoint config references the alias
# entity_name: "main.ml.churn_model"
# entity_version: "champion"  (alias, not version number)
```

When the alias is reassigned, the endpoint automatically serves the new version.

## Model Version Statuses

| Status | Description |
|--------|-------------|
| `PENDING_REGISTRATION` | Version is being registered |
| `READY` | Version is ready for use |
| `FAILED_REGISTRATION` | Registration failed |

## Legacy Stages (Workspace Registry)

The legacy registry uses stages for model lifecycle:

| Stage | Description |
|-------|-------------|
| `None` | Initial state |
| `Staging` | Under evaluation |
| `Production` | Serving in production |
| `Archived` | Retired |

Legacy models are accessed via `search_mlflow_models`. Transition between stages requires the `model_registry.transition_stage` API (not exposed as MCP tool).

## Model Naming

### Unity Catalog Models

```
catalog.schema.model_name

Examples:
  main.ml.churn_model
  prod.models.fraud_detector
  dev.experiments.prototype_v2
```

### Legacy Models

```
model_name  (flat, workspace-scoped)

Examples:
  churn_prediction
  [dev user_name] my_model
```

## Finding a Model's Source Run

Each model version tracks the MLflow run that produced it:

```python
# Get version details
version = get_mlflow_model_version("main.ml.churn_model", version=3)
run_id = version["run_id"]

# Inspect the source run
get_mlflow_run(run_id=run_id)
# See metrics, params, tags from the training run
```

## Common Workflows

### Inventory Models in a Schema

```python
# List all models
models = list_mlflow_models(catalog_name="main", schema_name="ml")

# For each model, check versions
for model in models["models"]:
    versions = list_mlflow_model_versions(model["full_name"])
    print(f"{model['full_name']}: {versions['count']} versions")
```

### Find the Champion Version

```python
# Resolve alias to version
champion = get_mlflow_model_version_by_alias("main.ml.churn_model", "champion")
print(f"Champion is version {champion['version']}, run_id={champion['run_id']}")
```
