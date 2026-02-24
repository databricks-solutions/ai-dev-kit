"""Vector Search tools - Manage endpoints, indexes, and query vector data.

Provides 8 workflow-oriented tools following the Lakebase pattern:
- create_or_update for idempotent resource management
- get doubling as list when no name/id provided
- explicit delete
- query as hot-path, manage_vs_data for maintenance ops (upsert/delete/scan/sync)
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union

from databricks_tools_core.vector_search import (
    create_vs_endpoint as _create_vs_endpoint,
    get_vs_endpoint as _get_vs_endpoint,
    list_vs_endpoints as _list_vs_endpoints,
    delete_vs_endpoint as _delete_vs_endpoint,
    create_vs_index as _create_vs_index,
    get_vs_index as _get_vs_index,
    list_vs_indexes as _list_vs_indexes,
    delete_vs_index as _delete_vs_index,
    sync_vs_index as _sync_vs_index,
    query_vs_index as _query_vs_index,
    upsert_vs_data as _upsert_vs_data,
    delete_vs_data as _delete_vs_data,
    scan_vs_index as _scan_vs_index,
)

from ..server import mcp

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================


def _find_endpoint_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Find a vector search endpoint by name, returns None if not found."""
    try:
        result = _get_vs_endpoint(name=name)
        if result.get("state") == "NOT_FOUND":
            return None
        return result
    except Exception:
        return None


def _find_index_by_name(index_name: str) -> Optional[Dict[str, Any]]:
    """Find a vector search index by name, returns None if not found."""
    try:
        result = _get_vs_index(index_name=index_name)
        if result.get("state") == "NOT_FOUND":
            return None
        return result
    except Exception:
        return None


# ============================================================================
# Tool 1: create_or_update_vs_endpoint
# ============================================================================


@mcp.tool
def create_or_update_vs_endpoint(
    name: str,
    endpoint_type: str = "STANDARD",
) -> Dict[str, Any]:
    """
    Idempotent create for Vector Search endpoints. Returns existing if one
    with the same name already exists (endpoints are immutable after creation).

    Endpoints are compute resources that host vector search indexes.
    Creation is asynchronous -- use get_vs_endpoint() to check status.

    Args:
        name: Endpoint name (unique within workspace)
        endpoint_type: "STANDARD" (low-latency, <100ms) or
            "STORAGE_OPTIMIZED" (cost-effective, ~250ms, supports 1B+ vectors)

    Returns:
        Dictionary with endpoint details and whether it was created or already existed.

    Example:
        >>> create_or_update_vs_endpoint("my-endpoint", "STORAGE_OPTIMIZED")
        {"name": "my-endpoint", "endpoint_type": "STORAGE_OPTIMIZED", "created": True}
    """
    existing = _find_endpoint_by_name(name)
    if existing:
        return {**existing, "created": False}

    result = _create_vs_endpoint(name=name, endpoint_type=endpoint_type)
    return {**result, "created": True}


# ============================================================================
# Tool 2: get_vs_endpoint
# ============================================================================


@mcp.tool
def get_vs_endpoint(
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get Vector Search endpoint details, or list all endpoints.

    Pass a name to get one endpoint's details. Omit name to list all endpoints.

    Args:
        name: Endpoint name. If omitted, lists all endpoints.

    Returns:
        Single endpoint dict (if name provided) or {"endpoints": [...]}.

    Example:
        >>> get_vs_endpoint("my-endpoint")
        {"name": "my-endpoint", "state": "ONLINE", "num_indexes": 3}
        >>> get_vs_endpoint()
        {"endpoints": [{"name": "my-endpoint", "state": "ONLINE", ...}]}
    """
    if name:
        return _get_vs_endpoint(name=name)

    return {"endpoints": _list_vs_endpoints()}


# ============================================================================
# Tool 3: delete_vs_endpoint
# ============================================================================


@mcp.tool
def delete_vs_endpoint(name: str) -> Dict[str, Any]:
    """
    Delete a Vector Search endpoint.

    All indexes on the endpoint must be deleted first.

    Args:
        name: Endpoint name to delete

    Returns:
        Dictionary with name and status ("deleted" or error info)

    Example:
        >>> delete_vs_endpoint("my-endpoint")
        {"name": "my-endpoint", "status": "deleted"}
    """
    return _delete_vs_endpoint(name=name)


# ============================================================================
# Tool 4: create_or_update_vs_index
# ============================================================================


@mcp.tool
def create_or_update_vs_index(
    name: str,
    endpoint_name: str,
    primary_key: str,
    index_type: str = "DELTA_SYNC",
    delta_sync_index_spec: Optional[Dict[str, Any]] = None,
    direct_access_index_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Idempotent create for Vector Search indexes. Returns existing if one
    with the same name already exists. Triggers an initial sync after
    creating a new DELTA_SYNC index.

    For DELTA_SYNC indexes (auto-sync from Delta table):
      - Managed embeddings: provide embedding_source_columns with model endpoint
      - Self-managed: provide embedding_vector_columns with pre-computed vectors

    For DIRECT_ACCESS indexes (manual CRUD):
      - Provide embedding_vector_columns and schema_json

    Args:
        name: Fully qualified index name (catalog.schema.index_name)
        endpoint_name: Vector Search endpoint to host this index
        primary_key: Column name for the primary key
        index_type: "DELTA_SYNC" or "DIRECT_ACCESS"
        delta_sync_index_spec: Config for Delta Sync index:
            - source_table: Fully qualified source table
            - embedding_source_columns: For managed embeddings
              [{"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}]
            - embedding_vector_columns: For self-managed embeddings
              [{"name": "embedding", "embedding_dimension": 768}]
            - pipeline_type: "TRIGGERED" or "CONTINUOUS"
            - columns_to_sync: Optional list of columns to include
        direct_access_index_spec: Config for Direct Access index:
            - embedding_vector_columns: [{"name": "embedding", "embedding_dimension": 768}]
            - schema_json: JSON schema string

    Returns:
        Dictionary with index details and whether it was created or already existed.

    Example:
        >>> create_or_update_vs_index(
        ...     name="catalog.schema.docs_index",
        ...     endpoint_name="my-endpoint",
        ...     primary_key="id",
        ...     delta_sync_index_spec={
        ...         "source_table": "catalog.schema.documents",
        ...         "embedding_source_columns": [
        ...             {"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}
        ...         ],
        ...         "pipeline_type": "TRIGGERED"
        ...     }
        ... )
    """
    existing = _find_index_by_name(name)
    if existing:
        return {**existing, "created": False}

    result = _create_vs_index(
        name=name,
        endpoint_name=endpoint_name,
        primary_key=primary_key,
        index_type=index_type,
        delta_sync_index_spec=delta_sync_index_spec,
        direct_access_index_spec=direct_access_index_spec,
    )

    # Trigger initial sync for DELTA_SYNC indexes
    if index_type == "DELTA_SYNC" and result.get("status") != "ALREADY_EXISTS":
        try:
            _sync_vs_index(index_name=name)
            result["sync_triggered"] = True
        except Exception as e:
            logger.warning("Failed to trigger initial sync for index '%s': %s", name, e)
            result["sync_triggered"] = False

    return {**result, "created": True}


# ============================================================================
# Tool 5: get_vs_index
# ============================================================================


@mcp.tool
def get_vs_index(
    index_name: Optional[str] = None,
    endpoint_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get Vector Search index details, or list indexes on an endpoint.

    Pass index_name to get one index's details. Pass endpoint_name to list
    all indexes on that endpoint. Omit both to list all endpoints (use
    the endpoint names to then list indexes).

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name).
            If provided, returns detailed index info.
        endpoint_name: Endpoint name. Lists all indexes on this endpoint.

    Returns:
        Single index dict, {"indexes": [...]}, or {"endpoints": [...]}.

    Example:
        >>> get_vs_index(index_name="catalog.schema.docs_index")
        {"name": "catalog.schema.docs_index", "state": "ONLINE", ...}
        >>> get_vs_index(endpoint_name="my-endpoint")
        {"indexes": [{"name": "catalog.schema.docs_index", ...}]}
        >>> get_vs_index()
        {"endpoints": [{"name": "my-endpoint", ...}], "hint": "Pass endpoint_name to list indexes"}
    """
    if index_name:
        return _get_vs_index(index_name=index_name)

    if endpoint_name:
        return {"indexes": _list_vs_indexes(endpoint_name=endpoint_name)}

    # No args: list endpoints so the caller knows which to drill into
    return {
        "endpoints": _list_vs_endpoints(),
        "hint": "Pass endpoint_name to list indexes on a specific endpoint, or index_name to get details.",
    }


# ============================================================================
# Tool 6: delete_vs_index
# ============================================================================


@mcp.tool
def delete_vs_index(index_name: str) -> Dict[str, Any]:
    """
    Delete a Vector Search index.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)

    Returns:
        Dictionary with name and status ("deleted" or error info)

    Example:
        >>> delete_vs_index("catalog.schema.docs_index")
        {"name": "catalog.schema.docs_index", "status": "deleted"}
    """
    return _delete_vs_index(index_name=index_name)


# ============================================================================
# Tool 7: query_vs_index
# ============================================================================


@mcp.tool
def query_vs_index(
    index_name: str,
    columns: List[str],
    query_text: Optional[str] = None,
    query_vector: Optional[List[float]] = None,
    num_results: int = 5,
    filters_json: Optional[Union[str, dict]] = None,
    filter_string: Optional[str] = None,
    query_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query a Vector Search index for similar documents.

    Provide either query_text (for indexes with embedding models) or
    query_vector (pre-computed embedding).

    For filters:
    - Standard endpoints: filters_json (dict format) e.g. '{"category": "ai"}'
    - Storage-Optimized endpoints: filter_string (SQL syntax) e.g. "category = 'ai'"

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        columns: Column names to return in results
        query_text: Text query (for managed/attached embeddings)
        query_vector: Pre-computed query embedding vector
        num_results: Number of results to return (default: 5)
        filters_json: JSON string filters for Standard endpoints
        filter_string: SQL-like filter for Storage-Optimized endpoints
        query_type: "ANN" (default) or "HYBRID" (vector + keyword search)

    Returns:
        Dictionary with:
        - columns: Column names in results
        - data: List of result rows (similarity score appended as last column)
        - num_results: Number of results returned

    Example:
        >>> query_vs_index(
        ...     index_name="catalog.schema.docs_index",
        ...     columns=["id", "content"],
        ...     query_text="What is machine learning?",
        ...     num_results=5
        ... )
        {"columns": ["id", "content", "score"], "data": [...], "num_results": 5}
    """
    # MCP deserializes JSON params, so filters_json may arrive as a dict
    if isinstance(filters_json, dict):
        filters_json = json.dumps(filters_json)

    return _query_vs_index(
        index_name=index_name,
        columns=columns,
        query_text=query_text,
        query_vector=query_vector,
        num_results=num_results,
        filters_json=filters_json,
        filter_string=filter_string,
        query_type=query_type,
    )


# ============================================================================
# Tool 8: manage_vs_data
# ============================================================================


@mcp.tool
def manage_vs_data(
    index_name: str,
    operation: str,
    inputs_json: Optional[Union[str, list]] = None,
    primary_keys: Optional[List[str]] = None,
    num_results: int = 100,
) -> Dict[str, Any]:
    """
    Manage data in a Vector Search index: upsert, delete, scan, or sync.

    Required parameters per operation:
    - "upsert": inputs_json (JSON string of records with primary key + embedding columns)
    - "delete": primary_keys (list of primary key values to remove)
    - "scan": num_results (optional, defaults to 100)
    - "sync": no extra params (triggers re-sync for TRIGGERED pipeline DELTA_SYNC indexes)

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        operation: One of "upsert", "delete", "scan", or "sync"
        inputs_json: Records to upsert. REQUIRED for "upsert", ignored otherwise.
            Example: '[{"id": "1", "text": "hello", "embedding": [0.1, 0.2, ...]}]'
        primary_keys: Primary key values to delete. REQUIRED for "delete", ignored otherwise.
        num_results: Maximum entries to return for "scan" (default: 100)

    Returns:
        Dictionary with operation results.

    Example:
        >>> manage_vs_data("catalog.schema.idx", "upsert",
        ...     inputs_json='[{"id": "1", "text": "hello", "embedding": [0.1]}]')
        {"name": "catalog.schema.idx", "status": "SUCCESS", "num_records": 1}
        >>> manage_vs_data("catalog.schema.idx", "delete", primary_keys=["1", "2"])
        {"name": "catalog.schema.idx", "status": "SUCCESS", "num_deleted": 2}
        >>> manage_vs_data("catalog.schema.idx", "scan", num_results=10)
        {"columns": [...], "data": [...], "num_results": 10}
        >>> manage_vs_data("catalog.schema.idx", "sync")
        {"index_name": "catalog.schema.idx", "status": "sync_triggered"}
    """
    op = operation.lower()

    if op == "upsert":
        if inputs_json is None:
            return {"error": "inputs_json is required for upsert operation."}
        # MCP deserializes JSON params, so inputs_json may arrive as a list
        if isinstance(inputs_json, (dict, list)):
            inputs_json = json.dumps(inputs_json)
        return _upsert_vs_data(index_name=index_name, inputs_json=inputs_json)

    elif op == "delete":
        if primary_keys is None:
            return {"error": "primary_keys is required for delete operation."}
        return _delete_vs_data(index_name=index_name, primary_keys=primary_keys)

    elif op == "scan":
        return _scan_vs_index(index_name=index_name, num_results=num_results)

    elif op == "sync":
        _sync_vs_index(index_name=index_name)
        return {"index_name": index_name, "status": "sync_triggered"}

    else:
        return {"error": f"Invalid operation '{operation}'. Use 'upsert', 'delete', 'scan', or 'sync'."}
