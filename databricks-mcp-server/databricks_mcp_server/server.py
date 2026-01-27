"""
Databricks MCP Server

A FastMCP server that exposes Databricks operations as MCP tools.
Simply wraps functions from databricks-tools-core.
"""
from fastmcp import FastMCP

# Create the server
mcp = FastMCP("Databricks MCP Server")

# Import and register all tools
from .tools import sql, compute, file, pipelines, jobs, agent_bricks, aibi_dashboards
