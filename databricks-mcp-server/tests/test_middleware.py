"""Tests for the TimeoutHandlingMiddleware."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

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
async def test_timeout_error_returns_structured_result(middleware):
    """TimeoutError is caught and converted to a structured JSON result."""
    call_next = AsyncMock(side_effect=TimeoutError("Run did not complete within 3600 seconds"))
    ctx = _make_context(tool_name="wait_for_run")

    result = await middleware.on_call_tool(ctx, call_next)

    assert result is not None
    assert len(result.content) == 1

    payload = json.loads(result.content[0].text)
    assert payload["error"] is True
    assert payload["error_type"] == "timeout"
    assert payload["tool"] == "wait_for_run"
    assert "3600 seconds" in payload["message"]
    assert "Do NOT retry" in payload["action_required"]


@pytest.mark.asyncio
async def test_asyncio_timeout_error_returns_structured_result(middleware):
    """asyncio.TimeoutError is caught and converted to a structured JSON result."""
    call_next = AsyncMock(side_effect=asyncio.TimeoutError())
    ctx = _make_context(tool_name="long_running_tool")

    result = await middleware.on_call_tool(ctx, call_next)

    assert result is not None
    payload = json.loads(result.content[0].text)
    assert payload["error"] is True
    assert payload["error_type"] == "timeout"
    assert payload["tool"] == "long_running_tool"


@pytest.mark.asyncio
async def test_cancelled_error_returns_structured_result(middleware):
    """asyncio.CancelledError is caught and converted to a structured JSON result."""
    call_next = AsyncMock(side_effect=asyncio.CancelledError())
    ctx = _make_context(tool_name="cancelled_tool")

    result = await middleware.on_call_tool(ctx, call_next)

    assert result is not None
    payload = json.loads(result.content[0].text)
    assert payload["error"] is True
    assert payload["error_type"] == "cancelled"
    assert payload["tool"] == "cancelled_tool"


@pytest.mark.asyncio
async def test_generic_exception_returns_structured_result(middleware):
    """Generic exceptions are caught and converted to structured JSON results."""
    call_next = AsyncMock(side_effect=ValueError("bad input"))
    ctx = _make_context(tool_name="failing_tool")

    result = await middleware.on_call_tool(ctx, call_next)

    # Should return a ToolResult, not raise
    assert result is not None
    payload = json.loads(result.content[0].text)
    assert payload["error"] is True
    assert payload["error_type"] == "ValueError"
    assert payload["tool"] == "failing_tool"
    assert "bad input" in payload["message"]
