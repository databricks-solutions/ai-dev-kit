"""Tests for the TimeoutHandlingMiddleware."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from fastmcp.exceptions import ToolError

from databricks_mcp_server.middleware import TimeoutHandlingMiddleware


@pytest.fixture
def middleware():
    return TimeoutHandlingMiddleware()


def _make_context(tool_name="test_tool", arguments=None):
    """Build a minimal MiddlewareContext mock for on_call_tool."""
    ctx = MagicMock()
    ctx.message.name = tool_name
    ctx.message.arguments = arguments or {}
    return ctx


@pytest.mark.asyncio
async def test_normal_call_passes_through(middleware):
    """Tool results pass through unchanged when no error occurs."""
    expected = MagicMock()
    call_next = AsyncMock(return_value=expected)
    ctx = _make_context()

    result = await middleware.on_call_tool(ctx, call_next)

    assert result is expected
    call_next.assert_awaited_once_with(ctx)


@pytest.mark.asyncio
async def test_timeout_error_raises_tool_error(middleware):
    """TimeoutError is caught and re-raised as ToolError with structured JSON."""
    call_next = AsyncMock(side_effect=TimeoutError("Run did not complete within 3600 seconds"))
    ctx = _make_context(tool_name="wait_for_run")

    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(ctx, call_next)

    payload = json.loads(str(exc_info.value))
    assert payload["error"] is True
    assert payload["error_type"] == "timeout"
    assert payload["tool"] == "wait_for_run"
    assert "3600 seconds" in payload["message"]
    assert "Do NOT retry" in payload["action_required"]


@pytest.mark.asyncio
async def test_asyncio_timeout_error_raises_tool_error(middleware):
    """asyncio.TimeoutError is caught and re-raised as ToolError with structured JSON."""
    call_next = AsyncMock(side_effect=asyncio.TimeoutError())
    ctx = _make_context(tool_name="long_running_tool")

    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(ctx, call_next)

    payload = json.loads(str(exc_info.value))
    assert payload["error"] is True
    assert payload["error_type"] == "timeout"
    assert payload["tool"] == "long_running_tool"


@pytest.mark.asyncio
async def test_cancelled_error_is_reraised(middleware):
    """asyncio.CancelledError is re-raised to let MCP SDK handle cleanup."""
    call_next = AsyncMock(side_effect=asyncio.CancelledError())
    ctx = _make_context(tool_name="cancelled_tool")

    with pytest.raises(asyncio.CancelledError):
        await middleware.on_call_tool(ctx, call_next)


@pytest.mark.asyncio
async def test_generic_exception_raises_tool_error(middleware):
    """Generic exceptions are caught and re-raised as ToolError with structured JSON."""
    call_next = AsyncMock(side_effect=ValueError("bad input"))
    ctx = _make_context(tool_name="failing_tool")

    with pytest.raises(ToolError) as exc_info:
        await middleware.on_call_tool(ctx, call_next)

    payload = json.loads(str(exc_info.value))
    assert payload["error"] is True
    assert payload["error_type"] == "ValueError"
    assert payload["tool"] == "failing_tool"
    assert "bad input" in payload["message"]
