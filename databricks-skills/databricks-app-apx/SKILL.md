---
name: databricks-app-apx
description: "Build full-stack Databricks applications using APX framework (FastAPI + React). Handles project scaffolding, Pydantic 3-model pattern, FastAPI routing, React + shadcn/ui frontend, Lakebase persistence, and deployment. Use when building full-stack apps, custom UIs beyond dashboards, API-first architectures, or when the user mentions APX, FastAPI + React, or full-stack Databricks app."
---

# Databricks APX Application (FastAPI + React)

Build full-stack Databricks applications with a FastAPI backend and React + TypeScript frontend. APX is the recommended framework when you need custom UI beyond dashboards, complex frontend interactions, or API-first architecture. For additional recipes and patterns, see the [Databricks Apps Cookbook](https://apps-cookbook.dev/).

---

## Critical Rules (always follow)

- **MUST** use the Pydantic 3-model pattern (`EntityIn`, `EntityRecord`, `EntityOut`) for all data models
- **MUST** include `response_model` on every FastAPI route (enables OpenAPI spec generation for the frontend)
- **MUST** use shadcn/ui as the component library for the React frontend
- **MUST** build the frontend (`npm run build`) before deploying
- **MUST** deploy with `create_or_update_app` (pass `source_code_path` to deploy source code) — no APX-specific deploy tools exist
- **MUST** add `psycopg2-binary` to `requirements.txt` when using Lakebase (not pre-installed)

## Required Steps

Copy this checklist and verify each item:
```
- [ ] Project structure scaffolded (backend + frontend)
- [ ] Pydantic models defined (EntityIn, EntityRecord, EntityOut)
- [ ] FastAPI routes built with response_model on every endpoint
- [ ] React frontend built with shadcn/ui components
- [ ] Lakebase connection configured (if using persistence)
- [ ] Frontend built (npm run build)
- [ ] app.yaml configured with resources and command
- [ ] Deployed with create_or_update_app
```

---

## When to Use APX vs Other Frameworks

| Need | Recommended |
|------|-------------|
| Custom UI with complex interactivity | **APX** |
| API-first architecture with typed contracts | **APX** |
| Multi-page app with client-side routing | **APX** |
| Rapid prototype / data exploration | Streamlit |
| Production BI dashboard | Dash |
| ML demo / model interface | Gradio |
| Simple REST API (no frontend) | FastAPI (see databricks-app-python) |

---

## Project Structure

```
src/{app_name}/
  backend/
    __init__.py
    main.py              # FastAPI app entry point
    models.py            # Pydantic models (3-model pattern)
    config.py            # App configuration
    routes/
      __init__.py
      entities.py        # API route modules
  frontend/
    src/
      components/        # Reusable React components
      pages/             # Page components
      lib/               # Utilities and API client
      App.tsx            # Root component
      main.tsx           # Entry point
    package.json
    vite.config.ts
    tsconfig.json
  app.yaml               # Databricks Apps configuration
  requirements.txt       # Python dependencies
```

---

## Quick Start Workflow

### Step 1: Scaffold project structure

Create the directory layout shown above. Start with the backend.

### Step 2: Define Pydantic models

```python
# src/{app_name}/backend/models.py
from pydantic import BaseModel, Field
from datetime import datetime

# Input validation - what the client sends
class ProjectIn(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""

# Database record - stored internally
class ProjectRecord(ProjectIn):
    id: str
    created_at: datetime
    updated_at: datetime

# API response - what the client receives
class ProjectOut(ProjectRecord):
    pass
```

### Step 3: Build FastAPI routes

```python
# src/{app_name}/backend/routes/projects.py
from fastapi import APIRouter, HTTPException
from ..models import ProjectIn, ProjectOut

router = APIRouter(prefix="/api/projects", tags=["projects"])

@router.get("/", response_model=list[ProjectOut])
async def list_projects():
    return await db.get_all_projects()

@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str):
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.post("/", response_model=ProjectOut, status_code=201)
async def create_project(project: ProjectIn):
    return await db.create_project(project)

@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, project: ProjectIn):
    return await db.update_project(project_id, project)

@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str):
    await db.delete_project(project_id)
```

### Step 4: Build React frontend

```tsx
// src/{app_name}/frontend/src/pages/ProjectsPage.tsx
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface Project {
  id: string;
  name: string;
  description: string;
  created_at: string;
}

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    fetch("/api/projects")
      .then((res) => res.json())
      .then(setProjects);
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Projects</h1>
      {projects.map((p) => (
        <Card key={p.id}>
          <CardHeader>
            <CardTitle>{p.name}</CardTitle>
          </CardHeader>
          <CardContent>{p.description}</CardContent>
        </Card>
      ))}
    </div>
  );
}
```

### Step 5: Connect to Lakebase

See [Lakebase persistence](#lakebase-persistence) below.

### Step 6: Test locally

```bash
# Backend
cd src/{app_name}/backend
uvicorn main:app --reload --port 8000

# Frontend (separate terminal)
cd src/{app_name}/frontend
npm run dev
```

### Step 7: Deploy

```python
# Build frontend first
# npm run build (in frontend directory)

# Upload to workspace
upload_to_workspace(
    local_path="src/{app_name}",
    workspace_path="/Workspace/Users/user@example.com/{app_name}"
)

# Create and deploy
create_or_update_app(
    name="my-apx-app",
    description="Full-stack APX application",
    source_code_path="/Workspace/Users/user@example.com/{app_name}"
)
```

---

## Detailed Guides

**Backend patterns**: Use [backend-patterns.md](backend-patterns.md) for FastAPI application setup, Pydantic 3-model pattern details, dependency injection, error handling, CORS configuration, and health checks. (Keywords: FastAPI, Pydantic, routes, models, CORS, middleware)

**Frontend patterns**: Use [frontend-patterns.md](frontend-patterns.md) for React setup, shadcn/ui integration, TypeScript configuration, API client patterns, routing, and form handling. (Keywords: React, shadcn, TypeScript, Vite, components, forms)

**Best practices**: Use [best-practices.md](best-practices.md) for production guidelines covering API design, project organization, Lakebase integration, local development workflow, and testing. (Keywords: guidelines, production, testing, mock backend, migrations)

---

## Lakebase Persistence

APX backends connect to Lakebase (managed PostgreSQL) for transactional data storage.

### Connection setup

```python
# src/{app_name}/backend/config.py
import os

DATABASE_URL = (
    f"postgresql://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
    f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT', '5432')}"
    f"/{os.getenv('PGDATABASE')}"
)
```

### psycopg with FastAPI

```python
# src/{app_name}/backend/main.py
import os
import psycopg2
from contextlib import contextmanager

@contextmanager
def get_db():
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        port=os.getenv("PGPORT", "5432"),
    )
    try:
        yield conn
    finally:
        conn.close()
```

### SQLAlchemy ORM (optional)

```python
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import DATABASE_URL

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class ProjectTable(Base):
    __tablename__ = "projects"
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
```

### app.yaml with Lakebase resource

```yaml
command:
  - "uvicorn"
  - "backend.main:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"

env:
  - name: DB_CONNECTION_STRING
    valueFrom:
      resource: database
```

Add the Lakebase database resource via the Databricks Apps UI after creating the app. Databricks auto-injects `PGHOST`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, and `PGPORT` environment variables.

---

## Deployment

### MCP Tools

| Tool | Description |
|------|-------------|
| **`create_or_update_app`** | Create app if it doesn't exist, optionally deploy (pass `source_code_path`) |
| **`get_app`** | Get app details by name (with `include_logs=True` for logs) |
| **`delete_app`** | Delete an app |
| **`upload_to_workspace`** | Upload files/folders to workspace |

### Build before deploy

The frontend must be built before deployment. The build output is served as static files by the FastAPI backend.

```bash
cd src/{app_name}/frontend
npm run build
```

### Deploy via MCP

```python
# Upload source (including built frontend)
upload_to_workspace(
    local_path="src/{app_name}",
    workspace_path="/Workspace/Users/user@example.com/{app_name}"
)

# Create and deploy
create_or_update_app(
    name="my-apx-app",
    description="Full-stack APX application",
    source_code_path="/Workspace/Users/user@example.com/{app_name}"
)

# Verify deployment
get_app(name="my-apx-app", include_logs=True)
```

### Deploy via CLI

```bash
databricks apps create my-apx-app
databricks workspace import-dir ./src/{app_name} /Workspace/Users/user@example.com/{app_name}
databricks apps deploy my-apx-app \
  --source-code-path /Workspace/Users/user@example.com/{app_name}
databricks apps get my-apx-app
```

### Post-deployment

```bash
# Check logs for errors
databricks apps logs my-apx-app

# Verify app URL
databricks apps get my-apx-app
```

---

## Testing

### Backend: pytest + httpx

```python
# tests/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_list_projects(client):
    response = await client.get("/api/projects")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

@pytest.mark.asyncio
async def test_create_project(client):
    response = await client.post(
        "/api/projects",
        json={"name": "Test Project", "description": "A test"},
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Test Project"
```

### Frontend: TypeScript type checking

```bash
cd src/{app_name}/frontend
npx tsc --noEmit
```

### API contract testing

Ensure frontend types match the OpenAPI spec generated by FastAPI:

1. Export the OpenAPI schema: `GET /openapi.json`
2. Generate TypeScript types from the schema
3. Use those types in the frontend API client

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **CORS errors in local dev** | Add CORS middleware to FastAPI (see [backend-patterns.md](backend-patterns.md)) |
| **Frontend build fails** | Run `npm install` first; check `vite.config.ts` proxy settings |
| **Lakebase connection refused** | Verify resource is added in Databricks UI; check `PGHOST` env var |
| **Static files not served** | Configure FastAPI to mount the frontend build directory |
| **psycopg2 import error on deploy** | Add `psycopg2-binary` to `requirements.txt` |
| **Port conflict** | Bind to `DATABRICKS_APP_PORT` (defaults to 8000), never use 8080 |
| **TypeScript errors** | Run `npx tsc --noEmit` and fix before building |
| **API returns 422** | Check Pydantic model validation; inspect request body against `EntityIn` schema |

---

## Platform Constraints

| Constraint | Details |
|------------|---------|
| **Runtime** | Python 3.11, Ubuntu 22.04 LTS |
| **Compute** | 2 vCPUs, 6 GB memory (default) |
| **Pre-installed** | FastAPI 0.115.0, uvicorn (backend); Node.js runtime (build only) |
| **Custom packages** | Python: `requirements.txt`; JS: `package.json` (build before deploy) |
| **Network** | Apps can reach Databricks APIs; external access depends on workspace config |

---

## Related Skills

- **[databricks-app-python](../databricks-app-python/SKILL.md)** - Python-only apps (Dash, Streamlit, Flask)
- **[databricks-lakebase-provisioned](../databricks-lakebase-provisioned/SKILL.md)** - Lakebase PostgreSQL patterns
- **[databricks-lakebase-autoscale](../databricks-lakebase-autoscale/SKILL.md)** - Lakebase autoscaling configuration
- **[databricks-bundles](../databricks-bundles/SKILL.md)** - deploying apps via DABs
- **[databricks-model-serving](../databricks-model-serving/SKILL.md)** - integrating ML model endpoints
