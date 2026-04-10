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
# MCP tool visibility — hide tools whose scopes are unavailable
# ---------------------------------------------------------------------------

# Tools to remove because the required Databricks Apps OAuth scopes don't
# exist yet.  When Databricks adds a scope, move the tool out of this set.
_HIDDEN_TOOLS: dict[str, str] = {
    # scope: clusters
    "list_compute":          "clusters",
    "manage_cluster":        "clusters",
    # scope: jobs
    "manage_jobs":           "jobs",
    "manage_job_runs":       "jobs",
    # scope: pipelines
    "manage_pipeline":       "pipelines",
    "manage_pipeline_run":   "pipelines",
    # scope: workspace
    "manage_workspace":      "workspace",
    "manage_workspace_files": "workspace",
    # scope: apps
    "manage_app":            "apps",
}


def _hide_unsupported_tools() -> None:
    """Remove tools that will always fail due to missing OAuth scopes."""
    loop = asyncio.new_event_loop()
    try:
        removed = []
        for name in _HIDDEN_TOOLS:
            try:
                loop.run_until_complete(mcp.remove_tool(name))
                removed.append(name)
            except Exception:
                pass  # tool may not exist (upstream changes)
    finally:
        loop.close()
    if removed:
        logger.info("Removed %d tools (missing scopes): %s",
                     len(removed), ", ".join(sorted(removed)))


_hide_unsupported_tools()


# ---------------------------------------------------------------------------
# MCP tool annotations — categorise tools for client UIs (Claude, etc.)
# ---------------------------------------------------------------------------

# Tools that only read data and never modify state.
_READ_ONLY_TOOLS = {
    "ask_genie",
    "get_current_user",
    "get_table_stats_and_schema",
    "get_volume_folder_details",
    "list_tracked_resources",
    "manage_warehouse",        # list / get_best only
    "query_vs_index",
}

# Tools that can permanently delete or irreversibly modify resources.
_DESTRUCTIVE_TOOLS = {
    "delete_tracked_resource",
    "manage_genie",            # has delete action
    "manage_dashboard",        # has delete action
    "manage_ka",               # has delete action
    "manage_lakebase_branch",  # has delete action
    "manage_lakebase_database",# has delete action
    "manage_lakebase_sync",    # has delete action
    "manage_mas",              # has delete action
    "manage_sql_warehouse",    # has delete action
    "manage_uc_connections",   # has delete action
    "manage_uc_objects",       # has delete (catalog/schema/volume)
    "manage_uc_sharing",       # has delete action
    "manage_uc_storage",       # has delete action
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
