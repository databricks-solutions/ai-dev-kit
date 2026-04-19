# user-journeys

End-to-end workflows with decision points. Read the journey that matches your situation.

---

## Journey 1: First model (train → register → score) — the 90%-case

Most users arrive here. Goal: a UC-registered model with a `@champion` alias, producing batch predictions.

**Prerequisites:**
- UC catalog + schema where you have `CREATE MODEL` permission
- A UC volume for MLflow artifacts (create if missing — `patterns-experiment-setup.md` Pattern 2)
- Features in a Spark table (Bronze → Silver → Gold already done)

**Steps:**

1. **Set up the experiment** (`patterns-experiment-setup.md` Pattern 1)
   - `mlflow.set_registry_uri("databricks-uc")`
   - `mlflow.set_experiment(experiment_name=..., artifact_location=<uc_volume_path>)`
2. **Train + log** (`patterns-training.md` Pattern 1 or 2)
   - Always include `signature` and `input_example`
   - If you have preprocessing, wrap in `sklearn.Pipeline` (Pattern 2)
3. **Register** (`patterns-uc-registration.md` Pattern 1)
   - `mlflow.register_model(f"runs:/{run_id}/model", "catalog.schema.model")`
4. **Set alias** (`patterns-uc-registration.md` Pattern 3)
   - `client.set_registered_model_alias(name, "champion", version)`
5. **Verify** (`patterns-uc-registration.md` Pattern 4)
   - `DESCRIBE MODEL catalog.schema.model` OR Catalog Explorer UI
6. **Load + score** (`patterns-batch-inference.md` Pattern 1 or 2)
   - `model = mlflow.pyfunc.load_model("models:/catalog.schema.model@champion")`
   - `model.predict(features_df)`

**Done.** You have a UC-registered model with a canonical loading URI that downstream code can depend on.

---

## Journey 2: Retrain + promote (A/B)

You already have `@champion`. You trained a new version and want to decide whether to promote it.

**Prerequisites:**
- Model exists in UC with `@champion` set (you did Journey 1)
- New training run logged to the same experiment

**Steps:**

1. **Register new version** (`patterns-uc-registration.md` Pattern 1)
   - Same `MODEL_NAME` as before — UC auto-increments version
2. **Set `@challenger`** (`patterns-uc-registration.md` Pattern 3)
   - `client.set_registered_model_alias(name, "challenger", new_version)`
3. **A/B validate** (`patterns-batch-inference.md` Pattern 5)
   - Load both aliases, score validation set, compare metrics
4. **Decide**:
   - Challenger wins → **Pattern 5 in `patterns-uc-registration.md`**: swap aliases
   - Champion wins → delete `@challenger` alias, keep current `@champion`
5. **Verify** downstream loaders picked up the new version (after swap)
   - Any code using `models:/<name>@champion` will see the new version on next load

---

## Journey 3: Lakeflow SDP batch pipeline

You want predictions to land in a scheduled gold table, not an ad-hoc notebook.

**Prerequisites:**
- Model registered with `@champion` (Journey 1 complete)
- Lakeflow SDP pipeline defined (one already running is ideal)

**Steps:**

1. **Add a new file** to the pipeline source: `src/gold/gold_forecast.py`
2. **Construct the UDF at module scope** (`patterns-batch-inference.md` Pattern 3)
   - `mlflow.set_registry_uri("databricks-uc")`
   - `predict_udf = mlflow.pyfunc.spark_udf(spark, "models:/...@champion", result_type="double")`
3. **Define the `@dp.materialized_view`** that reads silver features, applies the UDF
4. **Deploy + run** the pipeline
   - `databricks bundle deploy && databricks bundle run <pipeline_name>`
5. **Verify** the `gold_forecast` table materializes
   - Row count matches `silver_features`
   - Query from Genie or SQL editor

**Do NOT use `ai_query`** in this pipeline — see `GOTCHAS.md` #9.

---

## Journey 4: Debug a registration that went to workspace registry

The #1 support question. Symptoms: model doesn't appear in Catalog Explorer; URL contains `/ml/models/` instead of `/explore/data/models/`.

**Steps:**

1. Confirm the diagnosis:
   - Catalog Explorer → catalog → schema → Models tab: **missing**
   - MLflow icon (left sidebar) → Models: **present**
   - That's the workspace registry, not UC
2. Verify registry URI in the training session
   - `mlflow.get_registry_uri()` — should return `"databricks-uc"`, not a workspace URI
3. If the URI was wrong, fix it and re-register:
   - Add `mlflow.set_registry_uri("databricks-uc")` at the top of the training code
   - Re-run `mlflow.register_model(...)` — this creates a new entry in UC
   - The orphaned workspace-registry entry can be deleted via MLflow UI (optional)
4. Set the `@champion` alias on the new UC version
5. Verify via `DESCRIBE MODEL` — see `patterns-uc-registration.md` Pattern 4

---

## Journey 5: Debug a `pyfunc.load_model` that fails or predicts wrong

Model loaded successfully, but `.predict()` raises or produces nonsense.

**Steps:**

1. **Check the signature was logged:**
   ```python
   from mlflow.models import get_model_info
   info = get_model_info("models:/<name>@champion")
   print(info.signature)
   ```
   If `None` — see `GOTCHAS.md` #8. Re-log the model with `signature=infer_signature(...)`.

2. **Check the input column order:**
   ```python
   expected = model.metadata.get_input_schema().input_names()
   print(f"Model expects: {expected}")
   print(f"You passed: {list(features_df.columns)}")
   ```
   If the order differs, pass `features_df[expected]`.

3. **Check preprocessing coverage:**
   - Does the training notebook call a scaler / encoder / imputer before fitting?
   - Is that preprocessing in the logged artifact?
   - If not — see `GOTCHAS.md` #12. Re-train with preprocessing wrapped in `sklearn.Pipeline`.

4. **Check for type coercion:**
   - Integer column becoming float (or vice versa) — fine for sklearn, sometimes breaks for xgboost/pytorch
   - Categorical as string vs int — depends on the flavor
   - Fix: cast `features_df` to match `model.metadata.get_input_schema()` dtypes before predicting

---

## Journey 6: Schema evolution — your features changed since the model was logged

The silver features pipeline added a new column. Your deployed `@champion` model was trained without it. Predictions still work (extra columns are ignored), but you want to include the new feature.

**Steps:**

1. Retrain with the new feature:
   ```python
   # Same Journey 1 steps, but with expanded feature set
   mlflow.sklearn.log_model(
       sk_model=new_pipeline,
       artifact_path="model",
       signature=infer_signature(X_train_expanded, new_pipeline.predict(X_train_expanded[:5])),
       input_example=X_train_expanded.iloc[:5],
   )
   ```
2. Register as a new version
3. Validate via A/B (Journey 2)
4. Promote to `@champion`

Schema changes are always a new version. Never mutate a logged model in place.

---

## Journey 7: "Everything is on fire, I have 10 minutes to demo"

Someone registered a fallback model. Load it.

```python
import mlflow
mlflow.set_registry_uri("databricks-uc")
model = mlflow.pyfunc.load_model(
    "models:/<fallback_catalog>.<fallback_schema>.<model>@fallback"
)
features = spark.table("<fallback_catalog>.<fallback_schema>.sample_features").limit(500).toPandas()
features["prediction"] = model.predict(features)
display(spark.createDataFrame(features))
```

Every escape-hatch pattern should pre-register a `@fallback` version for exactly this case.

---

## When to use which journey

| Situation | Journey |
|-----------|---------|
| I'm starting from zero | 1 |
| I have `@champion`, trained something new | 2 |
| I want predictions in a scheduled table | 3 |
| Registered but can't find in Catalog Explorer | 4 |
| `load_model` succeeds but `predict` fails | 5 |
| My features changed | 6 |
| Demo in 10 minutes, nothing works | 7 |
