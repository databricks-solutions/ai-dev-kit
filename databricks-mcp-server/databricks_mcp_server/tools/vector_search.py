"""Vector Search tools - Manage endpoints, indexes, and query vector data.

Consolidated into 4 tools:
- manage_vs_endpoint: create_or_update, get, list, delete
- manage_vs_index: create_or_update, get, list, delete
- query_vs_index: query vectors (hot path - kept separate)
- manage_vs_data: upsert, delete, scan, sync
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
# Tool 1: manage_vs_endpoint
# ============================================================================


@mcp.tool(timeout=120)
def manage_vs_endpoint(
    action: str,
    name: Optional[str] = None,
    endpoint_type: str = "STANDARD",
) -> Dict[str, Any]:
    """Manage Vector Search endpoints: create, get, list, delete.

    Actions:
    - create_or_update: Idempotent create. Returns existing if found. Requires name.
      endpoint_type: "STANDARD" (<100ms latency) or "STORAGE_OPTIMIZED" (~250ms, 1B+ vectors).
      Async creation - poll with action="get" until state=ONLINE.
      Returns: {name, endpoint_type, state, created: bool}.
    - get: Get endpoint details. Requires name.
      Returns: {name, state, num_indexes, ...}.
    - list: List all endpoints.
      Returns: {endpoints: [{name, state, ...}, ...]}.
    - delete: Delete endpoint. All indexes must be deleted first. Requires name.
      Returns: {name, status}.

    See databricks-vector-search skill for endpoint configuration."""
    act = action.lower()

    if act == "create_or_update":
        if not name:
            return {"error": "create_or_update requires: name"}

        existing = _find_endpoint_by_name(name)
        if existing:
            return {**existing, "created": False}

        result = _create_vs_endpoint(name=name, endpoint_type=endpoint_type)

        try:
            from ..manifest import track_resource
            track_resource(resource_type="vs_endpoint", name=name, resource_id=name)
        except Exception:
            pass

        return {**result, "created": True}

    elif act == "get":
        if not name:
            return {"error": "get requires: name"}
        return _get_vs_endpoint(name=name)

    elif act == "list":
        return {"endpoints": _list_vs_endpoints()}

    elif act == "delete":
        if not name:
            return {"error": "delete requires: name"}
        return _delete_vs_endpoint(name=name)

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: create_or_update, get, list, delete"}


# ============================================================================
# Tool 2: manage_vs_index
# ============================================================================


@mcp.tool(timeout=120)
def manage_vs_index(
    action: str,
    # For create_or_update:
    name: Optional[str] = None,
    endpoint_name: Optional[str] = None,
    primary_key: Optional[str] = None,
    index_type: str = "DELTA_SYNC",
    delta_sync_index_spec: Optional[Dict[str, Any]] = None,
    direct_access_index_spec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Manage Vector Search indexes: create, get, list, delete.

    Actions:
    - create_or_update: Idempotent create. Returns existing if found. Auto-triggers initial sync for DELTA_SYNC.
      Requires name, endpoint_name, primary_key.
      index_type: "DELTA_SYNC" (auto-sync from Delta table) or "DIRECT_ACCESS" (manual CRUD via manage_vs_data).
      delta_sync_index_spec: {source_table, embedding_source_columns OR embedding_vector_columns, pipeline_type}.
        - embedding_source_columns: List of text columns for managed embeddings (Databricks generates vectors).
        - embedding_vector_columns: List of {name, dimension} for self-managed embeddings (you provide vectors).
        - pipeline_type: "TRIGGERED" (manual sync) or "CONTINUOUS" (auto-sync on changes).
      direct_access_index_spec: {embedding_vector_columns: [{name, dimension}], schema_json}.
      Returns: {name, created: bool, sync_triggered}.
    - get: Get index details. Requires name (format: catalog.schema.index_name).
      Returns: {name, state, index_type, ...}.
    - list: List indexes. Optional endpoint_name to filter. Omit for all indexes across all endpoints.
      Returns: {indexes: [...]}.
    - delete: Delete index. Requires name.
      Returns: {name, status}.

    See databricks-vector-search skill for full spec details and examples."""
    act = action.lower()

    if act == "create_or_update":
        if not all([name, endpoint_name, primary_key]):
            return {"error": "create_or_update requires: name, endpoint_name, primary_key"}

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

        try:
            from ..manifest import track_resource
            track_resource(resource_type="vs_index", name=name, resource_id=name)
        except Exception:
            pass

        return {**result, "created": True}

    elif act == "get":
        if not name:
            return {"error": "get requires: name"}
        return _get_vs_index(index_name=name)

    elif act == "list":
        if endpoint_name:
            return {"indexes": _list_vs_indexes(endpoint_name=endpoint_name)}

        # List all indexes across all endpoints
        all_indexes = []
        endpoints = _list_vs_endpoints()
        for ep in endpoints:
            ep_name = ep.get("name")
            if not ep_name:
                continue
            try:
                indexes = _list_vs_indexes(endpoint_name=ep_name)
                for idx in indexes:
                    idx["endpoint_name"] = ep_name
                all_indexes.extend(indexes)
            except Exception:
                logger.warning("Failed to list indexes on endpoint '%s'", ep_name)
        return {"indexes": all_indexes}

    elif act == "delete":
        if not name:
            return {"error": "delete requires: name"}
        return _delete_vs_index(index_name=name)

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: create_or_update, get, list, delete"}


# ============================================================================
# Tool 3: query_vs_index (HOT PATH - kept separate for performance)
# ============================================================================


@mcp.tool(timeout=60)
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
    """Query a Vector Search index for similar documents.

    Use ONE OF:
    - query_text: For managed embeddings (Databricks generates vector from text).
    - query_vector: For self-managed embeddings (you provide the vector).

    columns: List of columns to return in results.
    num_results: Number of results to return (default 5).
    Filters (use one based on endpoint type):
    - filters_json: For STANDARD endpoints. Dict like {"field": "value"} or {"field NOT": "value"}.
    - filter_string: For STORAGE_OPTIMIZED endpoints. SQL WHERE clause like "field = 'value'".
    query_type: "ANN" (default, approximate) or "HYBRID" (combines vector + keyword search).

    Returns: {columns, data (with similarity score appended), num_results}."""
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
# Tool 4: manage_vs_data
# ============================================================================


@mcp.tool(timeout=120)
def manage_vs_data(
    action: str,
    index_name: str,
    # For upsert:
    inputs_json: Optional[Union[str, list]] = None,
    # For delete:
    primary_keys: Optional[List[str]] = None,
    # For scan:
    num_results: int = 100,
) -> Dict[str, Any]:
    """Manage Vector Search index data: upsert, delete, scan, sync.

    Actions:
    - upsert: Insert or update records. Requires inputs_json.
      inputs_json: List of records, each with primary key + embedding vector.
      Example: [{"id": "doc1", "text": "...", "embedding": [0.1, 0.2, ...]}]
      Returns: {status, upserted_count}.
    - delete: Delete records by primary key. Requires primary_keys.
      primary_keys: List of primary key values to delete.
      Returns: {status, deleted_count}.
    - scan: Scan index contents. Optional num_results (default 100).
      Returns: {columns, data, num_results}.
    - sync: Trigger re-sync for TRIGGERED DELTA_SYNC indexes.
      Returns: {index_name, status: "sync_triggered"}.

    For DIRECT_ACCESS indexes, use upsert/delete to manage data.
    For DELTA_SYNC indexes, use sync to trigger refresh from source table."""
    act = action.lower()

    if act == "upsert":
        if inputs_json is None:
            return {"error": "upsert requires: inputs_json"}
        # MCP deserializes JSON params, so inputs_json may arrive as a list
        if isinstance(inputs_json, (dict, list)):
            inputs_json = json.dumps(inputs_json)
        return _upsert_vs_data(index_name=index_name, inputs_json=inputs_json)

    elif act == "delete":
        if primary_keys is None:
            return {"error": "delete requires: primary_keys"}
        return _delete_vs_data(index_name=index_name, primary_keys=primary_keys)

    elif act == "scan":
        return _scan_vs_index(index_name=index_name, num_results=num_results)

    elif act == "sync":
        _sync_vs_index(index_name=index_name)
        return {"index_name": index_name, "status": "sync_triggered"}

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: upsert, delete, scan, sync"}
