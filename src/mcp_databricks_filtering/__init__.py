"""Tag-based table filtering for the Databricks MCP server."""

from mcp_databricks_filtering.config import FilterConfig
from mcp_databricks_filtering.table_filter import (
    TableTagFilter,
    get_table_filter,
    reset_singleton,
)

__all__ = [
    "FilterConfig",
    "TableTagFilter",
    "get_table_filter",
    "reset_singleton",
]

__version__ = "0.1.0"
