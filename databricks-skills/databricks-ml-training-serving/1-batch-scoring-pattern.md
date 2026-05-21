# Nightly train + batch-score into a gold table

The canonical demo flow. One notebook trains the model, registers `@prod` in UC, scores the latest features, and writes a gold predictions table that dashboards/apps/Genie read. Run it on a serverless job nightly. Re-running = retraining.

```
silver_<entity>_features    silver_<entity>_label_events
        │                            │
        └────────── join ────────────┘
                     │
              [this notebook]
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
  mlflow tracking   UC registry   gold_<entity>_predictions
   (experiments)   ({name}@prod)  (one row per entity, overwritten)
```

## Why this shape

- **One notebook, one artifact.** No hand-off between data scientist and engineer — the same file trains, registers, and produces the gold table downstream reads.
- **Gold is where truth lives.** Dashboards, Genie, and apps never call the model directly for batch use. They read `gold_<entity>_predictions`. Cheap, consistent, fast.
- **Label join lives in the notebook during dev, gets promoted to SDP when stable.** Iterate on the label window (`failure occurred within 7 days`) in Python; once locked, move into a silver materialized view.

## Full example (Databricks notebook source format)

```python
# Databricks notebook source
# MAGIC %md
# MAGIC # Turbine failure: train + score → gold_turbine_predictions
# MAGIC Runs nightly on serverless. End-to-end: build label → HPO → register → score.

# COMMAND ----------
# MAGIC %pip install -q optuna xgboost==2.1.3 mlflow==2.22.0
# MAGIC dbutils.library.restartPython()

# COMMAND ----------
import json
from datetime import timedelta
import mlflow, optuna
from mlflow.tracking import MlflowClient
from xgboost import XGBClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
import pyspark.sql.functions as F

CATALOG, SCHEMA, NAME = "ai_demo_gen", "wind_farm", "turbine_failure"
FULL_NAME = f"{CATALOG}.{SCHEMA}.{NAME}"
EXPERIMENT_PATH = "/Users/me@example.com/turbine_failure"  # paste into resources.json after first run
LABEL_WINDOW_DAYS = 7

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(EXPERIMENT_PATH)
client = MlflowClient(registry_uri="databricks-uc")

# COMMAND ----------
# MAGIC %md ## 1. Build the training set (features + label join)

features = spark.table(f"{CATALOG}.{SCHEMA}.silver_turbine_features_daily")
events   = spark.table(f"{CATALOG}.{SCHEMA}.silver_turbine_failure_events")

# Label = 1 if a failure occurred within LABEL_WINDOW_DAYS of the feature row.
labeled = (features.alias("f")
    .join(events.alias("e"),
          (F.col("f.turbine_id") == F.col("e.turbine_id")) &
          (F.col("e.failure_ts").between(
              F.col("f.feature_ts"),
              F.col("f.feature_ts") + F.expr(f"INTERVAL {LABEL_WINDOW_DAYS} DAYS"))),
          "left")
    .withColumn("label", F.col("e.failure_ts").isNotNull().cast("int"))
    .select("f.*", "label")
    .toPandas())

FEATURE_COLS = ["vib_rms", "vib_kurtosis", "rpm_mean", "rpm_std",
                "bearing_temp_max", "gen_temp_max", "wind_speed_avg", "hours_since_maint"]
X = labeled[FEATURE_COLS]; y = labeled["label"]
X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)

# COMMAND ----------
# MAGIC %md ## 2. Optuna HPO with autologged trials, then register the best

mlflow.xgboost.autolog(log_input_examples=True)  # each trial → child run

def objective(trial):
    params = {
        "n_estimators":     trial.suggest_int("n_estimators", 100, 400),
        "max_depth":        trial.suggest_int("max_depth", 3, 10),
        "learning_rate":    trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "subsample":        trial.suggest_float("subsample", 0.6, 1.0),
        "scale_pos_weight": (y_tr == 0).sum() / max((y_tr == 1).sum(), 1),
    }
    with mlflow.start_run(nested=True):
        m = XGBClassifier(**params, eval_metric="auc").fit(X_tr, y_tr)
        auc = roc_auc_score(y_te, m.predict_proba(X_te)[:, 1])
        mlflow.log_metric("val_auc", auc)
        return auc

with mlflow.start_run(run_name="hpo") as parent:
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=20, show_progress_bar=False)

    best = XGBClassifier(**study.best_params, eval_metric="auc").fit(X_tr, y_tr)
    best_auc = roc_auc_score(y_te, best.predict_proba(X_te)[:, 1])
    mlflow.log_metric("best_val_auc", best_auc)

    info = mlflow.xgboost.log_model(
        best, "model",
        input_example=X_tr.iloc[:5],
        registered_model_name=FULL_NAME,
    )

new_version = max(
    client.search_model_versions(f"name='{FULL_NAME}'"),
    key=lambda v: int(v.version),
).version
client.set_registered_model_alias(FULL_NAME, "prod", new_version)

# COMMAND ----------
# MAGIC %md ## 3. Batch score latest features → gold_turbine_predictions

predict = mlflow.pyfunc.spark_udf(
    spark, model_uri=f"models:/{FULL_NAME}@prod", env_manager="local",
)

latest = spark.table(f"{CATALOG}.{SCHEMA}.silver_turbine_features_latest")
scored = (latest
    .withColumn("risk_score", predict(*[F.col(c) for c in FEATURE_COLS]))
    .withColumn("risk_level", F.when(F.col("risk_score") > 0.7, "HIGH")
                              .when(F.col("risk_score") > 0.4, "MEDIUM")
                              .otherwise("LOW"))
    .withColumn("scored_at", F.current_timestamp())
    .withColumn("model_version", F.lit(new_version))
    .select("turbine_id", "risk_score", "risk_level", "scored_at", "model_version"))

(scored.write
    .option("mergeSchema", "true")
    .mode("overwrite")
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_turbine_predictions"))

rows = spark.table(f"{CATALOG}.{SCHEMA}.gold_turbine_predictions").count()

# COMMAND ----------
# Return structured result. print() is unreliable on serverless; this lands in
# `databricks jobs get-run-output <TASK_RUN_ID> | jq '.notebook_output.result'`.
dbutils.notebook.exit(json.dumps({
    "model_version": new_version,
    "val_auc": float(best_auc),
    "rows_scored": int(rows),
    "experiment_path": EXPERIMENT_PATH,
}))
```

## Notes specific to this shape

- **`env_manager="local"`** because training and scoring run in the same job — no need to rebuild the model's env from `pip_requirements`. Switch to `"virtualenv"` or `"uv"` (MLflow ≥ 2.22) if scoring runs in a different job than training.
- **Overwrite vs MERGE.** Overwrite is correct when you want "latest score per entity" semantics (one row per turbine). If you want history (one row per turbine per scoring run), MERGE on `(turbine_id, scored_at)` into a partitioned table instead.
- **Label window in code, not SDP.** Keep `LABEL_WINDOW_DAYS` as a notebook config while you're tuning the model. Once the label definition is stable, promote it to a silver materialized view in SDP and read the labeled table directly.
- **`EXPERIMENT_PATH` hard-coded.** After the first successful run, copy that path into `resources.json` as `mlflow_experiment_path` so the app, dashboards, and downstream traces can reference it.

## Running it as a serverless job

See **[databricks-jobs](../databricks-jobs/SKILL.md)** for the full `databricks jobs submit --no-wait` pattern and the TASK-run-id-vs-submit-run-id trap. The model-specific bits:

- Top of the notebook does `%pip install -q optuna xgboost==2.1.3 mlflow==2.22.0` as a backstop in case the job's `environments[].spec.dependencies` aren't honored. Submit with `spec.client: "4"` so they are honored — `"1"` silently ignores the list.
- The notebook ends with `dbutils.notebook.exit(json.dumps(...))` so the structured result comes back via `get-run-output`.

## Optional: deploy a serving endpoint from the same notebook

If the demo also needs per-request scoring (app calls during a user action), append a cell that creates an endpoint using the same `new_version`. See the **Real-time serving endpoint** section in [SKILL.md](SKILL.md#consume-real-time-serving-endpoint). The endpoint takes ~5 min to come ready — don't block the job on it.
