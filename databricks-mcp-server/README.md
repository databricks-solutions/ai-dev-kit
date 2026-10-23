# Databricks MCP Server

A simple [FastMCP](https://github.com/jlowin/fastmcp) server that exposes Databricks operations as MCP tools for AI assistants like Claude Code, Cursor, and Genie Code.

This server is a **self-contained install**. It has no dependency on Databricks skills — follow the steps below and the server runs on its own. (If you *also* want skills, see the optional section at the end.)

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — used to create the virtual environment and install the packages:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
  `uv` is **required** on macOS/Linux: `mcp_install.sh`/`setup.sh` exit with an error if it isn't on your PATH (pass `--skip-venv` to reuse an existing venv and bypass the check). On Windows, `setup.ps1` falls back to `python -m venv` when `uv` is missing.
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

### Step 2: Install the server plus configurations
**Recommended:** use the bundled installer (Option A) to build the venv *and* register the server with your MCP clients in one step. It wraps `setup.sh`/`setup.ps1` (the venv build) and writes the client config for you, prompting for scope, which clients to configure, and which Databricks profile to inject.

#### Option A - mcp_install.sh

The MCP server depends on the `databricks-tools-core` library, which also lives in this repo. Install both as editable packages into a virtual environment.

You can do this in one shot with the installer script, which creates a `.venv`, installs both packages, verifies the import, and creates your client configs:

```bash
# macOS / Linux
./databricks-mcp-server/mcp_install.sh

# Windows (PowerShell)
.\databricks-mcp-server\mcp_install.ps1
```

It supports Claude Code, Cursor, GitHub Copilot, OpenAI Codex, Gemini CLI, Antigravity, Windsurf, OpenCode, and Kiro, and can be reverted with `--uninstall` (`-Uninstall` on PowerShell).

> **Encoding note:** `mcp_install.ps1` and `setup.ps1` are stored as UTF-8 **with BOM**. Keep that encoding if you edit them — Windows PowerShell 5.1 decodes BOM-less files as ANSI, which garbles the scripts' `─`/`✓` output. PowerShell 7+ is unaffected.

The installer prompts for **scope** (project vs. global), **which clients** to configure, and **which Databricks profile** to inject. Where it writes each client's config depends on the scope you choose:

| Client | Project scope | Global scope |
|--------|---------------|--------------|
| Claude Code | `<cwd>/.mcp.json` | `~/.claude.json` |
| Cursor | `<cwd>/.cursor/mcp.json` | — (configure in Settings) |
| GitHub Copilot | `<cwd>/.vscode/mcp.json` | — (configure in VS Code) |
| OpenAI Codex | `<cwd>/.codex/config.toml` | `~/.codex/config.toml` |
| Gemini CLI | `<cwd>/.gemini/settings.json` | `~/.gemini/settings.json` |
| Antigravity | — | `~/.gemini/antigravity/mcp_config.json` |
| Windsurf | — | `~/.codeium/windsurf/mcp_config.json` |
| OpenCode | `<cwd>/opencode.json` | `~/.config/opencode/opencode.json` |
| Kiro | `<cwd>/.kiro/settings/mcp.json` | `~/.kiro/settings/mcp.json` |

For Claude Code specifically, **global** scope writes the `databricks` entry into `~/.claude.json` (the same file that holds your other Claude Code settings), while **project** scope writes `<cwd>/.mcp.json`. Existing config files are backed up (`.bak`) and merged, not overwritten.

> **Note:** the MCP server runs from the cloned repo (Step 1) — the client config points at the venv Python and `run_server.py` by absolute path, so the repo must stay on disk.

#### Option B - manual
Run the steps manually:

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

Then, configure your MCP client:

**Claude Code** — add to your project's `.mcp.json` (create the file if it doesn't exist):

```json
{
  "mcpServers": {
    "databricks": {
      "command": "/path/to/ai-dev-kit/.venv/bin/python",
      "args": ["/path/to/ai-dev-kit/databricks-mcp-server/run_server.py"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "your-profile"},
      "defer_loading": true
    }
  }
}
```

Or register it with the Claude CLI. By default `claude mcp add-json` writes to Claude's own config (a per-project `local` entry inside `~/.claude.json`), **not** the project's `.mcp.json` file shown above; pass `-s project` to write `.mcp.json` instead:

```bash
claude mcp add-json databricks -s project '{"command":"/path/to/ai-dev-kit/.venv/bin/python","args":["/path/to/ai-dev-kit/databricks-mcp-server/run_server.py"],"env":{"DATABRICKS_CONFIG_PROFILE":"your-profile"},"defer_loading":true}'
```

**Cursor / Genie Code** — use the same JSON in your client's MCP config (e.g. Cursor's `.cursor/mcp.json`).

**Note:** the `env` block pins the Databricks profile the server authenticates with (see Step 3); `"defer_loading": true` improves startup time by not loading all tools upfront.

### Step 3: Authenticate

The server uses the Databricks Unified Authentication chain, so it picks up whatever the Databricks CLI/SDK already uses. Choose a profile in one of these ways:

```bash
# Option 1: Named profile from ~/.databrickscfg (recommended)
export DATABRICKS_CONFIG_PROFILE="your-profile"

# Option 2: Explicit host + token
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-token"
```

To make a profile available to a GUI MCP client, add it to the `env` block of the server config, e.g. `"env": {"DATABRICKS_CONFIG_PROFILE": "your-profile"}`.

### Step 4: Smoke test

Confirm the server starts and can reach your workspace:

```bash
# The server speaks MCP over stdio; it should start without errors, then Ctrl-C to exit.
.venv/bin/python databricks-mcp-server/run_server.py
```

Then in your MCP client, ask it to run a lightweight tool such as `get_current_user`, or `manage_warehouse` with the `list` action. A successful response confirms the server is installed, launched, and authenticated.

## Available Tools

The server registers **44 tools**. Most are *action-dispatch* tools: you pass an `action` argument (and sometimes a secondary type argument) to select the operation. The tables below list each tool, its supported actions, and what it does.

### SQL & Warehouses

| Tool | Actions | Description |
|------|---------|-------------|
| `execute_sql` | — | Execute a SQL query on a Databricks SQL warehouse (auto-selects one if not given) |
| `execute_sql_multi` | — | Execute multiple SQL statements with dependency-aware parallelism |
| `manage_warehouse` | `list`, `get_best` | List SQL warehouses or get the best available one |
| `get_table_stats_and_schema` | — | Get schema and statistics for tables |
| `get_volume_folder_details` | — | Get schema/stats for data files in a Volume folder |

### Compute

| Tool | Actions | Description |
|------|---------|-------------|
| `execute_code` | — | Execute code on Databricks via serverless or cluster compute |
| `manage_cluster` | `create`, `modify`, `start`, `terminate`, `delete`, `get` | Manage clusters |
| `manage_sql_warehouse` | `create`, `modify`, `delete` | Create, modify, or delete a SQL warehouse |
| `list_compute` | — | List compute resources: clusters, node types, or spark versions |

### Jobs

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_jobs` | `create`, `get`, `list`, `find_by_name`, `update`, `delete` | Manage Databricks jobs |
| `manage_job_runs` | `run_now`, `repair`, `get`, `get_output`, `cancel`, `list`, `wait` | Manage job runs |

### Spark Declarative Pipelines (SDP)

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_pipeline` | `create`, `create_or_update`, `get`, `update`, `delete`, `find_by_name` | Manage Spark Declarative Pipelines |
| `manage_pipeline_run` | `start`, `get`, `stop`, `get_events` | Manage pipeline runs |

### Unity Catalog

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_uc_objects` | `create`, `get`, `list`, `update`, `delete` | Manage UC namespace objects: catalog/schema/volume/function * |
| `manage_uc_grants` | `grant`, `revoke`, `get`, `get_effective` | Manage UC permissions |
| `manage_uc_storage` | `create`, `get`, `list`, `update`, `delete`, `validate` | Manage storage credentials and external locations * |
| `manage_uc_connections` | `create`, `get`, `list`, `update`, `delete`, `create_foreign_catalog` | Manage Lakehouse Federation connections |
| `manage_uc_tags` | `set_tags`, `unset_tags`, `set_comment`, `query_table_tags`, `query_column_tags` | Manage UC tags and comments |
| `manage_uc_security_policies` | `set_row_filter`, `drop_row_filter`, `set_column_mask`, `drop_column_mask`, `create_security_function` | Manage row-level security and column masking |
| `manage_uc_monitors` | `create`, `get`, `run_refresh`, `list_refreshes`, `delete` | Manage Lakehouse quality monitors |
| `manage_uc_sharing` | `create`, `get`, `list`, `delete`, `add_table`, `remove_table`, `grant_to_recipient`, `revoke_from_recipient`, `rotate_token`, `list_shares` | Manage Delta Sharing: shares, recipients, providers * |

> \* Some Unity Catalog tools take a secondary type argument (e.g. `object_type`, `resource_type`) that determines which of the listed actions apply. See the tool's own parameter docs for the exact combinations.

### Metric Views

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_metric_views` | `create`, `alter`, `describe`, `query`, `drop`, `grant` | Manage UC metric views (requires DBR 17.2+) |

### Vector Search

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_vs_endpoint` | `create_or_update`, `get`, `list`, `delete` | Manage Vector Search endpoints |
| `manage_vs_index` | `create_or_update`, `get`, `list`, `delete` | Manage Vector Search indexes |
| `manage_vs_data` | `upsert`, `delete`, `scan`, `sync` | Manage Vector Search index data |
| `query_vs_index` | — | Query a Vector Search index for similar documents |

### Lakebase

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_lakebase_database` | `create_or_update`, `get`, `list`, `delete` | Manage Lakebase PostgreSQL databases |
| `manage_lakebase_branch` | `create_or_update`, `delete` | Manage Autoscale branches |
| `manage_lakebase_sync` | `create_or_update`, `delete` | Manage Lakebase sync (reverse ETL) |
| `generate_lakebase_credential` | — | Generate a short-lived OAuth token for a Lakebase connection |

### Apps

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_app` | `create_or_update`, `get`, `list`, `delete` | Manage Databricks Apps |

### Genie Spaces

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_genie` | `create_or_update`, `get`, `list`, `delete`, `export`, `import` | Manage Genie Spaces |
| `ask_genie` | — | Ask a natural-language question to a Genie Space |

### Agent Bricks

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_ka` | `create_or_update`, `get`, `find_by_name`, `delete` | Manage Knowledge Assistants (RAG document Q&A) |
| `manage_mas` | `create_or_update`, `get`, `find_by_name`, `delete` | Manage Supervisor Agents (multi-agent orchestration) |

### AI/BI Dashboards

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_dashboard` | `create_or_update`, `get`, `list`, `delete`, `publish`, `unpublish` | Manage AI/BI dashboards |

### Model Serving

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_serving_endpoint` | `get`, `list`, `query` | Manage Model Serving endpoints |

### Workspace & Files

| Tool | Actions | Description |
|------|---------|-------------|
| `manage_workspace` | `status`, `list`, `switch`, `login` | Manage the active workspace connection (session-scoped) |
| `manage_workspace_files` | `upload`, `delete` | Upload or delete workspace files |
| `manage_volume_files` | `list`, `upload`, `download`, `delete`, `mkdir`, `get_info` | Manage Unity Catalog Volume files |

### PDF

| Tool | Actions | Description |
|------|---------|-------------|
| `generate_and_upload_pdf` | — | Convert HTML to PDF and upload to a Unity Catalog volume |

### Resource Tracking

| Tool | Actions | Description |
|------|---------|-------------|
| `list_tracked_resources` | — | List resources tracked in the project manifest |
| `delete_tracked_resource` | — | Delete a resource from the manifest (optionally from Databricks too) |

### User

| Tool | Actions | Description |
|------|---------|-------------|
| `get_current_user` | — | Get the current Databricks user identity |

## Architecture

For a high-level overview of how the MCP client, server, and `databricks-tools-core` fit together, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Development

The server is intentionally simple - each tool file just imports functions from `databricks-tools-core` and decorates them with `@mcp.tool`.

### Running Integration Tests

Integration tests run against a real Databricks workspace. Configure authentication first (see [Step 3: Authenticate](#step-3-authenticate) above).

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
- **AI Dev Kit installer:** run the repo's top-level `install.sh` (skills-only; the MCP server has its own installer described above).

See the [ai-dev-kit README](../README.md) for details. Skills are installed into your own project (e.g. `.claude/skills/`) and are picked up independently of this server.

## License

© Databricks, Inc. See [LICENSE.md](../LICENSE.md).
