"""
Vector Search Operations

Functions for managing Databricks Vector Search endpoints, indexes,
and performing similarity queries.
"""

from .endpoints import (
    create_vs_endpoint,
    get_vs_endpoint,
    list_vs_endpoints,
    delete_vs_endpoint,
)
from .indexes import (
    create_vs_index,
    get_vs_index,
    list_vs_indexes,
    delete_vs_index,
    sync_vs_index,
    query_vs_index,
    upsert_vs_data,
    delete_vs_data,
    scan_vs_index,
)

__all__ = [
    # Endpoints
    "create_vs_endpoint",
    "get_vs_endpoint",
    "list_vs_endpoints",
    "delete_vs_endpoint",
    # Indexes
    "create_vs_index",
    "get_vs_index",
    "list_vs_indexes",
    "delete_vs_index",
    "sync_vs_index",
    "query_vs_index",
    "upsert_vs_data",
    "delete_vs_data",
    "scan_vs_index",
]
