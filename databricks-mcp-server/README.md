# Databricks MCP Server

A simple [FastMCP](https://github.com/jlowin/fastmcp) server that exposes Databricks operations as MCP tools for AI assistants like Claude Code.

## Quick Start

### Step 1: Clone the repository

```bash
git clone https://github.com/databricks-solutions/ai-dev-kit.git
cd ai-dev-kit
```

### Step 2: Install the packages

```bash
# Install the core library
uv pip install -e ./databricks-tools-core

# Install the MCP server
uv pip install -e ./databricks-mcp-server
```

### Step 3: Configure Databricks authentication

```bash
# Option 1: Environment variables
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-token"

# Option 2: Use a profile from ~/.databrickscfg
export DATABRICKS_CONFIG_PROFILE="your-profile"
```

### Step 4: Add MCP server to Claude Code

For Claude Code, add to your project's `.mcp.json` (create the file if it doesn't exist).
For Cursor, add to your project's `.cursor/mcp.json` (create the file if it doesn't exist).

```json
{
  "mcpServers": {
    "databricks": {
      "command": "uv",
      "args": ["run",  "--directory", "/path/to/ai-dev-kit", "python", "databricks-mcp-server/run_server.py"],
      "defer_loading": true
    }
  }
}
```

**Replace `/path/to/ai-dev-kit`** with the actual path where you cloned the repo.

**Note:** `"defer_loading": true` improves startup time by not loading all tools upfront.

### Step 5 (Recommended): Install Databricks skills

The MCP server works best with **Databricks skills** that teach Claude best practices:

```bash
# In your project directory (not ai-dev-kit)
cd /path/to/your/project
curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash
```

### Step 6: Start Claude Code

```bash
cd /path/to/your/project
claude
```

Claude now has both:
- **Skills** (knowledge) - patterns and best practices in `.claude/skills/`
- **MCP Tools** (actions) - Databricks operations via the MCP server

## Available Tools

### SQL Operations

| Tool | Description |
|------|-------------|
| `execute_sql` | Execute a SQL query on a Databricks SQL Warehouse |
| `execute_sql_multi` | Execute multiple SQL statements with parallel execution |
| `list_warehouses` | List all SQL warehouses in the workspace |
| `get_best_warehouse` | Get the ID of the best available warehouse |
| `get_table_details` | Get table schema and statistics |

### Compute

| Tool | Description |
|------|-------------|
| `list_clusters` | List all clusters in the workspace |
| `get_best_cluster` | Get the best available cluster for execution |
| `execute_databricks_command` | Execute code on a Databricks cluster |
| `run_python_file_on_databricks` | Run a local Python file on a cluster |

### File Operations

| Tool | Description |
|------|-------------|
| `upload_folder` | Upload a local folder to Databricks workspace (parallel) |
| `upload_file` | Upload a single file to workspace |

### Jobs

| Tool | Description |
|------|-------------|
| `create_job` | Create a new job with tasks (serverless by default) |
| `get_job` | Get detailed job configuration |
| `list_jobs` | List jobs with optional name filter |
| `find_job_by_name` | Find job by exact name, returns job ID |
| `update_job` | Update job configuration |
| `delete_job` | Delete a job |
| `run_job_now` | Trigger a job run, returns run ID |
| `get_run` | Get run status and details |
| `get_run_output` | Get run output and logs |
| `list_runs` | List runs with filters |
| `cancel_run` | Cancel a running job |
| `wait_for_run` | Wait for run completion |

### Spark Declarative Pipelines (SDP)

| Tool | Description |
|------|-------------|
| `create_pipeline` | Create a new SDP pipeline |
| `get_pipeline` | Get pipeline details and configuration |
| `update_pipeline` | Update pipeline configuration |
| `delete_pipeline` | Delete a pipeline |
| `start_update` | Start pipeline run or dry-run validation |
| `get_update` | Get update status (QUEUED, RUNNING, COMPLETED, FAILED) |
| `stop_pipeline` | Stop a running pipeline |
| `get_pipeline_events` | Get error messages for debugging |
| `create_or_update_pipeline` | Create or update pipeline by name (auto-detects existing) |
| `find_pipeline_by_name` | Find pipeline by name, returns pipeline ID |

### Knowledge Assistants (KA)

| Tool | Description |
|------|-------------|
| `create_or_update_ka` | Create or update a Knowledge Assistant with document sources |
| `get_ka` | Get KA details by tile ID |
| `find_ka_by_name` | Find KA by name, returns tile ID |
| `delete_ka` | Delete a Knowledge Assistant |

### Genie Spaces

| Tool | Description |
|------|-------------|
| `create_or_update_genie` | Create or update a Genie Space for SQL-based data exploration |
| `get_genie` | Get Genie Space details by space ID |
| `find_genie_by_name` | Find Genie Space by name, returns space ID |
| `delete_genie` | Delete a Genie Space |

### Multi-Agent Supervisor (MAS)

| Tool | Description |
|------|-------------|
| `create_or_update_mas` | Create or update a Multi-Agent Supervisor |
| `get_mas` | Get MAS details by tile ID |
| `find_mas_by_name` | Find MAS by name, returns tile ID |
| `delete_mas` | Delete a Multi-Agent Supervisor |

### AI/BI Dashboards

| Tool | Description |
|------|-------------|
| `create_or_update_dashboard` | Create or update an AI/BI dashboard from JSON content |
| `get_dashboard` | Get dashboard details by ID |
| `list_dashboards` | List all dashboards in the workspace |
| `trash_dashboard` | Move a dashboard to trash |
| `publish_dashboard` | Publish a dashboard to make it accessible |
| `unpublish_dashboard` | Unpublish a dashboard |

### Unity Catalog FGAC Governance

| Tool | Description |
|------|-------------|
| `manage_uc_fgac_policies` | Unified tool for FGAC policy governance — dispatches to discovery, analysis, preview, and management actions via the `action` parameter |

**Actions:** `list_fgac_policies`, `get_fgac_policy`, `get_table_policies`, `get_masking_functions`, `get_column_tags_api`, `get_schema_info`, `get_catalog_info`, `list_table_policies_in_schema`, `analyze_fgac_coverage`, `check_policy_quota`, `preview_policy_changes`, `create_fgac_policy`, `update_fgac_policy`, `delete_fgac_policy`

### Model Serving

| Tool | Description |
|------|-------------|
| `get_serving_endpoint_status` | Get the status of a Model Serving endpoint |
| `query_serving_endpoint` | Query a Model Serving endpoint with chat or ML model inputs |
| `list_serving_endpoints` | List all Model Serving endpoints in the workspace |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code                             │
│                                                             │
│  Skills (knowledge)          MCP Tools (actions)            │
│  └── .claude/skills/         └── .claude/mcp.json           │
│      ├── sdp-writer              └── databricks server      │
│      ├── asset-bundles                                      │
│      └── ...                                                │
└──────────────────────────────┬──────────────────────────────┘
                               │ MCP Protocol (stdio)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              databricks-mcp-server (FastMCP)                │
│                                                             │
│  tools/sql.py ──────────────┐                               │
│  tools/compute.py ──────────┤                               │
│  tools/file.py ─────────────┤                               │
│  tools/jobs.py ─────────────┼──► @mcp.tool decorators       │
│  tools/pipelines.py ────────┤                               │
│  tools/agent_bricks.py ─────┤                               │
│  tools/aibi_dashboards.py ──┤                               │
│  tools/fgac_policies.py ────┤                               │
│  tools/serving.py ──────────┘                               │
└──────────────────────────────┬──────────────────────────────┘
                               │ Python imports
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                   databricks-tools-core                     │
│                                                             │
│  sql/         compute/       jobs/         pipelines/       │
│  └── execute  └── run_code   └── run/wait  └── create/run   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Databricks SDK
                               ▼
                    ┌─────────────────────┐
                    │  Databricks         │
                    │  Workspace          │
                    └─────────────────────┘
```

## Development

The server is intentionally simple - each tool file just imports functions from `databricks-tools-core` and decorates them with `@mcp.tool`.

To add a new tool:

1. Add the function to `databricks-tools-core`
2. Create a wrapper in `databricks_mcp_server/tools/`
3. Import it in `server.py`

Example:

```python
# tools/my_module.py
from databricks_tools_core.my_module import my_function as _my_function
from ..server import mcp

@mcp.tool
def my_function(arg1: str, arg2: int = 10) -> dict:
    """Tool description shown to the AI."""
    return _my_function(arg1=arg1, arg2=arg2)
```

## Usage Tracking via Audit Logs

All API calls made through the MCP server are tagged with a custom `User-Agent` header:

```
databricks-ai-dev-kit/0.1.0 databricks-sdk-py/... project/<auto-detected-repo-name>
```

The project name is auto-detected from the git remote URL (no configuration needed). This makes every call filterable in the `system.access.audit` system table.

> **Note:** Audit log entries may take 2–10 minutes to appear. The workspace must have Unity Catalog enabled to query `system.access.audit`.

## License

© Databricks, Inc. See [LICENSE.md](../LICENSE.md).
