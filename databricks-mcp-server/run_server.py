#!/usr/bin/env python
"""Run the Databricks MCP Server."""

import logging
import os
import sys

if os.environ.get("DATABRICKS_MCP_DEBUG"):
    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

from databricks_mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
