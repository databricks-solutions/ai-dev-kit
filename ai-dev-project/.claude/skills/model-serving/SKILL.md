---
name: model-serving
description: "Deploy and query Databricks Model Serving endpoints. Use when (1) deploying MLflow models or AI agents to endpoints, (2) creating ChatAgent/ResponsesAgent agents, (3) integrating UC Functions or Vector Search tools, (4) querying deployed endpoints, (5) checking endpoint status. Covers classical ML models, custom pyfunc, and GenAI agents."
---

# Databricks Model Serving

Deploy MLflow models and AI agents to scalable REST API endpoints.

## Quick Decision: What Are You Deploying?

| Model Type | Pattern | Reference |
|------------|---------|-----------|
| **Traditional ML** (sklearn, xgboost) | `mlflow.sklearn.autolog()` | [1-classical-ml.md](1-classical-ml.md) |
| **Custom Python model** | `mlflow.pyfunc.PythonModel` | [2-custom-pyfunc.md](2-custom-pyfunc.md) |
| **GenAI Agent** (LangGraph, tool-calling) | `ResponsesAgent` | [3-genai-agents.md](3-genai-agents.md) |

## Prerequisites

- **DBR 16.1+** recommended (pre-installed GenAI packages)
- Unity Catalog enabled workspace
- Model Serving enabled

## Reference Files

| Topic | File | When to Read |
|-------|------|--------------|
| Classical ML | [1-classical-ml.md](1-classical-ml.md) | sklearn, xgboost, autolog |
| Custom PyFunc | [2-custom-pyfunc.md](2-custom-pyfunc.md) | Custom preprocessing, signatures |
| GenAI Agents | [3-genai-agents.md](3-genai-agents.md) | ResponsesAgent, LangGraph |
| Tools Integration | [4-tools-integration.md](4-tools-integration.md) | UC Functions, Vector Search |
| Development & Testing | [5-development-testing.md](5-development-testing.md) | MCP workflow, iteration |
| Logging & Registration | [6-logging-registration.md](6-logging-registration.md) | mlflow.pyfunc.log_model |
| Deployment | [7-deployment.md](7-deployment.md) | Job-based async deployment |
| Querying Endpoints | [8-querying-endpoints.md](8-querying-endpoints.md) | SDK, REST, MCP tools |
| Package Requirements | [9-package-requirements.md](9-package-requirements.md) | DBR versions, pip |

---

## Quick Start: Deploy a GenAI Agent

### Step 1: Install Packages (in notebook or via MCP)

```python
%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic
dbutils.library.restartPython()
```

Or via MCP:
```
execute_databricks_command(code="%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic")
```

### Step 2: Create Agent File

Create `agent.py` locally with `ResponsesAgent` pattern (see [3-genai-agents.md](3-genai-agents.md)).

### Step 3: Upload to Workspace

```
upload_folder(
    local_folder="./my_agent",
    workspace_folder="/Workspace/Users/you@company.com/my_agent"
)
```

### Step 4: Test Agent

```
run_python_file_on_databricks(
    file_path="./my_agent/test_agent.py",
    cluster_id="<cluster_id>"
)
```

### Step 5: Log Model

```
run_python_file_on_databricks(
    file_path="./my_agent/log_model.py",
    cluster_id="<cluster_id>"
)
```

### Step 6: Deploy (Async via Job)

See [7-deployment.md](7-deployment.md) for job-based deployment that doesn't timeout.

### Step 7: Query Endpoint

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

---

## Quick Start: Deploy a Classical ML Model

```python
import mlflow
import mlflow.sklearn
from sklearn.linear_model import LogisticRegression

# Enable autolog with auto-registration
mlflow.sklearn.autolog(
    log_input_examples=True,
    registered_model_name="main.models.my_classifier"
)

# Train - model is logged and registered automatically
model = LogisticRegression()
model.fit(X_train, y_train)
```

Then deploy via UI or SDK. See [1-classical-ml.md](1-classical-ml.md).

---

## MCP Tools

> **If MCP tools are not available**, use the SDK/CLI examples in the reference files below.

### Development & Testing

| Tool | Purpose |
|------|---------|
| `upload_folder` | Upload agent files to workspace |
| `run_python_file_on_databricks` | Test agent, log model |
| `execute_databricks_command` | Install packages, quick tests |

### Deployment

| Tool | Purpose |
|------|---------|
| `create_job` | Create deployment job (one-time) |
| `run_job_now` | Kick off deployment (async) |
| `get_run` | Check deployment job status |

### Querying

| Tool | Purpose |
|------|---------|
| `get_serving_endpoint_status` | Check if endpoint is READY |
| `query_serving_endpoint` | Send requests to endpoint |
| `list_serving_endpoints` | List all endpoints |

---

## Common Workflows

### Check Endpoint Status After Deployment

```
get_serving_endpoint_status(name="my-agent-endpoint")
```

Returns:
```json
{
    "name": "my-agent-endpoint",
    "state": "READY",
    "served_entities": [...]
}
```

### Query a Chat/Agent Endpoint

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[
        {"role": "user", "content": "What is Databricks?"}
    ],
    max_tokens=500
)
```

### Query a Traditional ML Endpoint

```
query_serving_endpoint(
    name="sklearn-classifier",
    dataframe_records=[
        {"age": 25, "income": 50000, "credit_score": 720}
    ]
)
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Invalid output format** | Use `self.create_text_output_item(text, id)` - NOT raw dicts! |
| **Endpoint NOT_READY** | Deployment takes ~15 min. Use `get_serving_endpoint_status` to poll. |
| **Package not found** | Specify exact versions in `pip_requirements` when logging model |
| **Tool timeout** | Use job-based deployment, not synchronous calls |
| **Auth error on endpoint** | Ensure `resources` specified in `log_model` for auto passthrough |
| **Model not found** | Check Unity Catalog path: `catalog.schema.model_name` |

### Critical: ResponsesAgent Output Format

**WRONG** - raw dicts don't work:
```python
return ResponsesAgentResponse(output=[{"role": "assistant", "content": "..."}])
```

**CORRECT** - use helper methods:
```python
return ResponsesAgentResponse(
    output=[self.create_text_output_item(text="...", id="msg_1")]
)
```

Available helper methods:
- `self.create_text_output_item(text, id)` - text responses
- `self.create_function_call_item(id, call_id, name, arguments)` - tool calls
- `self.create_function_call_output_item(call_id, output)` - tool results

---

## Resources

- [Model Serving Documentation](https://docs.databricks.com/machine-learning/model-serving/)
- [MLflow 3 ResponsesAgent](https://mlflow.org/docs/latest/llms/responses-agent-intro/)
- [Agent Framework](https://docs.databricks.com/generative-ai/agent-framework/)
