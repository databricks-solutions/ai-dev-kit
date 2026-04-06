# Backend Patterns (FastAPI)

Detailed FastAPI backend patterns for APX applications.

---

## FastAPI App Entry Point

```python
# src/{app_name}/backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from .routes import projects, health

app = FastAPI(title="My APX App", version="1.0.0")

# CORS (for local development with Vite dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(projects.router)

# Serve built frontend (production)
frontend_build = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_build.exists():
    app.mount("/", StaticFiles(directory=str(frontend_build), html=True), name="frontend")
```

---

## Pydantic 3-Model Pattern

Every entity follows the same three-class pattern:

```python
# src/{app_name}/backend/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"

# 1. Input model - what the client sends
class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    status: TaskStatus = TaskStatus.PENDING

# 2. Record model - database representation
class TaskRecord(TaskIn):
    id: str
    created_at: datetime
    updated_at: datetime

# 3. Output model - what the client receives
class TaskOut(TaskRecord):
    pass
```

**Why three models?**

- `TaskIn` omits server-generated fields (`id`, timestamps) so clients cannot set them
- `TaskRecord` adds all database columns for internal use
- `TaskOut` controls the API response shape (you can exclude internal fields here)

### When EntityOut diverges from EntityRecord

```python
class UserRecord(UserIn):
    id: str
    password_hash: str
    created_at: datetime

# Exclude sensitive fields from API response
class UserOut(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime
```

---

## Router Conventions

### Standard CRUD router

```python
# src/{app_name}/backend/routes/tasks.py
from fastapi import APIRouter, HTTPException, Depends
from ..models import TaskIn, TaskOut

router = APIRouter(prefix="/api/tasks", tags=["tasks"])

@router.get("/", response_model=list[TaskOut])
async def list_tasks(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List tasks with optional filtering."""
    return await db.list_tasks(status=status, limit=limit, offset=offset)

@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str):
    """Get a single task by ID."""
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task

@router.post("/", response_model=TaskOut, status_code=201)
async def create_task(task: TaskIn):
    """Create a new task."""
    return await db.create_task(task)

@router.put("/{task_id}", response_model=TaskOut)
async def update_task(task_id: str, task: TaskIn):
    """Update an existing task."""
    updated = await db.update_task(task_id, task)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return updated

@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str):
    """Delete a task."""
    deleted = await db.delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
```

### Rules for routers

- Always include `response_model` (enables OpenAPI spec for frontend client generation)
- Use `status_code=201` for POST (create) endpoints
- Use `status_code=204` for DELETE endpoints (no response body)
- Use `tags` for OpenAPI grouping
- Prefix all API routes with `/api/` to avoid conflicts with frontend routing

---

## Health Check Endpoint

```python
# src/{app_name}/backend/routes/health.py
from fastapi import APIRouter

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    return {"status": "healthy"}
```

---

## Dependency Injection

### Database session dependency

```python
# src/{app_name}/backend/dependencies.py
from typing import Generator
from sqlalchemy.orm import Session
from .config import SessionLocal

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Using dependencies in routes

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from ..dependencies import get_db

@router.get("/", response_model=list[TaskOut])
async def list_tasks(db: Session = Depends(get_db)):
    return db.query(TaskTable).all()
```

---

## Error Handling

### Structured error responses

```python
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": exc.errors(),
        },
    )

# In route handlers, use HTTPException with clear messages
@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str):
    task = await db.get_task(task_id)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} not found. Use GET /api/tasks to list available tasks.",
        )
    return task
```

### HTTP status code conventions

| Status | Use Case |
|--------|----------|
| 200 | Successful GET, PUT |
| 201 | Successful POST (resource created) |
| 204 | Successful DELETE (no body) |
| 400 | Bad request (invalid parameters) |
| 404 | Resource not found |
| 409 | Conflict (duplicate resource) |
| 422 | Validation error (Pydantic) |
| 500 | Internal server error |

---

## CORS Configuration

### Local development

During local development, the React dev server (Vite) runs on port 5173 while the FastAPI backend runs on port 8000. CORS middleware bridges this gap:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",    # Vite dev server
        "http://localhost:3000",    # Alternate React dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Production

In production (deployed to Databricks), the frontend is served as static files by FastAPI. CORS is not needed since both frontend and backend share the same origin. You can leave the middleware in place (it is harmless) or gate it with an environment variable:

```python
import os

if os.getenv("ENVIRONMENT", "development") == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

---

## Serving Static Frontend

In production, FastAPI serves the built React app as static files:

```python
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Mount after all API routes are registered
frontend_build = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_build.exists():
    app.mount("/", StaticFiles(directory=str(frontend_build), html=True), name="frontend")
```

The `html=True` parameter enables SPA (single-page application) routing: any route not matched by an API endpoint serves `index.html`, letting React Router handle client-side navigation.

---

## Configuration

```python
# src/{app_name}/backend/config.py
import os

# Databricks environment
DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "")
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID", "")

# Lakebase PostgreSQL (auto-injected when resource is added)
PGHOST = os.getenv("PGHOST", "localhost")
PGDATABASE = os.getenv("PGDATABASE", "app_db")
PGUSER = os.getenv("PGUSER", "postgres")
PGPASSWORD = os.getenv("PGPASSWORD", "")
PGPORT = os.getenv("PGPORT", "5432")

DATABASE_URL = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{PGDATABASE}"

# App settings
APP_PORT = int(os.getenv("DATABRICKS_APP_PORT", "8000"))
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
```
