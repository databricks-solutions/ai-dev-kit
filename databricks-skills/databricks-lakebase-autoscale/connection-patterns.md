# Lakebase Autoscaling Connection Patterns

## Overview

This document covers the canonical connection patterns for Lakebase Autoscaling, ordered by recommendation:

1. **`psycopg_pool.ConnectionPool` + `OAuthConnection`** — canonical for production Databricks Apps. Used by the [official tutorial](https://docs.databricks.com/aws/en/oltp/projects/tutorial-databricks-apps-autoscaling), the [external app SDK guide](https://docs.databricks.com/aws/en/oltp/projects/external-apps-connect), and [`databricks-ai-bridge`](https://github.com/databricks/databricks-ai-bridge/blob/main/src/databricks_ai_bridge/lakebase.py). Zero background threads — rotation is handled by pool recycling.
2. **SQLAlchemy `do_connect` event + background refresh** — alternative for apps already using SQLAlchemy async. Works but adds a background `asyncio.Task` you don't need.
3. **Direct `psycopg.connect`** — only for one-off scripts / notebooks where the session lives < 1 hour.
4. **Static URL** — local development only.

## Authentication

Lakebase Autoscaling supports two authentication methods:

| Method | Token Lifetime | Best For |
|--------|---------------|----------|
| **OAuth tokens** (`generate_database_credential`) | 1 hour, enforced at login only | Apps — rotate via pool recycling |
| **Native Postgres passwords** | No expiry | Long-running processes, tools without token rotation |

**Critical distinction:** The workspace OAuth token (`w.config.oauth_token().access_token`) is *workspace-scoped* — it will **fail at PG login**. You must call `w.postgres.generate_database_credential(endpoint=...)` to mint a separate *Lakebase-scoped* JWT:

```python
# ✅ CORRECT — Lakebase-scoped database credential
cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
password = cred.token

# ❌ WRONG — workspace-scoped token
password = w.config.oauth_token().access_token
```

**Connection timeouts (both methods):**
- **24-hour idle timeout**: Connections with no activity for 24 hours are automatically closed
- **3-day maximum connection life**: Connections alive for more than 3 days may be closed

Design your applications to handle connection timeouts with retry logic.

## 1. `psycopg_pool.ConnectionPool` + `OAuthConnection` (CANONICAL)

This is the pattern from the official Databricks tutorial, external app guide, and `databricks-ai-bridge`. **Use this for any production Databricks App.**

### How it works

1. `OAuthConnection.connect()` mints a fresh Lakebase credential every time the pool opens a new physical connection.
2. Lakebase tokens expire at 1 hour, but expiration is enforced **only at login** — already-open connections stay valid.
3. `max_lifetime=2700` (45 min) tells the pool to recycle connections before tokens expire. When the pool reopens, `OAuthConnection.connect()` fires and gets a fresh token.
4. The 15-minute buffer (60 min token − 45 min recycle) means you never race against expiry.

**Result:** Fully transparent token rotation with zero background tasks, zero timers, zero manual refresh logic.

> **Why not `max_lifetime=3600` (the default)?** You'd hand out connections with nearly-expired tokens. A connection established at minute 59 with a token that expires at minute 60 will fail a minute later. Always use 2700.

### `app.yaml`

```yaml
command: ['flask', '--app', 'app.py', 'run', '--host', '0.0.0.0', '--port', '8000']
env:
  # These 5 are auto-injected when you add a Lakebase (postgres) resource in the UI:
  # PGHOST, PGPORT, PGDATABASE, PGUSER, PGSSLMODE
  # You MUST manually add ENDPOINT_NAME — it's needed by generate_database_credential():
  - name: ENDPOINT_NAME
    value: 'projects/<project-id>/branches/<branch-id>/endpoints/<endpoint-id>'
```

### `requirements.txt`

```
flask
psycopg[binary,pool]>=3.1.0
databricks-sdk>=0.81.0
```

### `app.py` (Flask)

```python
import os
from databricks.sdk import WorkspaceClient
import psycopg
from psycopg_pool import ConnectionPool
from flask import Flask

app = Flask(__name__)

# Inside Databricks Apps, WorkspaceClient() auto-authenticates via SP credentials.
w = WorkspaceClient()


class OAuthConnection(psycopg.Connection):
    """Inject a fresh Lakebase OAuth token on every pool-opened connection.

    The pool calls OAuthConnection.connect() when:
      - Filling min_size on startup
      - Recycling a connection (max_lifetime exceeded)
      - Creating a new connection under load
      - Replacing a connection that failed health-check

    No background refresh thread is needed: tokens are always fresh at login
    time, and login is where Lakebase enforces expiration.
    """

    @classmethod
    def connect(cls, conninfo='', **kwargs):
        endpoint_name = os.environ["ENDPOINT_NAME"]
        cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
        kwargs['password'] = cred.token
        return super().connect(conninfo, **kwargs)


username = os.environ["PGUSER"]     # SP client ID — auto-injected
host     = os.environ["PGHOST"]     # e.g. ep-restless-pond-e4wvk0yn... — auto-injected
port     = os.environ.get("PGPORT", "5432")
database = os.environ["PGDATABASE"]  # typically "databricks_postgres" — auto-injected
sslmode  = os.environ.get("PGSSLMODE", "require")

pool = ConnectionPool(
    conninfo=(
        f"dbname={database} user={username} "
        f"host={host} port={port} sslmode={sslmode}"
    ),
    connection_class=OAuthConnection,
    min_size=1,
    max_size=10,
    # CRITICAL: 2700 (45 min), not the 3600 default.
    # Recycles connections 15 min before the 1-hour token expiry.
    max_lifetime=2700,
    open=True,
)


@app.route('/')
def index():
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database()")
            row = cur.fetchone()
    return f"Connected as {row[0]} to {row[1]}"


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8000)
```

### FastAPI variant

Identical pattern, but use `open=False` with an explicit lifespan so startup failures surface immediately:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

pool = ConnectionPool(
    conninfo=...,
    connection_class=OAuthConnection,
    min_size=1, max_size=10,
    max_lifetime=2700,
    open=False,  # Opened explicitly in lifespan
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=30.0)  # Fail fast if DB unreachable
    yield
    pool.close()


app = FastAPI(lifespan=lifespan)


@app.get("/api/data")
def get_data():  # sync def — FastAPI runs in threadpool automatically
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ...")
            return cur.fetchall()
```

## 2. SQLAlchemy `do_connect` Event (Alternative)

**Use only if your app is already SQLAlchemy-async.** Otherwise prefer pattern 1 — this adds a background refresh task you don't need.

```python
import asyncio
from typing import AsyncGenerator, Optional
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from databricks.sdk import WorkspaceClient


class LakebaseAutoscaleConnectionManager:
    """Manages Lakebase Autoscaling connections with background token refresh.

    This pattern works but adds operational complexity (a background asyncio.Task)
    that isn't necessary. Prefer psycopg_pool + OAuthConnection (pattern 1).
    """

    def __init__(
        self,
        project_id: str,
        branch_id: str = "production",
        database_name: str = "databricks_postgres",
        pool_size: int = 5,
        max_overflow: int = 10,
        token_refresh_seconds: int = 3000,  # 50 minutes
    ):
        self.project_id = project_id
        self.branch_id = branch_id
        self.database_name = database_name
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.token_refresh_seconds = token_refresh_seconds

        self._current_token: Optional[str] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._engine = None
        self._session_maker = None

    def _endpoint_name(self) -> str:
        w = WorkspaceClient()
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{self.project_id}/branches/{self.branch_id}"
        ))
        if not endpoints:
            raise RuntimeError(
                f"No endpoints for projects/{self.project_id}/branches/{self.branch_id}"
            )
        return endpoints[0].name

    def _generate_token(self) -> str:
        w = WorkspaceClient()
        cred = w.postgres.generate_database_credential(endpoint=self._endpoint_name())
        return cred.token

    def _get_host(self) -> str:
        w = WorkspaceClient()
        ep = w.postgres.get_endpoint(name=self._endpoint_name())
        return ep.status.hosts.host

    async def _refresh_loop(self):
        while True:
            await asyncio.sleep(self.token_refresh_seconds)
            try:
                self._current_token = await asyncio.to_thread(self._generate_token)
            except Exception as e:
                print(f"Token refresh failed: {e}")

    def initialize(self):
        w = WorkspaceClient()
        host = self._get_host()
        username = w.current_user.me().user_name

        self._current_token = self._generate_token()

        url = f"postgresql+psycopg://{username}@{host}:5432/{self.database_name}"
        self._engine = create_async_engine(
            url,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_recycle=3600,
            connect_args={"sslmode": "require"},
        )

        @event.listens_for(self._engine.sync_engine, "do_connect")
        def inject_token(dialect, conn_rec, cargs, cparams):
            cparams["password"] = self._current_token

        self._session_maker = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    def start_refresh(self):
        if not self._refresh_task:
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop_refresh(self):
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_maker() as session:
            yield session

    async def close(self):
        await self.stop_refresh()
        if self._engine:
            await self._engine.dispose()
```

## 3. Direct `psycopg.connect` (Scripts / Notebooks Only)

For one-off scripts or notebooks where the process lives well under an hour:

```python
import psycopg
from databricks.sdk import WorkspaceClient


def get_connection(project_id: str, branch_id: str = "production",
                   endpoint_id: str = None, database_name: str = "databricks_postgres"):
    """Get a one-shot database connection with a fresh OAuth token."""
    w = WorkspaceClient()

    if endpoint_id:
        ep_name = f"projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}"
    else:
        # Pick the first endpoint under the branch
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{project_id}/branches/{branch_id}"
        ))
        ep_name = endpoints[0].name

    endpoint = w.postgres.get_endpoint(name=ep_name)
    host = endpoint.status.hosts.host

    cred = w.postgres.generate_database_credential(endpoint=ep_name)

    return psycopg.connect(
        host=host,
        dbname=database_name,
        user=w.current_user.me().user_name,
        password=cred.token,
        sslmode="require",
    )


# Usage
with get_connection("my-app") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT NOW()")
        print(cur.fetchone())
```

## 4. Static URL (Local Development Only)

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine

# LAKEBASE_PG_URL=postgresql://user:password@host:5432/database

def get_database_url() -> str:
    url = os.environ.get("LAKEBASE_PG_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_async_engine(
    get_database_url(),
    pool_size=5,
    connect_args={"sslmode": "require"},
)
```

## DNS Resolution Workaround (macOS)

Python's `socket.getaddrinfo()` can fail with long hostnames on macOS. Fall back to `dig`:

```python
import subprocess
import socket


def resolve_hostname(hostname: str) -> str:
    """Resolve hostname using dig command (macOS workaround)."""
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror:
        pass

    try:
        result = subprocess.run(
            ["dig", "+short", hostname],
            capture_output=True, text=True, timeout=5,
        )
        for ip in result.stdout.strip().split('\n'):
            if ip and not ip.startswith(';'):
                return ip
    except Exception:
        pass

    raise RuntimeError(f"Could not resolve hostname: {hostname}")


# Use with psycopg: set `host` for TLS SNI and `hostaddr` for the actual connection
conn_params = {
    "host": hostname,
    "hostaddr": resolve_hostname(hostname),
    "dbname": database_name,
    "user": username,
    "password": token,
    "sslmode": "require",
}
conn = psycopg.connect(**conn_params)
```

## Best Practices

1. **Default to pattern 1** (`psycopg_pool.ConnectionPool` + `OAuthConnection`). It's the canonical Databricks App pattern, works out of the box, no background tasks.
2. **Use `max_lifetime=2700`, not 3600.** The default creates a race condition where connections are handed out with nearly-expired tokens.
3. **Always `sslmode=require`** on every connection (it's auto-injected as `PGSSLMODE` in Databricks Apps).
4. **Never use `config.token` / `oauth_token().access_token` as the PG password** — that's a workspace-scoped token. Use `generate_database_credential()` to mint a Lakebase-scoped one.
5. **Handle DNS issues on macOS** using the `hostaddr` workaround if your dev machine can't resolve Lakebase hostnames.
6. **Use context managers** (`with pool.connection() as conn:`) so connections are always returned to the pool.
7. **Expect 2-5 second wake-up latency** on the first query after scale-to-zero — retry with backoff.
8. **Log credential refresh events** in `OAuthConnection.connect()` during early development — makes token-related failures easy to spot.
