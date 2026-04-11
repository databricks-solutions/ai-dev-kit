"""Databricks MCP App — streamable HTTP wrapper for Databricks Apps deployment.

Wraps the existing databricks-mcp-server as a streamable-HTTP endpoint.
Authentication uses the app's service principal (OAuth M2M) credentials,
which the Databricks SDK refreshes automatically.
"""

import logging

from mcp.types import ToolAnnotations
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from databricks_mcp_server.server import mcp

logger = logging.getLogger(__name__)


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
    # Vector Search
    "query_vs_index",
    "manage_vs_data",
    "manage_vs_index",
}


# ---------------------------------------------------------------------------
# MCP tool annotations — categorise tools for client UIs (Claude, etc.)
# ---------------------------------------------------------------------------

# Tools that only read data and never modify state.
_READ_ONLY_TOOLS = {
    "query_vs_index",
}

# Tools that can permanently delete or irreversibly modify resources.
_DESTRUCTIVE_TOOLS = {
    "manage_vs_index",         # has delete action
    "manage_vs_data",          # has delete action
}


def _configure_tools() -> None:
    """Restrict the tool surface to the allowlist and set annotations.

    1. Remove every tool not in ``_ALLOWED_TOOLS``.
    2. Annotate the remaining tools with ``readOnlyHint`` /
       ``destructiveHint`` so MCP clients can categorise them.

    Uses ``mcp.local_provider`` (public) to access the tool registry
    synchronously so this works at module-load time even when an asyncio
    event loop is already running.  ``_components`` is an internal dict
    keyed by component key — the only sync path to enumerate tools in
    FastMCP 3.1.  If a future FastMCP version exposes a sync listing
    method, prefer that instead.
    """
    from fastmcp.tools.tool import Tool as FunctionTool

    provider = mcp.local_provider

    # --- Phase 1: restrict to allowlist ---
    # De-duplicate names to avoid double-removal if multiple versions exist.
    to_remove = {
        v.name for v in provider._components.values()
        if isinstance(v, FunctionTool) and v.name not in _ALLOWED_TOOLS
    }
    for name in to_remove:
        provider.remove_tool(name)

    # --- Phase 2: annotate remaining tools ---
    remaining = [
        v for v in provider._components.values()
        if isinstance(v, FunctionTool)
    ]
    n_read = n_destructive = n_write = 0
    for tool in remaining:
        if tool.name in _READ_ONLY_TOOLS:
            tool.annotations = ToolAnnotations(
                readOnlyHint=True,
                destructiveHint=False,
                openWorldHint=True,
            )
            n_read += 1
        elif tool.name in _DESTRUCTIVE_TOOLS:
            tool.annotations = ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=True,
                openWorldHint=True,
            )
            n_destructive += 1
        else:
            tool.annotations = ToolAnnotations(
                readOnlyHint=False,
                destructiveHint=False,
                openWorldHint=True,
            )
            n_write += 1

    logger.info(
        "Kept %d tools (%d read-only, %d destructive, %d write), removed %d",
        len(remaining), n_read, n_destructive, n_write, len(to_remove),
    )


_configure_tools()


# ---------------------------------------------------------------------------
# Application assembly
# ---------------------------------------------------------------------------

# Build the streamable-HTTP Starlette app from the MCP server.
# All tools are already registered via side-effect imports in server.py.
# The returned app already includes FastMCP's middleware and lifespan.
mcp_app = mcp.http_app(path="/mcp", transport="streamable-http")

# Add our health check route to the existing MCP app.
mcp_app.routes.insert(0, Route("/", health, methods=["GET"]))

app = mcp_app
