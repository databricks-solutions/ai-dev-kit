# Databricks MCP Server

A simple [FastMCP](https://github.com/jlowin/fastmcp) server that exposes Databricks operations as MCP tools for AI assistants like Claude Code, Cursor, and Genie Code.

This server is a **self-contained install**. It has no dependency on Databricks skills — follow the steps below and the server runs on its own. (If you *also* want skills, see the optional section at the end.)

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — used to create the virtual environment and install the packages:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Python 3.9+** (uv can install one for you with `uv venv --python 3.11`).
- **[Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html)** with a configured auth profile, so the server can reach your workspace. Verify with:
  ```bash
  databricks auth profiles
  ```
  If you have none, create one with `databricks auth login --host https://your-workspace.cloud.databricks.com`.

## Quick Start

### Step 1: Clone the repository

```bash
git clone https://github.com/databricks-solutions/ai-dev-kit.git
cd ai-dev-kit
```

### Step 2: Install the server

The MCP server depends on the `databricks-tools-core` library, which also lives in this repo. Install both as editable packages into a virtual environment.

You can do this in one shot with the setup script, which creates a `.venv`, installs both packages, verifies the import, and prints ready-to-paste client config:

```bash
./databricks-mcp-server/setup.sh
```

Or run the steps manually:

```bash
# Create and activate a virtual environment
uv venv --python 3.11
source .venv/bin/activate

# Install the core library, then the MCP server (both editable, from this repo)
uv pip install -e ./databricks-tools-core -e ./databricks-mcp-server
```

Verify the server imports cleanly:

```bash
python -c "import databricks_mcp_server; print('OK')"
```

### Step 3: Configure your MCP client

Point your MCP client at the server's `run_server.py`. Use the Python interpreter from the `.venv` you just created (replace `/path/to/ai-dev-kit` with the absolute path where you cloned the repo).

**Claude Code** — add to your project's `.mcp.json` (create the file if it doesn't exist):

```json
{
  "mcpServers": {
    "databricks": {
      "command": "/path/to/ai-dev-kit/.venv/bin/python",
      "args": ["/path/to/ai-dev-kit/databricks-mcp-server/run_server.py"],
      "defer_loading": true
    }
  }
}
```

Or register it from the CLI:

```bash
claude mcp add-json databricks '{"command":"/path/to/ai-dev-kit/.venv/bin/python","args":["/path/to/ai-dev-kit/databricks-mcp-server/run_server.py"]}'
```

**Cursor / Genie Code** — use the same JSON in your client's MCP config (e.g. Cursor's `.cursor/mcp.json`).

**Note:** `"defer_loading": true` improves startup time by not loading all tools upfront.

### Step 4: Authenticate

The server uses the Databricks Unified Authentication chain, so it picks up whatever the Databricks CLI/SDK already uses. Choose a profile in one of these ways:

```bash
# Option 1: Named profile from ~/.databrickscfg (recommended)
export DATABRICKS_CONFIG_PROFILE="your-profile"

# Option 2: Explicit host + token
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-token"
```

To make a profile available to a GUI MCP client, add it to the `env` block of the server config, e.g. `"env": {"DATABRICKS_CONFIG_PROFILE": "your-profile"}`.

### Step 5: Smoke test

Confirm the server starts and can reach your workspace:

```bash
# The server speaks MCP over stdio; it should start without errors, then Ctrl-C to exit.
.venv/bin/python databricks-mcp-server/run_server.py
```

Then in your MCP client, ask it to run a lightweight tool such as `list_warehouses` or `get_current_user`. A successful response confirms the server is installed, launched, and authenticated.

## Available Tools

### SQL Operations

| Tool | Description |
|------|-------------|
| `execute_sql` | Execute a SQL query on a Databricks SQL Warehouse |
| `execute_sql_multi` | Execute multiple SQL statements with parallel execution |
| `list_warehouses` | List all SQL warehouses in the workspace |
| `get_best_warehouse` | Get the ID of the best available warehouse |
| `get_table_stats_and_schema` | Get table schema and statistics |

### Compute

| Tool | Description |
|------|-------------|
| `execute_code` | Execute code on Databricks (serverless or cluster), or run a local file |
| `manage_cluster` | Create, modify, start, terminate, or delete clusters |
| `manage_sql_warehouse` | Create, modify, or delete SQL warehouses |
| `list_compute` | List clusters, node types, or spark versions |

### File Operations

| Tool | Description |
|------|-------------|
| `upload_to_workspace` | Upload files/folders to workspace (works like `cp` - handles files, folders, globs) |

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
| `create_or_update_pipeline` | Create or update pipeline by name (auto-detects existing) |
| `get_pipeline` | Get pipeline details by ID or name; enriched with latest update status and events. Omit args to list all. |
| `delete_pipeline` | Delete a pipeline |
| `run_pipeline` | Start, stop, or wait for pipeline runs |

### Knowledge Assistants (KA)

| Tool | Description |
|------|-------------|
| `manage_ka` | Manage Knowledge Assistants (create/update, get, find by name, delete) |

### Genie Spaces

| Tool | Description |
|------|-------------|
| `create_or_update_genie` | Create or update a Genie Space for SQL-based data exploration |
| `get_genie` | Get Genie Space details by space ID |
| `find_genie_by_name` | Find Genie Space by name, returns space ID |
| `delete_genie` | Delete a Genie Space |

### Supervisor Agent (MAS)

| Tool | Description |
|------|-------------|
| `manage_mas` | Manage Supervisor Agents (create/update, get, find by name, delete) |

### AI/BI Dashboards

| Tool | Description |
|------|-------------|
| `create_or_update_dashboard` | Create or update an AI/BI dashboard from JSON content |
| `get_dashboard` | Get dashboard details by ID, or list all dashboards (omit dashboard_id) |
| `delete_dashboard` | Soft-delete a dashboard (moves to trash) |
| `publish_dashboard` | Publish or unpublish a dashboard (`publish=True/False`) |

### Model Serving

| Tool | Description |
|------|-------------|
| `get_serving_endpoint_status` | Get the status of a Model Serving endpoint |
| `query_serving_endpoint` | Query a Model Serving endpoint with chat or ML model inputs |
| `list_serving_endpoints` | List all Model Serving endpoints in the workspace |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              MCP Client (Claude Code / Cursor / …)          │
│                                                             │
│  MCP Tools (actions)                                        │
│  └── .mcp.json ──► databricks server                        │
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

### Running Integration Tests

Integration tests run against a real Databricks workspace. Configure authentication first (see Step 3 above).

```bash
# Run all tests (excluding slow tests like cluster creation)
python tests/integration/run_tests.py

# Run all tests including slow tests
python tests/integration/run_tests.py --all

# Show report from the latest run
python tests/integration/run_tests.py --report

# Run with fewer parallel workers (default: 8)
python tests/integration/run_tests.py -j 4
```

Results are saved to `tests/integration/.test-results/<timestamp>/` with logs for each test folder.

See [tests/integration/README.md](tests/integration/README.md) for more details.

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

## Optional: If you also want Databricks skills

This MCP server runs completely on its own — you do **not** need skills for any of the steps above. Skills are a *separate*, optional add-on that give AI assistants written guidance (patterns and best practices) to complement the executable tools this server provides.

If you want them, install them separately — do not combine the two installs:

- **Databricks CLI (recommended):** `databricks aitools install` (requires Databricks CLI v1.0.0+). This is the supported way to get the latest skills.
- **AI Dev Kit installer:** run the repo's top-level `install.sh` and choose the skills option.

See the [ai-dev-kit README](../README.md) for details. Skills are installed into your own project (e.g. `.claude/skills/`) and are picked up independently of this server.

## License

© Databricks, Inc. See [LICENSE.md](../LICENSE.md).
