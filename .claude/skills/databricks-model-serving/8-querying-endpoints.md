# Querying Endpoints

Send requests to deployed Model Serving endpoints.

> **If MCP tools are not available**, use the Python SDK or REST API examples below.

## MCP Tools

### Check Endpoint Status

Before querying, verify the endpoint is ready:

```
get_serving_endpoint_status(name="my-agent-endpoint")
```

Response:
```json
{
    "name": "my-agent-endpoint",
    "state": "READY",
    "served_entities": [
        {"name": "my_agent-1", "entity_name": "main.agents.my_agent", "deployment_state": "READY"}
    ]
}
```

### Query Chat/Agent Endpoint

```
query_serving_endpoint(
    name="my-agent-endpoint",
    messages=[
        {"role": "user", "content": "What is Databricks?"}
    ],
    max_tokens=500,
    temperature=0.7
)
```

Response:
```json
{
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": "Databricks is a unified data intelligence platform..."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 150,
        "total_tokens": 160
    }
}
```

### Query ML Model Endpoint

```
query_serving_endpoint(
    name="sklearn-classifier",
    dataframe_records=[
        {"age": 25, "income": 50000, "credit_score": 720},
        {"age": 35, "income": 75000, "credit_score": 680}
    ]
)
```

Response:
```json
{
    "predictions": [0.85, 0.72]
}
```

### List All Endpoints

```
list_serving_endpoints(limit=20)
```

## Python SDK

### Query Agent/Chat Endpoint

```python
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()

response = w.serving_endpoints.query(
    name="my-agent-endpoint",
    messages=[
        {"role": "user", "content": "What is Databricks?"}
    ],
    max_tokens=500
)

print(response.choices[0].message.content)
```

### Query ML Model

```python
response = w.serving_endpoints.query(
    name="sklearn-classifier",
    dataframe_records=[
        {"age": 25, "income": 50000, "credit_score": 720}
    ]
)

print(response.predictions)
```

### Streaming (Agent Endpoints)

```python
for chunk in w.serving_endpoints.query(
    name="my-agent-endpoint",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
):
    if chunk.choices:
        print(chunk.choices[0].delta.content, end="")
```

## REST API

### Get Endpoint Status

```bash
curl -X GET \
  "https://<workspace>.databricks.com/api/2.0/serving-endpoints/<endpoint-name>" \
  -H "Authorization: Bearer <token>"
```

### Query Chat/Agent Endpoint

```bash
curl -X POST \
  "https://<workspace>.databricks.com/serving-endpoints/<endpoint-name>/invocations" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
        {"role": "user", "content": "What is Databricks?"}
    ],
    "max_tokens": 500
  }'
```

### Query ML Model

```bash
curl -X POST \
  "https://<workspace>.databricks.com/serving-endpoints/<endpoint-name>/invocations" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "dataframe_records": [
        {"age": 25, "income": 50000, "credit_score": 720}
    ]
  }'
```

## Integration Patterns

### In a Python Application

```python
from databricks.sdk import WorkspaceClient
import os

# Uses DATABRICKS_HOST and DATABRICKS_TOKEN from environment
w = WorkspaceClient()

def ask_agent(question: str) -> str:
    response = w.serving_endpoints.query(
        name="my-agent-endpoint",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content

# Usage
answer = ask_agent("What is a Delta table?")
print(answer)
```

### In Another Agent (Agent Chaining)

```python
from databricks.sdk import WorkspaceClient
from langchain_core.tools import tool

w = WorkspaceClient()

@tool
def ask_specialist_agent(question: str) -> str:
    """Ask a specialist agent for domain-specific answers."""
    response = w.serving_endpoints.query(
        name="specialist-agent-endpoint",
        messages=[{"role": "user", "content": question}]
    )
    return response.choices[0].message.content

# Add to your main agent's tools
tools = [ask_specialist_agent]
```

### With OpenAI-Compatible Libraries

Databricks endpoints are OpenAI-compatible:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://<workspace>.databricks.com/serving-endpoints/<endpoint-name>",
    api_key="<databricks-token>"
)

response = client.chat.completions.create(
    model="<endpoint-name>",  # Any value works, endpoint determines model
    messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
```

## Error Handling

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound, PermissionDenied

w = WorkspaceClient()

try:
    response = w.serving_endpoints.query(
        name="my-endpoint",
        messages=[{"role": "user", "content": "Test"}]
    )
except NotFound:
    print("Endpoint not found - check name or wait for deployment")
except PermissionDenied:
    print("No permission to query this endpoint")
except Exception as e:
    if "NOT_READY" in str(e):
        print("Endpoint is still starting up")
    else:
        raise
```

## Common Issues

| Issue | Solution |
|-------|----------|
| **Endpoint NOT_READY** | Wait for deployment (~15 min for agents) |
| **404 Not Found** | Check endpoint name, may differ from model name |
| **Permission Denied** | Ensure token has serving endpoint permissions |
| **Timeout** | Increase timeout, reduce max_tokens |
| **Empty response** | Check model signature matches input format |
