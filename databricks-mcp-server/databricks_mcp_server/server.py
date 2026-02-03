"""
Databricks MCP Server

A FastMCP server that exposes Databricks operations as MCP tools.
Simply wraps functions from databricks-tools-core.
"""

from fastmcp import FastMCP

# Create the server
mcp = FastMCP("Databricks MCP Server")

# Import and register all tools (imports trigger @mcp.tool decorator registration)
from .tools import sql  # noqa: F401, E402
from .tools import compute  # noqa: F401, E402
from .tools import file  # noqa: F401, E402
from .tools import pipelines  # noqa: F401, E402
from .tools import jobs  # noqa: F401, E402
from .tools import agent_bricks  # noqa: F401, E402
from .tools import aibi_dashboards  # noqa: F401, E402
from .tools import serving  # noqa: F401, E402
from .tools import unity_catalog  # noqa: F401, E402
from .tools import volume_files  # noqa: F401, E402
from .tools import genie  # noqa: F401, E402
