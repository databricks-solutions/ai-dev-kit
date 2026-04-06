# Lakebase (PostgreSQL) Connectivity

Lakebase provides low-latency transactional storage for Databricks Apps via a managed PostgreSQL interface. There are two offerings: **Provisioned** (fixed capacity, auto-injected env vars) and **Autoscale** (elastic compute, OAuth tokens, branching).

**Docs**: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/lakebase

---

## When to Use Lakebase

| Use Case | Recommended Backend |
|----------|-------------------|
| Analytical queries on Delta tables | SQL Warehouse |
| Low-latency transactional CRUD | **Lakebase** |
| App-specific metadata/config | **Lakebase** |
| User session data | **Lakebase** |
| Large-scale data exploration | SQL Warehouse |

---

## psycopg2 vs psycopg3 Decision

| | psycopg2 | psycopg3 (psycopg) |
|--|----------|---------------------|
| When to use | Provisioned (auto-injected env vars) | Autoscale (OAuth token refresh) |
| Install | `psycopg2-binary` | `psycopg[binary]>=3.0` |
| Import | `import psycopg2` | `import psycopg` |
| Token refresh | Not needed (env vars auto-refresh) | Required (OAuth tokens expire ~1 hour) |
| Async support | No native | Yes (`psycopg.AsyncConnection`) |
| Recommendation | Legacy, works for provisioned | **Preferred for new projects** |

For new projects, prefer **psycopg3** (`psycopg`) regardless of Lakebase type. It works with both provisioned and autoscale, supports async, and handles the `hostaddr` parameter needed for the macOS DNS workaround.

---

## Lakebase Provisioned (Auto-Injected Env Vars)

### Setup

1. Add Lakebase as an app resource in the Databricks UI (resource type: **Lakebase database**)
2. Databricks auto-injects PostgreSQL connection env vars:

| Variable | Description |
|----------|-------------|
| `PGHOST` | Database hostname |
| `PGDATABASE` | Database name |
| `PGUSER` | PostgreSQL role (created per app) |
| `PGPASSWORD` | Role password |
| `PGPORT` | Port (typically 5432) |

3. Reference in `app.yaml`:

```yaml
env:
  - name: DB_CONNECTION_STRING
    valueFrom:
      resource: database
```

### Connection Patterns

#### psycopg2 (Synchronous)

```python
import os
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("PGHOST"),
    database=os.getenv("PGDATABASE"),
    user=os.getenv("PGUSER"),
    password=os.getenv("PGPASSWORD"),
    port=os.getenv("PGPORT", "5432"),
)

with conn.cursor() as cur:
    cur.execute("SELECT * FROM my_table LIMIT 10")
    rows = cur.fetchall()

conn.close()
```

#### asyncpg (Asynchronous)

```python
import os
import asyncpg

async def get_data():
    conn = await asyncpg.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        port=int(os.getenv("PGPORT", "5432")),
    )
    rows = await conn.fetch("SELECT * FROM my_table LIMIT 10")
    await conn.close()
    return rows
```

#### SQLAlchemy

```python
import os
from sqlalchemy import create_engine

DATABASE_URL = (
    f"postgresql://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
    f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT', '5432')}"
    f"/{os.getenv('PGDATABASE')}"
)

engine = create_engine(DATABASE_URL)
```

### Streamlit with Provisioned Lakebase

```python
import streamlit as st
import psycopg2

@st.cache_resource
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("PGHOST"),
        database=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
    )
```

---

## Lakebase Autoscale (OAuth Tokens)

Lakebase Autoscale does **not** auto-inject `PGHOST`/`PGDATABASE`/etc. env vars into the app runtime. You must generate an OAuth token via the Databricks SDK and manage token refresh yourself.

### Setup

1. Create a Lakebase Autoscale project (via SDK, CLI, or `create_or_update_lakebase_database` MCP tool with `type="autoscale"`)
2. Configure your app to access the project. Add a serving endpoint resource for SDK authentication:

```yaml
# app.yaml
command: ["python", "app.py"]
env:
  - name: LAKEBASE_PROJECT_ID
    value: "my-app"
  - name: LAKEBASE_BRANCH
    value: "production"
  - name: LAKEBASE_DATABASE
    value: "databricks_postgres"
resources:
  - name: serving-endpoint
    serving_endpoint:
      name: "databricks-meta-llama-3-3-70b-instruct"
      permission: CAN_QUERY
```

The app's service principal must have permission to call `w.postgres.generate_database_credential()`.

### Basic Connection with psycopg3

```python
import psycopg
from databricks.sdk import WorkspaceClient


def get_autoscale_connection(
    project_id: str,
    branch_id: str = "production",
    database: str = "databricks_postgres",
):
    """Get a connection to Lakebase Autoscale with a fresh OAuth token."""
    w = WorkspaceClient()

    # Resolve the primary endpoint
    endpoints = list(w.postgres.list_endpoints(
        parent=f"projects/{project_id}/branches/{branch_id}"
    ))
    if not endpoints:
        raise RuntimeError(f"No endpoints for projects/{project_id}/branches/{branch_id}")

    ep_name = endpoints[0].name
    endpoint = w.postgres.get_endpoint(name=ep_name)
    host = endpoint.status.hosts.host

    # Generate OAuth token (valid ~1 hour)
    cred = w.postgres.generate_database_credential(endpoint=ep_name)

    return psycopg.connect(
        host=host,
        dbname=database,
        user=w.current_user.me().user_name,
        password=cred.token,
        sslmode="require",
    )
```

### Token Refresh for Long-Running Apps

OAuth tokens expire after 1 hour. For apps that run continuously (Streamlit, Dash, FastAPI), refresh the token at 50 minutes to avoid mid-request failures.

#### FastAPI with Connection Pool and Token Refresh

```python
import asyncio
import os

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from databricks.sdk import WorkspaceClient


class AutoscaleConnectionManager:
    """Manages Lakebase Autoscale connections with automatic token refresh."""

    def __init__(self, project_id: str, branch_id: str = "production",
                 database: str = "databricks_postgres",
                 token_refresh_seconds: int = 3000):
        self.project_id = project_id
        self.branch_id = branch_id
        self.database = database
        self.token_refresh_seconds = token_refresh_seconds
        self._current_token = None
        self._refresh_task = None
        self._engine = None
        self._session_maker = None

    def _resolve_endpoint(self):
        """Get host and endpoint name from the primary endpoint."""
        w = WorkspaceClient()
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{self.project_id}/branches/{self.branch_id}"
        ))
        if not endpoints:
            raise RuntimeError("No endpoints found")
        ep = w.postgres.get_endpoint(name=endpoints[0].name)
        return endpoints[0].name, ep.status.hosts.host

    def _generate_token(self, endpoint_name: str) -> str:
        """Generate a fresh OAuth token."""
        w = WorkspaceClient()
        cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
        return cred.token

    async def _refresh_loop(self, endpoint_name: str):
        """Background task to refresh token before expiry."""
        while True:
            await asyncio.sleep(self.token_refresh_seconds)
            try:
                self._current_token = await asyncio.to_thread(
                    self._generate_token, endpoint_name
                )
            except Exception as e:
                print(f"Token refresh failed: {e}")

    def initialize(self):
        """Initialize the database engine and session maker."""
        w = WorkspaceClient()
        ep_name, host = self._resolve_endpoint()
        username = w.current_user.me().user_name

        self._current_token = self._generate_token(ep_name)

        url = f"postgresql+psycopg://{username}@{host}:5432/{self.database}"
        self._engine = create_async_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            connect_args={"sslmode": "require"},
        )

        # Inject the latest token on every new connection
        @event.listens_for(self._engine.sync_engine, "do_connect")
        def inject_token(dialect, conn_rec, cargs, cparams):
            cparams["password"] = self._current_token

        self._session_maker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

        # Start background refresh
        ep_name_copy = ep_name
        self._refresh_task = asyncio.create_task(self._refresh_loop(ep_name_copy))

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_maker() as session:
            yield session

    async def close(self):
        if self._refresh_task:
            self._refresh_task.cancel()
        if self._engine:
            await self._engine.dispose()


# Usage
db = AutoscaleConnectionManager(
    project_id=os.getenv("LAKEBASE_PROJECT_ID", "my-app"),
    branch_id=os.getenv("LAKEBASE_BRANCH", "production"),
    database=os.getenv("LAKEBASE_DATABASE", "databricks_postgres"),
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.initialize()
    yield
    await db.close()

app = FastAPI(lifespan=lifespan)

@app.get("/data")
async def get_data():
    async with db.session() as session:
        result = await session.execute(text("SELECT * FROM my_table LIMIT 10"))
        return [dict(row._mapping) for row in result]
```

#### Streamlit with Token Refresh

Streamlit reruns the script on each interaction, so use `st.cache_resource` with a TTL to refresh the token periodically:

```python
import os

import psycopg
import streamlit as st
from databricks.sdk import WorkspaceClient


@st.cache_resource(ttl=2400)  # Refresh every 40 minutes (before 1-hour expiry)
def get_autoscale_connection():
    """Create a connection with a fresh OAuth token. Cached with TTL."""
    w = WorkspaceClient()
    project_id = os.getenv("LAKEBASE_PROJECT_ID", "my-app")
    branch_id = os.getenv("LAKEBASE_BRANCH", "production")

    endpoints = list(w.postgres.list_endpoints(
        parent=f"projects/{project_id}/branches/{branch_id}"
    ))
    ep_name = endpoints[0].name
    endpoint = w.postgres.get_endpoint(name=ep_name)
    host = endpoint.status.hosts.host

    cred = w.postgres.generate_database_credential(endpoint=ep_name)

    return psycopg.connect(
        host=host,
        dbname=os.getenv("LAKEBASE_DATABASE", "databricks_postgres"),
        user=w.current_user.me().user_name,
        password=cred.token,
        sslmode="require",
    )


conn = get_autoscale_connection()
with conn.cursor() as cur:
    cur.execute("SELECT * FROM my_table LIMIT 10")
    rows = cur.fetchall()
st.dataframe(rows)
```

---

## Critical: requirements.txt

`psycopg2`, `psycopg`, and `asyncpg` are **NOT pre-installed** in the Databricks Apps runtime. You **MUST** include them in `requirements.txt` or the app will crash on startup.

For provisioned (psycopg2):
```
psycopg2-binary
```

For autoscale or new projects (psycopg3):
```
psycopg[binary]>=3.0
databricks-sdk>=0.81.0
```

For async apps:
```
asyncpg
```

**This is the most common cause of Lakebase app failures.**

---

## Common Issues

| Issue | Solution |
|-------|----------|
| **Token expired (autoscale)** | Implement token refresh at 50 minutes; do not cache connections beyond 1 hour |
| **psycopg2 with autoscale fails** | Use psycopg3 (`psycopg`) for autoscale -- it supports `hostaddr` and async patterns |
| **DNS resolution fails on macOS** | Use `dig` to resolve the hostname and pass `hostaddr` to psycopg; see [connection-patterns.md](../databricks-lakebase-autoscale/connection-patterns.md) |
| **Scale-to-zero wake-up latency** | First connection after idle may take 10-30 seconds; add retry logic or a loading indicator |
| **Missing requirements** | Add `psycopg2-binary` or `psycopg[binary]>=3.0` to `requirements.txt` |
| **No PGHOST env var (autoscale)** | Autoscale does not auto-inject env vars; use the SDK to resolve the endpoint host |

## Notes

- Lakebase is in **Public Preview**
- Each app gets its own PostgreSQL role with `Can connect and create` permission (provisioned only)
- Autoscale apps must generate OAuth tokens via the Databricks SDK
- Lakebase is ideal alongside SQL warehouse: use Lakebase for app state, SQL warehouse for analytics
- For comprehensive autoscale patterns (branching, reverse ETL, compute sizing), see the [databricks-lakebase-autoscale skill](../databricks-lakebase-autoscale/SKILL.md)
