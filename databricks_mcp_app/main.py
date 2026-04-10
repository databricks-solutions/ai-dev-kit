"""Databricks MCP App — streamable HTTP wrapper for Databricks Apps deployment.

Wraps the existing databricks-mcp-server with on-behalf-of-user OAuth so
that each MCP request executes under the calling user's Databricks identity.
"""

import os

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from databricks_mcp_server.server import mcp
from databricks_tools_core.auth import clear_databricks_auth, set_databricks_auth


# ---------------------------------------------------------------------------
# ASGI middleware — captures the per-user token from the Databricks Apps proxy
# ---------------------------------------------------------------------------


class OnBehalfOfUserMiddleware:
    """Extract ``x-forwarded-access-token`` and set per-request auth context.

    When running behind the Databricks Apps proxy, every request includes the
    calling user's OAuth token in the ``x-forwarded-access-token`` header.
    This middleware feeds it into :func:`set_databricks_auth` so that all
    downstream ``get_workspace_client()`` calls return a client scoped to
    that user.

    ``force_token=True`` ensures the user token takes priority over the
    service principal's OAuth M2M credentials injected by the Databricks
    Apps runtime.

    For local development (no header present), auth falls through to the
    default SDK chain (env vars / config file).
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        token = headers.get(b"x-forwarded-access-token", b"").decode()
        if token:
            host = os.environ.get("DATABRICKS_HOST", "")
            set_databricks_auth(host, token, force_token=True)
        try:
            await self.app(scope, receive, send)
        finally:
            clear_databricks_auth()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "name": "databricks-mcp-app"})


# ---------------------------------------------------------------------------
# Application assembly
# ---------------------------------------------------------------------------

# Build the streamable-HTTP Starlette app from the MCP server.
# All tools are already registered via side-effect imports in server.py.
# The returned app already includes FastMCP's middleware and lifespan.
mcp_app = mcp.http_app(path="/mcp", transport="streamable-http")

# Add our health check route to the existing MCP app.
mcp_app.routes.insert(0, Route("/", health, methods=["GET"]))

# Wrap with auth middleware (outermost layer).
app = OnBehalfOfUserMiddleware(mcp_app)
