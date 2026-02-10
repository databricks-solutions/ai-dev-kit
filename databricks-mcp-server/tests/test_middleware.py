"""Tests for the TimeoutHandlingMiddleware."""

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
async def test_timeout_returns_structured_result(middleware):
    """TimeoutError is caught and converted to a structured JSON result."""
    call_next = AsyncMock(side_effect=TimeoutError("Run did not complete within 3600 seconds"))
    ctx = _make_context(
        tool_name="wait_for_run",
        arguments={"run_id": 42, "timeout": 3600},
    )

    result = await middleware.on_call_tool(ctx, call_next)

    # Should return a ToolResult, not raise
    assert result is not None
    assert len(result.content) == 1

    payload = json.loads(result.content[0].text)
    assert payload["timed_out"] is True
    assert payload["tool"] == "wait_for_run"
    assert payload["arguments"] == {"run_id": 42, "timeout": 3600}
    assert "3600 seconds" in payload["message"]
    assert "Do NOT retry" in payload["action_required"]


@pytest.mark.asyncio
async def test_non_timeout_exceptions_propagate(middleware):
    """Non-timeout exceptions are NOT caught — they propagate normally."""
    call_next = AsyncMock(side_effect=ValueError("bad input"))
    ctx = _make_context()

    with pytest.raises(ValueError, match="bad input"):
        await middleware.on_call_tool(ctx, call_next)


@pytest.mark.asyncio
async def test_timeout_preserves_arguments(middleware):
    """The structured result includes the original arguments for debugging."""
    call_next = AsyncMock(side_effect=TimeoutError("timed out"))
    args = {"pipeline_id": "abc-123", "update_id": "upd-456", "timeout": 1800}
    ctx = _make_context(
        tool_name="wait_for_pipeline_update",
        arguments=args,
    )

    result = await middleware.on_call_tool(ctx, call_next)
    payload = json.loads(result.content[0].text)

    assert payload["arguments"] == args
    assert payload["tool"] == "wait_for_pipeline_update"
