# Databricks Builder App

A web application that provides a Claude Code agent interface with integrated Databricks tools. Users interact with Claude through a chat interface, and the agent can execute SQL queries, manage pipelines, upload files, and more on their Databricks workspace.

## Choose Your Path

- **[Local Development](#local-development)** - Run on your machine for development and testing
- **[Deploy to Databricks Apps](#deploy-to-databricks-apps)** - Production deployment with multi-user auth

---

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Python | 3.11+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |
| uv (or pip) | any | `uv --version` |

You also need:

- **Databricks workspace** with a personal access token (PAT)
  - Go to your workspace > User Settings > Access Tokens > Generate New Token
- **Claude API access** via one of these providers:

| Provider | How It Works | What You Need |
|----------|-------------|---------------|
| **Databricks FMAPI** (default) | Routes Claude API calls through your workspace at `{DATABRICKS_HOST}/serving-endpoints/anthropic` | A workspace with Claude models enabled. No extra keys needed — uses your PAT automatically |
| **Direct Anthropic** | Calls Anthropic API directly | `ANTHROPIC_API_KEY` in `.env.local` |
| **Azure OpenAI** | Uses Azure-hosted models | `AZURE_OPENAI_*` vars in `.env.local` |

> **Note**: If your workspace has Claude models available via Foundation Model APIs, the app uses them automatically with zero extra configuration. This is the default.

---

## Local Development

### 1. Install Dependencies

```bash
# Navigate to the app directory
cd databricks-builder-app

# Install backend dependencies
uv sync
# OR: pip install -e .

# Install sibling packages (required — these provide the Databricks tools)
cd ..
uv pip install -e databricks-tools-core -e databricks-mcp-server
# OR: pip install -e databricks-tools-core -e databricks-mcp-server
cd databricks-builder-app

# Install frontend dependencies
cd client && npm install && cd ..
```

### 2. Configure Environment

```bash
cp .env.example .env.local
```

Edit `.env.local`. **Minimum required for local dev:**

```bash
DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=dapi...
ENV=development
PROJECTS_BASE_DIR=./projects
```

**Optional — Database for persistence:**

```bash
# Static PostgreSQL URL (e.g., Lakebase)
LAKEBASE_PG_URL=postgresql://user:password@host:5432/database?sslmode=require
```

> The app runs fine **without** a database. Conversations won't persist across restarts, but all agent functionality works. The app logs a warning and continues.

**Optional — Direct Anthropic API (if not using Databricks FMAPI):**

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

**Optional — Skills filter:**

```bash
# Comma-separated list. Empty or omitted = ALL skills loaded.
ENABLED_SKILLS=spark-declarative-pipelines,databricks-python-sdk
```

See [`.env.example`](.env.example) for the complete list of configuration options including LLM provider settings, MLflow tracing, and advanced tuning.

### 3. Start Development Servers

**Recommended — use the start script:**

```bash
./scripts/start_dev.sh
```

This kills stale processes on ports 8000/3000, installs sibling packages, and starts both servers.

**Alternative — start separately:**

Terminal 1 (Backend):
```bash
uvicorn server.app:app --reload --port 8000 --reload-dir server
```

Terminal 2 (Frontend):
```bash
cd client && npm run dev
```

### 4. Access the App

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

---

## Architecture Overview

```
+-----------------------------------------------------------------------------+
|                              Web Application                                |
+-----------------------------------------------------------------------------+
|  React Frontend (client/)           FastAPI Backend (server/)               |
|  +---------------------+            +-------------------------------+      |
|  | Chat UI             |<---------->| /api/agent/invoke             |      |
|  | Project Selector    |   SSE      | /api/projects                 |      |
|  | Conversation List   |            | /api/conversations            |      |
|  +---------------------+            +-------------------------------+      |
+-----------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------+
|                           Claude Code Session                               |
+-----------------------------------------------------------------------------+
|  Each user message spawns a Claude Code agent session via claude-agent-sdk  |
|                                                                             |
|  Built-in Tools:              MCP Tools (Databricks):         Skills:      |
|  +------------------+         +-----------------------+    +-----------+   |
|  | Read, Write, Edit|         | execute_sql           |    | sdp       |   |
|  | Glob, Grep       |         | create_or_update_pipe |    | dabs      |   |
|  | Skill            |         | upload_folder         |    | sdk       |   |
|  +------------------+         | run_python_file       |    | ...       |   |
|                               | ...                   |    +-----------+   |
|                               +-----------------------+                    |
|                                          |                                 |
|                                          v                                 |
|                               +-----------------------+                    |
|                               | databricks-mcp-server |                    |
|                               | (in-process)          |                    |
|                               +-----------------------+                    |
+-----------------------------------------------------------------------------+
                                             |
                                             v
+-----------------------------------------------------------------------------+
|                            Databricks Workspace                             |
+-----------------------------------------------------------------------------+
|  SQL Warehouses    |    Clusters    |    Unity Catalog    |    Workspace    |
+-----------------------------------------------------------------------------+
```

### Key Concepts

- **Session resumption**: Each conversation stores a `claude_session_id` so context carries across messages.
- **Streaming**: All agent events (text, thinking, tool_use, tool_result) stream to the frontend via SSE.
- **Project isolation**: Each project gets its own working directory with sandboxed file access.
- **Multi-user auth**: In production, per-request credentials are injected via `contextvars`. In development, all requests use the env var credentials.
- **Async handoff**: Operations exceeding 10 seconds return an `operation_id` immediately. Claude can poll for results using `check_operation_status`.
- **In-process MCP**: Databricks tools are loaded in-process (no subprocess), which avoids the event loop issues that affect stdio-based MCP servers.

### Authentication Flow

| Mode | User Identity | Databricks Token | Claude API |
|------|--------------|-------------------|------------|
| **Production** (Databricks Apps) | `X-Forwarded-User` header | `X-Forwarded-Access-Token` header | Routed through Databricks FMAPI using user's token |
| **Development** (local) | Fetched via `WorkspaceClient.current_user.me()` | `DATABRICKS_TOKEN` env var | Databricks FMAPI (default) or `ANTHROPIC_API_KEY` |

### Skills System

Skills are markdown files with instructions and examples that Claude loads on demand via the `Skill` tool.

1. On startup, skills are copied from `../databricks-skills/` to `./skills/`
2. When a project is created, skills are copied to `project/.claude/skills/`
3. The agent invokes skills with: `skill: "sdp"`, `skill: "databricks-python-sdk"`, etc.

---

## Configuration Reference

### Environment Variables

See [`.env.example`](.env.example) for the full list with descriptions. Key variables:

| Variable | Required | Mode | Purpose |
|----------|----------|------|---------|
| `DATABRICKS_HOST` | Yes | Both | Workspace URL (no trailing slash) |
| `DATABRICKS_TOKEN` | Dev only | Dev | Personal access token |
| `ENV` | Yes | Both | `development` or `production` |
| `PROJECTS_BASE_DIR` | No | Both | Project directory (default: `./projects`) |
| `LAKEBASE_PG_URL` | No | Dev | Static PostgreSQL URL for persistence |
| `LAKEBASE_INSTANCE_NAME` | No | Prod | Lakebase instance (dynamic OAuth mode) |
| `LAKEBASE_DATABASE_NAME` | No | Prod | Database name (default: `databricks_postgres`) |
| `ENABLED_SKILLS` | No | Both | Comma-separated skill names. Empty = all |
| `SKILLS_ONLY_MODE` | No | Both | `true` to only enable the Skill tool (debugging) |
| `LLM_PROVIDER` | No | Both | `DATABRICKS` (default) or `AZURE` |
| `DATABRICKS_MODEL` | No | Both | Model for title generation etc. (default: `databricks-meta-llama-3-3-70b-instruct`) |
| `ANTHROPIC_API_KEY` | No | Both | Direct Anthropic API key (bypasses FMAPI) |
| `MLFLOW_TRACKING_URI` | No | Both | Set to `databricks` to enable tracing |
| `MLFLOW_EXPERIMENT_NAME` | No | Both | Custom experiment path for traces |
| `CLAUDE_CODE_STREAM_CLOSE_TIMEOUT` | No | Both | Stream timeout in ms (default: `3600000` = 1 hour) |

### Claude API / LLM Provider

The agent (Claude Code) needs access to the Claude API. The app resolves credentials in this order:

1. **Databricks FMAPI (default)** - No extra config needed if your workspace has Claude models:
   - Constructs: `https://{DATABRICKS_HOST}/serving-endpoints/anthropic`
   - Uses the user's Databricks token as the API key
   - Models: `databricks-claude-opus-4-5`, `databricks-claude-sonnet-4-5`

2. **Direct Anthropic API** - Set `ANTHROPIC_API_KEY` in `.env.local`:
   - Calls `api.anthropic.com` directly
   - Models: `claude-opus-4-6`, `claude-sonnet-4-5`

3. **Custom routing via `.claude/settings.json`** - Create this file in the **repo root** (not in the app directory) to override model names and base URL:
   ```json
   {
     "env": {
       "ANTHROPIC_MODEL": "databricks-claude-sonnet-4-5",
       "ANTHROPIC_BASE_URL": "https://your-workspace.cloud.databricks.com/serving-endpoints/anthropic",
       "ANTHROPIC_AUTH_TOKEN": "dapi..."
     }
   }
   ```
   > Add `.claude/settings.json` to `.gitignore` — it contains credentials.

### Skills

17 skills are available in `../databricks-skills/`:

| Skill | Description |
|-------|-------------|
| `agent-bricks` | Building AI agents on Databricks |
| `aibi-dashboards` | AI/BI Lakeview dashboards |
| `asset-bundles` | Databricks Asset Bundles config |
| `databricks-app-apx` | Full-stack apps (FastAPI + React) |
| `databricks-app-python` | Python apps (Dash, Streamlit, Flask) |
| `databricks-config` | Workspace configuration |
| `databricks-docs` | Documentation patterns |
| `databricks-genie` | Genie Spaces |
| `databricks-jobs` | Scheduled workflows |
| `databricks-python-sdk` | Python SDK patterns |
| `databricks-unity-catalog` | Unity Catalog management |
| `lakebase-provisioned` | Lakebase database setup |
| `mlflow-evaluation` | MLflow evaluation and traces |
| `model-serving` | Model serving endpoints |
| `spark-declarative-pipelines` | SDP/DLT development |
| `synthetic-data-generation` | Test dataset creation |
| `unstructured-pdf-generation` | PDF document processing |

**Filtering:**
```bash
# Enable specific skills only
ENABLED_SKILLS=spark-declarative-pipelines,databricks-python-sdk

# Enable all skills (default when empty or omitted)
ENABLED_SKILLS=
```

**Adding custom skills:**
1. Create `../databricks-skills/my-skill/SKILL.md` with YAML frontmatter:
   ```markdown
   ---
   name: my-skill
   description: "What this skill does"
   ---

   # Skill content here
   ```
2. Add `my-skill` to `ENABLED_SKILLS`

### Database (Optional)

The app uses PostgreSQL (Lakebase) for persisting projects, conversations, messages, and backups. **The database is optional** — if not configured, the app starts normally and logs a warning.

**Two connection modes:**

| Mode | When to Use | Config |
|------|------------|--------|
| **Static URL** | Local development | `LAKEBASE_PG_URL=postgresql://user:pass@host:5432/db?sslmode=require` |
| **Dynamic OAuth** | Databricks Apps | `LAKEBASE_INSTANCE_NAME` + `LAKEBASE_DATABASE_NAME` (tokens refresh automatically every 50 min) |

**Migrations** run automatically on startup. To run manually:
```bash
alembic upgrade head
```

### MLflow Tracing

Enable tracing to capture Claude Code conversations in your Databricks MLflow UI:

```bash
MLFLOW_TRACKING_URI=databricks
# Optional: custom experiment
MLFLOW_EXPERIMENT_NAME=/Users/your-email@company.com/claude-code-traces
```

Traces include user prompts, Claude responses, tool usage, and session metadata. See the [Databricks MLflow Tracing docs](https://docs.databricks.com/aws/en/mlflow3/genai/tracing/integrations/claude-code).

---

## Deploy to Databricks Apps

### Prerequisites

1. **[Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html)** installed and authenticated
2. **Node.js 18+** for building the frontend
3. **Full repository clone** (the app depends on sibling packages `databricks-tools-core` and `databricks-mcp-server`)
4. **(Optional) Lakebase instance** in your workspace for database persistence

### Quick Deploy

```bash
# 1. Authenticate with Databricks CLI
databricks auth login --host https://your-workspace.cloud.databricks.com

# 2. Create the app (first time only)
databricks apps create my-builder-app

# 3. (Optional) Add Lakebase as a resource
databricks apps add-resource my-builder-app \
  --resource-type database \
  --resource-name lakebase \
  --database-instance <your-lakebase-instance-name>

# 4. Configure app.yaml
cp app.yaml.example app.yaml
# Edit app.yaml with your settings

# 5. Deploy
./scripts/deploy.sh my-builder-app
```

### Step-by-Step Guide

#### 1. Install and Authenticate Databricks CLI

```bash
# Install (see https://docs.databricks.com/dev-tools/cli/install.html)
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh

# Authenticate
databricks auth login --host https://your-workspace.cloud.databricks.com

# Verify
databricks auth describe
```

If you have multiple profiles:
```bash
export DATABRICKS_CONFIG_PROFILE=your-profile-name
```

#### 2. Create the Databricks App

```bash
databricks apps create my-builder-app
databricks apps get my-builder-app  # verify
```

#### 3. (Optional) Create a Lakebase Instance

1. Go to your Databricks workspace
2. Navigate to **Catalog** > **Lakebase**
3. Click **Create Instance**
4. Note the instance name

#### 4. (Optional) Add Lakebase as an App Resource

```bash
databricks apps add-resource my-builder-app \
  --resource-type database \
  --resource-name lakebase \
  --database-instance <your-lakebase-instance-name>
```

This configures the database connection environment variables automatically (`PGHOST`, `PGPORT`, etc.).

#### 5. Configure app.yaml

```bash
cp app.yaml.example app.yaml
```

Edit `app.yaml` with your settings. Key values to configure:
- `LAKEBASE_INSTANCE_NAME` — your Lakebase instance name
- `ENABLED_SKILLS` — which skills to include
- Claude SDK model names (e.g., `databricks-claude-opus-4-5`)

See [`app.yaml.example`](app.yaml.example) for the full template with comments.

#### 6. Deploy

```bash
# Full deploy (builds frontend + uploads + deploys)
./scripts/deploy.sh my-builder-app

# Skip frontend rebuild if already built
./scripts/deploy.sh my-builder-app --skip-build
```

The deploy script will:
1. Build the React frontend (`client/out/`)
2. Stage server code, frontend build, sibling packages, and skills
3. Upload to your Databricks workspace
4. Deploy the app

#### 7. (If using Lakebase) Grant Database Permissions

After the first deployment, grant the app's service principal access to the database:

```bash
# Get the service principal ID
databricks apps get my-builder-app --output json | jq '.service_principal_id'
```

Run this SQL in a Databricks notebook or SQL editor (replace `<service-principal-id>`):

```sql
GRANT USAGE ON SCHEMA public TO `<service-principal-id>`;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO `<service-principal-id>`;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO `<service-principal-id>`;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO `<service-principal-id>`;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO `<service-principal-id>`;
```

> If you're using a fresh/private Lakebase instance, migrations create tables with proper ownership automatically.

#### 8. Access Your App

After deployment, the script displays your app URL:
```
App URL: https://my-builder-app-1234567890.aws.databricksapps.com
```

---

## Troubleshooting

### Agent not executing tools / "MCP connection unstable"

This was a known issue with `claude-agent-sdk` in FastAPI contexts ([issue #462](https://github.com/anthropics/claude-agent-sdk-python/issues/462)). The app includes a workaround: the agent runs in a fresh event loop in a separate thread with `contextvars` properly propagated. See [EVENT_LOOP_FIX.md](./EVENT_LOOP_FIX.md) for details.

### Claude API errors / "Authentication failed"

- **Using Databricks FMAPI (default)**: Verify your workspace has Claude models enabled at `{DATABRICKS_HOST}/serving-endpoints/anthropic`. Check that `DATABRICKS_TOKEN` is valid.
- **Using direct Anthropic**: Verify `ANTHROPIC_API_KEY` is set and valid.
- **Using `.claude/settings.json`**: Verify the file is in the repo root (not in the app directory) and contains valid credentials.

### Skills not loading

1. Check `ENABLED_SKILLS` in `.env.local` — names must match directory names in `../databricks-skills/`
2. Each skill directory must contain a `SKILL.md` file with YAML frontmatter
3. Check startup logs for: `Copied X skills to ./skills`

### Database connection failing

- **Local dev**: Verify `LAKEBASE_PG_URL` is a valid PostgreSQL connection string (not the placeholder from `.env.example`)
- **Databricks Apps**: Verify the Lakebase resource is added and the service principal has permissions
- **No database needed?** Remove `LAKEBASE_PG_URL` from `.env.local` entirely — the app will run without persistence

### Stream timeout during long operations

Increase the timeout in `.env.local`:
```bash
CLAUDE_CODE_STREAM_CLOSE_TIMEOUT=7200000  # 2 hours
```

### Port already in use

```bash
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9
```

Or use `./scripts/start_dev.sh` which handles this automatically.

### Databricks token expired

Regenerate: Workspace > User Settings > Access Tokens > Generate New Token. Update `DATABRICKS_TOKEN` in `.env.local`.

### App shows blank page after deployment

Check app logs:
```bash
databricks apps get-logs my-builder-app
```

Common causes:
- Frontend build not included (check `client/out/` exists in staging)
- Database connection issues (verify Lakebase resource is added)
- Python import errors (check logs for traceback)

### Redeploying after changes

```bash
# Full redeploy (rebuilds frontend)
./scripts/deploy.sh my-builder-app

# Quick redeploy (skip frontend build)
./scripts/deploy.sh my-builder-app --skip-build
```

---

## Project Structure

```
databricks-builder-app/
├── server/                 # FastAPI backend
│   ├── app.py             # Main FastAPI app with lifespan events
│   ├── db/                # Database models and session management
│   │   ├── models.py      # SQLAlchemy models (Project, Conversation, Message, etc.)
│   │   └── database.py    # Async engine, OAuth token refresh, migrations
│   ├── routers/           # API endpoints
│   │   ├── agent.py       # /api/agent/* (invoke, stream)
│   │   ├── projects.py    # /api/projects/*
│   │   ├── conversations.py
│   │   ├── config.py      # /api/config/user
│   │   ├── skills.py      # /api/skills/*
│   │   ├── clusters.py    # /api/clusters/*
│   │   └── warehouses.py  # /api/warehouses/*
│   └── services/          # Business logic
│       ├── agent.py       # Claude Code session management + event loop fix
│       ├── databricks_tools.py  # MCP tool loading from SDK
│       ├── user.py        # User auth (headers/env vars)
│       ├── skills_manager.py
│       ├── backup_manager.py
│       ├── system_prompt.py
│       └── operation_tracker.py  # Async handoff for long-running ops
├── client/                # React frontend
│   ├── src/
│   │   ├── pages/         # Main pages (ProjectPage, etc.)
│   │   └── components/    # UI components
│   ├── out/               # Production build output (gitignored)
│   └── package.json
├── alembic/               # Database migrations
├── scripts/
│   ├── start_dev.sh       # Development startup (both servers)
│   └── deploy.sh          # Databricks Apps deployment
├── skills/                # Cached skills (gitignored, populated on startup)
├── projects/              # Project working directories (gitignored)
├── pyproject.toml         # Python dependencies
├── .env.example           # Environment template (all options documented)
├── app.yaml.example       # Databricks Apps deployment template
└── EVENT_LOOP_FIX.md      # Event loop workaround documentation
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/projects` | GET | List all projects |
| `/api/projects` | POST | Create new project |
| `/api/projects/{project_id}` | GET, PATCH, DELETE | Get, update, or delete a project |
| `/api/projects/{project_id}/conversations` | GET, POST | List or create conversations |
| `/api/projects/{project_id}/conversations/{conversation_id}` | GET, PATCH, DELETE | Get, update, or delete a conversation |
| `/api/invoke_agent` | POST | Send message to agent (SSE stream) |
| `/api/stream_progress/{execution_id}` | POST | Reconnect to an in-progress agent stream |
| `/api/stop_stream/{execution_id}` | POST | Stop an active agent stream |
| `/api/me` | GET | Get current user info |
| `/api/health` | GET | Health check |
| `/api/clusters` | GET | List available clusters |
| `/api/warehouses` | GET | List available SQL warehouses |
| `/api/projects/{project_id}/skills/tree` | GET | Get skills file tree |
| `/api/projects/{project_id}/skills/reload` | POST | Reload skills for a project |

## Embedding in Other Apps

For integrating the agent into your own application, see the example at:

```
scripts/_integration-example/
```

## Related Packages

- **[databricks-tools-core](../databricks-tools-core/)**: Core library with high-level Databricks functions
- **[databricks-mcp-server](../databricks-mcp-server/)**: MCP server exposing Databricks tools
- **[databricks-skills](../databricks-skills/)**: Skill definitions for Databricks development patterns
