"""Databricks MCP App — streamable HTTP wrapper for Databricks Apps deployment.

Wraps the existing databricks-mcp-server with on-behalf-of-user OAuth so
that each MCP request executes under the calling user's Databricks identity.
"""

import asyncio
import logging
import os

from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from databricks_mcp_server.server import mcp
from databricks_tools_core.auth import clear_databricks_auth, set_databricks_auth

logger = logging.getLogger(__name__)


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
# MCP tool allowlist — expose only the tools we need
# ---------------------------------------------------------------------------

# Only these tools are exposed to MCP clients.  Everything else registered
# by the upstream databricks-mcp-server is removed at startup.
_ALLOWED_TOOLS = {
    # SQL
    "execute_sql",
    "execute_sql_multi",
    "manage_warehouse",
    "manage_sql_warehouse",
    "get_table_stats_and_schema",
    "get_volume_folder_details",
    # Genie
    "ask_genie",
    "manage_genie",
    # AI/BI Dashboards
    "manage_dashboard",
    # Vector Search
    "manage_vs_endpoint",
    "manage_vs_index",
    "query_vs_index",
    "manage_vs_data",
    # Volume files
    "manage_volume_files",
    # User
    "get_current_user",
}


def _restrict_tools() -> None:
    """Remove every tool not in the allowlist."""
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(mcp.list_tools())
        removed = []
        for tool in tools:
            if tool.name not in _ALLOWED_TOOLS:
                loop.run_until_complete(mcp.remove_tool(tool.name))
                removed.append(tool.name)
    finally:
        loop.close()
    logger.info("Kept %d tools, removed %d: %s",
                len(_ALLOWED_TOOLS), len(removed), ", ".join(sorted(removed)))


_restrict_tools()


# ---------------------------------------------------------------------------
# MCP tool annotations — categorise tools for client UIs (Claude, etc.)
# ---------------------------------------------------------------------------

# Tools that only read data and never modify state.
_READ_ONLY_TOOLS = {
    "ask_genie",
    "get_current_user",
    "get_table_stats_and_schema",
    "get_volume_folder_details",
    "manage_warehouse",        # list / get_best only
    "query_vs_index",
}

# Tools that can permanently delete or irreversibly modify resources.
_DESTRUCTIVE_TOOLS = {
    "manage_genie",            # has delete action
    "manage_dashboard",        # has delete action
    "manage_sql_warehouse",    # has delete action
    "manage_vs_endpoint",      # has delete action
    "manage_vs_index",         # has delete action
    "manage_vs_data",          # has delete action
}


def _annotate_tools() -> None:
    """Set MCP tool annotations so client UIs can categorise tools.

    ``list_tools()`` returns ``FunctionTool`` objects whose ``annotations``
    attribute is a mutable reference — changes persist in the FastMCP
    registry and are reflected in subsequent ``tools/list`` responses.
    """
    loop = asyncio.new_event_loop()
    try:
        tools = loop.run_until_complete(mcp.list_tools())
        for tool in tools:
            if tool.name in _READ_ONLY_TOOLS:
                tool.annotations = ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    openWorldHint=True,
                )
            elif tool.name in _DESTRUCTIVE_TOOLS:
                tool.annotations = ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=True,
                    openWorldHint=True,
                )
            else:
                # Write tools that aren't destructive (create/update/execute)
                tool.annotations = ToolAnnotations(
                    readOnlyHint=False,
                    destructiveHint=False,
                    openWorldHint=True,
                )
    finally:
        loop.close()

    logger.info(
        "Annotated %d tools (%d read-only, %d destructive, %d write)",
        len(tools),
        len(_READ_ONLY_TOOLS),
        len(_DESTRUCTIVE_TOOLS),
        len(tools) - len(_READ_ONLY_TOOLS) - len(_DESTRUCTIVE_TOOLS),
    )


_annotate_tools()


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
