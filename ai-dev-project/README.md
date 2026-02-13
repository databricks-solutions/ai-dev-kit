# Databricks AI Dev Project (Starter Project / Template)

A template for creating a new project configured with Databricks AI Dev Kit for Claude Code or Cursor. Use this as a template to create a new AI coding project focused on Databricks. It can also be used to experiment with the skills, MCP server integration, and test tools before using them in a real project.

## Prerequisites

- [uv](https://github.com/astral-sh/uv) - Python package manager
- [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/) - Command line interface for Databricks
- [Claude Code](https://claude.ai/code) or [Cursor](https://cursor.com) - AI Coding environment

## Quick Start

### 1. Setup

Make scripts executable and install dependencies.
```bash
chmod +x setup.sh cleanup.sh
./setup.sh
```

This will:
- Check for `uv` installation
- Install dependencies for `databricks-tools-core` and `databricks-mcp-server`
- Install Databricks skills to `.claude/skills/`
- Setup MCP server config for this project in `.mcp.json` (Claude Code) and `.cursor/mcp.json` (Cursor)
- Create `CLAUDE.md` with project context

### 2. Configure Databricks Credentials

Set your Databricks credentials:

Option 1: Profile:
```bash
export DATABRICKS_CONFIG_PROFILE=your-profile
```

Option 2: Host and Databricks Personal Access Token:
```bash
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."
```

Or create a `.env.local` file (gitignored):

```bash
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...
```

### 3. Run Claude Code

```bash
# Start Claude Code in this directory
claude
```

### 4. Test MCP Tools

Try these commands to test the Databricks MCP integration:

```
# List available warehouses
List my SQL warehouses

# Run a simple query
Run this SQL query: SELECT current_timestamp()

# Check clusters
What clusters do I have available?

# Test Unity Catalog
List the catalogs in my workspace
```

## MCP Server Configuration

The setup script registers the `databricks-mcp-server` to run from the sibling directory.

### Manual MCP Configuration - Claude

In your project directory, create `.mcp.json` (Claude) or `.cursor/mcp.json` (Cursor). **Replace `/path/to/ai-dev-kit`** with the actual path where you cloned the repo.


```json
{
  "mcpServers": {
    "databricks": {
      "command": "/path/to/ai-dev-kit/databricks-mcp-server/.venv/bin/python",
      "args": ["/path/to/ai-dev-kit/databricks-mcp-server/run_server.py"]
    }
  }
}
```

### Manual MCP Configuration - Claude CLI

To manually add or reconfigure the MCP server from another project directory:

Set variable with directory to your path:
```bash
export DEV_KIT_DIR=/path/to/ai-dev-kit
```

Run remove and add script for Claude. 
```bash
# Remove existing (if any)
claude mcp remove databricks

claude mcp add --transport stdio databricks -- ${DEV_KIT_DIR}/.venv/bin/python -- ${DEV_KIT_DIR}/databricks-mcp-server/run_server.py
```

To verify the server is configured:

```bash
claude mcp list
```

### Cursor-Specific Setup

#### Enable the MCP Server

After adding the MCP config, you must enable the server in Cursor:
1. Open Cursor Settings (`Cmd+,`)
2. Search for "MCP" 
3. Find "databricks" under Installed MCP Servers
4. Toggle it **on**

#### Authentication with Config Profiles

Cursor spawns MCP servers as subprocesses that don't inherit shell environment variables. If you use `DATABRICKS_CONFIG_PROFILE`, you must pass it explicitly in the config:

```json
{
  "mcpServers": {
    "databricks": {
      "command": "/path/to/databricks-mcp-server/.venv/bin/python",
      "args": ["/path/to/databricks-mcp-server/run_server.py"],
      "env": {
        "DATABRICKS_CONFIG_PROFILE": "your-profile-name"
      }
    }
  }
}
```

#### Project vs Global MCP Configs

Cursor loads MCP configs from both locations:
- **Global**: `~/.cursor/mcp.json` (applies to all projects)
- **Project**: `.cursor/mcp.json` (project-specific)

If you have the same server in both, the global config may take precedence. For project-specific profiles, remove the server from the global config.


## Available MCP Tools

Once configured, your coding agent has access to these Databricks tools:

### SQL Warehouse Tools
| Tool | Description |
|------|-------------|
| `mcp_databricks_execute_sql` | Execute SQL on Databricks SQL Warehouse |
| `mcp_databricks_execute_sql_multi` | Execute multiple SQL statements with dependency-aware parallelism |
| `mcp_databricks_list_warehouses` | List all SQL warehouses |
| `mcp_databricks_get_best_warehouse` | Get best available SQL warehouse |
| `mcp_databricks_get_table_details` | Get table schema and statistics |

### Cluster Tools
| Tool | Description |
|------|-------------|
| `mcp_databricks_list_clusters` | List all clusters |
| `mcp_databricks_get_best_cluster` | Get best available cluster |
| `mcp_databricks_execute_databricks_command` | Execute code (Python/Scala/SQL/R) on cluster |
| `mcp_databricks_run_python_file_on_databricks` | Run local Python file on cluster |

### Workspace File Tools
| Tool | Description |
|------|-------------|
| `mcp_databricks_upload_folder` | Upload folder to Databricks workspace |
| `mcp_databricks_upload_file` | Upload file to Databricks workspace |

### Pipeline Tools
| Tool | Description |
|------|-------------|
| `mcp_databricks_create_or_update_pipeline` | Main tool for pipeline management (create/update/run) |
| `mcp_databricks_find_pipeline_by_name` | Find pipeline by name |
| `mcp_databricks_create_pipeline` | Create new pipeline |
| `mcp_databricks_get_pipeline` | Get pipeline details |
| `mcp_databricks_update_pipeline` | Update pipeline configuration |
| `mcp_databricks_delete_pipeline` | Delete pipeline |
| `mcp_databricks_start_update` | Start pipeline update/validation |
| `mcp_databricks_get_update` | Get pipeline update status |
| `mcp_databricks_stop_pipeline` | Stop running pipeline |
| `mcp_databricks_get_pipeline_events` | Get pipeline events/errors |

## Skills

The setup script installs these skills to `.claude/skills/`:

- **asset-bundles** - Databricks Asset Bundles
- **databricks-app-apx** - Full-stack apps with APX framework (FastAPI + React)
- **databricks-app-python** - Python apps with Dash, Streamlit, Flask
- **databricks-python-sdk** - Python SDK patterns
- **mlflow-evaluation** - MLflow evaluation and trace analysis
- **spark-declarative-pipelines** - Spark Declarative Pipelines (SDP/DLT)
- **databricks-data-generation** - Test data generation

Use skills by asking Claude:
```
Load the spark-declarative-pipelines skill and help me create a pipeline
```

## Cleanup

To reset the project and start fresh:

```bash
./cleanup.sh
```

This removes:
- `.claude/` directory (skills, mcp.json, sessions)
- Generated test files (*.parquet, *.csv, etc.)
- Temporary directories

## Troubleshooting

### MCP Server Not Found

Make sure you're in the `ai-dev-kit` repository and the `databricks-mcp-server` directory exists:

```bash
ls ../databricks-mcp-server/
```

### Authentication Errors

Verify your credentials:

```bash
echo $DATABRICKS_HOST
echo $DATABRICKS_TOKEN
```

### Tool Errors

Check the MCP server logs - Claude Code shows tool errors in the chat. Common issues:
- Invalid warehouse ID
- Missing permissions
- Network connectivity

### Cursor: MCP Server Not Loading

1. Ensure the server is enabled in Cursor Settings → MCP
2. Reload window (`Cmd+Shift+P` → "Developer: Reload Window")
3. Check for conflicts with `~/.cursor/mcp.json`

### Cursor: Authentication Errors with Config Profiles

If using `DATABRICKS_CONFIG_PROFILE`, add it to the `env` block in `.cursor/mcp.json`. Shell environment variables are not inherited by MCP server subprocesses.

## Project Structure

```
ai-dev-project/
├── .claude/
│   └── skills/            # Installed Databricks skills
│       ├── asset-bundles/
│       ├── spark-declarative-pipelines/
│       └── ...
├── .cursor/
│   └── mcp.json           # MCP server configuration
├── .gitignore             # Ignores test artifacts
├── .mcp.json               # MCP server configuration
├── CLAUDE.md              # Project context for Claude
├── setup.sh               # Setup script
├── cleanup.sh             # Cleanup script
└── README.md              # This file
```
