---
name: databricks-mlflow-ml
description: "Classic ML model lifecycle on Databricks with MLflow and Unity Catalog. Use when training scikit-learn / XGBoost / PyTorch models with MLflow tracking, registering models to Unity Catalog (three-level names, @champion / @challenger aliases), setting mlflow.set_registry_uri('databricks-uc'), logging experiments with UC volume artifact_location, loading registered models via mlflow.pyfunc.load_model or mlflow.pyfunc.spark_udf, and running batch inference (notebook or Lakeflow SDP pipeline). Not for GenAI agent evaluation — use databricks-mlflow-evaluation for that. Not for Model Serving endpoints — use databricks-model-serving for that."
---

# MLflow + Unity Catalog — Classic ML

Read this file fully; consult `references/gotchas.md` before writing UC code; consult `references/recipes.md` only for the alias-swap and `spark_udf` patterns.

If you're tempted to read `patterns-training.md`, `patterns-experiment-setup.md`, `patterns-uc-registration.md`, or `patterns-batch-inference.md` to figure out basic sklearn training, stop — you don't need them. This skill is only about the Databricks / Unity Catalog parts that are easy to miss.

## Why This Skill Exists

Three skills in the AI Dev Kit touch MLflow; this one owns **classic ML training + UC registration + batch inference**.

| Skill | Scope | MLflow API Surface |
|-------|-------|--------------------|
| `databricks-mlflow-evaluation` | GenAI agent evaluation | `mlflow.genai.evaluate()`, scorers, judges, traces |
| `databricks-model-serving` | Real-time serving endpoints | Deployment APIs, endpoint management, `ai_query` |
| `databricks-mlflow-ml` *(this skill)* | Classic ML + UC registration + batch inference | `mlflow.sklearn.log_model`, `register_model`, `set_registered_model_alias`, `pyfunc.load_model`, `pyfunc.spark_udf` |

Use this skill when training forecasting / classification / regression models, registering them to Unity Catalog, and scoring them in a notebook or Lakeflow pipeline. Do not use it for GenAI evaluation or Model Serving endpoint management.

## Hard Rules

1. Call `mlflow.set_registry_uri("databricks-uc")` before registering or loading UC models.
2. UC model names are always three-level: `catalog.schema.model_name`.
3. Load by alias, not version: `models:/catalog.schema.model@champion`, not `models:/catalog.schema.model/3`.
4. In UC-enforced workspaces, experiments need `artifact_location="dbfs:/Volumes/<catalog>/<schema>/<volume>/<path>"`.
5. `register_model` creates a version; it does **not** set `@champion` or `@challenger`.
6. Use aliases for lifecycle. Legacy stages like `Production` / `Staging` are deprecated for UC models.

## Quick Start

Minimum viable path from trained model object to UC-registered, notebook-scored model:

```python
import mlflow
import mlflow.sklearn
from mlflow import MlflowClient
from mlflow.models import infer_signature

CATALOG = "my_catalog"
SCHEMA = "my_schema"
MODEL_NAME = f"{CATALOG}.{SCHEMA}.my_model"

# 1. Configure UC registry + UC volume-backed experiment.
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting",
    artifact_location=f"dbfs:/Volumes/{CATALOG}/{SCHEMA}/mlflow_artifacts/forecasting",
)

# 2. Train + log. Use name="model" in MLflow 3.x; artifact_path="model" only for older code.
with mlflow.start_run() as run:
    model.fit(X_train, y_train)
    signature = infer_signature(X_train, model.predict(X_train[:5]))

    mlflow.sklearn.log_model(
        sk_model=model,                  # log the full Pipeline if preprocessing exists
        name="model",
        signature=signature,
        input_example=X_train.iloc[:5],
    )

# 3. Register + set alias. register_model returns a ModelVersion; alias is a separate call.
result = mlflow.register_model(
    model_uri=f"runs:/{run.info.run_id}/model",
    name=MODEL_NAME,
)
MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", result.version)

# 4. Load by alias, never by hard-coded version.
loaded = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
predictions = loaded.predict(X_test)
```

## Decision Table

| Situation | Do this |
|-----------|---------|
| Starting a first UC-registered classic ML model | Quick Start, then `recipes.md` §1–2; check `gotchas.md` #1, #2, #4, #7 |
| Model registered but missing from Catalog Explorer | Diagnose `set_registry_uri` and three-level names in `gotchas.md` #1–2 |
| Need notebook batch scoring | Use `mlflow.pyfunc.load_model("models:/catalog.schema.model@champion")`; keep the alias rule above |
| Need scheduled / distributed batch scoring in Lakeflow SDP | Use `recipes.md` §3 and `gotchas.md` #11; construct `spark_udf` at module scope |
| Retrained a challenger and need promotion | Use `recipes.md` §4 exactly; delete old `@champion` before setting new `@champion` |
| Load or predict behaves oddly | Use `recipes.md` §5 for `get_model_info` / signature checks, then `gotchas.md` for UC-specific failures |

## Runtime Compatibility

MLflow 3.x prefers `name=` in `log_model`; MLflow 2.x examples often use `artifact_path=`, which works but warns in newer versions. UC model stages are deprecated across modern Databricks runtimes; use aliases.
