---
name: databricks-agent-deployment
description: "Deploy MLflow agents on Databricks Model Serving. Covers ResponsesAgent output format, UC Volume access in serving, notebook patterns with writefile, serverless jobs via REST API, multi-format document input, and common deployment pitfalls."
---

# Databricks Agent Deployment

Practical patterns and fixes for deploying MLflow agents (especially `ResponsesAgent`) on Databricks Model Serving, via notebooks, REST API, and serverless jobs.

## When to Use

- Deploying an MLflow agent to a Model Serving endpoint
- Hitting deployment errors with `ResponsesAgent`
- Bundling files (skills, prompts) with model artifacts
- Running deployment notebooks as serverless jobs
- Handling multi-format document input (PDF/JPEG/PNG)
- Using the `%%writefile` + `restartPython` notebook pattern

## Quick Start

### Deploy a ResponsesAgent

```python
import mlflow
from mlflow.models.resources import DatabricksServingEndpoint

mlflow.set_registry_uri("databricks-uc")

with mlflow.start_run():
    model_info = mlflow.pyfunc.log_model(
        artifact_path="agent",
        python_model="agent.py",
        pip_requirements=["mlflow", "databricks-sdk"],
        resources=[DatabricksServingEndpoint(endpoint_name="databricks-claude-sonnet-4-6")],
    )

# Register in Unity Catalog
mlflow.register_model(model_info.model_uri, "catalog.schema.my_agent")

# Deploy
from databricks import agents
agents.deploy("catalog.schema.my_agent", model_version=1)
```

## Common Patterns

### Pattern 1: ResponsesAgentResponse Output Format

`ResponsesAgentResponse` output items are Pydantic models requiring `id` and `status`:

```python
import uuid
from mlflow.pyfunc import ResponsesAgentResponse

return ResponsesAgentResponse(output=[
    {"id": str(uuid.uuid4()), "type": "message", "role": "assistant",
     "status": "completed",
     "content": [{"type": "output_text", "text": result}]}
])
```

Missing `id` or `status` causes silent validation failures. When consuming:

```python
result = agent.predict(request)
result_dict = result.model_dump(exclude_none=True)
text = result_dict["output"][0]["content"][0]["text"]
```

### Pattern 2: UC Volume Access in Serving

Model Serving endpoints can access UC Volumes at runtime, but `mlflow.models.predict` (pre-deployment validation) runs in an isolated environment that **cannot**.

**Solution — bundle files with fallback:**

```python
import shutil, tempfile, os

local_copy = os.path.join(tempfile.gettempdir(), "skills_bundle")
shutil.copytree("/Volumes/catalog/schema/volume/skills", local_copy)

mlflow.pyfunc.log_model(
    python_model="agent.py",
    code_paths=[local_copy],
)
```

In the agent, resolve with fallback:

```python
from pathlib import Path

def _resolve_path() -> str:
    volume_path = os.environ.get("MY_PATH", "/Volumes/catalog/schema/volume")
    if Path(volume_path).exists():
        return volume_path
    for candidate in [
        Path(__file__).parent / "skills_bundle",
        Path(__file__).parent / "code" / "skills_bundle",
    ]:
        if candidate.exists():
            return str(candidate)
    return volume_path
```

### Pattern 3: Notebook Deployment Pattern

The standard `%%writefile` + `restartPython` pattern:

1. **Cell 1:** `%pip install ...` + `dbutils.library.restartPython()`
2. **Cell 2:** Widgets + config + `os.environ[...] = ...`
3. **Cell 3:** `%%writefile agent.py` — agent code with env var fallbacks
4. **Cell 4:** `dbutils.library.restartPython()` — critical to pick up new file
5. **Cell 5:** `from agent import AGENT` — test locally
6. **Cell 6:** `mlflow.pyfunc.log_model(python_model="agent.py", ...)`
7. **Cell 7:** `agents.deploy(...)` + wait loop

The `restartPython()` between writing and importing is **critical** — without it, Python caches a stale module.

### Pattern 4: Serverless Notebook Jobs via REST API

```bash
curl -X POST "$HOST/api/2.1/jobs/runs/submit" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tasks": [{
      "task_key": "deploy",
      "notebook_task": {
        "notebook_path": "/Users/me/deploy_agent",
        "base_parameters": {"model_name": "my_agent"}
      },
      "environment_key": "default"
    }],
    "environments": [{
      "environment_key": "default",
      "spec": {
        "client": "2",
        "dependencies": ["mlflow", "databricks-sdk"]
      }
    }]
  }'
```

Key: `"client": "2"` = serverless (no cluster needed).

## Reference Files

- [endpoint-management.md](endpoint-management.md) - Endpoint creation, timing, and REST API patterns
- [document-input.md](document-input.md) - Multi-format document handling (PDF/JPEG/PNG)

## Common Issues

| Issue | Solution |
|-------|----------|
| **ResponsesAgentResponse validation error** | Add `id` (uuid4) and `status` ("completed") to every output item |
| **UC Volume not found during `mlflow.models.predict`** | Bundle files via `code_paths` + add fallback path resolution |
| **Stale module after `%%writefile`** | Add `dbutils.library.restartPython()` between write and import |
| **Endpoint stuck `IN_PROGRESS` > 30 min** | Delete and recreate the endpoint |
| **`UPDATE_FAILED` with `DEPLOYMENT_ABORTED`** | Infrastructure timeout — retry usually works |
| **`INVALID_PARAMETER_VALUE` on endpoint create** | Include `workload_size` field (e.g., `"Small"`) |
| **LLM returns JSON wrapped in markdown fences** | Strip fences and extract JSON between `{` and `}` |
| **`DIRECTORY_NOT_EMPTY` on `shutil.copytree`** | Use `tempfile.gettempdir()`, not notebook CWD |
