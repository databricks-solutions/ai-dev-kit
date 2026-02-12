# Lakebase Autoscaling Connection Patterns

## Overview

This document covers different connection patterns for Lakebase Autoscaling, from simple scripts to production applications with token refresh.

## Authentication Methods

Lakebase Autoscaling supports two authentication methods:

| Method | Token Lifetime | Best For |
|--------|---------------|----------|
| **OAuth tokens** | 1 hour (must refresh) | Interactive sessions, workspace-integrated apps |
| **Native Postgres passwords** | No expiry | Long-running processes, tools without token rotation |

**Connection timeouts (both methods):**
- **24-hour idle timeout**: Connections with no activity for 24 hours are automatically closed
- **3-day maximum connection life**: Connections alive for more than 3 days may be closed

Design your applications to handle connection timeouts with retry logic.

## Connection Methods

### 1. Direct psycopg Connection (Simple Scripts)

For one-off scripts or notebooks:

```python
import psycopg
from databricks.sdk import WorkspaceClient

def get_connection(project_id: str, branch_id: str = "production",
                   endpoint_id: str = None, database_name: str = "databricks_postgres"):
    """Get a database connection with fresh OAuth token."""
    w = WorkspaceClient()

    # Get endpoint details to find the host
    if endpoint_id:
        ep_name = f"projects/{project_id}/branches/{branch_id}/endpoints/{endpoint_id}"
    else:
        # List endpoints and pick the primary R/W one
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{project_id}/branches/{branch_id}"
        ))
        ep_name = endpoints[0].name

    endpoint = w.postgres.get_endpoint(name=ep_name)
    host = endpoint.status.hosts.host

    # Generate OAuth token (valid for 1 hour)
    cred = w.postgres.generate_database_credential(endpoint=ep_name)

    # Build connection string
    conn_string = (
        f"host={host} "
        f"dbname={database_name} "
        f"user={w.current_user.me().user_name} "
        f"password={cred.token} "
        f"sslmode=require"
    )

    return psycopg.connect(conn_string)

# Usage
with get_connection("my-app") as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT NOW()")
        print(cur.fetchone())
```

### 2. Connection Pool with Token Refresh (Production)

For long-running applications that need connection pooling:

```python
import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from databricks.sdk import WorkspaceClient


class LakebaseAutoscaleConnectionManager:
    """Manages Lakebase Autoscaling connections with automatic token refresh."""

    def __init__(
        self,
        project_id: str,
        branch_id: str = "production",
        database_name: str = "databricks_postgres",
        pool_size: int = 5,
        max_overflow: int = 10,
        token_refresh_seconds: int = 3000  # 50 minutes
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

    def _generate_token(self) -> str:
        """Generate fresh OAuth token."""
        w = WorkspaceClient()
        # Get primary endpoint name for token scoping
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{self.project_id}/branches/{self.branch_id}"
        ))
        endpoint_name = endpoints[0].name if endpoints else None
        cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
        return cred.token

    def _get_host(self) -> str:
        """Get the connection host from the primary endpoint."""
        w = WorkspaceClient()
        endpoints = list(w.postgres.list_endpoints(
            parent=f"projects/{self.project_id}/branches/{self.branch_id}"
        ))
        if not endpoints:
            raise RuntimeError(
                f"No endpoints found for projects/{self.project_id}/branches/{self.branch_id}"
            )
        endpoint = w.postgres.get_endpoint(name=endpoints[0].name)
        return endpoint.status.hosts.host

    async def _refresh_loop(self):
        """Background task to refresh token periodically."""
        while True:
            await asyncio.sleep(self.token_refresh_seconds)
            try:
                self._current_token = await asyncio.to_thread(self._generate_token)
            except Exception as e:
                print(f"Token refresh failed: {e}")

    def initialize(self):
        """Initialize database engine and start token refresh."""
        w = WorkspaceClient()

        # Get host info
        host = self._get_host()
        username = w.current_user.me().user_name

        # Generate initial token
        self._current_token = self._generate_token()

        # Create engine (password injected via event)
        url = (
            f"postgresql+psycopg://{username}@"
            f"{host}:5432/{self.database_name}"
        )

        self._engine = create_async_engine(
            url,
            pool_size=self.pool_size,
            max_overflow=self.max_overflow,
            pool_recycle=3600,
            connect_args={"sslmode": "require"}
        )

        # Inject token on connect
        @event.listens_for(self._engine.sync_engine, "do_connect")
        def inject_token(dialect, conn_rec, cargs, cparams):
            cparams["password"] = self._current_token

        self._session_maker = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False
        )

    def start_refresh(self):
        """Start background token refresh task."""
        if not self._refresh_task:
            self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def stop_refresh(self):
        """Stop token refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session."""
        async with self._session_maker() as session:
            yield session

    async def close(self):
        """Close all connections."""
        await self.stop_refresh()
        if self._engine:
            await self._engine.dispose()


# Usage in FastAPI
from fastapi import FastAPI

app = FastAPI()
db_manager = LakebaseAutoscaleConnectionManager("my-app", "production", "my_database")

@app.on_event("startup")
async def startup():
    db_manager.initialize()
    db_manager.start_refresh()

@app.on_event("shutdown")
async def shutdown():
    await db_manager.close()

@app.get("/data")
async def get_data():
    async with db_manager.session() as session:
        result = await session.execute("SELECT * FROM my_table")
        return result.fetchall()
```

### 3. Static URL Mode (Local Development)

For local development, use a static connection URL:

```python
import os
from sqlalchemy.ext.asyncio import create_async_engine

# Set environment variable with full connection URL
# LAKEBASE_PG_URL=postgresql://user:password@host:5432/database

def get_database_url() -> str:
    """Get database URL from environment."""
    url = os.environ.get("LAKEBASE_PG_URL")
    if url and url.startswith("postgresql://"):
        # Convert to psycopg3 async driver
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

engine = create_async_engine(
    get_database_url(),
    pool_size=5,
    connect_args={"sslmode": "require"}
)
```

### 4. DNS Resolution Workaround (macOS)

Python's `socket.getaddrinfo()` fails with long hostnames on macOS. Use `dig` as fallback:

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
            capture_output=True, text=True, timeout=5
        )
        ips = result.stdout.strip().split('\n')
        for ip in ips:
            if ip and not ip.startswith(';'):
                return ip
    except Exception:
        pass

    raise RuntimeError(f"Could not resolve hostname: {hostname}")

# Use with psycopg
conn_params = {
    "host": hostname,       # For TLS SNI
    "hostaddr": resolve_hostname(hostname),  # Actual IP
    "dbname": database_name,
    "user": username,
    "password": token,
    "sslmode": "require"
}
conn = psycopg.connect(**conn_params)
```

## Best Practices

1. **Always use SSL**: Set `sslmode=require` in all connections
2. **Implement token refresh**: Tokens expire after 1 hour; refresh at 50 minutes
3. **Use connection pooling**: Avoid creating new connections per request
4. **Handle DNS issues on macOS**: Use the `hostaddr` workaround if needed
5. **Close connections properly**: Use context managers or explicit cleanup
6. **Handle scale-to-zero wake-up**: First connection after idle may take 2-5 seconds
7. **Log token refresh events**: Helps debug authentication issues
