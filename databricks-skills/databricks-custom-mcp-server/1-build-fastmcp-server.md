# 1. Build the FastMCP Server

The server itself is FastAPI + FastMCP + your tools. Same shape as the official `mcp-server-hello-world` template; the only thing you change are the tools and the data-access helpers.

## Server skeleton

`server/app.py`:

```python
"""Custom MCP server — FastMCP + FastAPI, deployed as a Databricks App.

Exposes domain tools over the MCP streamable-HTTP transport at /mcp.
Authenticates downstream Databricks resources via WorkspaceClient (the
app's SP credentials at runtime, dev profile locally).
"""
from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import psycopg
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState
from mcp.server.fastmcp import FastMCP

# ─── workspace + lakebase helpers (lazy init, refresh on TTL) ──────────────

_w: WorkspaceClient | None = None

def get_w() -> WorkspaceClient:
    global _w
    if _w is None:
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
        _w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    return _w

# Lakebase OAuth tokens last ~1h — cache with a 10-min safety buffer.
_lakebase_cred = {"host": None, "user": None, "token": None, "exp": 0.0}

def get_lakebase_cred(instance_name: str) -> tuple[str, str, str]:
    now = time.time()
    if _lakebase_cred["token"] and _lakebase_cred["exp"] > now + 60:
        return _lakebase_cred["host"], _lakebase_cred["user"], _lakebase_cred["token"]
    w = get_w()
    inst = w.database.get_database_instance(name=instance_name)
    cred = w.database.generate_database_credential(
        request_id=str(uuid.uuid4()), instance_names=[instance_name],
    )
    _lakebase_cred.update({
        "host": inst.read_write_dns,
        "user": w.current_user.me().user_name,
        "token": cred.token,
        "exp": now + 50 * 60,
    })
    return _lakebase_cred["host"], _lakebase_cred["user"], _lakebase_cred["token"]

@contextmanager
def pg_conn(instance_name: str, db_name: str):
    host, user, token = get_lakebase_cred(instance_name)
    conn = psycopg.connect(
        host=host, port=5432, dbname=db_name, user=user, password=token,
        sslmode="require", autocommit=True,
    )
    try:
        yield conn
    finally:
        conn.close()

def wh_query(warehouse_id: str, sql: str) -> list[tuple]:
    w = get_w()
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=sql, wait_timeout="50s",
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(0.15)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        err = resp.status.error.message if resp.status.error else str(resp.status.state)
        raise RuntimeError(f"warehouse query failed: {err}")
    return resp.result.data_array or []

# ─── FastMCP server with tool definitions ──────────────────────────────────

mcp = FastMCP("my-custom-mcp")

@mcp.tool()
def query_lakebase_orders(customer_id: str, limit: int = 10) -> dict:
    """Read recent orders for a customer from Lakebase.

    Args:
        customer_id: Customer ID to look up
        limit: Max rows (default 10, max 100)
    """
    with pg_conn("my-lakebase-instance", "my_db") as c, c.cursor() as cur:
        cur.execute(
            "SELECT order_id, status, created_at FROM orders "
            "WHERE customer_id = %s ORDER BY created_at DESC LIMIT %s",
            (customer_id, max(1, min(int(limit), 100))),
        )
        rows = cur.fetchall()
    return {
        "binding": "my_catalog.my_db.orders",
        "object_type": "LAKEBASE_TABLE",
        "rows": [
            {"order_id": r[0], "status": r[1], "created_at": str(r[2])}
            for r in rows
        ],
    }

@mcp.tool()
def query_metric_view(view: str, dimension: str | None = None) -> dict:
    """Query a Unity Catalog Metric View using MEASURE() semantics.

    Args:
        view: Short view name (e.g. 'mv_sales_by_region')
        dimension: Optional GROUP BY dimension
    """
    select = f"SELECT MEASURE(net_revenue) AS net_revenue"
    if dimension:
        select = f"SELECT {dimension}, " + select.removeprefix("SELECT ")
    sql = f"{select} FROM my_catalog.gold.{view}"
    if dimension:
        sql += f" GROUP BY {dimension}"
    rows = wh_query("<your-warehouse-id>", sql)
    return {"view": view, "rows": [tuple(r) for r in rows]}

# ─── ASGI app for Databricks Apps to serve ─────────────────────────────────

http_app = mcp.streamable_http_app()

if __name__ == "__main__":
    # Local dev only
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(http_app, host="0.0.0.0", port=port, log_level="info")
```

## Tool design rules

| Rule | Why |
|---|---|
| **Type-hint every parameter** | The MCP protocol's tool-discovery embeds these in the schema sent to the LLM. No types = no schema = LLM picks wrong tool. |
| **Write a clear one-line docstring summary** | The first line is what the LLM sees when choosing which tool to call. "Read orders for a customer" vs "Database accessor". |
| **Return a dict with stable keys**, not a free-form string | Lets downstream agents pattern-match. Include `binding` / `object_type` keys so the agent can cite the source. |
| **Validate inputs at the tool boundary** | LLMs hallucinate. Cap `limit`, reject empty strings, sanity-check ID formats. The tool is your SQL injection boundary. |
| **Never do destructive ops by default** | Read tools are fine. Write tools should require explicit caller flags or sit behind a separate auth check. |
| **Avoid one giant `query_anything` tool** | LLMs route better between 10 specific tools than they construct SQL for one generic tool. |

## User-token passthrough (when the tool needs the *end user's* identity)

By default, your tools authenticate as the **app's service principal** (`get_w()` returns the app SP's `WorkspaceClient`). If a tool needs to act as the *calling user* (e.g., respect that user's row-level UC grants), use the `x-forwarded-access-token` header that Databricks Apps SSO injects:

```python
import contextvars
header_store: contextvars.ContextVar[dict] = contextvars.ContextVar("headers")

# in your FastAPI middleware (combined_app):
@combined_app.middleware("http")
async def capture_headers(request, call_next):
    header_store.set(dict(request.headers))
    return await call_next(request)

def get_user_w() -> WorkspaceClient:
    """WorkspaceClient acting as the calling user, not the app SP."""
    if "DATABRICKS_APP_NAME" not in os.environ:
        return WorkspaceClient()  # local dev
    headers = header_store.get({})
    token = headers.get("x-forwarded-access-token")
    if not token:
        raise PermissionError("no x-forwarded-access-token in request")
    return WorkspaceClient(token=token, auth_type="pat")
```

This is the same pattern the stock `mcp-server-hello-world` template uses. Use `get_user_w()` for tools that should respect UC row-filters / per-user grants; use `get_w()` for tools that read shared reference data.

## `pyproject.toml` + `requirements.txt`

```toml
# pyproject.toml
[project]
name = "my-custom-mcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.27",
    "mcp[cli]>=1.14.0",
    "fastmcp>=2.12",
    "databricks-sdk>=0.40",
    "psycopg[binary]>=3.2",
    "pyyaml>=6.0",
]

[project.scripts]
custom-mcp-server = "server.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["server"]
```

Pin `mcp >= 1.14.0` — older versions don't implement the streamable-HTTP transport that Supervisor Agents expect.

## Local testing

```bash
# Run the server locally on :8000
uv run uvicorn server.app:http_app --host 0.0.0.0 --port 8000

# In another terminal, hit it with the SDK
uv run python -c "
from databricks_mcp import DatabricksMCPClient
from databricks.sdk import WorkspaceClient
c = DatabricksMCPClient(server_url='http://localhost:8000/mcp',
                        workspace_client=WorkspaceClient(profile='dev'))
print(c.list_tools())
print(c.call_tool('query_lakebase_orders', {'customer_id': 'CUST_001'}))
"
```

If `list_tools()` returns your tool names with full schemas — the protocol layer is right. Move on to [2-deploy-as-databricks-app.md](2-deploy-as-databricks-app.md).
