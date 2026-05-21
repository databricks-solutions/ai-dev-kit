# Custom pyfunc model

When sklearn / XGBoost autolog isn't enough: custom preprocessing not captured by a sklearn pipeline, multiple sub-models behind one endpoint, external API calls during inference, business-logic-heavy post-processing.

Same UC registry + serving story as classical ML — only the *logging* step changes.

## End-to-end example: file-based pyfunc with preprocessing + sub-model

Project layout:

```
my_model/
├── model.py        # PythonModel + mlflow.models.set_model(...)
├── log_model.py    # Logs + registers to UC
└── artifacts/
    ├── preprocessor.pkl
    └── booster.json
```

```python
# model.py — logged verbatim via python_model="model.py" (Models from Code).
# DO NOT pickle a class instance; use this file-path pattern instead.
import json, pickle, pandas as pd
import mlflow
from mlflow.pyfunc import PythonModel

class TurbineRiskModel(PythonModel):
    def load_context(self, context):
        with open(context.artifacts["preprocessor"], "rb") as f:
            self.pre = pickle.load(f)
        from xgboost import Booster
        self.booster = Booster()
        self.booster.load_model(context.artifacts["booster"])

    def predict(self, context, model_input: pd.DataFrame, params=None) -> pd.DataFrame:
        X = self.pre.transform(model_input)
        proba = self.booster.predict(X)
        return pd.DataFrame({
            "risk_score": proba,
            "risk_level": ["HIGH" if p > 0.7 else "MEDIUM" if p > 0.4 else "LOW" for p in proba],
        })

mlflow.models.set_model(TurbineRiskModel())
```

```python
# log_model.py
import mlflow
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Users/me@example.com/turbine_risk")

CATALOG, SCHEMA, NAME = "ai_demo_gen", "wind_farm", "turbine_risk"
FULL_NAME = f"{CATALOG}.{SCHEMA}.{NAME}"

sample_input = pd.DataFrame({"vib_rms": [0.4], "rpm_mean": [18.2], "bearing_temp_max": [71.3]})
sample_output = pd.DataFrame({"risk_score": [0.0], "risk_level": ["LOW"]})

with mlflow.start_run():
    info = mlflow.pyfunc.log_model(
        name="model",
        python_model="model.py",           # file path, not an instance
        artifacts={
            "preprocessor": "artifacts/preprocessor.pkl",
            "booster":      "artifacts/booster.json",
        },
        signature=infer_signature(sample_input, sample_output),
        input_example=sample_input,
        # Pin exact versions — endpoint rebuilds the env from these:
        pip_requirements=["mlflow==2.22.0", "xgboost==2.1.3", "scikit-learn==1.5.2", "pandas"],
        # Extra modules to ship with the model (e.g. shared util libs):
        # code_paths=["src/utils.py"],
        registered_model_name=FULL_NAME,
    )

# Pre-deploy validation — rebuilds the env locally and runs predict().
# Catches missing deps / signature drift BEFORE the endpoint does.
mlflow.models.predict(
    model_uri=info.model_uri,
    input_data=sample_input,
    env_manager="uv",   # MLflow ≥ 2.22; falls back to "virtualenv" otherwise
)

# Promote to @prod
client = MlflowClient(registry_uri="databricks-uc")
v = max(client.search_model_versions(f"name='{FULL_NAME}'"), key=lambda x: int(x.version)).version
client.set_registered_model_alias(FULL_NAME, "prod", v)
```

## Why file-based (`python_model="model.py"`)

- **No class pickling**: the file is logged verbatim. Avoids the "I trained on Python 3.10 but the endpoint runs 3.11 and unpickling crashes" class of bugs.
- **Lets `code_paths=[...]`** ship companion modules the file imports.
- **`mlflow.models.set_model(instance)`** at the bottom of the file is the contract — exactly one call, exactly one instance.

## Consume

Same two paths as autologged classical ML — see [SKILL.md](SKILL.md#consume-batch-scoring-over-delta).

- **Batch**: `mlflow.pyfunc.spark_udf(spark, model_uri=f"models:/{FULL_NAME}@prod", env_manager="local")` over a Delta table.
- **Real-time**: `client.create_endpoint(...)` (see SKILL.md). Query returns a DataFrame-shaped JSON since `predict` returns a DataFrame.

```bash
databricks serving-endpoints query turbine-risk-endpoint --json '{
  "dataframe_records": [{"vib_rms": 0.6, "rpm_mean": 19.0, "bearing_temp_max": 78.0}]
}'
# → {"predictions": [{"risk_score": 0.82, "risk_level": "HIGH"}]}
```
