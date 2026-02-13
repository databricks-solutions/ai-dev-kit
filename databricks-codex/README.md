# Databricks Codex Integration

Python SDK for integrating OpenAI Codex CLI with Databricks.

## Features

- **Configuration Management** - Programmatic control of `~/.codex/config.toml`
- **Authentication** - Bridge Databricks credentials into Codex environment
- **Executor** - Sync/async execution of `codex exec` with timeout handling
- **MCP Client** - Connect to Codex running as MCP server
- **Session Management** - Resume and fork Codex sessions

## Installation

```bash
# Basic installation
pip install databricks-codex

# With Databricks SDK support
pip install databricks-codex[databricks]

# With HTTP transport for MCP
pip install databricks-codex[http]

# All optional dependencies
pip install databricks-codex[all]

# Development dependencies
pip install databricks-codex[dev]
```

## Prerequisites

- Python 3.9+
- Codex CLI installed: `npm i -g @openai/codex`
- Codex authenticated: `codex login`
- (Optional) Databricks CLI configured for credential injection

## Quick Start

### Install Skills + MCP (Codex Session)

```bash
# From ai-dev-kit repo root
bash databricks-codex/scripts/install_codex_skills_and_mcp.sh
# or override profile explicitly
bash databricks-codex/scripts/install_codex_skills_and_mcp.sh --profile ai-specialist
```

This installs Databricks skills into `~/.codex/skills` and writes a project MCP entry to `.codex/config.toml` for `databricks-mcp-server`.
By default it uses the first profile from `databricks auth profiles`.
Restart Codex after running it.

### Run It (End-to-End)

```bash
# from ai-dev-kit repo root
source ./.databricks_cfg  # or export DATABRICKS_HOST / DATABRICKS_TOKEN

# install skills + MCP wiring
bash databricks-codex/scripts/install_codex_skills_and_mcp.sh

# run the installer + dashboard-prompt integration tests
cd databricks-codex
uv run pytest tests/integration/test_install_and_dashboard_prompt.py -vv
```

What this validates:
- installer copies skills into `~/.codex/skills`
- project MCP config is written to `.codex/config.toml`
- Codex can execute a prompt that generates dashboard SQL

### Configuration

```python
from databricks_codex import CodexConfigManager

# Configure Databricks MCP server
manager = CodexConfigManager()
manager.configure_databricks_mcp(profile="DEFAULT")

# Check configuration
if manager.has_databricks_mcp():
    config = manager.get_databricks_mcp_config()
    print(f"MCP server: {config.command}")
```

### Authentication

```python
from databricks_codex import check_codex_auth, login_codex, CodexAuthMethod

# Check auth status
status = check_codex_auth()
if status.is_authenticated:
    print(f"Logged in via {status.method.value}")
else:
    # Login with device code (for headless environments)
    login_codex(method=CodexAuthMethod.DEVICE_CODE)
```

### Executor

```python
from databricks_codex import CodexExecutor, CodexExecOptions, SandboxMode

# Create executor
executor = CodexExecutor()

# Synchronous execution
options = CodexExecOptions(
    prompt="Create a Python function to calculate factorial",
    sandbox_mode=SandboxMode.READ_ONLY,
    timeout=60,
)
result = executor.exec_sync(options)
print(result.stdout)

# Async execution with Databricks context
import asyncio

async def main():
    options = CodexExecOptions(
        prompt="Query the customers table",
        inject_databricks_env=True,
        databricks_profile="PROD",
    )
    result = await executor.exec_async(options)

    if result.operation_id:
        # Long-running operation handed off
        print(f"Operation {result.operation_id} running in background")
    else:
        print(result.stdout)

asyncio.run(main())
```

### MCP Client

```python
from databricks_codex import CodexMCPClient
import asyncio

async def main():
    async with CodexMCPClient() as client:
        # List available tools
        tools = await client.list_tools()
        for tool in tools:
            print(f"{tool.name}: {tool.description}")

        # Call a tool
        result = await client.call_tool(
            "generate_code",
            {"prompt": "Create a hello world function"}
        )
        print(result)

asyncio.run(main())
```

### Session Management

```python
from databricks_codex import SessionManager

manager = SessionManager()

# List recent sessions
sessions = manager.list_sessions(limit=5)
for session in sessions:
    print(f"{session.session_id}: {session.created_at}")

# Resume last session
manager.resume_session(last=True)

# Fork a session
new_id = manager.fork_session(
    "original-session-id",
    new_prompt="Continue but focus on error handling"
)
```

## API Reference

### Models

| Class | Description |
|-------|-------------|
| `SandboxMode` | Enum: READ_ONLY, WORKSPACE_WRITE, FULL_ACCESS |
| `ExecutionStatus` | Enum: PENDING, RUNNING, COMPLETED, FAILED, TIMEOUT |
| `CodexAuthMethod` | Enum: CHATGPT_OAUTH, DEVICE_CODE, API_KEY, NONE |
| `CodexExecOptions` | Pydantic model for executor options |
| `ExecutionResult` | Dataclass for execution results |
| `MCPToolInfo` | Dataclass for MCP tool metadata |

### Configuration

| Class/Function | Description |
|----------------|-------------|
| `CodexConfigManager` | Manage `~/.codex/config.toml` |
| `MCPServerConfig` | MCP server configuration model |
| `CodexConfig` | Full configuration model |

### Authentication

| Function | Description |
|----------|-------------|
| `check_codex_auth()` | Check Codex authentication status |
| `login_codex()` | Authenticate with Codex CLI |
| `logout_codex()` | Log out from Codex CLI |
| `get_combined_auth_context()` | Get Databricks credentials |
| `get_databricks_env()` | Get env vars for Databricks |

### Executor

| Class/Method | Description |
|--------------|-------------|
| `CodexExecutor` | Execute Codex commands |
| `exec_sync()` | Synchronous execution |
| `exec_async()` | Async execution with timeout handling |
| `get_operation()` | Check async operation status |

### MCP Client

| Class/Method | Description |
|--------------|-------------|
| `CodexMCPClient` | MCP protocol client |
| `connect()` | Establish connection |
| `list_tools()` | List available tools |
| `call_tool()` | Execute a tool |

### Session Management

| Class/Method | Description |
|--------------|-------------|
| `SessionManager` | Manage Codex sessions |
| `list_sessions()` | List recent sessions |
| `resume_session()` | Resume a session |
| `fork_session()` | Fork a session |

## Testing

```bash
# Export Databricks env vars for integration tests
export DATABRICKS_HOST="https://<your-workspace-host>"
export DATABRICKS_TOKEN="<your-pat>"
# or: source ./.databricks_cfg

# Run unit tests
pytest tests/ -v --ignore=tests/integration

# Run integration tests (requires Codex + Databricks)
pytest tests/integration/ -v -m integration

# Run installer + dashboard prompt tests only
pytest tests/integration/test_install_and_dashboard_prompt.py -vv

# Run with coverage
pytest tests/ --cov=databricks_codex --cov-report=html
```

## License

Apache-2.0
