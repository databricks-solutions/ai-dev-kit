# AI Dev Kit Integration Example

This directory shows how to embed `ai-dev-kit` into your own application.

**What you get:** The same Claude Agent SDK-based agent used by `databricks-builder-app`, with:
- Databricks MCP tools (SQL, clusters, jobs, pipelines, Unity Catalog, etc.)
- Skills for guided development (SDP, SDK patterns, MLflow, etc.)
- Multi-user auth support via contextvars

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip
- Databricks workspace with:
  - SQL warehouse (for SQL queries)
  - Personal Access Token (PAT)
- Claude API access (either Anthropic API key or Databricks Model Serving)

## Quick Start

### 1. Copy this directory to your project

```bash
cp -r _integration-example /path/to/your/project/
cd /path/to/your/project/_integration-example
```

### 2. Run setup

```bash
./setup.sh
```

This creates a virtual environment, installs dependencies, and sets up skills.

### 3. Configure credentials

Create a `.env` file:

```bash
# Databricks
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...

# Claude API (Option A: Direct Anthropic)
ANTHROPIC_API_KEY=sk-ant-...

# Claude API (Option B: Databricks Model Serving)
# ANTHROPIC_BASE_URL=https://your-workspace.cloud.databricks.com/serving-endpoints/anthropic
# ANTHROPIC_AUTH_TOKEN=dapi...  # Use your Databricks PAT
# ANTHROPIC_MODEL=databricks-claude-sonnet-4
```

### 4. Run the example

```bash
source .venv/bin/activate
python example_integration.py
```

## Integration Guide

### What's Under the Hood

This integration uses:
- **Claude Agent SDK** (`claude-agent-sdk`) - Anthropic's SDK for running Claude as an agentic assistant
- **Databricks MCP Tools** (`databricks-mcp-server`) - Tools loaded in-process via MCP protocol
- **Skills** - Markdown files in `.claude/skills/` that provide domain-specific guidance

The `stream_agent_response` function is the same one used by `databricks-builder-app`.

### Importing

```python
# The agent service (uses claude-agent-sdk internally)
from server.services.agent import stream_agent_response

# Auth utilities for per-request Databricks credentials
from databricks_tools_core import set_databricks_auth, clear_databricks_auth
```

### Basic Usage

```python
import asyncio

async def run_agent(message: str):
    # Set Databricks auth for this request (passed to MCP tools)
    set_databricks_auth(
        host="https://your-workspace.cloud.databricks.com",
        token="dapi..."
    )
    
    try:
        async for event in stream_agent_response(
            project_id="my-project",
            message=message,
        ):
            # Handle events
            if event["type"] == "text_delta":
                print(event["text"], end="", flush=True)
            elif event["type"] == "tool_use":
                print(f"\n[Tool: {event['tool_name']}]")
            elif event["type"] == "tool_result":
                print(f"[Result: {event['content'][:100]}...]")
            elif event["type"] == "error":
                print(f"Error: {event['error']}")
    finally:
        clear_databricks_auth()

asyncio.run(run_agent("List my SQL warehouses"))
```

### Event Types

The agent streams these event types:

| Event Type | Description | Key Fields |
|------------|-------------|------------|
| `text_delta` | Token-by-token text output | `text` |
| `text` | Complete text block | `text` |
| `thinking_delta` | Token-by-token thinking | `thinking` |
| `thinking` | Complete thinking block | `thinking` |
| `tool_use` | Tool invocation started | `tool_name`, `tool_input`, `tool_id` |
| `tool_result` | Tool execution completed | `content`, `is_error`, `tool_use_id` |
| `result` | Session completed | `session_id`, `duration_ms`, `total_cost_usd` |
| `error` | Error occurred | `error` |
| `keepalive` | Connection keepalive | `elapsed_since_last_event` |

### Available Tools

The agent has access to Databricks tools via MCP:

- **SQL**: `execute_sql`, `execute_sql_multi`, `list_warehouses`, `get_table_details`
- **Compute**: `execute_code`, `manage_cluster`, `manage_sql_warehouse`, `list_compute`
- **Jobs**: `create_job`, `run_job_now`, `wait_for_run`, `list_runs`
- **Pipelines**: `create_or_update_pipeline`, `start_update`, `get_update`
- **Files**: `upload_to_workspace`
- **Unity Catalog**: Catalog, schema, table, volume operations

### Configuring Context

Pass additional context to help the agent:

```python
async for event in stream_agent_response(
    project_id="my-project",
    message="Create a table",
    # Optional context
    warehouse_id="abc123",           # Default SQL warehouse
    cluster_id="def456",             # Default cluster for Python execution
    default_catalog="my_catalog",    # Default Unity Catalog
    default_schema="my_schema",      # Default schema
    workspace_folder="/Users/me/",   # Workspace folder for file uploads
):
    ...
```

### Session Management

Resume conversations using session IDs:

```python
# First message - get session_id from result event
session_id = None
async for event in stream_agent_response(project_id="demo", message="Hello"):
    if event["type"] == "result":
        session_id = event["session_id"]

# Follow-up message - pass session_id to continue conversation
async for event in stream_agent_response(
    project_id="demo",
    message="What did I just ask?",
    session_id=session_id,  # Resume session
):
    ...
```

## Customization

### Adding Custom Skills

Skills are markdown files that provide specialized guidance. To add skills:

1. Create `.claude/skills/my-skill/SKILL.md` in your project
2. The agent will automatically discover and use them

### Modifying the System Prompt

To customize the agent's behavior, you can wrap `stream_agent_response` and inject your own system prompt modifications via the `system_prompt` parameter in `ClaudeAgentOptions`.

## Troubleshooting

### "Module not found" errors

Make sure you've activated the virtual environment:
```bash
source .venv/bin/activate
```

### Authentication failures

Check that your `DATABRICKS_HOST` doesn't have a trailing slash and your token is valid.

### Tools timing out

Long-running tools (>10s) automatically switch to async mode. The agent will return an `operation_id` that you can poll with `check_operation_status`.

## File Structure

```
_integration-example/
├── README.md              # This file
├── requirements.txt       # Dependencies
├── setup.sh              # One-command setup
├── example_integration.py # Working example
└── .claude/
    └── skills/           # Installed by setup.sh
```
