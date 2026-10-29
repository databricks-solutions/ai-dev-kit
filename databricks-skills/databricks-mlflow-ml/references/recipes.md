# UC-Specific Recipes

These are code shapes, not full sklearn implementations. Use them to get Databricks / Unity Catalog arguments and ordering right.

## 1. Experiment + UC Volume Setup

Do this before training if the workspace enforces Unity Catalog storage.

- Set the registry URI every session:
  ```python
  mlflow.set_registry_uri("databricks-uc")
  ```
- Create the artifact volume once per schema:
  ```sql
  CREATE VOLUME IF NOT EXISTS my_catalog.my_schema.mlflow_artifacts;
  ```
- Create / select the experiment with a UC volume artifact location:
  ```python
  mlflow.set_experiment(
      experiment_name="/Users/me@company.com/forecasting",
      artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting",
  )
  ```

If the experiment already exists with a non-UC artifact location, create a new experiment path. Do not try to move MLflow artifacts manually; run metadata already points at the original location.

## 2. Log → Register → Alias

### Logging UC essentials

When logging the model:

- Include `signature=infer_signature(X_train, model.predict(X_train[:5]))`.
- Include `input_example=X_train.iloc[:5]` or equivalent real rows.
- Use `name="model"` for MLflow 3.x / newer code; `artifact_path="model"` is the older spelling.
- If preprocessing exists, log the whole pipeline / wrapper, not just the final estimator.

Shape:

```python
with mlflow.start_run() as run:
    # train your estimator or pipeline here
    mlflow.<flavor>.log_model(
        <model_arg>=model_or_pipeline,
        name="model",
        signature=signature,
        input_example=input_example,
    )
```

### Register + champion alias

After training:

```python
result = mlflow.register_model(
    f"runs:/{run_id}/model",
    "my_catalog.my_schema.my_model",
)
MlflowClient().set_registered_model_alias(
    "my_catalog.my_schema.my_model",
    "champion",
    result.version,
)
```

`register_model` returns a `ModelVersion`; `result.version` is a string such as `"1"`. It does **not** set aliases — the alias call is separate and required.

### Tags syntax

Tags can be set at registration time:

```python
result = mlflow.register_model(
    f"runs:/{run_id}/model",
    MODEL_NAME,
    tags={"dataset_version": "2024-Q4", "trained_by": "forecasting_team"},
)
```

Or after registration:

```python
client.set_registered_model_tag(MODEL_NAME, "domain", "retail")
client.set_model_version_tag(MODEL_NAME, result.version, "reviewed", "true")
```

### Minimal UC permission checklist

| Operation | Required UC privilege |
|-----------|-----------------------|
| First registration of a model in a schema | `CREATE MODEL ON SCHEMA catalog.schema` |
| Registering a new version | `EDIT ON MODEL catalog.schema.model` |
| Setting aliases / tags | `EDIT ON MODEL catalog.schema.model` |
| Loading for inference | `EXECUTE ON MODEL catalog.schema.model` plus `USE CATALOG` / `USE SCHEMA` |

## 3. Lakeflow SDP `spark_udf` Shape

For Lakeflow SDP, create the UDF at module scope, not inside the decorated dataset function.

```python
# src/gold/score_model.py
import mlflow
import databricks.declarative_pipelines as dp

mlflow.set_registry_uri("databricks-uc")

MODEL_NAME = "my_catalog.my_schema.my_model"

predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    model_uri=f"models:/{MODEL_NAME}@champion",
    result_type="double",
    env_manager="local",
)

@dp.materialized_view
def gold_predictions():
    return (
        spark.read.table("my_catalog.my_schema.silver_features")
        .withColumn(
            "prediction",
            predict_udf("feature_a", "feature_b", "feature_c"),
        )
    )
```

Pass feature columns in the order expected by the model signature.

`result_type` shapes:

| Model output | `result_type` |
|--------------|---------------|
| Single numeric prediction | `"double"` |
| Integer class id | `"long"` |
| String class label | `"string"` |
| Multi-output numeric vector | `"array<double>"` |
| Named outputs | `StructType([...])` |

Do not use `ai_query` here unless you have explicitly deployed a Model Serving endpoint.

## 4. A/B Promotion Alias Swap

This order is intentional: delete old `@champion` before setting the new one. Otherwise, during a botched sequence or retry, the pre-existing alias can still point consumers at the wrong version.

```python
from mlflow import MlflowClient

client = MlflowClient()
MODEL_NAME = "my_catalog.my_schema.my_model"

model = client.get_registered_model(MODEL_NAME)
old_champion = model.aliases.get("champion")
new_champion = model.aliases.get("challenger")

if new_champion is None:
    raise RuntimeError("No @challenger alias set; nothing to promote")

# Optional: preserve an explicit rollback handle before moving champion.
if old_champion:
    client.set_registered_model_alias(
        MODEL_NAME,
        f"archived_{old_champion}",
        old_champion,
    )

# Required order: remove old champion, then set new champion.
if old_champion:
    client.delete_registered_model_alias(MODEL_NAME, "champion")

client.set_registered_model_alias(MODEL_NAME, "champion", new_champion)

# Remove challenger after it has become champion.
client.delete_registered_model_alias(MODEL_NAME, "challenger")
```

Downstream code using `models:/my_catalog.my_schema.my_model@champion` picks up the new version on next load. No loader code changes.

Rollback shape:

```python
client.delete_registered_model_alias(MODEL_NAME, "champion")
client.set_registered_model_alias(MODEL_NAME, "champion", old_champion)
```

## 5. Verification One-Liners

### SQL

```sql
DESCRIBE MODEL my_catalog.my_schema.my_model;
SHOW MODEL VERSIONS ON MODEL my_catalog.my_schema.my_model;
SHOW GRANTS ON MODEL my_catalog.my_schema.my_model;
SHOW GRANTS ON SCHEMA my_catalog.my_schema;
```

If `DESCRIBE MODEL` cannot find it but `register_model` succeeded, suspect the workspace-registry trap: missing `mlflow.set_registry_uri("databricks-uc")`.

### Alias dictionary shape

```python
model = MlflowClient().get_registered_model("my_catalog.my_schema.my_model")
model.aliases
# Expected shape: {"champion": "3", "challenger": "4"}
```

Use this to confirm that `@champion` exists and points at the version you intended.

### Signature debugging

```python
from mlflow.models import get_model_info

info = get_model_info("models:/my_catalog.my_schema.my_model@champion")
info.signature
info.flavors
```

If `info.signature` is missing or does not match the DataFrame columns you pass to `predict`, re-log the model with a signature and input example.

### Load URI sanity check

```python
mlflow.pyfunc.load_model("models:/my_catalog.my_schema.my_model@champion")
```

Correct URI shape is:

```text
models:/<catalog>.<schema>.<model>@<alias>
```

Avoid version-pinned loaders such as `models:/catalog.schema.model/3` unless you are doing forensic debugging.
