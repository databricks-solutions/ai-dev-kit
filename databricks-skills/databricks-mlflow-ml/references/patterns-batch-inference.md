# patterns-batch-inference

Loading a UC-registered model and scoring features in batch. Two scales — interactive notebook (Pattern 1–2) and distributed Lakeflow pipeline (Patterns 3–4). Plus A/B validation (Pattern 5).

---

## Pattern 1: Notebook batch inference — pandas path

For interactive exploration, ad-hoc scoring, and sample sizes up to ~10k rows.

```python
import mlflow

mlflow.set_registry_uri("databricks-uc")

model = mlflow.pyfunc.load_model(
    "models:/my_catalog.my_schema.grocery_forecaster@champion"
)

# Load a sample of features (LIMIT in SQL to avoid loading full table)
features = (
    spark.table("my_catalog.my_schema.silver_features")
    .orderBy("month_date")
    .limit(1000)
    .toPandas()
)

# The model's signature determines which columns it expects
feature_cols = model.metadata.get_input_schema().input_names()

predictions = model.predict(features[feature_cols])

# Attach predictions for display/export
features["prediction"] = predictions
display(spark.createDataFrame(features))
```

---

## Pattern 2: Notebook batch inference with chart

Same pattern, adds a predicted-vs-actual visual. Useful as a demo artifact.

```python
import matplotlib.pyplot as plt

# (continuing from Pattern 1)
features_with_pred = features.sort_values("month_date")

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(features_with_pred["month_date"], features_with_pred["actual"],
        label="Actual", linewidth=2)
ax.plot(features_with_pred["month_date"], features_with_pred["prediction"],
        label="Predicted", linestyle="--", linewidth=2)
ax.set_xlabel("Month")
ax.set_ylabel("Turnover (millions)")
ax.set_title(f"Forecast — {model.metadata.run_id[:8]}")
ax.legend()
plt.xticks(rotation=45)
plt.tight_layout()
display(fig)
```

---

## Pattern 3: Lakeflow SDP batch via `spark_udf`

For scheduled batch inference at scale. Distributes across Spark executors — no per-row Python overhead, no serving endpoint.

```python
# src/gold/gold_forecast.py
import mlflow
import databricks.declarative_pipelines as dp

# Construct the UDF ONCE at module scope — see GOTCHAS #11
mlflow.set_registry_uri("databricks-uc")

MODEL_NAME = "my_catalog.my_schema.grocery_forecaster"
predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    model_uri=f"models:/{MODEL_NAME}@champion",
    result_type="double",
    env_manager="local",   # "local" avoids conda/virtualenv setup overhead
)

@dp.materialized_view(
    comment="Grocery turnover forecast from @champion model",
)
def gold_forecast():
    return (
        spark.read.table("my_catalog.my_schema.silver_features")
        .withColumn(
            "forecast_turnover_millions",
            predict_udf(
                "turnover_lag_1",
                "turnover_lag_12",
                "rolling_3m_avg",
                "state_share_of_national",
                # ... pass each signature input column in the order the signature declares
            ),
        )
    )
```

**What this gives you:**
- A `gold_forecast` table that refreshes on every pipeline run
- Distributed scoring (no serving endpoint, no auth token)
- Full UC lineage: `silver_features` → `gold_forecast` via `grocery_forecaster@champion`
- Genie can query it: *"what's the forecast for each state next month?"*

---

## Pattern 4: `spark_udf` with `result_type` for multi-output models

Multi-output regressors or classifiers need a richer result type.

```python
from pyspark.sql.types import ArrayType, DoubleType, StructType, StructField

# Multi-output regression — model returns 2 predictions per row
predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    model_uri=f"models:/{MODEL_NAME}@champion",
    result_type=ArrayType(DoubleType()),
)

# Classifier with probabilities
predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    model_uri=f"models:/{MODEL_NAME}@champion",
    result_type=StructType([
        StructField("class", StringType(), True),
        StructField("confidence", DoubleType(), True),
    ]),
)
```

---

## Pattern 5: A/B validation — compare `@challenger` vs `@champion`

Run both models on a validation set, compare error metrics, decide whether to promote.

```python
import mlflow
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

mlflow.set_registry_uri("databricks-uc")
MODEL_NAME = "my_catalog.my_schema.grocery_forecaster"

champion = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@champion")
challenger = mlflow.pyfunc.load_model(f"models:/{MODEL_NAME}@challenger")

# Hold-out validation set (not seen during training)
validation = spark.table(f"{MODEL_NAME.rsplit('.', 1)[0]}.validation_features").toPandas()
feature_cols = champion.metadata.get_input_schema().input_names()
actuals = validation["turnover_millions"]

champion_preds = champion.predict(validation[feature_cols])
challenger_preds = challenger.predict(validation[feature_cols])

print(f"Champion    RMSE: {root_mean_squared_error(actuals, champion_preds):.2f}")
print(f"Challenger  RMSE: {root_mean_squared_error(actuals, challenger_preds):.2f}")
print(f"Champion    MAE:  {mean_absolute_error(actuals, champion_preds):.2f}")
print(f"Challenger  MAE:  {mean_absolute_error(actuals, challenger_preds):.2f}")

# Decision logic — promote if challenger beats champion by >2%
if root_mean_squared_error(actuals, challenger_preds) < root_mean_squared_error(actuals, champion_preds) * 0.98:
    print("→ Promote @challenger. See patterns-uc-registration.md Pattern 5.")
else:
    print("→ Keep @champion. Delete @challenger.")
```

---

## Pattern 6: Structured streaming inference

For models scoring events as they arrive (not batch-scheduled).

```python
from pyspark.sql.functions import col

predict_udf = mlflow.pyfunc.spark_udf(
    spark,
    model_uri=f"models:/{MODEL_NAME}@champion",
    result_type="double",
)

events = (
    spark.readStream
    .format("delta")
    .table("my_catalog.my_schema.silver_events")
)

scored = events.withColumn(
    "prediction",
    predict_udf(*[col(c) for c in feature_cols]),
)

(
    scored.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", "dbfs:/Volumes/my_catalog/my_schema/checkpoints/scoring")
    .toTable("my_catalog.my_schema.gold_scored_events")
)
```

For most classic-ML batch use cases, Pattern 3 (Lakeflow SDP) is simpler. Use streaming only when event-time scoring matters.

---

## What NOT to do for batch inference

### Do not use `ai_query` for custom UC models

`ai_query('<custom-uc-model>', <input>)` requires the model to be deployed as a **Model Serving endpoint**. UC-registered models are NOT automatically behind an endpoint. Use `pyfunc.load_model` (Pattern 1) or `pyfunc.spark_udf` (Pattern 3) instead.

`ai_query` IS the right call for:
- Foundation Model API endpoints: `ai_query('databricks-dbrx-instruct', prompt)`
- Model Serving endpoints you've explicitly provisioned

See `GOTCHAS.md` #9.

### Do not use `mlflow.pyfunc.load_model` for billion-row batches on a single node

Pattern 1 collects to pandas — fine up to ~10k rows, painful beyond ~100k, impossible for millions. For distributed scale, use Pattern 3 (`spark_udf`).

### Do not construct `spark_udf` inside the function body

See `GOTCHAS.md` #11. Construct once at module scope, reuse inside `@dp.materialized_view` / `@dp.table`.

---

## Troubleshooting batch inference

| Error | Cause | Fix |
|-------|-------|-----|
| `RESOURCE_DOES_NOT_EXIST` on load | Wrong registry URI or two-level name | `GOTCHAS.md` #1, #2 |
| Predictions are NaN | Input columns in wrong order | Pass columns in the order `model.metadata.get_input_schema().input_names()` declares |
| `PERMISSION_DENIED: EXECUTE ON MODEL` | No read access to model | `GRANT EXECUTE ON MODEL ... TO <user>` |
| `spark_udf` raises `PicklingError` | Model has un-picklable state (e.g., Spark session) | Re-train ensuring the model is pure Python/numpy — don't capture `spark` at training time |
| Pipeline hangs on `gold_forecast` | Model artifact is large; first load is slow | Normal — subsequent runs are fast (UDF is cached per executor) |
| Column type mismatch in Spark | UDF expects double; column is int/string | Cast explicitly: `col("feature").cast("double")` |
