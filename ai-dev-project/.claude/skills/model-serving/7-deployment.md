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

Use the `create_job` MCP tool:

```
create_job(
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

Use `run_job_now` - returns immediately:

```
run_job_now(
    job_id="<job_id>",
    job_parameters={"model_name": "main.agents.my_agent", "version": "1"}
)
```

Save the returned `run_id`.

### Step 4: Check Status

Check job run status:

```
get_run(run_id="<run_id>")
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

## Endpoint Naming

For agents deployed with `databricks.agents.deploy()`:

- Endpoint name is derived from model name
- `main.agents.my_agent` → `agents_my_agent` or similar
- Check with `list_serving_endpoints()` after deployment

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
| Create job (one-time) | `create_job` | Yes |
| Run deployment | `run_job_now` | **No** - returns immediately |
| Check job status | `get_run` | Yes |
| Check endpoint status | `get_serving_endpoint_status` | Yes |

## After Deployment

Once endpoint is READY:

1. **Test with MCP**: `query_serving_endpoint(name="...", messages=[...])`
2. **Share with team**: Endpoint URL in Databricks UI
3. **Integrate in apps**: Use REST API or SDK
