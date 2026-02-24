# Custom PyFunc Models

Deploy custom Python models with preprocessing, postprocessing, or complex logic.

## When to Use Custom PyFunc

- Custom preprocessing not captured in sklearn pipeline
- Multiple models in one endpoint
- Custom output formatting
- External API calls during inference
- Complex business logic

## Basic Pattern

```python
import mlflow
import pandas as pd

class MyCustomModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        """Load artifacts when model is loaded."""
        import pickle
        with open(context.artifacts["preprocessor"], "rb") as f:
            self.preprocessor = pickle.load(f)
        with open(context.artifacts["model"], "rb") as f:
            self.model = pickle.load(f)
    
    def predict(self, context, model_input: pd.DataFrame) -> pd.DataFrame:
        """Run prediction with preprocessing."""
        # Preprocess
        processed = self.preprocessor.transform(model_input)
        # Predict
        predictions = self.model.predict(processed)
        # Return as DataFrame
        return pd.DataFrame({"prediction": predictions})

# Log the model
with mlflow.start_run():
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=MyCustomModel(),
        artifacts={
            "preprocessor": "artifacts/preprocessor.pkl",
            "model": "artifacts/model.pkl"
        },
        pip_requirements=["scikit-learn==1.3.0", "pandas"],
        registered_model_name="main.models.custom_model"
    )
```

## With Model Signature

```python
from mlflow.models import infer_signature, ModelSignature
from mlflow.types.schema import Schema, ColSpec

# Option 1: Infer from data
signature = infer_signature(
    model_input=X_sample,
    model_output=predictions_sample
)

# Option 2: Define explicitly
input_schema = Schema([
    ColSpec("double", "age"),
    ColSpec("double", "income"),
    ColSpec("string", "category"),
])
output_schema = Schema([
    ColSpec("double", "probability"),
    ColSpec("string", "class"),
])
signature = ModelSignature(inputs=input_schema, outputs=output_schema)

mlflow.pyfunc.log_model(
    artifact_path="model",
    python_model=MyModel(),
    signature=signature,
    input_example={"age": 25, "income": 50000, "category": "A"},
    registered_model_name="main.models.my_model"
)
```

## File-Based Logging (Models from Code)

For complex models, log from a Python file instead of a class instance:

```python
# my_model.py
import mlflow
from mlflow.pyfunc import PythonModel

class MyModel(PythonModel):
    def predict(self, context, model_input):
        # Your prediction logic
        return model_input * 2

# Export the model instance
mlflow.models.set_model(MyModel())
```

```python
# log_model.py
import mlflow

mlflow.set_registry_uri("databricks-uc")

with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        name="my-model",
        python_model="my_model.py",  # File path, not instance
        pip_requirements=["mlflow>=3.0"],
        registered_model_name="main.models.my_model"
    )
```

## With External Dependencies

```python
mlflow.pyfunc.log_model(
    artifact_path="model",
    python_model=MyModel(),
    pip_requirements=[
        "scikit-learn==1.3.0",
        "pandas==2.0.0",
        "numpy==1.24.0",
        "requests>=2.28.0",  # For external API calls
    ],
    # Or reference a requirements file
    # pip_requirements="requirements.txt",
    registered_model_name="main.models.my_model"
)
```

## With Code Dependencies

```python
mlflow.pyfunc.log_model(
    artifact_path="model",
    python_model=MyModel(),
    code_paths=["src/utils.py", "src/preprocessing.py"],
    pip_requirements=["scikit-learn"],
    registered_model_name="main.models.my_model"
)
```

## Testing Before Deployment

```python
# Load and test locally
loaded_model = mlflow.pyfunc.load_model(model_info.model_uri)

# Test prediction
test_input = pd.DataFrame({"age": [25], "income": [50000]})
result = loaded_model.predict(test_input)
print(result)

# Pre-deployment validation
mlflow.models.predict(
    model_uri=model_info.model_uri,
    input_data={"age": 25, "income": 50000},
    env_manager="uv",  # Use uv for faster env creation
)
```

## Deploy Custom Model

Same as classical ML - use UI, MLflow SDK, or Databricks SDK:

```python
from mlflow.deployments import get_deploy_client

client = get_deploy_client("databricks")
endpoint = client.create_endpoint(
    name="custom-model-endpoint",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.custom_model",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ]
    }
)
```

## Query Custom Model

```
query_serving_endpoint(
    name="custom-model-endpoint",
    dataframe_records=[
        {"age": 25, "income": 50000, "category": "A"}
    ]
)
```

Or with inputs format:

```
query_serving_endpoint(
    name="custom-model-endpoint",
    inputs={"age": 25, "income": 50000, "category": "A"}
)
```
