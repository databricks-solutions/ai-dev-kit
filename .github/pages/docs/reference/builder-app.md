# Visual Builder App

A web-based chat UI for building on Databricks — powered by Claude Code under the hood. Same skills and tools as the CLI experience, but through a browser.

---

## What it does

- Chat with an AI assistant to build Databricks resources
- Manage projects with file editing and preview
- Back up and restore project state to PostgreSQL

## Architecture

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite |
| Backend | FastAPI + Uvicorn |
| Database | PostgreSQL (Lakebase) |
| AI Agent | Claude Code via claude-agent-sdk |

## Setup

```bash
cd ai-dev-kit/databricks-builder-app
./scripts/setup.sh
```

## Deploy to Databricks Apps

```bash
databricks apps create my-builder --from app.yaml
databricks apps deploy my-builder
```

See the full [Builder App README](https://github.com/databricks-solutions/ai-dev-kit/tree/main/databricks-builder-app) for detailed setup, configuration, and troubleshooting.
