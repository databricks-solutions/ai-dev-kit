# Databricks / Unity Catalog Gotchas

Only the Databricks + Unity Catalog-specific failures are here. Generic MLflow, sklearn, and modeling advice intentionally lives elsewhere.

## Runtime Gotcha Matrix

| Area | MLflow 2.x | MLflow 3.x / newer Databricks guidance |
|------|------------|-----------------------------------------|
| Model artifact argument | `artifact_path="model"` is common | Prefer `name="model"`; `artifact_path` warns and may disappear later |
| UC lifecycle | Stages already deprecated for UC | Use aliases only: `@champion`, `@challenger`, custom aliases |
| Registry target | Workspace registry remains default unless changed | Still call `mlflow.set_registry_uri("databricks-uc")` explicitly |

---

## 1. Missing `mlflow.set_registry_uri("databricks-uc")`

**How it fails:** Silent. `register_model` succeeds, but the model lands in the legacy workspace registry, not Unity Catalog; Catalog Explorer cannot find it.

**Fix:** call this before any register or load:

```python
mlflow.set_registry_uri("databricks-uc")
assert mlflow.get_registry_uri() == "databricks-uc"
```

**Why:** MLflow keeps workspace-registry defaults for backward compatibility, so the API call can succeed in the wrong registry.

---

## 2. Not using a three-level UC model name

**How it fails:** Loud with UC registry (`INVALID_PARAMETER_VALUE`), but silent-wrong if you also forgot `set_registry_uri`: two-level names can register to the workspace registry.

**Fix:** always use `catalog.schema.model_name`.

```python
# Wrong
"my_model"
"my_schema.my_model"

# Correct
"my_catalog.my_schema.my_model"
```

**Why:** Unity Catalog models are securable objects under a catalog and schema; workspace-registry names are not.

---

## 3. Experiment artifact location is not a UC volume

**How it fails:** Usually loud later, not at setup: `log_model` or artifact upload fails with storage / permission errors. In older patterns, artifacts may silently land in DBFS root, which breaks UC governance expectations.

**Fix:** set a UC volume-backed artifact location when creating the experiment.

```python
mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting",
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting",
)
```

**Why:** UC-enforced workspaces reject unmanaged DBFS-root artifact writes; UC volumes keep model artifacts governed and loadable.

---

## 4. Using legacy `Production` / `Staging` stages

**How it fails:** Silent or misleading. Stage APIs such as `transition_model_version_stage()` are deprecated / ineffective for UC models; aliases named `"Production"` may exist as labels but are not treated as lifecycle stages.

**Fix:** use UC aliases by convention:

```python
MlflowClient().set_registered_model_alias(name, "champion", version)
MlflowClient().set_registered_model_alias(name, "challenger", version)
```

**Why:** Unity Catalog model lifecycle moved from stages to free-form aliases; downstream loaders should use `models:/name@champion`.

---

## 5. Missing `CREATE MODEL ON SCHEMA`

**How it fails:** Loud. `register_model` raises `PERMISSION_DENIED: User ... does not have CREATE MODEL permission`.

**Fix:** ask the schema owner for the schema-level model-creation grant.

```sql
GRANT CREATE MODEL ON SCHEMA my_catalog.my_schema TO `user@company.com`;
SHOW GRANTS ON SCHEMA my_catalog.my_schema;
```

**Why:** `USE CATALOG` and `USE SCHEMA` are not enough; model creation is a separate UC privilege.

---

## 6. Assuming `ai_query` is batch inference for custom UC models

**How it fails:** Loud or wrong-primitive. `ai_query` calls serving endpoints; a UC-registered custom model is not automatically a serving endpoint.

**Fix:** for batch inference, use:

```python
mlflow.pyfunc.load_model("models:/catalog.schema.model@champion")   # notebook / pandas path
mlflow.pyfunc.spark_udf(spark, "models:/catalog.schema.model@champion", result_type="double")
```

**Why:** registration and serving are separate. `ai_query` belongs to Model Serving / Foundation Model endpoint workflows, not ordinary UC batch scoring.

---

## 7. Constructing `spark_udf` inside a Lakeflow SDP function

**How it fails:** Often loud and slow: repeated model deserialization, serialization errors, or pipeline refreshes that hang / retry. Sometimes just silently expensive.

**Fix:** construct the UDF once at module scope and call it inside `@dp.table` / `@dp.materialized_view`.

```python
mlflow.set_registry_uri("databricks-uc")
predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    "models:/catalog.schema.model@champion",
    result_type="double",
)
```

**Why:** Lakeflow SDP can evaluate dataset functions repeatedly; model loading belongs at module import time, not inside the dataset function body.

---

## 8. Missing `mlflow[databricks]` extras outside Databricks compute

**How it fails:** Loud. Local laptop / CI / non-Databricks jobs may train and log, then fail on UC registration with missing cloud SDK imports such as `azure`, `boto3`, or `google.cloud`.

**Fix:**

```bash
pip install 'mlflow[databricks]'
# or
pip install 'mlflow-skinny[databricks]'
```

**Why:** UC registration stages artifacts through cloud-managed storage; the Databricks extras include the provider SDKs that plain `mlflow` may omit.

---

## 9. Using deprecated `artifact_path=` instead of `name=`

**How it fails:** Noisy now, possibly loud later. Newer MLflow warns that `artifact_path` is deprecated; future major versions may remove it.

**Fix:** prefer:

```python
mlflow.sklearn.log_model(
    sk_model=model,
    name="model",
    signature=signature,
    input_example=input_example,
)
```

**Why:** MLflow renamed the within-run model artifact argument; the value still becomes the path used by `runs:/<run_id>/model`.
