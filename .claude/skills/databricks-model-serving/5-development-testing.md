# Development & Testing Workflow

MCP-based workflow for developing and testing agents on Databricks.

> **If MCP tools are not available**, use Databricks CLI or the Python SDK directly. See [Databricks CLI docs](https://docs.databricks.com/dev-tools/cli/) for `databricks workspace import` and `databricks clusters spark-submit` commands.

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Write agent code locally (agent.py)                 │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: Upload to workspace                                 │
│   → upload_folder MCP tool                                  │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Install packages                                    │
│   → execute_databricks_command MCP tool                     │
└─────────────────────────────────────────────────────────────┘
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Test agent (iterate)                                │
│   → run_python_file_on_databricks MCP tool                  │
│   → If error: fix locally, re-upload, re-run                │
└─────────────────────────────────────────────────────────────┘
```

## Step 1: Create Local Files

Create a project folder with your agent:

```
my_agent/
├── agent.py           # Agent implementation (ResponsesAgent)
├── test_agent.py      # Local testing script
├── log_model.py       # MLflow logging script
└── requirements.txt   # Dependencies (optional)
```

### agent.py

```python
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentResponse
from databricks_langchain import ChatDatabricks

LLM_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"

class MyAgent(ResponsesAgent):
    def __init__(self):
        self.llm = ChatDatabricks(endpoint=LLM_ENDPOINT)
    
    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        messages = [{"role": m.role, "content": m.content} for m in request.input]
        response = self.llm.invoke(messages)
        # CRITICAL: Must use helper methods for output items
        return ResponsesAgentResponse(
            output=[self.create_text_output_item(text=response.content, id="msg_1")]
        )

AGENT = MyAgent()
mlflow.models.set_model(AGENT)
```

### test_agent.py

```python
from agent import AGENT
from mlflow.types.responses import ResponsesAgentRequest, ChatContext

# Test request
request = ResponsesAgentRequest(
    input=[{"role": "user", "content": "What is Databricks?"}],
    context=ChatContext(user_id="test@example.com")
)

# Run prediction
result = AGENT.predict(request)
print("Response:", result.model_dump(exclude_none=True))
```

## Step 2: Upload to Workspace

Use the `upload_folder` MCP tool:

```
upload_folder(
    local_folder="./my_agent",
    workspace_folder="/Workspace/Users/you@company.com/my_agent"
)
```

This uploads all files in parallel.

## Step 3: Install Packages

Use `execute_databricks_command` to install dependencies:

```
execute_databricks_command(
    code="%pip install -U mlflow==3.6.0 databricks-langchain langgraph==0.3.4 databricks-agents pydantic"
)
```

**Important:** Save the returned `cluster_id` and `context_id` for subsequent calls - reusing the context is faster and keeps packages installed.

### Follow-up Commands (Reuse Context)

```
execute_databricks_command(
    code="dbutils.library.restartPython()",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

## Step 4: Test the Agent

Use `run_python_file_on_databricks`:

```
run_python_file_on_databricks(
    file_path="./my_agent/test_agent.py",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

### If Test Fails

1. Read the error from the output
2. Fix the local file (`agent.py` or `test_agent.py`)
3. Re-upload: `upload_folder(...)`
4. Re-run: `run_python_file_on_databricks(...)`

### Iteration Tips

- **Keep context alive** - Reuse `cluster_id` and `context_id` for faster iterations
- **Packages persist** - Once installed, packages stay in the context
- **Check imports first** - Run a minimal test before full agent test

## Quick Debugging Commands

### Check if packages are installed

```
execute_databricks_command(
    code="import mlflow; print(mlflow.__version__)",
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

### List available endpoints

```
execute_databricks_command(
    code="""
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
for ep in list(w.serving_endpoints.list())[:10]:
    print(f"{ep.name}: {ep.state.ready if ep.state else 'unknown'}")
    """,
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

### Test LLM endpoint directly

```
execute_databricks_command(
    code="""
from databricks_langchain import ChatDatabricks
llm = ChatDatabricks(endpoint="databricks-meta-llama-3-3-70b-instruct")
response = llm.invoke([{"role": "user", "content": "Hello!"}])
print(response.content)
    """,
    cluster_id="<cluster_id>",
    context_id="<context_id>"
)
```

## Workflow Summary

| Step | MCP Tool | Purpose |
|------|----------|---------|
| Upload files | `upload_folder` | Sync local files to workspace |
| Install packages | `execute_databricks_command` | Set up dependencies |
| Restart Python | `execute_databricks_command` | Apply package changes |
| Test agent | `run_python_file_on_databricks` | Run test script |
| Debug | `execute_databricks_command` | Quick checks |

## Next Steps

Once your agent tests successfully:

1. **Log to MLflow** → See [6-logging-registration.md](6-logging-registration.md)
2. **Deploy endpoint** → See [7-deployment.md](7-deployment.md)
3. **Query endpoint** → See [8-querying-endpoints.md](8-querying-endpoints.md)
