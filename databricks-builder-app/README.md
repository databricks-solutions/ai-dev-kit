# Databricks Builder App

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
│                               │ run_python_file         │    │ ...       │  │
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
- Cluster execution (`execute_databricks_command`, `run_python_file_on_databricks`)
- Pipeline management (`create_or_update_pipeline`, `start_update`, etc.)
- File operations (`upload_file`, `upload_folder`)

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

### Quick Start

#### 1. Run the Setup Script

From the repository root:

```bash
cd databricks-builder-app
./scripts/setup.sh
```

This will:

- Verify prerequisites (uv, Node.js, npm)
- Create a `.env.local` file from `.env.example` (if one doesn't already exist)
- Install backend Python dependencies via `uv sync`
- Install sibling packages (`databricks-tools-core`, `databricks-mcp-server`)
- Install frontend Node.js dependencies

#### 2. Configure Your `.env.local` File

> **You must do this before running the app.** The setup script creates a `.env.local` file from `.env.example`, but all values are placeholders. Open `.env.local` and fill in your actual values.

The `.env.local` file is gitignored and will never be committed. At a minimum, you need to set these:

```bash
# Required: Your Databricks workspace
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...

# Required: Database for project persistence (pick ONE option)

# Option A — Autoscale Lakebase (recommended, scales to zero):
LAKEBASE_ENDPOINT=projects/<project-name>/branches/production/endpoints/primary
LAKEBASE_DATABASE_NAME=databricks_postgres

# Option B — Provisioned Lakebase (fixed capacity):
# LAKEBASE_INSTANCE_NAME=your-lakebase-instance
# LAKEBASE_DATABASE_NAME=databricks_postgres

# Option C — Static connection URL (any type, simplest for local dev):
# LAKEBASE_PG_URL=postgresql://user:password@host:5432/database?sslmode=require
```

The app auto-detects the mode based on which variable is set:
- `LAKEBASE_ENDPOINT` → autoscale mode (`client.postgres` API, host looked up automatically)
- `LAKEBASE_INSTANCE_NAME` → provisioned mode (`client.database` API)
- `LAKEBASE_PG_URL` → static URL mode (no OAuth token refresh)

See `.env.example` for the full list of available settings including LLM provider, skills configuration, and MLflow tracing. The app loads `.env.local` (not `.env`) at startup.

**Getting your Databricks token:**
1. Go to your Databricks workspace
2. Click your username → User Settings
3. Go to Developer → Access Tokens → Generate New Token
4. Copy the token value

#### 3. Start the Development Servers

```bash
./scripts/start_dev.sh
```

This starts both the backend and frontend in one terminal.

You can also start them separately if you prefer:

```bash
# Terminal 1 — Backend
uvicorn server.app:app --reload --port 8000 --reload-dir server

# Terminal 2 — Frontend
cd client && npm run dev
```

#### 4. Access the App

- **Frontend**: <http://localhost:3000>
- **Backend API**: <http://localhost:8000>
- **API Docs**: <http://localhost:8000/docs>

#### 5. (Optional) Configure Claude via Databricks Model Serving

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
│   └── start_dev.sh       # Development startup
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

This section covers deploying the Builder App to Databricks Apps platform for production use.

### Prerequisites

Before deploying, ensure you have:

1. **Databricks CLI** installed and authenticated
2. **Node.js 18+** for building the frontend
3. **A Lakebase instance** in your Databricks workspace (for database persistence)
4. Access to the **full repository** (not just this directory) since the app depends on sibling packages

### Quick Deploy

```bash
# 1. Authenticate with Databricks CLI
databricks auth login --host https://your-workspace.cloud.databricks.com

# 2. Create the app (first time only)
databricks apps create my-builder-app

# 3. Configure app.yaml (copy and edit the example)
cp app.yaml.example app.yaml
# Edit app.yaml — set LAKEBASE_ENDPOINT (autoscale) or LAKEBASE_INSTANCE_NAME (provisioned)

# 4. (Provisioned Lakebase only) Add Lakebase as an app resource
#    Skip this step if using autoscale — it connects via OAuth directly.
databricks apps add-resource my-builder-app \
  --resource-type database \
  --resource-name lakebase \
  --database-instance <your-lakebase-instance-name>

# 5. Deploy
./scripts/deploy.sh my-builder-app

# 6. Grant database permissions to the app's service principal (see Section 7)
```

### Step-by-Step Deployment Guide

#### 1. Install and Authenticate Databricks CLI

```bash
# Install Databricks CLI
pip install databricks-cli

# Authenticate (interactive browser login)
databricks auth login --host https://your-workspace.cloud.databricks.com

# Verify authentication
databricks auth describe
```

If you have multiple profiles, set the profile before deploying:
```bash
export DATABRICKS_CONFIG_PROFILE=your-profile-name
```

#### 2. Create the Databricks App

```bash
# Create a new app
databricks apps create my-builder-app

# Verify it was created
databricks apps get my-builder-app
```

#### 3. Create a Lakebase Instance

The app requires a PostgreSQL database (Lakebase) for storing projects, conversations, and messages.

**Autoscale Lakebase** (recommended — scales to zero when idle):
1. Go to your Databricks workspace → **Catalog** → **Lakebase**
2. Click **Create** → select **Autoscale**
3. Note the endpoint resource name (e.g., `projects/my-app/branches/production/endpoints/primary`)
4. Set in `app.yaml`: `LAKEBASE_ENDPOINT=projects/my-app/branches/production/endpoints/primary`

**Provisioned Lakebase** (fixed capacity):
1. Go to **Catalog** → **Lakebase** → **Create** → select **Provisioned**
2. Note the instance name (e.g., `my-lakebase-instance`)
3. Set in `app.yaml`: `LAKEBASE_INSTANCE_NAME=my-lakebase-instance`

#### 4. Add Lakebase as an App Resource

**Autoscale Lakebase**: Skip this step. Autoscale connects via OAuth using `LAKEBASE_ENDPOINT` — no app resource needed.

**Provisioned Lakebase**: Add the instance as an app resource:

```bash
databricks apps add-resource my-builder-app \
  --resource-type database \
  --resource-name lakebase \
  --database-instance <your-lakebase-instance-name>
```

This automatically configures the database connection environment variables (`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`).

#### 5. Configure app.yaml

Copy the example configuration and customize it:

```bash
cp app.yaml.example app.yaml
```

Edit `app.yaml` with your settings:

```yaml
command:
  - "uvicorn"
  - "server.app:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "$DATABRICKS_APP_PORT"

env:
  # Required: Lakebase database (pick ONE option)

  # Option A — Autoscale Lakebase (recommended):
  - name: LAKEBASE_ENDPOINT
    value: "projects/<project-name>/branches/production/endpoints/primary"
  - name: LAKEBASE_DATABASE_NAME
    value: "databricks_postgres"

  # Option B — Provisioned Lakebase:
  # - name: LAKEBASE_INSTANCE_NAME
  #   value: "<your-lakebase-instance-name>"
  # - name: LAKEBASE_DATABASE_NAME
  #   value: "databricks_postgres"

  # Skills to enable (comma-separated)
  - name: ENABLED_SKILLS
    value: "databricks-agent-bricks,databricks-python-sdk,databricks-spark-declarative-pipelines"

  # MLflow tracing (optional)
  - name: MLFLOW_TRACKING_URI
    value: "databricks"
  # - name: MLFLOW_EXPERIMENT_NAME
  #   value: "/Users/your-email@company.com/claude-code-traces"

  # Other settings
  - name: ENV
    value: "production"
  - name: PROJECTS_BASE_DIR
    value: "./projects"
```

#### 6. Deploy the App

Run the deploy script from the `databricks-builder-app` directory:

```bash
./scripts/deploy.sh my-builder-app
```

The deploy script will:
1. Build the React frontend
2. Package the server code
3. Bundle sibling packages (`databricks-tools-core`, `databricks-mcp-server`)
4. Copy skills from `databricks-skills/`
5. Upload everything to your Databricks workspace
6. Deploy the app

**Skip frontend build** (if already built):
```bash
./scripts/deploy.sh my-builder-app --skip-build
```

#### 7. Grant Database Permissions

After the first deployment, the app's service principal needs two things:
1. A **Lakebase OAuth role** (so it can authenticate via OAuth tokens)
2. **PostgreSQL grants** on the `builder_app` schema (so it can create/read/write tables)

##### Step 7a: Find the service principal's client ID

```bash
SP_CLIENT_ID=$(databricks apps get my-builder-app --output json | jq -r '.service_principal_client_id')
echo $SP_CLIENT_ID
```

##### Step 7b: Create a Lakebase OAuth role for the SP

> **Important**: Do NOT use PostgreSQL `CREATE ROLE` directly. Lakebase Autoscaling requires
> roles to be created through the Databricks API so the OAuth authentication layer recognizes them.

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.postgres import Role, RoleRoleSpec, RoleAuthMethod, RoleIdentityType

w = WorkspaceClient()

# Replace with your branch path and SP client ID
branch = "projects/<project-id>/branches/<branch-id>"
sp_client_id = "<sp-client-id>"

w.postgres.create_role(
    parent=branch,
    role=Role(
        spec=RoleRoleSpec(
            postgres_role=sp_client_id,
            auth_method=RoleAuthMethod.LAKEBASE_OAUTH_V1,
            identity_type=RoleIdentityType.SERVICE_PRINCIPAL,
        )
    ),
).wait()
```

Or via CLI:

```bash
databricks postgres create-role \
  "projects/<project-id>/branches/<branch-id>" \
  --json '{
    "spec": {
      "postgres_role": "<sp-client-id>",
      "auth_method": "LAKEBASE_OAUTH_V1",
      "identity_type": "SERVICE_PRINCIPAL"
    }
  }'
```

**Provisioned Lakebase**: This step is not needed — adding the instance as an app resource
(Step 4) automatically configures authentication.

##### Step 7c: Grant PostgreSQL permissions

Connect to your Lakebase database as your own user (via psql or a notebook) and run:

```sql
-- Replace <sp-client-id> with the service_principal_client_id

-- 1. Allow the SP to create the builder_app schema
GRANT CREATE ON DATABASE databricks_postgres TO "<sp-client-id>";

-- 2. Create the schema and grant full access
CREATE SCHEMA IF NOT EXISTS builder_app;
GRANT USAGE ON SCHEMA builder_app TO "<sp-client-id>";
GRANT ALL PRIVILEGES ON SCHEMA builder_app TO "<sp-client-id>";

-- 3. Grant access to any existing tables/sequences (needed if you ran migrations locally)
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA builder_app TO "<sp-client-id>";
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA builder_app TO "<sp-client-id>";

-- 4. Ensure the SP has access to future tables/sequences created by other users
ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app
  GRANT ALL ON TABLES TO "<sp-client-id>";
ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app
  GRANT ALL ON SEQUENCES TO "<sp-client-id>";
```

After granting permissions, redeploy the app so it can run migrations with the new role.

#### 8. Access Your App

After successful deployment, the script will display your app URL:
```
App URL: https://my-builder-app-1234567890.aws.databricksapps.com
```

### Deployment Troubleshooting

#### "Could not determine Databricks workspace"

Your Databricks CLI authentication may be invalid or using the wrong profile:
```bash
# Check available profiles
databricks auth profiles

# Use a specific profile
export DATABRICKS_CONFIG_PROFILE=your-valid-profile

# Re-authenticate if needed
databricks auth login --host https://your-workspace.cloud.databricks.com
```

#### "Build directory client/out not found"

The frontend build is missing. The deploy script should build it automatically, but you can build manually:
```bash
cd client
npm install
npm run build
cd ..
```

#### "Skill 'X' not found"

Skills are copied from the sibling `databricks-skills/` directory. Ensure:
1. You're running the deploy script from the full repository (not just this directory)
2. The skill name in `ENABLED_SKILLS` matches a directory in `databricks-skills/`
3. The skill directory contains a `SKILL.md` file

#### "password authentication failed" or "Permission denied for table projects"

See [Section 7: Grant Database Permissions](#7-grant-database-permissions) for the complete setup.

Common causes:

| Error | Cause | Fix |
|-------|-------|-----|
| `password authentication failed` | Lakebase OAuth role missing or created via SQL instead of API | Create the role via `w.postgres.create_role()` with `LAKEBASE_OAUTH_V1` auth (Step 7b) |
| `permission denied for table` | SP lacks PostgreSQL grants on schema/tables | Run the GRANT statements (Step 7c) |
| `schema "builder_app" does not exist` | SP lacks `CREATE` on the database | `GRANT CREATE ON DATABASE databricks_postgres TO "<sp-client-id>"` |
| `relation does not exist` | Migrations haven't run | Redeploy the app, or run `alembic upgrade head` locally |

> **Autoscale Lakebase pitfall**: Do NOT use `CREATE ROLE ... LOGIN` in PostgreSQL directly.
> Lakebase Autoscaling requires roles to be created through the Databricks API so that OAuth
> token authentication works. Manually created roles get `NO_LOGIN` auth and will fail with
> "password authentication failed".

#### App shows blank page or "Not Found"

Check the app logs in Databricks:
```bash
databricks apps logs my-builder-app
```

Common causes:
- Frontend files not properly deployed (check `client/out` exists in staging)
- Database connection issues (verify Lakebase resource is added)
- Python import errors (check logs for traceback)

#### Redeploying After Changes

```bash
# Full redeploy (rebuilds frontend)
./scripts/deploy.sh my-builder-app

# Quick redeploy (skip frontend build)
./scripts/deploy.sh my-builder-app --skip-build
```

### MLflow Tracing

The app supports MLflow tracing for Claude Code conversations. To enable:

1. Set `MLFLOW_TRACKING_URI=databricks` in `app.yaml`
2. Optionally set `MLFLOW_EXPERIMENT_NAME` to a specific experiment path

Traces will appear in your Databricks MLflow UI and include:
- User prompts and Claude responses
- Tool usage and results
- Session metadata

See the [Databricks MLflow Tracing documentation](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code) for more details.

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
