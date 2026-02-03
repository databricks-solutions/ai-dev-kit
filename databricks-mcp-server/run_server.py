#!/usr/bin/env python
"""Run the Databricks MCP Server."""

from databricks_mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
