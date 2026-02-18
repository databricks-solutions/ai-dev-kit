"""
Databricks MCP Server

A FastMCP server that exposes Databricks operations as MCP tools.
Simply wraps functions from databricks-tools-core.
"""

import asyncio
import functools
import inspect
import sys

from fastmcp import FastMCP

from .middleware import TimeoutHandlingMiddleware

# Create the server
mcp = FastMCP("Databricks MCP Server")

# Register middleware (see middleware.py for details on each)
mcp.add_middleware(TimeoutHandlingMiddleware())


def _patch_tool_decorator_for_windows():
    """Wrap sync tool functions in asyncio.to_thread() on Windows.

    FastMCP's FunctionTool.run() calls sync functions directly on the asyncio
    event loop thread, which blocks the stdio transport's I/O tasks. On Windows
    (ProactorEventLoop), this causes a deadlock — all MCP tools hang indefinitely.

    This patch intercepts @mcp.tool registration to wrap sync functions so they
    run in a thread pool, yielding control back to the event loop for I/O.

    See: https://github.com/modelcontextprotocol/python-sdk/issues/671
    """
    original_tool = mcp.tool

    @functools.wraps(original_tool)
    def patched_tool(fn=None, *args, **kwargs):
        # Handle @mcp.tool("name") — returns a decorator
        if fn is None or isinstance(fn, str):
            decorator = original_tool(fn, *args, **kwargs)

            @functools.wraps(decorator)
            def wrapper(func):
                if not inspect.iscoroutinefunction(func):
                    func = _wrap_sync_in_thread(func)
                return decorator(func)

            return wrapper

        # Handle @mcp.tool (bare decorator, fn is the function)
        if not inspect.iscoroutinefunction(fn):
            fn = _wrap_sync_in_thread(fn)
        return original_tool(fn, *args, **kwargs)

    mcp.tool = patched_tool


def _wrap_sync_in_thread(fn):
    """Wrap a sync function to run in asyncio.to_thread(), preserving metadata."""

    @functools.wraps(fn)
    async def async_wrapper(**kwargs):
        return await asyncio.to_thread(fn, **kwargs)

    return async_wrapper


if sys.platform == "win32":
    _patch_tool_decorator_for_windows()

# Import and register all tools (side-effect imports: each module registers @mcp.tool decorators)
from .tools import (  # noqa: F401, E402
    sql,
    compute,
    file,
    pipelines,
    jobs,
    agent_bricks,
    aibi_dashboards,
    serving,
    unity_catalog,
    volume_files,
    genie,
    manifest,
    vector_search,
    lakebase,
    user,
    apps,
)
