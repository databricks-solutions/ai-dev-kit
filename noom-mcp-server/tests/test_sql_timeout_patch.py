"""Unit tests for customization.sql_timeout_patch.

These build a throwaway FastMCP instance with stand-in tools named like the
upstream SQL tools, so no live workspace, server import, or OAuth is needed.
"""

import asyncio

from fastmcp import FastMCP

from customization.sql_timeout_patch import (
    SQL_TOOL_TIMEOUT_CEILING,
    apply_sql_timeout_ceiling,
)


def _build_mcp_with_sql_tools(timeout=60):
    """FastMCP with execute_sql / execute_sql_multi registered at `timeout`."""
    mcp = FastMCP("test")

    @mcp.tool(timeout=timeout)
    def execute_sql(sql_query: str = "") -> str:
        return sql_query

    @mcp.tool(timeout=timeout)
    def execute_sql_multi(sql_content: str = "") -> str:
        return sql_content

    return mcp


def _timeouts(mcp):
    provider = mcp._local_provider
    return {t.name: t.timeout for t in asyncio.run(provider.list_tools())}


class TestApplySqlTimeoutCeiling:
    def test_raises_ceiling_on_both_sql_tools(self):
        mcp = _build_mcp_with_sql_tools(timeout=60)
        apply_sql_timeout_ceiling(mcp)

        timeouts = _timeouts(mcp)
        assert timeouts["execute_sql"] == SQL_TOOL_TIMEOUT_CEILING
        assert timeouts["execute_sql_multi"] == SQL_TOOL_TIMEOUT_CEILING

    def test_default_ceiling_is_600(self):
        assert SQL_TOOL_TIMEOUT_CEILING == 600

    def test_respects_explicit_ceiling_argument(self):
        mcp = _build_mcp_with_sql_tools(timeout=60)
        apply_sql_timeout_ceiling(mcp, ceiling=420)

        assert _timeouts(mcp)["execute_sql"] == 420

    def test_does_not_touch_other_tools(self):
        mcp = _build_mcp_with_sql_tools(timeout=60)

        @mcp.tool(timeout=30)
        def manage_warehouse(action: str = "list") -> str:
            return action

        apply_sql_timeout_ceiling(mcp)

        assert _timeouts(mcp)["manage_warehouse"] == 30

    def test_idempotent(self):
        mcp = _build_mcp_with_sql_tools(timeout=60)
        apply_sql_timeout_ceiling(mcp)
        apply_sql_timeout_ceiling(mcp)

        assert _timeouts(mcp)["execute_sql"] == SQL_TOOL_TIMEOUT_CEILING

    def test_missing_tool_is_non_fatal_and_warns(self, caplog):
        """If a SQL tool isn't registered, patch logs a warning, doesn't raise."""
        mcp = FastMCP("test")

        @mcp.tool(timeout=60)
        def execute_sql(sql_query: str = "") -> str:
            return sql_query

        # execute_sql_multi is absent on purpose.
        with caplog.at_level("WARNING"):
            apply_sql_timeout_ceiling(mcp)

        assert _timeouts(mcp)["execute_sql"] == SQL_TOOL_TIMEOUT_CEILING
        assert "execute_sql_multi" in caplog.text
