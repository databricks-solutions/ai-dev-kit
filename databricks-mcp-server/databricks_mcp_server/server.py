"""
Databricks MCP Server

A FastMCP server that exposes Databricks operations as MCP tools.
Simply wraps functions from databricks-tools-core.
"""

import asyncio
import functools
import inspect
import subprocess
import sys
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .middleware import TimeoutHandlingMiddleware


# ---------------------------------------------------------------------------
# Windows fixes — must run BEFORE FastMCP init and tool registration
# ---------------------------------------------------------------------------


def _patch_subprocess_stdin():
    """Monkey-patch subprocess so stdin defaults to DEVNULL on Windows.

    When the MCP server runs in stdio mode, stdin IS the JSON-RPC pipe.
    Any subprocess call without explicit stdin lets child processes inherit
    this pipe handle. On Windows the Databricks SDK refreshes auth tokens
    via ``subprocess.run(["databricks", "auth", "token", ...], shell=True)``
    without setting stdin — the spawned ``databricks.exe`` blocks reading
    from the shared pipe, hanging every MCP tool call.

    Fix: default stdin to DEVNULL so child processes never touch the pipe.

    See: https://github.com/modelcontextprotocol/python-sdk/issues/671
    """
    _original_run = subprocess.run

    @functools.wraps(_original_run)
    def _patched_run(*args, **kwargs):
        kwargs.setdefault("stdin", subprocess.DEVNULL)
        return _original_run(*args, **kwargs)

    subprocess.run = _patched_run

    _OriginalPopen = subprocess.Popen

    class _PatchedPopen(_OriginalPopen):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("stdin", subprocess.DEVNULL)
            super().__init__(*args, **kwargs)

    subprocess.Popen = _PatchedPopen


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


# Apply subprocess patch early — before any Databricks SDK import
if sys.platform == "win32":
    _patch_subprocess_stdin()

# ---------------------------------------------------------------------------
# Server initialisation
# ---------------------------------------------------------------------------

# Disable FastMCP's built-in task worker on Windows.
# The docket worker uses fakeredis XREADGROUP BLOCK which deadlocks
# the ProactorEventLoop, preventing asyncio.to_thread() callbacks.
# Belt-and-suspenders: pass tasks=False AND override _docket_lifespan,
# because tasks=False alone does not prevent the worker from starting.
_fastmcp_kwargs = {}
if sys.platform == "win32":
    _fastmcp_kwargs["tasks"] = False

mcp = FastMCP("Databricks MCP Server", **_fastmcp_kwargs)

if sys.platform == "win32":

    @asynccontextmanager
    async def _noop_lifespan(*args, **kwargs):
        yield

    if hasattr(mcp, "_docket_lifespan"):
        mcp._docket_lifespan = _noop_lifespan

# Register middleware (see middleware.py for details on each)
mcp.add_middleware(TimeoutHandlingMiddleware())

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
    fgac_policies,
)
