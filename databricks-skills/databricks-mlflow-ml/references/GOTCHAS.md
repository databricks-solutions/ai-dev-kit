# GOTCHAS — Classic ML on MLflow + Unity Catalog

Fourteen mistakes that silently waste hours. Read before writing any code.

---

## 1. Missing `mlflow.set_registry_uri("databricks-uc")` → workspace registry

**Symptom:** `register_model` succeeds, but the model doesn't appear in Catalog Explorer. It's in the legacy **workspace registry** (visible under the MLflow icon in the left nav), not Unity Catalog.

**Fix:**
```python
import mlflow
mlflow.set_registry_uri("databricks-uc")   # MUST come before register_model / load_model
```

**Verification:**
```python
assert mlflow.get_registry_uri() == "databricks-uc"
```

**Why it bites:** defaults still route to the workspace registry for backward compatibility. The only indicator you missed it is a URL that shows `/ml/models/<name>` instead of `/explore/data/models/<catalog>/<schema>/<name>`.

---

## 2. Two-level model names → rejected or wrong registry

**Symptom:** `RestException: INVALID_PARAMETER_VALUE: Invalid model name`, or the model registers to the workspace registry silently.

**Fix:** always use three-level names: `catalog.schema.model_name`.

```python
# WRONG
mlflow.register_model(model_uri, "my_model")
mlflow.register_model(model_uri, "my_schema.my_model")

# CORRECT
mlflow.register_model(model_uri, "my_catalog.my_schema.my_model")
```

**Why it bites:** the error message depends on the registry URI. With UC URI + two-level name → parameter error. With workspace URI + two-level name → registers successfully to workspace (the silently-wrong case).

---

## 3. Loading with version number instead of alias

**Symptom:** works today, breaks tomorrow when someone registers a new version. You've hard-coded a version number into every downstream consumer.

**Fix:** load via alias, never version.

```python
# FRAGILE — every retrain requires updating every loader
model = mlflow.pyfunc.load_model("models:/my_catalog.my_schema.my_model/3")

# STABLE — promote a new version by moving @champion; no loader changes
model = mlflow.pyfunc.load_model("models:/my_catalog.my_schema.my_model@champion")
```

**Why it bites:** aliases are the UC-native way to decouple loader code from model lifecycle. Version numbers are legacy. New infrastructure (Lakeflow, Genie) assumes alias-based loading.

---

## 4. Experiment creation without UC volume `artifact_location`

**Symptom:** experiment creates, but any `log_model` call fails with storage / permission errors. Or artifacts land in DBFS root (deprecated) and can't be loaded downstream.

**Fix:** when you create the experiment, pin it to a UC volume.

```python
# Prerequisite: the UC volume must exist
# CREATE VOLUME my_catalog.my_schema.mlflow_artifacts;

mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting",
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting",
)
```

**Why it bites:** the default `artifact_location` used to be DBFS root. Unity-Catalog-enforced workspaces reject DBFS root writes, so `log_model` fails with opaque errors. Pointing at a UC volume makes artifact storage first-class-governed and keeps lineage intact.

**When the experiment already exists without a UC volume:** you can't retroactively change `artifact_location`. Either (a) delete + recreate, or (b) create a new experiment. Don't try to relocate artifacts manually.

---

## 5. Trusting `register_model` success without verifying in UC

**Symptom:** `register_model` returns a `ModelVersion` object. Feels successful. But the model is in workspace registry, or the version number is stale, or an alias wasn't set.

**Fix:** always verify explicitly.

```sql
-- In a SQL cell or notebook:
DESCRIBE MODEL my_catalog.my_schema.my_model;
```

Or via Python:
```python
from mlflow import MlflowClient
model = MlflowClient().get_registered_model("my_catalog.my_schema.my_model")
assert "champion" in model.aliases, "Missing @champion alias"
```

Or visually: open Catalog Explorer → `my_catalog` → `my_schema` → **Models** tab. If the model is under MLflow's workspace UI instead, you registered to the wrong place (see #1).

**Why it bites:** `register_model`'s return value only tells you a version was created. It doesn't tell you *where* or *with what aliases*. The Navigator's V-step in pair programming: verify before trusting.

---

## 6. Setting the alias to `"production"` or `"staging"` (legacy MLflow stages)

**Symptom:** you remember MLflow had `stage="Production"` / `"Staging"` transitions. You try the same with aliases and nothing recognizes them.

**Fix:** UC model aliases are free-form labels. The conventions are `@champion` (current winner) and `@challenger` (under evaluation). MLflow stages are deprecated in the UC registry.

```python
# WRONG (legacy stage concept)
MlflowClient().set_registered_model_alias(name, "Production", version)

# CORRECT
MlflowClient().set_registered_model_alias(name, "champion", version)
```

**Why it bites:** the old `transition_model_version_stage()` API still exists but is a no-op on UC-registered models. No error, no effect.

---

## 7. Missing `CREATE MODEL ON SCHEMA` permission

**Symptom:** `RestException: PERMISSION_DENIED: User ... does not have CREATE MODEL permission`.

**Fix:** grant the permission at the schema level.

```sql
GRANT CREATE MODEL ON SCHEMA my_catalog.my_schema TO `user@company.com`;
-- Or for a group:
GRANT CREATE MODEL ON SCHEMA my_catalog.my_schema TO `data-science-team`;
```

**Why it bites:** workspace admins often assume `USE SCHEMA` covers model registration. It doesn't — `CREATE MODEL` is a separate UC privilege that must be granted explicitly.

**Verification:**
```sql
SHOW GRANTS ON SCHEMA my_catalog.my_schema;
```

---

## 8. Logging a model without `signature` or `input_example`

**Symptom:** `mlflow.pyfunc.load_model(...)` returns an object, but `.predict(spark_df)` raises cryptic coercion errors. Or predictions silently cast (int → float, string → category) and produce wrong numbers.

**Fix:** always log both.

```python
from mlflow.models import infer_signature

signature = infer_signature(X_train, model.predict(X_train[:5]))
mlflow.sklearn.log_model(
    sk_model=model,
    artifact_path="model",
    signature=signature,
    input_example=X_train.iloc[:5],   # 5 real rows for the pyfunc wrapper to introspect
)
```

**Why it bites:** without a signature, the pyfunc wrapper can't coerce inputs — it accepts whatever you pass, then downstream operations (especially `spark_udf`) fail or produce wrong results. `input_example` is what `pyfunc.load_model` reads to build the wrapper's input coercer.

---

## 9. `ai_query` used for batch inference on a custom UC model

**Symptom:** you want batch inference on your custom-registered model. You see `ai_query()` in Genie docs and assume it works. It doesn't (for custom models) — `ai_query` only invokes **serving endpoints**, and your UC-registered model isn't behind one unless you deployed a serving endpoint for it.

**Fix:** for batch inference, use `pyfunc.load_model` (notebook) or `pyfunc.spark_udf` (Lakeflow SDP pipeline).

```python
# WRONG for custom UC models — requires a serving endpoint
spark.sql(f"SELECT ai_query('{MODEL_NAME}', features) FROM silver_features")

# CORRECT — notebook batch (single node)
model = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
predictions = model.predict(features_pandas_df)

# CORRECT — Lakeflow SDP batch (distributed)
predict_udf = mlflow.pyfunc.spark_udf(spark, f"models:/{MODEL_NAME}@champion", result_type="double")
silver_features.withColumn("prediction", predict_udf(*feature_cols))
```

**Why it bites:** `ai_query` *is* the right call for Foundation Model API endpoints (`ai_query('databricks-dbrx-instruct', prompt)`). The naming overlap leads to wrong assumptions for custom models.

---

## 10. Trying to delete / re-register a model at the same version number

**Symptom:** `RestException: ALREADY_EXISTS` when re-registering. You can't reuse version numbers.

**Fix:** UC versions are monotonically-increasing and immutable. To supersede a bad version, register a new version and move `@champion` to it. The old version stays in history for lineage.

```python
new_result = mlflow.register_model(new_run_uri, MODEL_NAME)
MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", new_result.version)
# Old version is still there; that's correct. Lineage preserved.
```

**Why it bites:** habits from the workspace registry (where deletion was forgiving) don't transfer. UC treats model versions as first-class auditable artifacts.

---

## 11. `pyfunc.spark_udf` constructed inside a function call

**Symptom:** in a Lakeflow SDP `@dp.materialized_view`, the UDF is constructed every time the view evaluates — slow and sometimes fails with serialization errors.

**Fix:** construct the UDF at module scope, reuse it inside the view.

```python
import mlflow
import databricks.declarative_pipelines as dp

# Construct ONCE, at module scope
mlflow.set_registry_uri("databricks-uc")
predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    f"models:/{MODEL_NAME}@champion",
    result_type="double",
)

@dp.materialized_view
def gold_forecast():
    return spark.read.table("silver_features").withColumn(
        "prediction",
        predict_udf("feat_a", "feat_b", "feat_c"),
    )
```

**Why it bites:** Lakeflow SDP may evaluate the function definition multiple times. Model deserialization is expensive — don't repeat it.

---

## 12. `mlflow[databricks]` extras missing when running outside Databricks

**Symptom:** training + logging works; `register_model` fails with `MlflowException: Unable to import necessary dependencies to access model version files in Unity Catalog` — root cause `ModuleNotFoundError: No module named 'azure'` (for Azure-hosted workspaces) or `'boto3'` (AWS) / `'google.cloud'` (GCP).

**Fix:** install the `databricks` extras, which pull cloud-storage SDKs MLflow needs to stage artifacts into the UC-managed location.

```bash
pip install 'mlflow[databricks]'
# or, for a lighter install:
pip install 'mlflow-skinny[databricks]'
```

**Why it bites:** plain `pip install mlflow` leaves out the cloud-provider SDKs because they're large and most local workflows don't need them. UC registration REQUIRES them because the registry stages artifacts into cloud-managed storage (Azure ADLS / S3 / GCS), and MLflow uses the provider's SDK for the upload. Local `log_model` works fine (artifacts go to the tracking server); registration doesn't.

**When it most commonly hits:** running training scripts from a laptop, CI runner, or non-Databricks compute — anywhere that isn't a Databricks cluster (which ships the extras pre-installed).

---

## 13. `artifact_path=` parameter is deprecated; new name is `name=`

**Symptom:** warning in logs: `WARNING mlflow.models.model: `artifact_path` is deprecated. Please use `name` instead.` Still works today; may break in a future MLflow major version.

**Fix:** use `name=` instead of `artifact_path=` in `log_model` calls.

```python
# OLD (still works, warns)
mlflow.sklearn.log_model(sk_model=model, artifact_path="model", ...)

# NEW (preferred, no warning)
mlflow.sklearn.log_model(sk_model=model, name="model", ...)
```

**Why it bites:** most online tutorials and training courses still use `artifact_path`. The rename shipped in MLflow 2.16. `name=` semantics are identical — still the within-run artifact folder. Aliases this to the preferred parameter, not a rename of what the parameter represents.

---

## 14. Custom preprocessing not captured in the logged model

**Symptom:** in the training notebook, predictions are accurate. After `pyfunc.load_model(...)`, predictions are garbage. The pipeline works in training because you're calling `scaler.transform()` manually; at inference time, nobody calls the scaler.

**Fix:** wrap preprocessing + model in an `sklearn.pipeline.Pipeline` (or a custom `PythonModel` for non-sklearn preprocessing). Log the whole pipeline.

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor

pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("model", GradientBoostingRegressor()),
])
pipeline.fit(X_train, y_train)

# Logs both the fitted scaler AND the model as a single artifact
mlflow.sklearn.log_model(
    sk_model=pipeline,
    artifact_path="model",
    signature=infer_signature(X_train, pipeline.predict(X_train[:5])),
    input_example=X_train.iloc[:5],
)
```

**Why it bites:** the most painful post-registration bug. Training and inference code paths are different files; the divergence is invisible until predictions are obviously wrong.
