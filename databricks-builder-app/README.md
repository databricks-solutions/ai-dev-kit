# Databricks Builder App

> **Security Notice:** This application wraps Claude Code. Projects created within the app by different users are not strongly isolated from each other (this project doesn't implement solutions like Firecracker microVM or Docker to isolate Claude sessions from the app). Only grant access to users you trust.

A web application that provides a Claude Code agent interface with integrated Databricks tools. Users interact with Claude through a chat interface, and the agent can execute SQL queries, manage pipelines, upload files, and more on their Databricks workspace.

> **✅ Event Loop Fix Implemented**
>
> We've implemented a workaround for `claude-agent-sdk` [issue #462](https://github.com/anthropics/claude-agent-sdk-python/issues/462) that was preventing the agent from executing Databricks tools in FastAPI contexts.
>
> **Solution:** The agent now runs in a fresh event loop in a separate thread, with `contextvars` properly copied to preserve Databricks authentication. See [EVENT_LOOP_FIX.md](./EVENT_LOOP_FIX.md) for details.
>
> **Status:** ✅ Fully functional - agent can execute all Databricks tools successfully

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Web Application                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  React Frontend (client/)           FastAPI Backend (server/)               │
│  ┌─────────────────────┐            ┌─────────────────────────────────┐     │
│  │ Chat UI             │◄──────────►│ /api/invoke_agent               │     │
│  │ Project Selector    │   SSE      │ /api/projects                   │     │
│  │ Conversation List   │            │ /api/conversations              │     │
│  └─────────────────────┘            └─────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Claude Code Session                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  Each user message spawns a Claude Code agent session via claude-agent-sdk  │
│                                                                              │
│  Built-in Tools:              MCP Tools (Databricks):         Skills:       │
│  ┌──────────────────┐         ┌─────────────────────────┐    ┌───────────┐  │
│  │ Read, Write, Edit│         │ execute_sql             │    │ sdp       │  │
│  │ Glob, Grep, Skill│         │ create_or_update_pipeline    │ dabs      │  │
│  └──────────────────┘         │ upload_folder           │    │ sdk       │  │
│                               │ execute_code            │    │ ...       │  │
│                               │ ...                     │    └───────────┘  │
│                               └─────────────────────────┘                   │
│                                          │                                  │
│                                          ▼                                  │
│                               ┌─────────────────────────┐                   │
│                               │ databricks-mcp-server   │                   │
│                               │ (in-process SDK tools)  │                   │
│                               └─────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                             │
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Databricks Workspace                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  SQL Warehouses    │    Clusters    │    Unity Catalog    │    Workspace    │
└─────────────────────────────────────────────────────────────────────────────┘
```

## How It Works

### 1. Claude Code Sessions

When a user sends a message, the backend creates a Claude Code session using the `claude-agent-sdk`:

```python
from claude_agent_sdk import ClaudeAgentOptions, query

options = ClaudeAgentOptions(
    cwd=str(project_dir),           # Project working directory
    allowed_tools=allowed_tools,     # Built-in + MCP tools
    permission_mode='bypassPermissions',  # Auto-accept all tools including MCP
    resume=session_id,               # Resume previous conversation
    mcp_servers=mcp_servers,         # Databricks MCP server config
    system_prompt=system_prompt,     # Databricks-focused prompt
    setting_sources=['user', 'project'],  # Load skills from .claude/skills
)

async for msg in query(prompt=message, options=options):
    yield msg  # Stream to frontend
```

Key features:
- **Session Resumption**: Each conversation stores a `claude_session_id` for context continuity
- **Streaming**: All events (text, thinking, tool_use, tool_result) stream to the frontend in real-time
- **Project Isolation**: Each project has its own working directory with sandboxed file access

### 2. Authentication Flow

The app supports multi-user authentication using per-request credentials:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Authentication Flow                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Production (Databricks Apps)         Development (Local)                   │
│  ┌──────────────────────────┐         ┌──────────────────────────┐          │
│  │ Request Headers:         │         │ Environment Variables:   │          │
│  │ X-Forwarded-User         │         │ DATABRICKS_HOST          │          │
│  │ X-Forwarded-Access-Token │         │ DATABRICKS_TOKEN         │          │
│  └────────────┬─────────────┘         └────────────┬─────────────┘          │
│               │                                    │                        │
│               └──────────────┬─────────────────────┘                        │
│                              ▼                                              │
│               ┌──────────────────────────┐                                  │
│               │ set_databricks_auth()    │  (contextvars)                   │
│               │ - host                   │                                  │
│               │ - token                  │                                  │
│               └────────────┬─────────────┘                                  │
│                            ▼                                                │
│               ┌──────────────────────────┐                                  │
│               │ get_workspace_client()   │  (used by all tools)             │
│               │ - Returns client with    │                                  │
│               │   context credentials    │                                  │
│               └──────────────────────────┘                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**How it works:**

1. **Request arrives** - The FastAPI backend extracts credentials:
   - **Production**: `X-Forwarded-User` and `X-Forwarded-Access-Token` headers (set by Databricks Apps proxy)
   - **Development**: Falls back to `DATABRICKS_HOST` and `DATABRICKS_TOKEN` env vars

2. **Auth context set** - Before invoking the agent:
   ```python
   from databricks_tools_core.auth import set_databricks_auth, clear_databricks_auth

   set_databricks_auth(workspace_url, user_token)
   try:
       # All tool calls use this user's credentials
       async for event in stream_agent_response(...):
           yield event
   finally:
       clear_databricks_auth()
   ```

3. **Tools use context** - All Databricks tools call `get_workspace_client()` which:
   - First checks contextvars for per-request credentials
   - Falls back to environment variables if no context set

This ensures each user's requests use their own Databricks credentials, enabling proper access control and audit logging.

### 3. MCP Integration (Databricks Tools)

Databricks tools are loaded in-process using the Claude Agent SDK's MCP server feature:

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

# Tools are dynamically loaded from databricks-mcp-server
server = create_sdk_mcp_server(name='databricks', tools=sdk_tools)

options = ClaudeAgentOptions(
    mcp_servers={'databricks': server},
    allowed_tools=['mcp__databricks__execute_sql', ...],
)
```

Tools are exposed as `mcp__databricks__<tool_name>` and include:
- SQL execution (`execute_sql`, `execute_sql_multi`)
- Warehouse management (`list_warehouses`, `get_best_warehouse`)
- Cluster execution (`execute_code`)
- Pipeline management (`create_or_update_pipeline`, `start_update`, etc.)
- File operations (`upload_to_workspace`)

### 4. Skills System

Skills provide specialized guidance for Databricks development tasks. They are markdown files with instructions and examples that Claude can load on demand.

**Skill loading flow:**
1. On startup, skills are copied from `../databricks-skills/` to `./skills/`
2. When a project is created, skills are copied to `project/.claude/skills/`
3. The agent can invoke skills using the `Skill` tool: `skill: "sdp"`

Skills include:
- **databricks-bundles**: DABs configuration
- **databricks-app-apx**: Full-stack apps with APX framework (FastAPI + React)
- **databricks-app-python**: Python apps with Dash, Streamlit, Flask
- **databricks-python-sdk**: Python SDK patterns
- **databricks-mlflow-evaluation**: MLflow evaluation and trace analysis
- **databricks-spark-declarative-pipelines**: Spark Declarative Pipelines (SDP) development
- **databricks-synthetic-data-gen**: Creating test datasets

### 5. Project Persistence

Projects are stored in the local filesystem with automatic backup to PostgreSQL:

```
projects/
  <project-uuid>/
    .claude/
      skills/        # Copied skills for this project
    src/             # User's code files
    ...
```

**Backup system:**
- After each agent interaction, the project is marked for backup
- A background worker runs every 10 minutes
- Projects are zipped and stored in PostgreSQL (Lakebase)
- On access, missing projects are restored from backup

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv) package manager
- Databricks workspace with:
  - SQL warehouse (for SQL queries)
  - Cluster (for Python/PySpark execution)
  - Unity Catalog enabled (recommended)
- PostgreSQL database (Lakebase) for project persistence — autoscale or provisioned

### Quick Start (Local Development)

One command provisions Lakebase, installs all dependencies, and starts the app:

```bash
cd databricks-builder-app
./scripts/start_local.sh --profile <your-profile>
```

This will:
- Check prerequisites (uv, Node.js, npm, Databricks CLI v0.287.0+)
- Get credentials from your Databricks CLI profile
- Provision a Lakebase Autoscale database via DAB (if needed)
- Generate `.env.local` with your workspace settings
- Install backend and frontend dependencies
- Install all Databricks skills (local + external)
- Test the Lakebase connection
- Start backend (http://localhost:8000) and frontend (http://localhost:3000)

#### Options

```bash
# First time — everything from scratch
./scripts/start_local.sh --profile dbx_shared_demo

# Subsequent runs — fast (deps cached, Lakebase exists)
./scripts/start_local.sh --profile dbx_shared_demo

# Skip Lakebase provisioning
./scripts/start_local.sh --profile dbx_shared_demo --skip-lakebase

# Force reinstall all dependencies
./scripts/start_local.sh --profile dbx_shared_demo --force-install

# Regenerate .env.local
./scripts/start_local.sh --profile dbx_shared_demo --force-env

# Custom Lakebase project name
./scripts/start_local.sh --profile dbx_shared_demo --lakebase-id my-custom-db
```

#### Access the App

- **Frontend**: <http://localhost:3000>
- **Backend API**: <http://localhost:8000>
- **API Docs**: <http://localhost:8000/docs>

Press `Ctrl+C` to stop both servers.

#### (Optional) Configure Claude via Databricks Model Serving

If you're routing Claude API calls through Databricks Model Serving instead of directly to Anthropic, create `.claude/settings.json` in the **repository root** (not in the app directory):

```json
{
    "env": {
        "ANTHROPIC_MODEL": "databricks-claude-sonnet-4-5",
        "ANTHROPIC_BASE_URL": "https://your-workspace.cloud.databricks.com/serving-endpoints/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "dapi...",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "databricks-claude-opus-4-5",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "databricks-claude-sonnet-4-5"
    }
}
```

Notes:

- `ANTHROPIC_AUTH_TOKEN` should be a Databricks PAT, not an Anthropic API key
- `ANTHROPIC_BASE_URL` should point to your Databricks Model Serving endpoint
- If this file doesn't exist, the app uses your `ANTHROPIC_API_KEY` from `.env.local`

### Configuration Details

#### Databricks Authentication Modes

The app supports two authentication modes:

**1. Local Development (Environment Variables)**
- Uses `DATABRICKS_HOST` and `DATABRICKS_TOKEN` from `.env.local`
- All users share the same credentials
- Good for local development and testing

**2. Production (Request Headers)**
- Uses `X-Forwarded-User` and `X-Forwarded-Access-Token` headers
- Set automatically by Databricks Apps proxy
- Each user has their own credentials
- Proper multi-user isolation

#### Skills Configuration

Skills are loaded from `../databricks-skills/` and filtered by the `ENABLED_SKILLS` environment variable:

- `databricks-python-sdk`: Patterns for using the Databricks Python SDK
- `databricks-spark-declarative-pipelines`: SDP/DLT pipeline development
- `databricks-synthetic-data-gen`: Creating test datasets
- `databricks-app-apx`: Full-stack apps with React (APX framework)
- `databricks-app-python`: Python apps with Dash, Streamlit, Flask

**Adding custom skills:**
1. Create a new directory in `../databricks-skills/`
2. Add a `SKILL.md` file with frontmatter:
   ```markdown
   ---
   name: my-skill
   description: "Description of the skill"
   ---
   
   # Skill content here
   ```
3. Add the skill name to `ENABLED_SKILLS` in `.env.local`

#### Database Setup

The app uses PostgreSQL (Lakebase) for:
- Project metadata
- Conversation history
- Message storage
- Project backups (zipped project files)

**Migrations:**
```bash
# Run migrations (done automatically on startup)
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"
```

### Troubleshooting

#### "MCP connection unstable" or agent not executing tools

This was a known issue with `claude-agent-sdk` in FastAPI contexts. We've implemented a fix:

- ✅ Agent runs in a fresh event loop in a separate thread
- ✅ Context variables (Databricks auth) are properly propagated
- ✅ All MCP tools work correctly

See [EVENT_LOOP_FIX.md](./EVENT_LOOP_FIX.md) for technical details.

#### Skills not loading

Check:
1. `ENABLED_SKILLS` environment variable in `.env.local`
2. Skill names match directory names in `../databricks-skills/`
3. Each skill has a `SKILL.md` file with proper frontmatter
4. Check logs: `Copied X skills to ./skills`

#### Databricks authentication failing

Check:
1. `DATABRICKS_HOST` is correct (no trailing slash)
2. `DATABRICKS_TOKEN` is valid and not expired
3. Token has proper permissions (cluster access, SQL warehouse access, etc.)
4. If using Databricks Model Serving, check `.claude/settings.json` configuration

#### Port already in use

```bash
# Kill processes on ports 8000 and 3000
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9
```

### Production Build

```bash
# Build frontend
cd client && npm run build && cd ..

# Run with uvicorn
uvicorn server.app:app --host 0.0.0.0 --port 8000
```

## Project Structure

```
databricks-builder-app/
├── server/                 # FastAPI backend
│   ├── app.py             # Main FastAPI app
│   ├── db/                # Database models and migrations
│   │   ├── models.py      # SQLAlchemy models
│   │   └── database.py    # Session management
│   ├── routers/           # API endpoints
│   │   ├── agent.py       # /api/agent/* (invoke, etc.)
│   │   ├── projects.py    # /api/projects/*
│   │   └── conversations.py
│   └── services/          # Business logic
│       ├── agent.py       # Claude Code session management
│       ├── databricks_tools.py  # MCP tool loading from SDK
│       ├── user.py        # User auth (headers/env vars)
│       ├── skills_manager.py
│       ├── backup_manager.py
│       └── system_prompt.py
├── client/                # React frontend
│   ├── src/
│   │   ├── pages/         # Main pages (ProjectPage, etc.)
│   │   └── components/    # UI components
│   └── package.json
├── alembic/               # Database migrations
├── scripts/               # Utility scripts
│   ├── start_local.sh     # Local development (one command)
│   └── _legacy/            # Old setup.sh and start_dev.sh
├── skills/                # Cached skills (gitignored)
├── projects/              # Project working directories (gitignored)
├── pyproject.toml         # Python dependencies
└── .env.example           # Environment template
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/me` | GET | Get current user info |
| `/api/health` | GET | Health check |
| `/api/system_prompt` | GET | Preview the system prompt |
| `/api/projects` | GET | List all projects |
| `/api/projects` | POST | Create new project |
| `/api/projects/{id}` | GET | Get project details |
| `/api/projects/{id}` | PATCH | Update project name |
| `/api/projects/{id}` | DELETE | Delete project |
| `/api/projects/{id}/conversations` | GET | List project conversations |
| `/api/projects/{id}/conversations` | POST | Create new conversation |
| `/api/projects/{id}/conversations/{cid}` | GET | Get conversation with messages |
| `/api/projects/{id}/files` | GET | List files in project directory |
| `/api/invoke_agent` | POST | Start agent execution (returns execution_id) |
| `/api/stream_progress/{execution_id}` | POST | SSE stream of agent events |
| `/api/stop_stream/{execution_id}` | POST | Cancel an active execution |
| `/api/projects/{id}/skills/available` | GET | List skills with enabled status |
| `/api/projects/{id}/skills/enabled` | PUT | Update enabled skills for project |
| `/api/projects/{id}/skills/reload` | POST | Reload skills from source |
| `/api/projects/{id}/skills/tree` | GET | Get skills file tree |
| `/api/projects/{id}/skills/file` | GET | Get skill file content |
| `/api/clusters` | GET | List available Databricks clusters |
| `/api/warehouses` | GET | List available SQL warehouses |
| `/api/mlflow/status` | GET | Get MLflow tracing status |

## Deploying to Databricks Apps

The Builder App uses an automated deploy script that provisions all infrastructure and deploys the app in a single command.

### Prerequisites

- **Databricks CLI v0.287.0+** — [Install](https://docs.databricks.com/aws/en/dev-tools/cli/install)
- **Node.js 18+** — for building the frontend
- **uv** — Python package manager ([Install](https://github.com/astral-sh/uv))
- **Databricks workspace** with Lakebase Autoscaling enabled

### Quick Deploy

```bash
cd databricks-builder-app

# Full deploy — creates Lakebase, builds frontend, installs skills, creates app, grants permissions, deploys
./scripts/deploy.sh <app-name> --profile <your-profile>
```

That's it. The script handles everything:

| Step | What the script does |
|------|---------------------|
| 1 | Checks prerequisites (CLI version, auth) |
| 2 | Provisions Lakebase Autoscale via Databricks Asset Bundle (`databricks.yml`) |
| 3 | Builds the React frontend |
| 4 | Stages server code, packages, skills, and generates `app.yaml` |
| 5 | Creates the Databricks App (if it doesn't exist) |
| 6 | Creates Lakebase OAuth role and grants PostgreSQL permissions for the app's service principal |
| 7 | Uploads everything to workspace |
| 8 | Deploys the app |

### Deploy Options

```bash
# Full deploy from scratch
./scripts/deploy.sh my-builder-app --profile dbx_shared_demo

# Quick redeploy (skip Lakebase + frontend build + skills download)
./scripts/deploy.sh my-builder-app --profile dbx_shared_demo --skip-lakebase --skip-build --skip-skills

# Custom Lakebase project name
./scripts/deploy.sh my-builder-app --profile dbx_shared_demo --lakebase-id my-custom-db

# All options
./scripts/deploy.sh --help
```

### What Gets Created

| Resource | Details |
|----------|---------|
| **Lakebase Autoscale project** | PostgreSQL 17, 0.5-2 CU, scale-to-zero after 5 min |
| **Databricks App** | FastAPI backend + React frontend |
| **Lakebase OAuth role** | For the app's service principal |
| **PostgreSQL schema** | `builder_app` with full grants for the SP |
| **Database tables** | Created automatically via alembic migrations on first startup |

### Infrastructure as Code

The Lakebase database is managed declaratively via a Databricks Asset Bundle (`databricks.yml`):

```yaml
bundle:
  name: databricks-builder-app

variables:
  lakebase_project_id:
    description: "Lakebase project ID"
    default: "builder-app-db"

resources:
  postgres_projects:
    builder_db:
      project_id: ${var.lakebase_project_id}
      display_name: "builder-app-db"
      pg_version: 17
      default_endpoint_settings:
        autoscaling_limit_min_cu: 0.5
        autoscaling_limit_max_cu: 2
        suspend_timeout_duration: "300s"
```

You can manage the Lakebase infrastructure independently:

```bash
# Deploy/update Lakebase only
databricks bundle deploy --profile <profile>

# Destroy Lakebase (does NOT affect the app)
databricks bundle destroy --profile <profile>
```

### Redeploying After Code Changes

```bash
# Full redeploy (rebuilds everything)
./scripts/deploy.sh my-builder-app --profile <profile>

# Quick redeploy (server code changes only)
./scripts/deploy.sh my-builder-app --profile <profile> --skip-lakebase --skip-build --skip-skills
```

### Destroying Everything

```bash
# Delete the app
databricks apps delete my-builder-app --profile <profile>

# Delete the Lakebase database
databricks bundle destroy --profile <profile> --auto-approve
```

### MLflow Tracing

The app automatically traces Claude Code conversations to MLflow. Traces include user prompts, Claude responses, tool usage, and session metadata.

The deploy script configures tracing to the `/Workspace/Shared/builder_app_ml_trace` experiment by default. To customize, edit the `MLFLOW_EXPERIMENT_NAME` value in the generated `app.yaml` section of `scripts/deploy.sh`.

See the [Databricks MLflow Tracing documentation](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code) for more details.

### Deployment Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| CLI version too old | Need v0.287.0+ for Lakebase DAB support | `curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh \| sh` |
| `project with such id already exists` | Lakebase project name conflict | Use `--lakebase-id <different-name>` or destroy existing: `databricks bundle destroy` |
| `password authentication failed` | Lakebase OAuth role not created | Re-run deploy — Step 6 handles this automatically |
| `permission denied for table` | PostgreSQL grants missing | Re-run deploy — Step 6 is idempotent |
| `relation does not exist` | Migrations didn't run | Redeploy the app to trigger migrations |
| App shows blank page | Check logs: `databricks apps logs <app-name>` | Usually a package install error — check requirements.txt |

## Embedding in Other Apps

If you want to embed the Databricks agent into your own application, see the integration example at:

```
scripts/_integration-example/
```

This provides a minimal working example with setup instructions for integrating the agent services into external frameworks.

## Related Packages

- **databricks-tools-core**: Core MCP functionality and SQL operations
- **databricks-mcp-server**: MCP server exposing Databricks tools
- **databricks-skills**: Skill definitions for Databricks development
