"""SQL tool timeout ceiling patch.

Raises the FastMCP wall-clock tool-call timeout (the ``@mcp.tool(timeout=...)``
ceiling) on the SQL execution tools so legitimately long-running analytical
queries are not killed at the upstream default of 60s.

Why this exists
---------------
Upstream registers ``execute_sql`` and ``execute_sql_multi`` with a 60s FastMCP
tool-call timeout (see ``databricks-mcp-server/.../tools/sql.py``).  That ceiling
is the wall-clock limit on the *entire* tool call, and it **caps** the inner
per-call ``timeout`` argument: even if a caller passes ``timeout=300``, the call
is aborted at 60s.

60s is too low for analytical workloads — many well-formed queries (multi-table
joins, window functions over large fact tables) legitimately run longer.  When
the ceiling trips, the tool call is abandoned but the statement may keep running
on the warehouse, so a too-low ceiling also produces orphaned queries.

This patch raises only the *ceiling*.  It deliberately leaves untouched:
  - upstream's low per-call default (``timeout: int = 180``), and
  - the per-call ``timeout`` parameter already exposed on both tools.

The result is a "high ceiling, low default, per-call knob" policy:

  - everyday default stays short (180s)  -> fast feedback; mistakes fail fast
  - hard ceiling is generous (600s)      -> long queries can complete
  - per-call ``timeout`` is the knob     -> heavy queries opt into more,
    bounded by the ceiling

This is strictly safer than raising the everyday *default* globally: a runaway
or malformed query still fails quickly unless a caller has explicitly opted it
into a longer run, and even then the blast radius is bounded by the ceiling.

Patching strategy
-----------------
FastMCP ``Tool`` objects expose a mutable ``timeout`` attribute.  After the
upstream server module is imported (tools registered) we look up the SQL tools
on the FastMCP instance and raise their ``.timeout``.  Must run after the server
import and before ``mcp.run()`` — same lifecycle slot as the tool allowlist
patch.  Idempotent.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Wall-clock ceiling (seconds) for SQL tool calls.  This is the hard upper
# bound; it caps the per-call ``timeout`` argument and does NOT change the
# per-call default.
SQL_TOOL_TIMEOUT_CEILING = 600

# Tools whose ceiling we raise.
_SQL_TOOLS = ("execute_sql", "execute_sql_multi")


def apply_sql_timeout_ceiling(mcp, ceiling: int = SQL_TOOL_TIMEOUT_CEILING) -> None:
    """Raise the FastMCP tool-call timeout ceiling on the SQL tools.

    Must be called AFTER importing the upstream server module (which registers
    all tools) and BEFORE ``mcp.run()``.

    Args:
        mcp: The FastMCP server instance (from databricks_mcp_server.server).
        ceiling: New wall-clock ceiling in seconds.  Defaults to
            ``SQL_TOOL_TIMEOUT_CEILING``.
    """
    provider = mcp._local_provider
    tools = {t.name: t for t in asyncio.run(provider.list_tools())}

    raised, missing = [], []
    for name in _SQL_TOOLS:
        tool = tools.get(name)
        if tool is None:
            missing.append(name)
            continue
        old = tool.timeout
        tool.timeout = ceiling
        raised.append((name, old))

    for name, old in raised:
        logger.info(
            "SQL tool '%s' timeout ceiling raised: %ss -> %ss",
            name,
            old,
            ceiling,
        )
    if missing:
        # Non-fatal: the version pin (check_upstream_version) is the hard gate
        # for upstream drift.  If a SQL tool is renamed upstream we log loudly
        # rather than block startup, since the server is still usable.
        logger.warning(
            "SQL timeout patch: expected tool(s) not found, left unchanged: %s. "
            "Upstream may have renamed them — review this patch.",
            ", ".join(missing),
        )
