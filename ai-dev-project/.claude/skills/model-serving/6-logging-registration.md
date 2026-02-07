# Logging & Registration

Log models to MLflow and register to Unity Catalog.

## File-Based Logging (Recommended for Agents)

Log from a Python file instead of a class instance:

```python
# log_model.py
import mlflow
from agent import AGENT, LLM_ENDPOINT
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksFunction
from unitycatalog.ai.langchain.toolkit import UnityCatalogTool
from databricks_langchain import VectorSearchRetrieverTool

mlflow.set_registry_uri("databricks-uc")

# Collect resources for auto authentication
resources = [DatabricksServingEndpoint(endpoint_name=LLM_ENDPOINT)]

# Add UC function resources
from agent import tools  # If your agent exports tools
for tool in tools:
    if isinstance(tool, UnityCatalogTool):
        resources.append(DatabricksFunction(function_name=tool.uc_function_name))
    elif isinstance(tool, VectorSearchRetrieverTool):
        resources.extend(tool.resources)

# Input example
input_example = {
    "input": [{"role": "user", "content": "What is Databricks?"}]
}

# Log model
with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        name="agent",
        python_model="agent.py",  # File path
        input_example=input_example,
        resources=resources,
        pip_requirements=[
            "mlflow==3.6.0",
            "databricks-langchain",
            "langgraph==0.3.4",
            "pydantic",
        ],
    )
    print(f"Model URI: {model_info.model_uri}")

# Register to Unity Catalog
catalog = "main"
schema = "agents"
model_name = "my_agent"

uc_model_info = mlflow.register_model(
    model_uri=model_info.model_uri,
    name=f"{catalog}.{schema}.{model_name}"
)
print(f"Registered: {uc_model_info.name} version {uc_model_info.version}")
```

Run via MCP:

```
run_python_file_on_databricks(file_path="./my_agent/log_model.py")
```

## Resources for Auto Authentication

Databricks automatically provisions credentials for these resource types:

| Resource Type | Import | Usage |
|--------------|--------|-------|
| `DatabricksServingEndpoint` | `mlflow.models.resources` | LLM endpoints |
| `DatabricksFunction` | `mlflow.models.resources` | UC SQL/Python functions |
| `DatabricksVectorSearchIndex` | `mlflow.models.resources` | Vector Search indexes |
| `DatabricksLakebase` | `mlflow.models.resources` | Lakebase instances |

```python
from mlflow.models.resources import (
    DatabricksServingEndpoint,
    DatabricksFunction,
    DatabricksVectorSearchIndex,
    DatabricksLakebase,
)

resources = [
    DatabricksServingEndpoint(endpoint_name="databricks-meta-llama-3-3-70b-instruct"),
    DatabricksFunction(function_name="catalog.schema.my_function"),
    DatabricksVectorSearchIndex(index_name="catalog.schema.my_index"),
    DatabricksLakebase(database_instance_name="my-lakebase"),
]
```

## pip_requirements

### Recommended Versions (Tested)

```python
pip_requirements=[
    "mlflow==3.6.0",
    "databricks-langchain",  # Latest
    "langgraph==0.3.4",
    "pydantic",
    "databricks-agents",
]
```

### With Memory Support

```python
pip_requirements=[
    "mlflow==3.6.0",
    "databricks-langchain[memory]",  # Includes Lakebase support
    "langgraph==0.3.4",
]
```

### Get Current Versions

```python
from pkg_resources import get_distribution

pip_requirements=[
    f"mlflow=={get_distribution('mlflow').version}",
    f"databricks-langchain=={get_distribution('databricks-langchain').version}",
]
```

## Pre-Deployment Validation

Before deploying, validate the model loads and runs:

```python
# Validate locally (uses uv for fast env creation)
mlflow.models.predict(
    model_uri=model_info.model_uri,
    input_data={"input": [{"role": "user", "content": "Test"}]},
    env_manager="uv",
)
```

Run via MCP (in log_model.py or separate file):

```python
# validate_model.py
import mlflow

# Get model URI from previous step
model_uri = "runs:/<run_id>/agent"  # Or from UC: "models:/catalog.schema.model/1"

result = mlflow.models.predict(
    model_uri=model_uri,
    input_data={"input": [{"role": "user", "content": "Hello"}]},
    env_manager="uv",
)
print("Validation result:", result)
```

## Classical ML Logging

For traditional ML models, autolog handles everything:

```python
import mlflow
import mlflow.sklearn

mlflow.sklearn.autolog(
    log_input_examples=True,
    registered_model_name="main.models.my_model"
)

# Train - automatically logged and registered
model.fit(X_train, y_train)
```

## Manual Registration (Separate Step)

If you logged without registering:

```python
import mlflow

mlflow.set_registry_uri("databricks-uc")

# From run
mlflow.register_model(
    model_uri="runs:/<run_id>/agent",
    name="main.agents.my_agent"
)

# From logged model info
mlflow.register_model(
    model_uri=model_info.model_uri,
    name="main.agents.my_agent"
)
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **Package not found at serving time** | Specify exact versions in `pip_requirements` |
| **Auth error accessing endpoint** | Add resource to `resources` list |
| **Model signature mismatch** | Provide `input_example` matching your input format |
| **Slow model loading** | Use `env_manager="uv"` for faster validation |
| **Code not found** | Use `code_paths=["file.py"]` for additional dependencies |
