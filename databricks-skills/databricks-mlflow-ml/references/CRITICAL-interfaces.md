# CRITICAL-interfaces — Exact API signatures

The minimum set of APIs that every classic-ML + UC workflow touches. Copy-pasteable, with the exact arguments that matter.

---

## Registry URI configuration

```python
mlflow.set_registry_uri("databricks-uc")    # Call at the start of every session
mlflow.get_registry_uri()                    # Returns "databricks-uc" if set correctly
```

**Must be called BEFORE** any `register_model` or `load_model` call. Idempotent to repeat.

---

## Experiment creation with UC volume artifact_location

```python
mlflow.set_experiment(
    experiment_name="/Users/<email>/<experiment_name>",
    artifact_location="dbfs:/Volumes/<catalog>/<schema>/<volume>/<path>",
)
```

**`artifact_location` is required** for UC-enforced workspaces. The volume must exist:

```sql
CREATE VOLUME IF NOT EXISTS <catalog>.<schema>.<volume>;
```

---

## `models:/` URI format

All load / deploy / spark_udf calls use this URI. **One format to memorize:**

```
models:/<catalog>.<schema>.<model_name>@<alias>
```

Examples:
```
models:/my_catalog.my_schema.grocery_forecaster@champion
models:/my_catalog.my_schema.grocery_forecaster@challenger
```

**Avoid** these forms (either legacy, or not-UC-native):
```
models:/grocery_forecaster/3                  # workspace registry, version number
models:/my_schema.grocery_forecaster/3        # invalid in UC
```

---

## Model logging (sklearn-flavored)

```python
mlflow.sklearn.log_model(
    sk_model=<fitted_estimator_or_pipeline>,
    artifact_path="model",                    # convention — keep as "model"
    signature=<Signature>,                    # REQUIRED — use infer_signature()
    input_example=<pandas_DataFrame>,         # REQUIRED — 5 real rows
    registered_model_name=None,               # leave None; register separately (cleaner)
    code_paths=<optional_list_of_dependency_files>,
    extra_pip_requirements=<optional_list>,   # only if custom deps beyond environment
)
```

**Signature inference:**
```python
from mlflow.models import infer_signature
signature = infer_signature(X_train, model.predict(X_train[:5]))
```

**Other flavors with identical signature:**
- `mlflow.xgboost.log_model(xgb_model=..., ...)`
- `mlflow.pytorch.log_model(pytorch_model=..., ...)`
- `mlflow.tensorflow.log_model(model=..., ...)`
- `mlflow.pyfunc.log_model(python_model=..., artifact_path=..., ...)` — for custom PythonModel wrappers

---

## Explicit registration

```python
result = mlflow.register_model(
    model_uri=f"runs:/{run_id}/model",        # "runs:/<run_id>/<artifact_path>"
    name="<catalog>.<schema>.<model_name>",   # three-level, not optional
    tags=<optional_dict>,
)
# result.name: str — fully qualified name
# result.version: str — newly-created version (e.g., "1", "2")
```

---

## Alias management

```python
from mlflow import MlflowClient
client = MlflowClient()

# Set (creates if missing, moves if exists)
client.set_registered_model_alias(
    name="<catalog>.<schema>.<model_name>",
    alias="champion",                         # or "challenger", or custom
    version="<version_number>",                # accepts str or int
)

# Get current alias mapping
model = client.get_registered_model("<catalog>.<schema>.<model_name>")
print(model.aliases)   # {"champion": "3", "challenger": "4"}

# Delete
client.delete_registered_model_alias(
    name="<catalog>.<schema>.<model_name>",
    alias="challenger",
)
```

---

## Loading — notebook / single-node

```python
model = mlflow.pyfunc.load_model(
    model_uri="models:/<catalog>.<schema>.<model_name>@champion",
)

# Predict on a pandas DataFrame matching the signature
predictions = model.predict(features_df)
```

**Returns:** `mlflow.pyfunc.PyFuncModel`, regardless of the original flavor. Expose `.metadata.signature` for schema.

---

## Loading — distributed / Lakeflow SDP

```python
predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    model_uri="models:/<catalog>.<schema>.<model_name>@champion",
    result_type="double",                     # or "array<double>" for multi-output
    env_manager="local",                      # "local" | "virtualenv" | "conda"
)

# Apply to a Spark DataFrame
df_with_predictions = df.withColumn(
    "prediction",
    predict_udf("feature_a", "feature_b", "feature_c"),
)
```

**Construct ONCE at module scope** in Lakeflow pipelines. See `GOTCHAS.md` #11.

---

## Model introspection

```python
from mlflow.models import get_model_info

info = get_model_info("models:/<catalog>.<schema>.<model_name>@champion")
info.signature               # ModelSignature with inputs/outputs
info.flavors                 # {"sklearn": {...}, "python_function": {...}}
info.utc_time_created
info.model_uuid
```

Useful when debugging load-vs-predict mismatches.

---

## Run + experiment queries (introspection)

```python
runs = mlflow.search_runs(
    experiment_names=["/Users/me@company.com/forecasting"],
    filter_string="metrics.r2 > 0.8",
    order_by=["metrics.r2 DESC"],
    max_results=5,
)
# Returns a pandas DataFrame with run_id, metrics, params, etc.

best_run_id = runs.iloc[0]["run_id"]
```

---

## SQL introspection (UC-native)

```sql
-- Does the model exist and which aliases are set?
DESCRIBE MODEL <catalog>.<schema>.<model_name>;

-- List all model versions
SHOW MODEL VERSIONS ON MODEL <catalog>.<schema>.<model_name>;

-- Check grants
SHOW GRANTS ON MODEL <catalog>.<schema>.<model_name>;
SHOW GRANTS ON SCHEMA <catalog>.<schema>;
```

---

## What's NOT in this skill

If you see these in code, you're likely in the wrong skill:

| API | Belongs in |
|-----|------------|
| `mlflow.genai.evaluate(...)` | `databricks-mlflow-evaluation` |
| `@scorer` decorator, `GuidelinesJudge`, etc. | `databricks-mlflow-evaluation` |
| `databricks.sdk.service.serving.EndpointCoreConfigInput` | `databricks-model-serving` |
| `ai_query('<custom-uc-model>', ...)` | Wrong pattern — use `pyfunc.load_model` or `spark_udf` instead (see `GOTCHAS.md` #9) |
| `transition_model_version_stage(...)` | Deprecated — use aliases (see `GOTCHAS.md` #6) |
