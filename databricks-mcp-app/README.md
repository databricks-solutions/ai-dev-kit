# Databricks MCP App

Deploy the ai-dev-kit MCP server as a Databricks App, enabling it to be used as a custom MCP server from AI agents on Databricks, including the built-in Databricks Assistant.

## Overview

This app hosts the `databricks-mcp-server` as a Databricks App, exposing it via HTTP/SSE transport for the Model Context Protocol. Once deployed, agents can connect to it using the app's URL, and it can be registered as an External MCP server in Unity Catalog for use with Databricks Assistant.

**Key Features:**
- 75 MCP tools for Databricks operations
- 17 skill documentation files
- Browser-friendly status page at `/`
- Health check endpoint at `/health`
- Full MCP protocol support at `/mcp`
- **Vibe Coding UI at `/chat`** - Interactive chat interface with Foundation Model + tool execution

## Quick Start

```bash
# Deploy to Databricks (uses your default profile or specify one)
./deploy.sh dbx_shared_demo

# The script will output the app URL when complete
```

---

## Project Structure

```
databricks-mcp-app/
├── app.yaml                 # Databricks App configuration
├── pyproject.toml           # Python dependencies and entry point
├── deploy.sh                # Deployment script
├── server/
│   ├── __init__.py
│   └── main.py              # FastMCP server with custom routes
├── databricks_mcp_server/   # Copied from parent during deploy
├── databricks_tools_core/   # Copied from parent during deploy
└── skills/                  # Copied from databricks-skills during deploy
```

## How It Was Built

### Step 1: App Configuration (`app.yaml`)

Databricks Apps require an `app.yaml` that specifies how to run the app:

```yaml
command:
  - "uv"
  - "run"
  - "mcp-server"
env:
  - name: SKILLS_DIR
    value: "./skills"
```

Key decisions:
- Use `uv` as the package manager (faster, recommended by Databricks)
- Define `mcp-server` as a script entry point in `pyproject.toml`
- Set `SKILLS_DIR` environment variable for skills loading

### Step 2: Dependencies (`pyproject.toml`)

```toml
[project]
name = "ai-dev-kit-mcp"
version = "0.1.0"
dependencies = [
    "fastmcp>=2.0.0",
    "databricks-sdk>=0.20.0",
    "uvicorn>=0.27.0",
    "starlette>=0.37.0",
]

[project.scripts]
mcp-server = "server.main:main"
```

The entry point `mcp-server` calls `server.main:main`.

### Step 3: Server Implementation (`server/main.py`)

The server uses FastMCP with custom routes for browser access:

```python
from fastmcp import FastMCP
from starlette.responses import JSONResponse, HTMLResponse

# Import the MCP server from databricks_mcp_server
from databricks_mcp_server.server import mcp

# Add custom routes using fastmcp's custom_route decorator
@mcp.custom_route("/", methods=["GET"])
async def home_route(request):
    return HTMLResponse(home_html)

@mcp.custom_route("/health", methods=["GET"])
async def health_route(request):
    return JSONResponse({"status": "healthy", ...})

@mcp.custom_route("/tools", methods=["GET"])
async def tools_route(request):
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

@mcp.custom_route("/skills", methods=["GET"])
async def skills_route(request):
    return JSONResponse({"skills": skills, "count": len(skills)})

# Create HTTP app - serves MCP protocol at /mcp
app = mcp.http_app()
uvicorn.run(app, host="0.0.0.0", port=port)
```

**Important:** The `mcp.http_app()` creates an ASGI app that serves the MCP protocol at `/mcp`. Custom routes are added via `@mcp.custom_route()`.

### Step 4: Deployment Script (`deploy.sh`)

The deploy script handles:
1. Creating the app (if it doesn't exist)
2. Uploading all source code to workspace
3. Deploying and starting the app

```bash
#!/bin/bash
PROFILE=${1:-"DEFAULT"}
APP_NAME="ai-dev-kit-mcp"

# Get user email for workspace path
USER_EMAIL=$(databricks current-user me --profile "$PROFILE" --output json | ...)

# Create app if needed
databricks apps create "$APP_NAME" --profile "$PROFILE"

# Upload source code
databricks workspace import "$WORKSPACE_PATH/app.yaml" --file app.yaml ...
databricks workspace import "$WORKSPACE_PATH/pyproject.toml" --file pyproject.toml ...
databricks workspace import-dir server "$WORKSPACE_PATH/server" ...
databricks workspace import-dir ../databricks-mcp-server/databricks_mcp_server "$WORKSPACE_PATH/databricks_mcp_server" ...
databricks workspace import-dir ../databricks-tools-core/databricks_tools_core "$WORKSPACE_PATH/databricks_tools_core" ...
databricks workspace import-dir ../databricks-skills "$WORKSPACE_PATH/skills" ...

# Deploy
databricks apps deploy "$APP_NAME" --source-code-path "$WORKSPACE_PATH" --profile "$PROFILE"
```

---

## Deployment

### Prerequisites

1. Databricks CLI installed (`pip install databricks-cli` or `brew install databricks`)
2. CLI configured with a profile (`databricks configure --profile myprofile`)
3. Workspace with Apps enabled
4. Permissions to create apps

### Deploy

```bash
cd databricks-mcp-app
./deploy.sh <profile-name> <app-name>
```

Example:
```bash
./deploy.sh dbx_shared_demo mcp-test-app
```

The script outputs the app URL when complete:
```
App URL: https://ai-dev-kit-mcp-<workspace-id>.<region>.azure.databricksapps.com
```

### Verify Deployment

```bash
# Check app status
databricks apps get ai-dev-kit-mcp --profile dbx_shared_demo

# Test health endpoint (requires auth)
TOKEN=$(databricks auth token --profile dbx_shared_demo --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -H "Authorization: Bearer $TOKEN" "https://<app-url>/health"
```

---


## Available Tools (75)

| Category | Tools |
|----------|-------|
| **SQL** | `execute_sql`, `execute_sql_multi`, `list_warehouses`, `get_best_warehouse` |
| **Compute** | `execute_databricks_command`, `run_python_file_on_databricks`, `list_clusters`, `get_best_cluster` |
| **Jobs** | `create_job`, `update_job`, `delete_job`, `list_jobs`, `get_job`, `find_job_by_name`, `run_job_now`, `get_run`, `get_run_output`, `list_runs`, `wait_for_run`, `cancel_run` |
| **Pipelines** | `create_pipeline`, `create_or_update_pipeline`, `update_pipeline`, `delete_pipeline`, `get_pipeline`, `find_pipeline_by_name`, `start_update`, `get_update`, `stop_pipeline`, `get_pipeline_events` |
| **Dashboards** | `create_or_update_dashboard`, `get_dashboard`, `list_dashboards`, `publish_dashboard`, `unpublish_dashboard`, `trash_dashboard` |
| **Agent Bricks** | `create_or_update_ka`, `get_ka`, `find_ka_by_name`, `delete_ka`, `create_or_update_mas`, `get_mas`, `find_mas_by_name`, `delete_mas` |
| **Genie** | `create_or_update_genie`, `get_genie`, `list_genie`, `delete_genie`, `ask_genie`, `ask_genie_followup` |
| **Unity Catalog** | `manage_uc_objects`, `manage_uc_grants`, `manage_uc_storage`, `manage_uc_connections`, `manage_uc_tags`, `manage_uc_security_policies`, `manage_uc_monitors`, `manage_uc_sharing`, `get_table_details` |
| **Volumes** | `list_volume_files`, `upload_to_volume`, `download_from_volume`, `delete_volume_file`, `delete_volume_directory`, `create_volume_directory`, `get_volume_file_info` |
| **Workspace** | `upload_file`, `upload_folder` |
| **Serving** | `get_serving_endpoint_status`, `query_serving_endpoint`, `list_serving_endpoints` |
| **Skills** | `list_skills`, `get_skill`, `get_skill_tree`, `search_skills` |

## Available Skills (17)

| Skill | Description |
|-------|-------------|
| agent-bricks | Knowledge Assistants, Genie, Multi-Agent Supervisors |
| aibi-dashboards | Create AI/BI dashboards with SQL |
| asset-bundles | Databricks Asset Bundles (DABs) deployment |
| databricks-app-apx | APX framework apps (React/FastAPI) |
| databricks-app-python | Python apps (Dash/Streamlit) |
| databricks-config | Profile and authentication setup |
| databricks-docs | Documentation reference |
| databricks-genie | Genie data exploration |
| databricks-jobs | Job creation, scheduling, monitoring |
| databricks-python-sdk | SDK, Connect, CLI, REST API |
| databricks-unity-catalog | Unity Catalog management |
| lakebase-provisioned | Lakebase provisioned tables |
| mlflow-evaluation | MLflow 3 GenAI evaluation |
| model-serving | Deploy ML models and agents |
| spark-declarative-pipelines | DLT/SDP pipeline development |
| synthetic-data-generation | Generate test data with Faker |
| unstructured-pdf-generation | PDF generation for RAG |

---

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Browser-friendly status page with tools/skills list |
| `/health` | GET | JSON health check |
| `/tools` | GET | JSON list of all tools |
| `/skills` | GET | JSON list of all skills |
| `/mcp` | POST | MCP protocol endpoint (requires SSE headers) |
| `/chat` | GET | **Vibe Coding UI** - Interactive chat interface |
| `/api/chat` | POST | Chat API endpoint for LLM + tool execution |

---

## Vibe Coding UI

The `/chat` endpoint provides an interactive chat interface for "vibe coding" - creating Databricks resources through natural language conversation.

### Features

- **Foundation Model Integration**: Uses Databricks Foundation Models (Claude Sonnet 4, Claude 3.7, Llama 3.3 70B)
- **Tool Execution**: The LLM can call any of the 75+ MCP tools to create real resources
- **Conversation Context**: Maintains conversation history for follow-up questions
- **Tool Call Visibility**: Shows exactly which tools are called and their results

### What You Can Create

Ask the chat to:
- "Create a table in my catalog with sample data"
- "Set up a streaming pipeline from my volume"
- "Build a dashboard showing sales by region"
- "Create a job that runs a notebook daily"
- "Query my data and summarize the results"
- "Set up permissions for my team"

### API Usage

```bash
curl -X POST https://your-app.databricks.app/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "List all tables in the main catalog"}],
    "model": "databricks-claude-sonnet-4"
  }'
```

Response includes:
- `response`: The assistant's text response
- `tool_calls`: Array of tools called with their arguments and results

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Databricks App                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              FastMCP HTTP Server                     │    │
│  │  /         → Status page (HTML)                      │    │
│  │  /health   → Health check (JSON)                     │    │
│  │  /tools    → Tool list (JSON)                        │    │
│  │  /skills   → Skill list (JSON)                       │    │
│  │  /mcp      → MCP Protocol (SSE)                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            databricks-mcp-server                     │    │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐       │    │
│  │  │ SQL  │ │Compute│ │ Jobs │ │  UC  │ │Skills│ ...  │    │
│  │  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘       │    │
│  └─────────────────────────────────────────────────────┘    │
│                           │                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            databricks-tools-core                     │    │
│  │       (Databricks SDK wrapper functions)             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
              ┌───────────────────────────┐
              │     Databricks APIs       │
              │  - SQL Warehouses         │
              │  - Clusters               │
              │  - Unity Catalog          │
              │  - Jobs                   │
              │  - Model Serving          │
              └───────────────────────────┘
```

---

## Troubleshooting

### App Status

```bash
# Check if app is running
databricks apps get ai-dev-kit-mcp --profile dbx_shared_demo

# List recent deployments
databricks apps list-deployments ai-dev-kit-mcp --profile dbx_shared_demo
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `App CRASHED` | Port conflict or startup error | Check `app.yaml` uses PORT env var |
| `401 Unauthorized` | Token expired | Regenerate token and update UC connection |
| `307 Redirect` | Wrong base_path | Use `/mcp` without trailing slash |
| `406 Not Acceptable` | Missing SSE headers | MCP protocol requires `Accept: application/json, text/event-stream` |
| `Skills not loading` | Wrong path | Set `SKILLS_DIR=./skills` in app.yaml |

### Redeploy

```bash
cd databricks-mcp-app
./deploy.sh dbx_shared_demo
```

### Refresh UC Connection Token

```bash
# Get new token
TOKEN=$(databricks auth token --profile dbx_shared_demo --output json | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Drop and recreate connection (run in Databricks SQL)
DROP CONNECTION IF EXISTS ai_dev_kit_mcp;
CREATE CONNECTION ai_dev_kit_mcp TYPE HTTP OPTIONS (
  host '<YOUR-APP-URL>', 
  base_path '/mcp',
  bearer_token '<new-token>',
  is_mcp_connection 'true'
);
GRANT USE CONNECTION ON CONNECTION ai_dev_kit_mcp TO `account users`;
```

---

## Usage Examples

### From Python (with databricks_mcp client)

```python
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient

ws = WorkspaceClient(profile="dbx_shared_demo")
mcp = DatabricksMCPClient(
    server_url="https://<app-url>/mcp", 
    workspace_client=ws
)

# List tools
tools = mcp.list_tools()
print(f"Available: {len(tools)} tools")

# Execute SQL
result = mcp.call_tool("execute_sql", {"sql_query": "SELECT current_timestamp()"})

# List skills
skills = mcp.call_tool("list_skills", {})

# Get skill documentation
skill = mcp.call_tool("get_skill", {"skill_name": "aibi-dashboards"})
```

### From Databricks Assistant

1. Register the UC connection (see above)
2. Open AI Playground or a notebook
3. Add the MCP server as an external tool
4. Ask: "Use the MCP server to create a job that runs a Python script"

---

## Development

### Local Testing

```bash
# Install dependencies
cd databricks-mcp-app
pip install -e ../databricks-mcp-server
pip install -e ../databricks-tools-core

# Run locally
python -m server.main
```

### Modifying Tools

Tools are defined in `databricks-mcp-server/databricks_mcp_server/tools/`. Each module registers tools with the FastMCP server using decorators:

```python
from databricks_mcp_server.server import mcp

@mcp.tool()
def my_new_tool(param: str) -> dict:
    """Tool description shown to agents."""
    # Implementation using databricks-tools-core
    return {"result": "..."}
```

After adding tools, redeploy the app.
