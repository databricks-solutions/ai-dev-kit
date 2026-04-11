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


def _configure_tools() -> None:
    """Restrict the tool surface to the allowlist and mark all as read-only.

    The app's service principal is granted only "Can select" on specific
    Vector Search indexes — the platform enforces read-only at the resource
    level.  All tools are annotated ``readOnlyHint=True`` so MCP clients
    don't add unnecessary confirmation prompts.

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
    to_remove = {
        v.name for v in provider._components.values()
        if isinstance(v, FunctionTool) and v.name not in _ALLOWED_TOOLS
    }
    for name in to_remove:
        provider.remove_tool(name)

    # --- Phase 2: annotate all remaining tools as read-only ---
    remaining = [
        v for v in provider._components.values()
        if isinstance(v, FunctionTool)
    ]
    for tool in remaining:
        tool.annotations = ToolAnnotations(
            readOnlyHint=True,
            destructiveHint=False,
            openWorldHint=True,
        )

    logger.info("Kept %d tools (all read-only), removed %d", len(remaining), len(to_remove))


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
