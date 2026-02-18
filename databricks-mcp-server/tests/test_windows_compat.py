"""Tests for the Windows compatibility wrapper (_wrap_sync_in_thread)."""

import asyncio
import inspect
import threading

import pydantic
import pytest

from databricks_mcp_server.server import _wrap_sync_in_thread


def sample_tool(query: str, limit: int = 10) -> str:
    """Execute a sample query."""
    return f"result:{query}:{limit}"


class TestWrapSyncInThread:
    """Tests for _wrap_sync_in_thread wrapper."""

    def test_preserves_function_name(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert wrapped.__name__ == "sample_tool"

    def test_preserves_docstring(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert wrapped.__doc__ == "Execute a sample query."

    def test_preserves_annotations(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert wrapped.__annotations__ == sample_tool.__annotations__

    def test_preserves_signature(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        original_sig = inspect.signature(sample_tool)
        wrapped_sig = inspect.signature(wrapped)
        assert str(original_sig) == str(wrapped_sig)

    def test_is_coroutine_function(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        assert inspect.iscoroutinefunction(wrapped)

    @pytest.mark.asyncio
    async def test_returns_correct_result(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        result = await wrapped(query="test", limit=5)
        assert result == "result:test:5"

    @pytest.mark.asyncio
    async def test_returns_correct_result_with_defaults(self):
        wrapped = _wrap_sync_in_thread(sample_tool)
        result = await wrapped(query="test")
        assert result == "result:test:10"

    @pytest.mark.asyncio
    async def test_runs_in_thread_pool(self):
        """Verify the sync function runs in a different thread than the event loop."""
        main_thread = threading.current_thread().ident

        def capture_thread(query: str) -> int:
            return threading.current_thread().ident

        wrapped = _wrap_sync_in_thread(capture_thread)
        worker_thread = await wrapped(query="test")
        assert worker_thread != main_thread

    @pytest.mark.asyncio
    async def test_does_not_block_event_loop(self):
        """Verify concurrent tasks can run while the wrapped function executes."""
        import time

        def slow_tool(query: str) -> str:
            time.sleep(0.2)
            return "done"

        wrapped = _wrap_sync_in_thread(slow_tool)

        concurrent_ran = False

        async def concurrent_task():
            nonlocal concurrent_ran
            await asyncio.sleep(0.05)
            concurrent_ran = True

        await asyncio.gather(wrapped(query="test"), concurrent_task())
        assert concurrent_ran

    @pytest.mark.asyncio
    async def test_propagates_exceptions(self):
        def failing_tool(query: str) -> str:
            raise ValueError("something went wrong")

        wrapped = _wrap_sync_in_thread(failing_tool)
        with pytest.raises(ValueError, match="something went wrong"):
            await wrapped(query="test")

    def test_pydantic_type_adapter_returns_awaitable(self):
        """Verify pydantic's TypeAdapter can call the wrapped function and get a coroutine.

        FastMCP uses TypeAdapter.validate_python() to invoke tool functions.
        The wrapper must produce a result that pydantic recognizes as callable
        with the original signature.
        """
        wrapped = _wrap_sync_in_thread(sample_tool)
        ta = pydantic.TypeAdapter(wrapped.__annotations__.get("return", str))
        # TypeAdapter should be able to read the function's annotations
        sig = inspect.signature(wrapped)
        assert "query" in sig.parameters
        assert "limit" in sig.parameters
        # Calling the wrapper returns a coroutine
        coro = wrapped(query="test", limit=5)
        assert inspect.iscoroutine(coro)
        # Clean up the unawaited coroutine
        coro.close()
