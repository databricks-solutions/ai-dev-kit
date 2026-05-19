"""Entry point for the Noom-governed Databricks MCP server.

Start with:
    uv run python run.py

Or via MCP client config:
    {
        "command": "uv",
        "args": ["run", "--directory", "/path/to/noom-mcp-server", "python", "run.py"]
    }

Required env vars (see .env.example):
    DATABRICKS_MCP_SQL_CLIENT_ID      — OAuth client ID for the SQL SP
    DATABRICKS_MCP_SQL_CLIENT_SECRET  — OAuth client secret for the SQL SP

Optional:
    DATABRICKS_MCP_SQL_HOST           — Override workspace host for SQL SP
                                        (defaults to calling user's workspace)
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("noom_mcp")

# ---------------------------------------------------------------------------
# Step 1: Apply governance patches BEFORE the upstream server imports tools.
#
# patch_sql_executor() patches SQLExecutor at the class level — it only needs
# the databricks-tools-core package to be importable, not the MCP server.
#
# check_pat_rejected() makes a live Databricks API call, so it requires valid
# workspace credentials to be configured in the environment.
# ---------------------------------------------------------------------------

from noom_mcp.patches import apply_all_patches  # noqa: E402

try:
    apply_all_patches()
except RuntimeError as exc:
    logger.error("Governance check failed — server will not start: %s", exc)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 2: Import the upstream MCP server.
#
# Importing this module creates the FastMCP instance and registers all tools
# (including execute_sql / execute_sql_multi) via @mcp.tool decorators.
# The SQLExecutor patches are already in place at this point.
# ---------------------------------------------------------------------------

from databricks_mcp_server.server import mcp  # noqa: E402

# ---------------------------------------------------------------------------
# Step 3: Run.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting Noom MCP server (governed Databricks MCP)")
    mcp.run()
