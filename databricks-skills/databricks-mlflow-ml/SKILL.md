---
name: databricks-mlflow-ml
description: "Classic ML model lifecycle on Databricks with MLflow and Unity Catalog. Use when training scikit-learn / XGBoost / PyTorch models with MLflow tracking, registering models to Unity Catalog (three-level names, @champion / @challenger aliases), setting mlflow.set_registry_uri('databricks-uc'), logging experiments with UC volume artifact_location, loading registered models via mlflow.pyfunc.load_model or mlflow.pyfunc.spark_udf, and running batch inference (notebook or Lakeflow SDP pipeline). Not for GenAI agent evaluation — use databricks-mlflow-evaluation for that. Not for Model Serving endpoints — use databricks-model-serving for that."
---

# MLflow + Unity Catalog — Classic ML

## Before Writing Any Code

1. **Read `GOTCHAS.md`** — 12 common mistakes that cause silent failures or wasted time
2. **Read `CRITICAL-interfaces.md`** — exact API signatures and the `models:/` URI format

## End-to-End Workflows

Follow the workflow that matches your goal. Each step indicates which reference files to read.

### Workflow 1: Train → Register → Batch Score (most common)

For building a production-shape classic ML model with UC-native lineage. Covers the full path from raw features to predictions in a downstream table.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Create experiment with UC volume artifact_location | `patterns-experiment-setup.md` (Pattern 1) |
| 2 | Train model with signature + input_example | `patterns-training.md` (Patterns 1–3) |
| 3 | Register to Unity Catalog with three-level name | `patterns-uc-registration.md` (Patterns 1–2) |
| 4 | Set `@champion` alias | `patterns-uc-registration.md` (Pattern 3) |
| 5 | Verify registration (Navigator check) | `patterns-uc-registration.md` (Pattern 4) + `GOTCHAS.md` #5 |
| 6 | Load + score in notebook (Tier 1) | `patterns-batch-inference.md` (Patterns 1–2) |
| 7 | Optional: Lakeflow SDP batch via `spark_udf` | `patterns-batch-inference.md` (Patterns 3–4) |

### Workflow 2: Retrain + Promote (A/B pattern)

For adding a new version of an already-registered model and promoting it without touching downstream loader code.

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Train new version, log to same UC model name | `patterns-training.md` (Pattern 4) |
| 2 | Register as new version | `patterns-uc-registration.md` (Pattern 2) |
| 3 | Set `@challenger` alias | `patterns-uc-registration.md` (Pattern 3) |
| 4 | Validate `@challenger` predictions vs `@champion` | `patterns-batch-inference.md` (Pattern 5) |
| 5 | Swap aliases (`@challenger` → `@champion`) | `patterns-uc-registration.md` (Pattern 5) |

Downstream loader code that uses `models:/catalog.schema.model@champion` picks up the new version on next load — no code change needed.

### Workflow 3: Debugging a Failed Registration or Load

For the two most common support questions: "why did my model go to workspace registry?" and "why does pyfunc.load_model fail?"

| Step | Action | Reference Files |
|------|--------|-----------------|
| 1 | Verify registry URI is set to `databricks-uc` | `GOTCHAS.md` #1 |
| 2 | Verify three-level name | `GOTCHAS.md` #2 |
| 3 | Confirm model appears in Catalog Explorer | `patterns-uc-registration.md` (Pattern 4) |
| 4 | Check `CREATE MODEL` permissions | `GOTCHAS.md` #7 |
| 5 | Diagnose load failures | `GOTCHAS.md` #3, #8, #11 |

## Quick Start

The minimum viable path from untrained model to UC-registered, notebook-scored:

```python
import mlflow
from mlflow.models import infer_signature
from mlflow import MlflowClient

# 1. Configure: UC registry + UC volume for artifacts (both required)
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting",
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting",
)

# 2. Train + log
with mlflow.start_run() as run:
    model.fit(X_train, y_train)
    signature = infer_signature(X_train, model.predict(X_train[:5]))
    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        signature=signature,
        input_example=X_train.iloc[:5],
    )

# 3. Register + alias
MODEL_NAME = "my_catalog.my_schema.my_model"
result = mlflow.register_model(f"runs:/{run.info.run_id}/model", MODEL_NAME)
MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", result.version)

# 4. Load + predict (in any notebook, anywhere)
model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
predictions = model.predict(X_test)
```

## Why This Skill Exists

Three skills in the AI Dev Kit touch MLflow; this one owns **classic ML training + UC registration + batch inference**. The distinction matters because the APIs diverged:

| Skill | Scope | MLflow API Surface |
|-------|-------|--------------------|
| `databricks-mlflow-evaluation` | GenAI agent evaluation | `mlflow.genai.evaluate()`, scorers, judges, traces |
| `databricks-model-serving` | Real-time serving endpoints | Deployment APIs, endpoint management, `ai_query` |
| `databricks-mlflow-ml` *(this skill)* | Classic ML + UC registration + batch inference | `mlflow.sklearn.log_model`, `register_model`, `set_registered_model_alias`, `pyfunc.load_model`, `pyfunc.spark_udf` |

If you're training a forecasting / classification / regression model, registering it to UC, and scoring it in a notebook or Lakeflow pipeline — this skill. If you're evaluating an LLM agent's output quality — evaluation skill. If you're exposing a model behind an HTTP endpoint — model-serving skill.

## Common Issues

| Issue | Solution |
|-------|----------|
| **Model registered but not visible in Catalog Explorer** | Missing `mlflow.set_registry_uri("databricks-uc")`. See `GOTCHAS.md` #1. |
| **`RestException: INVALID_PARAMETER_VALUE` on `register_model`** | Two-level name used. UC requires `catalog.schema.name`. See `GOTCHAS.md` #2. |
| **Experiment creation fails with storage errors** | Missing `artifact_location` pointing at a UC volume. See `GOTCHAS.md` #4. |
| **`PERMISSION_DENIED: CREATE MODEL`** | Pair/user needs `CREATE MODEL ON SCHEMA <schema>`. See `GOTCHAS.md` #7. |
| **`pyfunc.load_model` returns but `predict()` fails** | Signature wasn't logged; inputs don't coerce. See `GOTCHAS.md` #8. |
| **Agent proposes `ai_query` for batch inference** | Wrong primitive — that requires a serving endpoint. Use `pyfunc.load_model` or `spark_udf`. See `GOTCHAS.md` #9. |

## Reference Files

- [`GOTCHAS.md`](references/GOTCHAS.md) — 12 common mistakes + fixes
- [`CRITICAL-interfaces.md`](references/CRITICAL-interfaces.md) — API signatures + `models:/` URI format
- [`patterns-experiment-setup.md`](references/patterns-experiment-setup.md) — experiment creation with UC volume artifact_location
- [`patterns-training.md`](references/patterns-training.md) — logging models with signature + input_example + autologging
- [`patterns-uc-registration.md`](references/patterns-uc-registration.md) — register + alias + verify + A/B promotion
- [`patterns-batch-inference.md`](references/patterns-batch-inference.md) — notebook (`pyfunc.load_model`) + Lakeflow (`spark_udf`) + champion-vs-challenger
- [`user-journeys.md`](references/user-journeys.md) — end-to-end workflows with decision points

## Runtime compatibility

Patterns verified against **MLflow 3.11** on **Lakeflow SDP serverless compute version 5** (default at time of writing). All APIs used (`set_registry_uri`, `log_model`, `register_model`, `set_registered_model_alias`, `pyfunc.load_model`, `pyfunc.spark_udf`) are compatible with MLflow 2.16+ as well, so the patterns work on older classic Databricks Runtimes that still ship 2.x. Where 3.x behaviour diverges (e.g., `artifact_path` deprecation → use `name=`), GOTCHAS.md calls it out.
