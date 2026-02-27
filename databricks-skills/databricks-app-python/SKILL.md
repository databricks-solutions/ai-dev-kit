---
name: databricks-app-python
description: "Builds Python-based Databricks applications using Dash, Streamlit, Gradio, Flask, FastAPI, or Reflex. Handles OAuth authorization (app and user auth), app resources, SQL warehouse and Lakebase connectivity, model serving integration, and deployment. Use when building Python web apps, dashboards, ML demos, or REST APIs for Databricks, or when the user mentions Streamlit, Dash, Gradio, Flask, FastAPI, Reflex, or Databricks app."
---

# Databricks Python Application

Build Python-based Databricks applications. For full examples and recipes, see the **[Databricks Apps Cookbook](https://apps-cookbook.dev/)**.

---

## Critical Rules (always follow)

- **MUST** confirm framework choice or use [Framework Selection](#framework-selection) below
- **MUST** use SDK `Config()` for authentication (never hardcode tokens)
- **MUST** use `app.yaml` `valueFrom` for resources (never hardcode resource IDs)
- **MUST** use `dash-bootstrap-components` for Dash app layout and styling
- **MUST** use `@st.cache_resource` for Streamlit database connections
- **MUST** deploy Flask with Gunicorn, FastAPI with uvicorn (not dev servers)

## Required Steps

Copy this checklist and verify each item:
```
- [ ] Framework selected
- [ ] Auth strategy decided: app auth, user auth, or both
- [ ] App resources identified (SQL warehouse, Lakebase, serving endpoint, etc.)
- [ ] Backend data strategy decided (SQL warehouse, Lakebase, or SDK)
- [ ] Deployment method: CLI or DABs
```

---

## Framework Selection

| Framework | Best For | app.yaml Command |
|-----------|----------|------------------|
| **Dash** | Production dashboards, BI tools, complex interactivity | `["python", "app.py"]` |
| **Streamlit** | Rapid prototyping, data science apps, internal tools | `["streamlit", "run", "app.py"]` |
| **Gradio** | ML demos, model interfaces, chat UIs | `["python", "app.py"]` |
| **Flask** | Custom REST APIs, lightweight apps, webhooks | `["gunicorn", "app:app", "-w", "4", "-b", "0.0.0.0:8080"]` |
| **FastAPI** | Async APIs, auto-generated OpenAPI docs | `["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]` |
| **Reflex** | Full-stack Python apps without JavaScript | `["reflex", "run", "--env", "prod"]` |

**Default**: Recommend **Streamlit** for prototypes, **Dash** for production dashboards, **FastAPI** for APIs, **Gradio** for ML demos.

---

## Quick Reference

| Concept | Details |
|---------|---------|
| **Runtime** | Python 3.11, Ubuntu 22.04, 2 vCPU, 6 GB RAM |
| **Pre-installed** | Dash 2.18.1, Streamlit 1.38.0, Gradio 4.44.0, Flask 3.0.3, FastAPI 0.115.0 |
| **Auth (app)** | Service principal via `Config()` — auto-injected `DATABRICKS_CLIENT_ID`/`DATABRICKS_CLIENT_SECRET` |
| **Auth (user)** | `x-forwarded-access-token` header — see [1-authorization.md](1-authorization.md) |
| **Resources** | `valueFrom` in app.yaml — see [2-app-resources.md](2-app-resources.md) |
| **Cookbook** | https://apps-cookbook.dev/ |
| **Docs** | https://docs.databricks.com/aws/en/dev-tools/databricks-apps/ |

---

## Detailed Guides

**Authorization**: Use [1-authorization.md](1-authorization.md) when configuring app or user authorization — covers service principal auth, on-behalf-of user tokens, OAuth scopes, and per-framework code examples. (Keywords: OAuth, service principal, user auth, on-behalf-of, access token, scopes)

**App resources**: Use [2-app-resources.md](2-app-resources.md) when connecting your app to Databricks resources — covers SQL warehouses, Lakebase, model serving, secrets, volumes, and the `valueFrom` pattern. (Keywords: resources, valueFrom, SQL warehouse, model serving, secrets, volumes, connections)

**Frameworks**: See [3-frameworks.md](3-frameworks.md) for Databricks-specific patterns per framework — covers Dash, Streamlit, Gradio, Flask, FastAPI, and Reflex with auth integration, deployment commands, and Cookbook links. (Keywords: Dash, Streamlit, Gradio, Flask, FastAPI, Reflex, framework selection)

**Deployment**: Use [4-deployment.md](4-deployment.md) when deploying your app — covers Databricks CLI, Asset Bundles (DABs), app.yaml configuration, and post-deployment verification. (Keywords: deploy, CLI, DABs, asset bundles, app.yaml, logs)

**Lakebase**: Use [5-lakebase.md](5-lakebase.md) when using Lakebase (PostgreSQL) as your app's data layer — covers auto-injected env vars, psycopg2/asyncpg patterns, and when to choose Lakebase vs SQL warehouse. (Keywords: Lakebase, PostgreSQL, psycopg2, asyncpg, transactional, PGHOST)

**MCP tools**: Use [6-mcp-approach.md](6-mcp-approach.md) for managing app lifecycle via MCP tools — covers creating, deploying, monitoring, and deleting apps programmatically. (Keywords: MCP, create app, deploy app, app logs)

---

## Workflow

1. Determine the task type:

   **New app from scratch?** → Use [Framework Selection](#framework-selection), then read [3-frameworks.md](3-frameworks.md)
   **Setting up authorization?** → Read [1-authorization.md](1-authorization.md)
   **Connecting to data/resources?** → Read [2-app-resources.md](2-app-resources.md)
   **Using Lakebase (PostgreSQL)?** → Read [5-lakebase.md](5-lakebase.md)
   **Deploying to Databricks?** → Read [4-deployment.md](4-deployment.md)
   **Using MCP tools?** → Read [6-mcp-approach.md](6-mcp-approach.md)

2. Follow the instructions in the relevant guide
3. For full code examples, browse https://apps-cookbook.dev/

---

## Core Architecture

All Python Databricks apps follow this pattern:

```
app-directory/
├── app.py                 # Main application (or framework-specific name)
├── models.py              # Pydantic data models
├── backend.py             # Data access layer
├── requirements.txt       # Additional Python dependencies
├── app.yaml               # Databricks Apps configuration
└── README.md
```

### Backend Toggle Pattern

```python
import os
from databricks.sdk.core import Config

USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"

if USE_MOCK:
    from backend_mock import MockBackend as Backend
else:
    from backend_real import RealBackend as Backend

backend = Backend()
```

### SQL Warehouse Connection (shared across all frameworks)

```python
from databricks.sdk.core import Config
from databricks import sql

cfg = Config()  # Auto-detects credentials from environment
conn = sql.connect(
    server_hostname=cfg.host,
    http_path=f"/sql/1.0/warehouses/{os.getenv('DATABRICKS_WAREHOUSE_ID')}",
    credentials_provider=lambda: cfg.authenticate,
)
```

### Pydantic Models

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class Status(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"

class EntityOut(BaseModel):
    id: str
    name: str
    status: Status
    created_at: datetime

class EntityIn(BaseModel):
    name: str = Field(..., min_length=1)
    status: Status = Status.PENDING
```

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Connection exhausted** | Use `@st.cache_resource` (Streamlit) or connection pooling |
| **Auth token not found** | Check `x-forwarded-access-token` header — only available when deployed, not locally |
| **App won't start** | Check `app.yaml` command matches framework; check `databricks apps logs <name>` |
| **Resource not accessible** | Add resource via UI, verify SP has permissions, use `valueFrom` in app.yaml |
| **Import error on deploy** | Add missing packages to `requirements.txt` (pre-installed packages don't need listing) |
| **Lakebase app crashes on start** | `psycopg2`/`asyncpg` are NOT pre-installed — MUST add to `requirements.txt` |
| **Port conflict** | Databricks Apps expects port 8080; configure your framework accordingly |
| **Streamlit: set_page_config error** | `st.set_page_config()` must be the first Streamlit command |
| **Dash: unstyled layout** | Add `dash-bootstrap-components`; use `dbc.themes.BOOTSTRAP` |
| **Slow queries** | Use Lakebase for transactional/low-latency; SQL warehouse for analytical queries |

---

## Platform Constraints

| Constraint | Details |
|------------|---------|
| **Runtime** | Python 3.11, Ubuntu 22.04 LTS |
| **Compute** | 2 vCPUs, 6 GB memory (default) |
| **Pre-installed frameworks** | Dash, Streamlit, Gradio, Flask, FastAPI, Shiny |
| **Custom packages** | Add to `requirements.txt` in app root |
| **Network** | Apps can reach Databricks APIs; external access depends on workspace config |
| **User auth** | Public Preview — workspace admin must enable before adding scopes |

---

## Official Documentation

- **[Databricks Apps Overview](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/)** — main docs hub
- **[Apps Cookbook](https://apps-cookbook.dev/)** — ready-to-use code snippets (Streamlit, Dash, Reflex, FastAPI)
- **[Authorization](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/auth)** — app auth and user auth
- **[Resources](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)** — SQL warehouse, Lakebase, serving, secrets
- **[app.yaml Reference](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime)** — command and env config
- **[System Environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env)** — pre-installed packages, runtime details

## Related Skills

- **[databricks-app-apx](../databricks-app-apx/SKILL.md)** - full-stack apps with FastAPI + React
- **[databricks-asset-bundles](../databricks-asset-bundles/SKILL.md)** - deploying apps via DABs
- **[databricks-python-sdk](../databricks-python-sdk/SKILL.md)** - backend SDK integration
- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** - adding persistent PostgreSQL state
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - serving ML models for app integration
