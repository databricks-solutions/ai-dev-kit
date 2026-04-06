# APX Best Practices

Guidelines for building production-quality APX applications.

---

## Project Organization

### Keep backend and frontend independent

The backend and frontend should be deployable and testable independently. The backend should never import frontend code, and the frontend should only communicate with the backend via HTTP API calls.

### Use the 3-model pattern consistently

Every entity needs three Pydantic models (`EntityIn`, `EntityRecord`, `EntityOut`). Skipping this leads to API contracts that leak internal fields or accept server-generated values from clients.

### One router per resource

Each API resource gets its own file in `routes/`. A project with tasks and comments should have:

```
routes/
  projects.py
  tasks.py
  comments.py
```

Register all routers in `main.py` with `app.include_router()`.

---

## API Design

### Always set response_model

Every FastAPI route must include `response_model`. This is not optional:

```python
# Correct
@router.get("/", response_model=list[TaskOut])

# Wrong - no response_model
@router.get("/")
```

`response_model` enables automatic OpenAPI schema generation, which the frontend uses for type safety.

### Prefix API routes with /api

All backend routes should be under `/api/` to avoid conflicts with frontend client-side routing:

```python
router = APIRouter(prefix="/api/tasks", tags=["tasks"])
```

### Use proper HTTP status codes

- `200` for successful reads and updates
- `201` for successful creates (always return the created object)
- `204` for successful deletes (no response body)
- `404` with actionable message for not-found errors
- `422` for validation errors (automatic from Pydantic)

### Return created objects from POST

```python
@router.post("/", response_model=TaskOut, status_code=201)
async def create_task(task: TaskIn):
    created = await db.create_task(task)
    return created  # Return the full object including id and timestamps
```

---

## Frontend Architecture

### Type everything

Use TypeScript strict mode. Define interfaces that mirror the backend's Pydantic models:

```typescript
// Must match backend's TaskOut model
interface Task {
  id: string;
  title: string;
  description: string;
  status: "pending" | "in_progress" | "done";
  created_at: string;
  updated_at: string;
}
```

### Centralize API calls

All API calls go through a single `api.ts` module. Never call `fetch()` directly in components:

```typescript
// Good - centralized
const tasks = await api.tasks.list();

// Bad - fetch in component
const response = await fetch("/api/tasks");
```

### Handle loading and error states

Every data-fetching component must handle three states:

```tsx
if (loading) return <Skeleton />;
if (error) return <ErrorMessage message={error} />;
return <DataDisplay data={data} />;
```

### Use shadcn/ui components

Do not build custom UI primitives. Use shadcn/ui for buttons, cards, tables, forms, dialogs, and other standard components. This ensures consistent styling and accessibility.

---

## Lakebase Integration

### Connection pooling

For production apps, use connection pooling instead of creating a new connection per request:

```python
from sqlalchemy import create_engine
from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
```

### Schema migrations

Use SQL scripts or Alembic for schema changes. Never modify tables manually in production:

```python
# backend/migrations/001_create_tasks.sql
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### Generate UUIDs server-side

```python
import uuid
from datetime import datetime, timezone

class TaskRecord(TaskIn):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## Deployment

### Build frontend before uploading

The frontend build step (`npm run build`) must happen before uploading to the workspace. The built output in `frontend/dist/` is what FastAPI serves as static files.

### Use app.yaml valueFrom for resources

Never hardcode resource IDs. Use `valueFrom` to reference Databricks-managed resources:

```yaml
env:
  - name: DB_CONNECTION_STRING
    valueFrom:
      resource: database
  - name: SERVING_ENDPOINT_NAME
    valueFrom: serving-endpoint
```

### Add psycopg2-binary to requirements.txt

This dependency is not pre-installed in the Databricks Apps runtime:

```
psycopg2-binary
sqlalchemy
```

### Check logs after deploy

```bash
databricks apps logs my-apx-app
```

Common issues:
- `ModuleNotFoundError: psycopg2` -- add `psycopg2-binary` to `requirements.txt`
- `Connection refused` -- Lakebase resource not added via UI
- `Address already in use` -- bind to `DATABRICKS_APP_PORT` env var

---

## Local Development

### Run backend and frontend separately

```bash
# Terminal 1: Backend
cd src/{app_name}/backend
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd src/{app_name}/frontend
npm run dev
```

The Vite dev server proxies `/api/*` requests to `localhost:8000` (configured in `vite.config.ts`).

### Use mock backend for frontend development

When iterating on the frontend without a database, use a mock backend:

```python
# backend/mock_db.py
from .models import TaskRecord
from datetime import datetime, timezone

MOCK_TASKS = [
    TaskRecord(
        id="1",
        title="Sample Task",
        description="A mock task for development",
        status="pending",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ),
]

async def list_tasks(**kwargs):
    return MOCK_TASKS
```

Toggle with an environment variable:

```python
import os

USE_MOCK = os.getenv("USE_MOCK_BACKEND", "true").lower() == "true"

if USE_MOCK:
    from . import mock_db as db
else:
    from . import real_db as db
```

---

## Testing

### Test API contracts, not implementation

```python
@pytest.mark.asyncio
async def test_create_returns_all_fields(client):
    response = await client.post(
        "/api/tasks",
        json={"title": "Test", "description": "Description"},
    )
    data = response.json()
    assert "id" in data
    assert "created_at" in data
    assert data["title"] == "Test"
```

### Test error responses

```python
@pytest.mark.asyncio
async def test_get_nonexistent_returns_404(client):
    response = await client.get("/api/tasks/nonexistent-id")
    assert response.status_code == 404
```

### Run type checks

```bash
# Backend
cd src/{app_name}/backend
basedpyright .

# Frontend
cd src/{app_name}/frontend
npx tsc --noEmit
```

Fix all type errors before deploying.
