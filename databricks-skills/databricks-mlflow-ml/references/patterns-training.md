# patterns-training

How to log classic ML models (sklearn / XGBoost / PyTorch) so they register cleanly and load correctly downstream. The two load-bearing decisions: `signature` and `input_example`.

---

## Pattern 1: Baseline sklearn training loop

```python
import mlflow
import mlflow.sklearn
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import root_mean_squared_error, mean_absolute_error
from sklearn.model_selection import train_test_split
from mlflow.models import infer_signature

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(
    experiment_name="/Users/me@company.com/forecasting",
    artifact_location="dbfs:/Volumes/my_catalog/my_schema/mlflow_artifacts/forecasting",
)

X_train, X_test, y_train, y_test = train_test_split(features, target, test_size=0.2)

with mlflow.start_run(run_name="gbr_baseline"):
    model = GradientBoostingRegressor(n_estimators=100, max_depth=3)
    model.fit(X_train, y_train)

    # Signature + input_example are both load-bearing
    signature = infer_signature(X_train, model.predict(X_train[:5]))

    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        signature=signature,
        input_example=X_train.iloc[:5],
    )

    # Log everything needed to reproduce
    mlflow.log_params({"n_estimators": 100, "max_depth": 3})
    predictions = model.predict(X_test)
    mlflow.log_metrics({
        "rmse": root_mean_squared_error(y_test, predictions),
        "mae": mean_absolute_error(y_test, predictions),
    })
```

---

## Pattern 2: Preprocessing + model as a Pipeline

Always log preprocessing alongside the model. See `GOTCHAS.md` #12 — inference-time preprocessing drift is the most painful post-registration bug.

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.compose import ColumnTransformer

numeric_features = ["turnover_lag_1", "turnover_lag_12", "rolling_3m_avg"]
categorical_features = ["state", "industry"]

preprocessor = ColumnTransformer([
    ("num", StandardScaler(), numeric_features),
    ("cat", "passthrough", categorical_features),    # handle in the model if needed
])

pipeline = Pipeline([
    ("preprocessor", preprocessor),
    ("model", GradientBoostingRegressor(n_estimators=100)),
])

with mlflow.start_run():
    pipeline.fit(X_train, y_train)

    signature = infer_signature(X_train, pipeline.predict(X_train[:5]))
    mlflow.sklearn.log_model(
        sk_model=pipeline,    # logs both preprocessor AND model as one artifact
        artifact_path="model",
        signature=signature,
        input_example=X_train.iloc[:5],
    )
```

At inference time, callers never need to know about `StandardScaler` — they pass raw features, `pyfunc.load_model` dispatches through the pipeline.

---

## Pattern 3: XGBoost / PyTorch — same interface, different flavor

```python
# XGBoost
import mlflow.xgboost
import xgboost as xgb

model = xgb.XGBRegressor(n_estimators=100, max_depth=3)
model.fit(X_train, y_train)

with mlflow.start_run():
    mlflow.xgboost.log_model(
        xgb_model=model,
        artifact_path="model",
        signature=infer_signature(X_train, model.predict(X_train[:5])),
        input_example=X_train.iloc[:5],
    )

# PyTorch
import mlflow.pytorch
import torch

class Forecaster(torch.nn.Module):
    ...

model = Forecaster()
# ... training loop ...

with mlflow.start_run():
    # For PyTorch, input_example must be a tensor or numpy array
    example = X_train.iloc[:5].to_numpy()
    mlflow.pytorch.log_model(
        pytorch_model=model,
        artifact_path="model",
        signature=infer_signature(example, model(torch.tensor(example)).detach().numpy()),
        input_example=example,
    )
```

---

## Pattern 4: Retraining — same experiment, new run

Retraining for an A/B test or a scheduled refresh. Log to the same experiment; register as a new version in Workflow 2.

```python
with mlflow.start_run(run_name="gbr_v2_with_seasonality") as run:
    model = GradientBoostingRegressor(n_estimators=200, max_depth=4)
    model.fit(X_train_with_seasonality, y_train)

    mlflow.sklearn.log_model(
        sk_model=model,
        artifact_path="model",
        signature=infer_signature(X_train_with_seasonality,
                                  model.predict(X_train_with_seasonality[:5])),
        input_example=X_train_with_seasonality.iloc[:5],
    )
    # Remember the run_id for the register step
    print(f"New run: {run.info.run_id}")
```

---

## Pattern 5: Autologging (quick path for iteration)

Autologging wraps `fit()` and logs params + metrics + model automatically. Convenient during experimentation; less explicit than manual logging.

```python
mlflow.sklearn.autolog(
    log_models=True,
    log_input_examples=True,       # IMPORTANT — otherwise no input_example is captured
    log_model_signatures=True,     # IMPORTANT — otherwise no signature is captured
    silent=False,
)

# Any subsequent fit() call auto-logs
model = GradientBoostingRegressor(n_estimators=100)
model.fit(X_train, y_train)
# Autolog handled the MLflow calls
```

**Caveat:** autologging infers signature + input_example heuristically. For production runs, prefer manual logging (Pattern 1) — you control what gets captured.

---

## Pattern 6: Searching runs to pick the best one for registration

Before registering, you typically want the best run from an experiment:

```python
runs = mlflow.search_runs(
    experiment_names=["/Users/me@company.com/forecasting"],
    filter_string="metrics.rmse < 100 AND tags.mlflow.runName LIKE 'gbr_%'",
    order_by=["metrics.rmse ASC"],
    max_results=1,
)

if runs.empty:
    raise RuntimeError("No runs match criteria")

best_run_id = runs.iloc[0]["run_id"]
best_rmse = runs.iloc[0]["metrics.rmse"]
print(f"Best run: {best_run_id} (RMSE={best_rmse:.2f})")

# Now register this run's model — see patterns-uc-registration.md Pattern 1
```

---

## Common logging mistakes

| Mistake | Effect | Fix |
|---------|--------|-----|
| No `signature` | `pyfunc.load_model` works, but `.predict()` coerces wrong | Always call `infer_signature(X_train, y_hat[:5])` |
| No `input_example` | `pyfunc.load_model` can't introspect input schema | Pass `X_train.iloc[:5]` (or `.to_numpy()[:5]` for non-pandas) |
| `artifact_path` changes between logs | Same model name → different paths → broken load URIs | Always use `artifact_path="model"` |
| Log preprocessing separately | Inference callers must reapply preprocessing manually | Wrap in a sklearn `Pipeline` and log the pipeline |
| Use `pickle.dump` directly | Loses MLflow's flavor dispatch | Always use `mlflow.<flavor>.log_model` |
