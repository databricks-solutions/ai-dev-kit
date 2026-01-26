# Custom Model Serving

Deploy your ML and Python models from Unity Catalog as scalable REST API endpoints.

---

## Prerequisites

1. **Model registered in Unity Catalog**:
   ```python
   import mlflow
   mlflow.set_registry_uri("databricks-uc")
   
   with mlflow.start_run():
       mlflow.sklearn.log_model(
           model,
           artifact_path="model",
           registered_model_name="catalog.schema.my_model"
       )
   ```

2. **Permissions**: `USE CATALOG`, `USE SCHEMA`, `EXECUTE` on the model

---

## Basic Deployment

### CPU Endpoint

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import EndpointCoreConfigInput, ServedEntityInput

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="my-sklearn-model",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                entity_name="catalog.schema.my_model",
                entity_version="1",
                workload_size="Small",
                scale_to_zero_enabled=True,
            )
        ]
    ),
)
```

### GPU Endpoint

```python
endpoint = w.serving_endpoints.create_and_wait(
    name="my-pytorch-model",
    config=EndpointCoreConfigInput(
        served_entities=[
            ServedEntityInput(
                entity_name="catalog.schema.pytorch_model",
                entity_version="1",
                workload_type="GPU_SMALL",  # T4 GPU
                workload_size="Small",
                scale_to_zero_enabled=False,  # Keep warm for faster inference
            )
        ]
    ),
)
```

---

## Workload Configuration

### CPU Workload Sizes

| Size | CPU Cores | Memory | Concurrent Requests |
|------|-----------|--------|---------------------|
| `Small` | 4 | 16GB | ~4 |
| `Medium` | 8 | 32GB | ~8 |
| `Large` | 16 | 64GB | ~16 |

### GPU Workload Types

| Type | GPU | VRAM | Best For |
|------|-----|------|----------|
| `GPU_SMALL` | 1x T4 | 16GB | Small models, embeddings |
| `GPU_MEDIUM` | 1x A10G | 24GB | Medium models, fine-tuned LLMs |
| `GPU_LARGE` | 1x A100 | 40GB | Large models, LLMs up to 13B |
| `GPU_LARGE_2` | 2x A100 | 80GB | Very large models, 70B+ |

### Autoscaling

```python
ServedEntityInput(
    entity_name="catalog.schema.my_model",
    entity_version="1",
    workload_size="Small",
    scale_to_zero_enabled=True,
    # Concurrency-based scaling
    min_provisioned_throughput=0,    # Scale to zero
    max_provisioned_throughput=100,  # Max concurrent requests
)
```

---

## Environment Variables

Pass configuration to your model at runtime:

```python
ServedEntityInput(
    entity_name="catalog.schema.my_model",
    entity_version="1",
    workload_size="Small",
    environment_vars={
        "MODEL_CONFIG": "production",
        "LOG_LEVEL": "INFO",
        # Reference secrets securely
        "API_KEY": "{{secrets/my-scope/api-key}}",
    },
)
```

---

## Model Input/Output Formats

### Dataframe Records (Most Common)

```python
# Query with records format
response = w.serving_endpoints.query(
    name="my-model",
    dataframe_records=[
        {"feature1": 1.0, "feature2": "A", "feature3": 100},
        {"feature1": 2.0, "feature2": "B", "feature3": 200},
    ],
)
print(response.predictions)  # [0.85, 0.23]
```

### Dataframe Split Format

```python
# Query with split format (columns + data)
response = w.serving_endpoints.query(
    name="my-model",
    dataframe_split={
        "columns": ["feature1", "feature2", "feature3"],
        "data": [
            [1.0, "A", 100],
            [2.0, "B", 200],
        ],
    },
)
```

### Tensor Input (PyTorch/TensorFlow)

```python
# Row-oriented (instances)
response = w.serving_endpoints.query(
    name="my-model",
    instances=[
        [[1.0, 2.0, 3.0]],  # Batch of tensors
    ],
)

# Column-oriented (inputs)
response = w.serving_endpoints.query(
    name="my-model",
    inputs={
        "input_tensor": [[1.0, 2.0, 3.0]],
    },
)
```

---

## Deploying Different Model Types

### Scikit-learn

```python
import mlflow.sklearn

with mlflow.start_run():
    mlflow.sklearn.log_model(
        model,
        artifact_path="model",
        registered_model_name="catalog.schema.sklearn_model",
        input_example=X_train[:5],  # Helps with schema inference
    )
```

### PyTorch

```python
import mlflow.pytorch

with mlflow.start_run():
    mlflow.pytorch.log_model(
        model,
        artifact_path="model",
        registered_model_name="catalog.schema.pytorch_model",
        input_example=sample_input,
    )
```

### Custom Python Model (PyFunc)

```python
import mlflow.pyfunc

class MyCustomModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        # Load artifacts, initialize resources
        import torch
        self.model = torch.load(context.artifacts["model_path"])
    
    def predict(self, context, model_input):
        # model_input is a pandas DataFrame
        return self.model(model_input.values)

with mlflow.start_run():
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=MyCustomModel(),
        artifacts={"model_path": "/path/to/model.pt"},
        registered_model_name="catalog.schema.custom_model",
        pip_requirements=["torch>=2.0", "numpy"],
    )
```

### Hugging Face Transformers

```python
import mlflow.transformers

with mlflow.start_run():
    mlflow.transformers.log_model(
        transformers_model={
            "model": model,
            "tokenizer": tokenizer,
        },
        artifact_path="model",
        registered_model_name="catalog.schema.hf_model",
        task="text-generation",
    )
```

---

## Updating Endpoints

### Update Model Version

```python
w.serving_endpoints.update_config_and_wait(
    name="my-model",
    served_entities=[
        ServedEntityInput(
            entity_name="catalog.schema.my_model",
            entity_version="2",  # New version
            workload_size="Small",
            scale_to_zero_enabled=True,
        )
    ],
)
```

### Blue-Green Deployment (Traffic Splitting)

```python
from databricks.sdk.service.serving import TrafficConfig, Route

w.serving_endpoints.update_config_and_wait(
    name="my-model",
    served_entities=[
        ServedEntityInput(
            name="model-v1",
            entity_name="catalog.schema.my_model",
            entity_version="1",
            workload_size="Small",
        ),
        ServedEntityInput(
            name="model-v2",
            entity_name="catalog.schema.my_model",
            entity_version="2",
            workload_size="Small",
        ),
    ],
    traffic_config=TrafficConfig(
        routes=[
            Route(served_model_name="model-v1", traffic_percentage=90),
            Route(served_model_name="model-v2", traffic_percentage=10),
        ]
    ),
)
```

---

## Debugging

### Get Build Logs

```python
logs = w.serving_endpoints.build_logs(
    name="my-model",
    served_model_name="my-model-1",  # Usually entity_name-version
)
print(logs.logs)
```

### Check Endpoint State

```python
endpoint = w.serving_endpoints.get(name="my-model")
print(f"Ready: {endpoint.state.ready}")
print(f"Config update: {endpoint.state.config_update}")

# Check pending config if updating
if endpoint.pending_config:
    for entity in endpoint.pending_config.served_entities:
        print(f"  {entity.name}: {entity.state}")
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **"Entity not found"** | Use full UC path: `catalog.schema.model` |
| **Build fails** | Check logs, verify pip requirements are correct |
| **Slow cold start** | Disable scale-to-zero or pre-warm endpoint |
| **OOM errors** | Increase workload size or use GPU |
| **Prediction errors** | Check input schema matches model signature |
| **Permission denied** | Grant `EXECUTE` on model to service principal |
