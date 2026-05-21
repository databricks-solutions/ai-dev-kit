"""Tool allowlist patch.

Removes any tool from the FastMCP server instance that is not on the
approved allowlist.  Called after the upstream server module is imported
(so all tools are registered) but before mcp.run() starts accepting
connections.

Full list of upstream tools (44 total):
  https://github.com/databricks-solutions/ai-dev-kit/blob/main/databricks-mcp-server/README.md#available-tools

Allowlist rationale
-------------------
Exactly the SQL Operations tools from the upstream README are exposed:
  https://github.com/databricks-solutions/ai-dev-kit/blob/main/databricks-mcp-server/README.md#sql-operations

  execute_sql             → execute_sql          (same name)
  execute_sql_multi       → execute_sql_multi    (same name)
  list_warehouses         → manage_warehouse     (merged in v0.1.12)
  get_best_warehouse      → manage_warehouse     (merged in v0.1.12)
  get_table_stats_and_schema → get_table_stats_and_schema (same name)

execute_sql, execute_sql_multi, and get_table_stats_and_schema all create
SQLExecutor internally, which our sql_executor_patch intercepts to enforce
SP credentials, warehouse override, and mcp_user query tagging.

manage_warehouse is read-only (list + get_best actions only) and runs under
the user's OAuth credentials.

All other tools (jobs, clusters, pipelines, dashboards, apps, Lakebase,
Vector Search, Genie, workspace files, UC write operations, grants, etc.)
are excluded because they either bypass the Service Principal, perform
write/delete/admin operations, or are out of scope for the SQL use case.
"""

import logging

logger = logging.getLogger(__name__)

# Tools that Noom engineers are allowed to use via this MCP server.
# Everything not on this list is removed at startup.
ALLOWED_TOOLS = frozenset(
    [
        # SQL execution — routed through the governed Service Principal,
        # forced to DATABRICKS_WAREHOUSE_ID, tagged with mcp_user:<email>
        "execute_sql",
        "execute_sql_multi",
        # Schema and statistics — uses SQLExecutor internally (SP-governed)
        "get_table_stats_and_schema",
        # Read-only warehouse listing (list + get_best) — user OAuth, no writes
        # Upstream README names: list_warehouses + get_best_warehouse (merged in v0.1.12)
        "manage_warehouse",
    ]
)


def apply_tool_allowlist(mcp) -> None:
    """Remove all tools not in ALLOWED_TOOLS from the FastMCP server instance.

    Must be called AFTER importing the upstream server module (which registers
    all tools) and BEFORE mcp.run().

    Args:
        mcp: The FastMCP server instance (from databricks_mcp_server.server).
    """
    import asyncio

    provider = mcp._local_provider
    registered = [t.name for t in asyncio.run(provider.list_tools())]
    removed, kept = [], []

    for name in registered:
        if name in ALLOWED_TOOLS:
            kept.append(name)
        else:
            provider.remove_tool(name)
            removed.append(name)

    logger.info(
        "Tool allowlist applied: %d kept, %d removed. Kept: %s",
        len(kept),
        len(removed),
        ", ".join(sorted(kept)),
    )
    if removed:
        logger.debug("Removed tools: %s", ", ".join(sorted(removed)))
