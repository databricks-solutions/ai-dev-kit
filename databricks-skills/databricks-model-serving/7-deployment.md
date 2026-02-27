# Deployment

Deploy models to serving endpoints. Uses async job-based approach for agents (deployment takes ~15 min).

> **If MCP tools are not available**, use `databricks.agents.deploy()` directly in a notebook, or create jobs via CLI: `databricks jobs create --json @job.json`

## Deployment Options

| Model Type | Method | Time |
|------------|--------|------|
| **Classical ML** | SDK/UI | 2-5 min |
| **GenAI Agent** | `databricks.agents.deploy()` | ~15 min |

## GenAI Agent Deployment (Job-Based)

Since agent deployment takes ~15 minutes, use a job to avoid MCP timeouts.

### Step 1: Create Deployment Script

```python
# deploy_agent.py
import sys
from databricks import agents

# Get params from job or command line
model_name = sys.argv[1] if len(sys.argv) > 1 else "main.agents.my_agent"
version = sys.argv[2] if len(sys.argv) > 2 else "1"

print(f"Deploying {model_name} version {version}...")

# Deploy - this takes ~15 min
deployment = agents.deploy(
    model_name,
    version,
    tags={"source": "mcp", "environment": "dev"}
)

print(f"Deployment complete!")
print(f"Endpoint: {deployment.endpoint_name}")
```

### Step 2: Create Deployment Job (One-Time)

Use the `manage_jobs` MCP tool with action="create":

```
manage_jobs(
    action="create",
    name="deploy-agent-job",
    tasks=[
        {
            "task_key": "deploy",
            "spark_python_task": {
                "python_file": "/Workspace/Users/you@company.com/my_agent/deploy_agent.py",
                "parameters": ["{{job.parameters.model_name}}", "{{job.parameters.version}}"]
            }
        }
    ],
    parameters=[
        {"name": "model_name", "default": "main.agents.my_agent"},
        {"name": "version", "default": "1"}
    ]
)
```

Save the returned `job_id`.

### Step 3: Run Deployment (Async)

Use `manage_job_runs` with action="run_now" - returns immediately:

```
manage_job_runs(
    action="run_now",
    job_id="<job_id>",
    job_parameters={"model_name": "main.agents.my_agent", "version": "1"}
)
```

Save the returned `run_id`.

### Step 4: Check Status

Check job run status:

```
manage_job_runs(action="get", run_id="<run_id>")
```

Or check endpoint directly:

```
get_serving_endpoint_status(name="<endpoint_name>")
```

## Classical ML Deployment

For traditional ML models, deployment is faster - use SDK directly.

### Via MLflow Deployments SDK

```python
from mlflow.deployments import get_deploy_client

mlflow.set_registry_uri("databricks-uc")
client = get_deploy_client("databricks")

endpoint = client.create_endpoint(
    name="my-sklearn-model",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.my_model",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ]
    }
)
```

### Via Databricks SDK

```python
from databricks.sdk import WorkspaceClient
from datetime import timedelta

w = WorkspaceClient()

endpoint = w.serving_endpoints.create_and_wait(
    name="my-sklearn-model",
    config={
        "served_entities": [
            {
                "entity_name": "main.models.my_model",
                "entity_version": "1",
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ]
    },
    timeout=timedelta(minutes=10)
)
```

## Endpoint Naming and Visibility

### Auto-generated Names

When you call `agents.deploy()`, the endpoint name is auto-derived from the UC model path by replacing dots with underscores and prefixing with `agents_`:

| UC Model Path | Auto-generated Endpoint Name |
|---------------|------------------------------|
| `main.agents.my_agent` | `agents_main-agents-my_agent` |
| `catalog.schema.model` | `agents_catalog-schema-model` |
| `users.jane.demo_bot` | `agents_users-jane-demo_bot` |

The exact format can vary. To avoid surprises, **always specify the endpoint name explicitly**:

```python
deployment = agents.deploy(
    "main.agents.my_agent",
    "1",
    endpoint_name="my-agent-endpoint",  # Control the name
    tags={"source": "mcp", "environment": "dev"}
)
```

### Finding Endpoints in the UI

Endpoints created via `agents.deploy()` appear under **Serving** in the Databricks UI. If you don't see your endpoint:

1. **Check the filter** - The Serving page defaults to "Owned by me". If the deployment ran as a service principal (e.g., via a job), switch to "All" to see it.
2. **Verify via API** - Use `list_serving_endpoints()` or `get_serving_endpoint_status(name="...")` to confirm the endpoint exists and check its state.
3. **Check the name** - The auto-generated name may not be what you expect. Print `deployment.endpoint_name` in the deploy script or check the job run output.

### Deployment Script with Explicit Naming

```python
# deploy_agent.py - recommended pattern
import sys
from databricks import agents

model_name = sys.argv[1] if len(sys.argv) > 1 else "main.agents.my_agent"
version = sys.argv[2] if len(sys.argv) > 2 else "1"
endpoint_name = sys.argv[3] if len(sys.argv) > 3 else None

deploy_kwargs = {
    "tags": {"source": "mcp", "environment": "dev"}
}
if endpoint_name:
    deploy_kwargs["endpoint_name"] = endpoint_name

print(f"Deploying {model_name} version {version}...")
deployment = agents.deploy(model_name, version, **deploy_kwargs)

print(f"Deployment complete!")
print(f"Endpoint name: {deployment.endpoint_name}")
print(f"Query URL: {deployment.query_endpoint}")
```

## Deployment Job Template

Complete job definition for reusable agent deployment:

```yaml
# resources/deploy_agent_job.yml (for Asset Bundles)
resources:
  jobs:
    deploy_agent:
      name: "[${bundle.target}] Deploy Agent"
      parameters:
        - name: model_name
          default: ""
        - name: version
          default: "1"
      tasks:
        - task_key: deploy
          spark_python_task:
            python_file: ../src/deploy_agent.py
            parameters:
              - "{{job.parameters.model_name}}"
              - "{{job.parameters.version}}"
          new_cluster:
            spark_version: "16.1.x-scala2.12"
            node_type_id: "i3.xlarge"
            num_workers: 0
            spark_conf:
              spark.master: "local[*]"
```

## Update Existing Endpoint

To update an endpoint with a new model version:

```python
from mlflow.deployments import get_deploy_client

client = get_deploy_client("databricks")

client.update_endpoint(
    endpoint="my-agent-endpoint",
    config={
        "served_entities": [
            {
                "entity_name": "main.agents.my_agent",
                "entity_version": "2",  # New version
                "workload_size": "Small",
                "scale_to_zero_enabled": True
            }
        ],
        "traffic_config": {
            "routes": [
                {"served_model_name": "my_agent-2", "traffic_percentage": 100}
            ]
        }
    }
)
```

## Workflow Summary

| Step | MCP Tool | Waits? |
|------|----------|--------|
| Upload deploy script | `upload_folder` | Yes |
| Create job (one-time) | `manage_jobs` (action="create") | Yes |
| Run deployment | `manage_job_runs` (action="run_now") | **No** - returns immediately |
| Check job status | `manage_job_runs` (action="get") | Yes |
| Check endpoint status | `get_serving_endpoint_status` | Yes |

## After Deployment

Once endpoint is READY:

1. **Test with MCP**: `query_serving_endpoint(name="...", messages=[...])`
2. **Share with team**: Endpoint URL in Databricks UI
3. **Integrate in apps**: Use REST API or SDK
