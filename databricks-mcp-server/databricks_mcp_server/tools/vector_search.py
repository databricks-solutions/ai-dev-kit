"""Vector Search tools - Manage endpoints, indexes, and query vector data."""

import json
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


# ============================================================================
# Endpoint Management Tools
# ============================================================================


@mcp.tool
def create_vs_endpoint(
    name: str,
    endpoint_type: str = "STANDARD",
) -> Dict[str, Any]:
    """
    Create a Vector Search endpoint.

    Endpoints are compute resources that host vector search indexes.
    Creation is asynchronous -- use get_vs_endpoint() to check status.

    Args:
        name: Endpoint name (unique within workspace)
        endpoint_type: "STANDARD" (low-latency, <100ms) or
            "STORAGE_OPTIMIZED" (cost-effective, ~250ms, supports 1B+ vectors)

    Returns:
        Dictionary with:
        - name: Endpoint name
        - endpoint_type: Type of endpoint
        - status: Creation status

    Example:
        >>> create_vs_endpoint("my-endpoint", "STORAGE_OPTIMIZED")
        {"name": "my-endpoint", "endpoint_type": "STORAGE_OPTIMIZED", "status": "CREATING"}
    """
    result = _create_vs_endpoint(name=name, endpoint_type=endpoint_type)

    try:
        from ..manifest import track_resource

        track_resource(
            resource_type="vs_endpoint",
            name=name,
            resource_id=name,
        )
    except Exception:
        pass  # best-effort tracking

    return result


@mcp.tool
def get_vs_endpoint(name: str) -> Dict[str, Any]:
    """
    Get Vector Search endpoint status and details.

    Args:
        name: Endpoint name

    Returns:
        Dictionary with:
        - name: Endpoint name
        - endpoint_type: STANDARD or STORAGE_OPTIMIZED
        - state: Current state (ONLINE, PROVISIONING, OFFLINE)
        - num_indexes: Number of indexes on this endpoint

    Example:
        >>> get_vs_endpoint("my-endpoint")
        {"name": "my-endpoint", "state": "ONLINE", "num_indexes": 3}
    """
    return _get_vs_endpoint(name=name)


@mcp.tool
def list_vs_endpoints() -> List[Dict[str, Any]]:
    """
    List all Vector Search endpoints in the workspace.

    Returns:
        List of endpoint dictionaries with name, endpoint_type, state,
        and num_indexes.

    Example:
        >>> list_vs_endpoints()
        [{"name": "my-endpoint", "state": "ONLINE", "endpoint_type": "STANDARD", ...}]
    """
    return _list_vs_endpoints()


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
# Index Management Tools
# ============================================================================


@mcp.tool
def create_vs_index(
    name: str,
    endpoint_name: str,
    primary_key: str,
    index_type: str = "DELTA_SYNC",
    delta_sync_index_spec: Optional[Dict[str, Any]] = None,
    direct_access_index_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a Vector Search index.

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
        Dictionary with index creation details

    Example:
        >>> create_vs_index(
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
    result = _create_vs_index(
        name=name,
        endpoint_name=endpoint_name,
        primary_key=primary_key,
        index_type=index_type,
        delta_sync_index_spec=delta_sync_index_spec,
        direct_access_index_spec=direct_access_index_spec,
    )

    try:
        from ..manifest import track_resource

        track_resource(
            resource_type="vs_index",
            name=name,
            resource_id=name,
        )
    except Exception:
        pass  # best-effort tracking

    return result


@mcp.tool
def get_vs_index(index_name: str) -> Dict[str, Any]:
    """
    Get Vector Search index status and details.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)

    Returns:
        Dictionary with:
        - name: Index name
        - endpoint_name: Hosting endpoint
        - index_type: DELTA_SYNC or DIRECT_ACCESS
        - state: ONLINE or NOT_READY
        - delta_sync_index_spec: Sync config details (if DELTA_SYNC)

    Example:
        >>> get_vs_index("catalog.schema.docs_index")
        {"name": "catalog.schema.docs_index", "state": "ONLINE", ...}
    """
    return _get_vs_index(index_name=index_name)


@mcp.tool
def list_vs_indexes(endpoint_name: str) -> List[Dict[str, Any]]:
    """
    List all Vector Search indexes on an endpoint.

    Args:
        endpoint_name: Endpoint name to list indexes for

    Returns:
        List of index dictionaries with name, index_type, primary_key, and state.

    Example:
        >>> list_vs_indexes("my-endpoint")
        [{"name": "catalog.schema.docs_index", "index_type": "DELTA_SYNC", "state": "ONLINE"}]
    """
    return _list_vs_indexes(endpoint_name=endpoint_name)


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


@mcp.tool
def sync_vs_index(index_name: str) -> Dict[str, Any]:
    """
    Trigger a sync for a TRIGGERED Delta Sync index.

    Only needed for indexes with pipeline_type="TRIGGERED".
    Continuous indexes sync automatically.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)

    Returns:
        Dictionary with sync status

    Example:
        >>> sync_vs_index("catalog.schema.docs_index")
        {"name": "catalog.schema.docs_index", "status": "SYNC_TRIGGERED"}
    """
    return _sync_vs_index(index_name=index_name)


# ============================================================================
# Query and Data Tools
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


@mcp.tool
def upsert_vs_data(
    index_name: str,
    inputs_json: Union[str, list],
) -> Dict[str, Any]:
    """
    Upsert data into a Direct Access Vector Search index.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        inputs_json: JSON string of records to upsert. Each record must include
            the primary key and embedding vector columns.
            Example: '[{"id": "1", "text": "hello", "embedding": [0.1, 0.2, ...]}]'

    Returns:
        Dictionary with name, status, and num_records

    Example:
        >>> upsert_vs_data(
        ...     "catalog.schema.direct_index",
        ...     '[{"id": "1", "text": "hello", "embedding": [0.1, 0.2]}]'
        ... )
        {"name": "catalog.schema.direct_index", "status": "SUCCESS", "num_records": 1}
    """
    # MCP deserializes JSON params, so inputs_json may arrive as a list
    if isinstance(inputs_json, (dict, list)):
        inputs_json = json.dumps(inputs_json)

    return _upsert_vs_data(index_name=index_name, inputs_json=inputs_json)


@mcp.tool
def delete_vs_data(
    index_name: str,
    primary_keys: List[str],
) -> Dict[str, Any]:
    """
    Delete data from a Direct Access Vector Search index.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        primary_keys: List of primary key values to delete

    Returns:
        Dictionary with name, status, and num_deleted

    Example:
        >>> delete_vs_data("catalog.schema.direct_index", ["1", "2"])
        {"name": "catalog.schema.direct_index", "status": "SUCCESS", "num_deleted": 2}
    """
    return _delete_vs_data(index_name=index_name, primary_keys=primary_keys)


@mcp.tool
def scan_vs_index(
    index_name: str,
    num_results: int = 100,
) -> Dict[str, Any]:
    """
    Scan a Vector Search index to retrieve entries.

    Useful for debugging, exporting, or verifying index contents.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        num_results: Maximum number of entries to return (default: 100)

    Returns:
        Dictionary with:
        - columns: Column names
        - data: List of index entries
        - num_results: Number of entries returned

    Example:
        >>> scan_vs_index("catalog.schema.docs_index", num_results=10)
        {"columns": ["id", "content", "embedding"], "data": [...], "num_results": 10}
    """
    return _scan_vs_index(index_name=index_name, num_results=num_results)
