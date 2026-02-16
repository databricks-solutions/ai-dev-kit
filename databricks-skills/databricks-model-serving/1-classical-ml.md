# Classical ML Model Serving

Deploy traditional ML models (sklearn, xgboost, pytorch, etc.) with MLflow autolog.

## Autolog Pattern (Recommended)

The simplest way to deploy ML models - train and everything is logged automatically.

```python
import mlflow
import mlflow.sklearn
from sklearn.linear_model import ElasticNet
from sklearn.model_selection import train_test_split

# Configuration
catalog = "main"
schema = "models"
model_name = "diabetes_predictor"

# Enable autolog with auto-registration to Unity Catalog
mlflow.sklearn.autolog(
    log_input_examples=True,
    registered_model_name=f"{catalog}.{schema}.{model_name}"
)

# Load and split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25)

# Train - model is logged and registered automatically
model = ElasticNet(alpha=0.05, l1_ratio=0.05)
model.fit(X_train, y_train)

# That's it! Model is now in Unity Catalog ready for serving
```

## Supported Frameworks

| Framework | Autolog Function | Notes |
|-----------|------------------|-------|
| sklearn | `mlflow.sklearn.autolog()` | Most sklearn estimators |
| xgboost | `mlflow.xgboost.autolog()` | XGBClassifier, XGBRegressor |
| lightgbm | `mlflow.lightgbm.autolog()` | LGBMClassifier, etc. |
| pytorch | `mlflow.pytorch.autolog()` | Lightning supported |
| tensorflow | `mlflow.tensorflow.autolog()` | Keras models |
| spark | `mlflow.spark.autolog()` | Spark ML pipelines |

## Manual Logging (When Autolog Isn't Enough)

```python
import mlflow
from sklearn.ensemble import RandomForestClassifier

mlflow.set_registry_uri("databricks-uc")

with mlflow.start_run():
    # Train model
    model = RandomForestClassifier(n_estimators=100)
    model.fit(X_train, y_train)
    
    # Log metrics
    accuracy = model.score(X_test, y_test)
    mlflow.log_metric("accuracy", accuracy)
    
    # Log model with signature
    from mlflow.models import infer_signature
    signature = infer_signature(X_train, model.predict(X_train))
    
    model_info = mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        signature=signature,
        input_example=X_train[:5],
        registered_model_name="main.models.random_forest"
    )
```

## Deploy to Serving Endpoint

### Option 1: Databricks UI

1. Go to **Serving** in the workspace
2. Click **Create serving endpoint**
3. Select your model from Unity Catalog
4. Configure scaling (workload size, scale-to-zero)
5. Click **Create**

### Option 2: MLflow Deployments SDK

```python
from mlflow.deployments import get_deploy_client

mlflow.set_registry_uri("databricks-uc")
client = get_deploy_client("databricks")

endpoint = client.create_endpoint(
    name="diabetes-predictor",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.diabetes_predictor",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ],
        "traffic_config": {
            "routes": [
                {
                    "served_model_name": "diabetes_predictor-1",
                    "traffic_percentage": 100
                }
            ]
        }
    }
)
```

### Option 3: Databricks SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="diabetes-predictor",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.diabetes_predictor",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ]
    },
    timeout=timedelta(minutes=30)
)
```

## Query the Endpoint

### Via MCP Tool

```
query_serving_endpoint(
    name="diabetes-predictor",
    dataframe_records=[
        {"age": 45, "bmi": 25.3, "bp": 120, "s1": 200}
    ]
)
```

### Via Python SDK

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
response = w.serving_endpoints.query(
    name="diabetes-predictor",
    dataframe_records=[
        {"age": 45, "bmi": 25.3, "bp": 120, "s1": 200}
    ]
)
print(response.predictions)
```

## Best Practices

1. **Always use `log_input_examples=True`** - helps with debugging and schema inference
2. **Use Unity Catalog** - `registered_model_name="catalog.schema.model"`
3. **Enable scale-to-zero** - saves costs when endpoint is idle
4. **Test locally first** - use `mlflow.pyfunc.load_model()` before deploying
5. **Version your models** - UC tracks versions automatically
