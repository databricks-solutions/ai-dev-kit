"""
Vector Search Index Operations

Functions for creating, managing, querying, and syncing Vector Search indexes.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


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

    For DELTA_SYNC indexes, provide delta_sync_index_spec with either:
    - embedding_source_columns (managed embeddings): Databricks computes embeddings
    - embedding_vector_columns (self-managed): you provide pre-computed embeddings

    For DIRECT_ACCESS indexes, provide direct_access_index_spec with:
    - embedding_vector_columns and schema_json

    Args:
        name: Fully qualified index name (catalog.schema.index_name)
        endpoint_name: Vector Search endpoint to host this index
        primary_key: Column name for the primary key
        index_type: "DELTA_SYNC" or "DIRECT_ACCESS"
        delta_sync_index_spec: Config for Delta Sync index. Keys:
            - source_table (str): Fully qualified source table name
            - embedding_source_columns (list): For managed embeddings,
              e.g. [{"name": "content", "embedding_model_endpoint_name": "databricks-gte-large-en"}]
            - embedding_vector_columns (list): For self-managed embeddings,
              e.g. [{"name": "embedding", "embedding_dimension": 768}]
            - pipeline_type (str): "TRIGGERED" or "CONTINUOUS"
            - columns_to_sync (list, optional): Column names to include
        direct_access_index_spec: Config for Direct Access index. Keys:
            - embedding_vector_columns (list): e.g. [{"name": "embedding", "embedding_dimension": 768}]
            - schema_json (str): JSON schema string
            - embedding_model_endpoint_name (str, optional): For query-time embedding

    Returns:
        Dictionary with index creation details

    Raises:
        Exception: If creation fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.vectorsearch import (
            DeltaSyncVectorIndexSpecRequest,
            DirectAccessVectorIndexSpec,
            EmbeddingSourceColumn,
            EmbeddingVectorColumn,
            VectorIndexType,
        )

        kwargs: Dict[str, Any] = {
            "name": name,
            "endpoint_name": endpoint_name,
            "primary_key": primary_key,
            "index_type": VectorIndexType(index_type),
        }

        if index_type == "DELTA_SYNC" and delta_sync_index_spec:
            spec = delta_sync_index_spec
            ds_kwargs: Dict[str, Any] = {}

            if "source_table" in spec:
                ds_kwargs["source_table"] = spec["source_table"]

            if "pipeline_type" in spec:
                from databricks.sdk.service.vectorsearch import PipelineType

                ds_kwargs["pipeline_type"] = PipelineType(spec["pipeline_type"])

            if "embedding_source_columns" in spec:
                ds_kwargs["embedding_source_columns"] = [
                    EmbeddingSourceColumn(**col)
                    for col in spec["embedding_source_columns"]
                ]

            if "embedding_vector_columns" in spec:
                ds_kwargs["embedding_vector_columns"] = [
                    EmbeddingVectorColumn(**col)
                    for col in spec["embedding_vector_columns"]
                ]

            if "columns_to_sync" in spec:
                ds_kwargs["columns_to_sync"] = spec["columns_to_sync"]

            kwargs["delta_sync_vector_index_spec"] = DeltaSyncVectorIndexSpecRequest(
                **ds_kwargs
            )

        elif index_type == "DIRECT_ACCESS" and direct_access_index_spec:
            spec = direct_access_index_spec
            da_kwargs: Dict[str, Any] = {}

            if "embedding_vector_columns" in spec:
                da_kwargs["embedding_vector_columns"] = [
                    EmbeddingVectorColumn(**col)
                    for col in spec["embedding_vector_columns"]
                ]

            if "schema_json" in spec:
                da_kwargs["schema_json"] = spec["schema_json"]

            if "embedding_model_endpoint_name" in spec:
                da_kwargs["embedding_source_columns"] = [
                    EmbeddingSourceColumn(
                        name="__query__",
                        embedding_model_endpoint_name=spec[
                            "embedding_model_endpoint_name"
                        ],
                    )
                ]

            kwargs["direct_access_index_spec"] = DirectAccessVectorIndexSpec(
                **da_kwargs
            )

        client.vector_search_indexes.create_index(**kwargs)

        return {
            "name": name,
            "endpoint_name": endpoint_name,
            "index_type": index_type,
            "primary_key": primary_key,
            "status": "CREATING",
            "message": f"Index '{name}' creation initiated. Use get_vs_index('{name}') to check status.",
        }
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": name,
                "status": "ALREADY_EXISTS",
                "error": f"Index '{name}' already exists",
            }
        raise Exception(f"Failed to create vector search index '{name}': {error_msg}")


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
        - primary_key: Primary key column
        - state: Index state (ONLINE, PROVISIONING, etc.)
        - delta_sync_index_spec: Sync config (if DELTA_SYNC)
        - direct_access_index_spec: Config (if DIRECT_ACCESS)

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        index = client.vector_search_indexes.get_index(index_name=index_name)
    except Exception as e:
        error_msg = str(e)
        if (
            "not found" in error_msg.lower()
            or "does not exist" in error_msg.lower()
            or "404" in error_msg
        ):
            return {
                "name": index_name,
                "state": "NOT_FOUND",
                "error": f"Index '{index_name}' not found",
            }
        raise Exception(
            f"Failed to get vector search index '{index_name}': {error_msg}"
        )

    result: Dict[str, Any] = {
        "name": index.name,
        "endpoint_name": index.endpoint_name,
        "primary_key": index.primary_key,
    }

    if index.index_type:
        result["index_type"] = index.index_type.value

    if index.status:
        if index.status.ready:
            result["state"] = "ONLINE" if index.status.ready else "NOT_READY"
        if index.status.message:
            result["message"] = index.status.message
        if index.status.index_url:
            result["index_url"] = index.status.index_url

    if index.delta_sync_index_spec:
        spec = index.delta_sync_index_spec
        result["delta_sync_index_spec"] = {
            "source_table": spec.source_table,
            "pipeline_type": spec.pipeline_type.value if spec.pipeline_type else None,
        }
        if spec.pipeline_id:
            result["delta_sync_index_spec"]["pipeline_id"] = spec.pipeline_id

    return result


def list_vs_indexes(endpoint_name: str) -> List[Dict[str, Any]]:
    """
    List all Vector Search indexes on an endpoint.

    Args:
        endpoint_name: Endpoint name to list indexes for

    Returns:
        List of index dictionaries with:
        - name: Index name
        - index_type: DELTA_SYNC or DIRECT_ACCESS
        - primary_key: Primary key column
        - state: Index state

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_indexes.list_indexes(
            endpoint_name=endpoint_name,
        )
    except Exception as e:
        raise Exception(
            f"Failed to list indexes on endpoint '{endpoint_name}': {str(e)}"
        )

    result = []
    # SDK may return an object with .vector_indexes or a generator directly
    if hasattr(response, "vector_indexes") and response.vector_indexes:
        indexes = response.vector_indexes
    elif response:
        indexes = list(response)
    else:
        indexes = []
    for idx in indexes:
        entry: Dict[str, Any] = {
            "name": idx.name,
        }

        # primary_key may not exist on MiniVectorIndex
        try:
            if idx.primary_key:
                entry["primary_key"] = idx.primary_key
        except (AttributeError, KeyError):
            pass

        try:
            if idx.index_type:
                entry["index_type"] = idx.index_type.value
        except (AttributeError, KeyError):
            pass

        # status may not exist on MiniVectorIndex (from generator response)
        try:
            if idx.status and idx.status.ready is not None:
                entry["state"] = "ONLINE" if idx.status.ready else "NOT_READY"
        except (AttributeError, KeyError):
            pass

        result.append(entry)

    return result


def delete_vs_index(index_name: str) -> Dict[str, Any]:
    """
    Delete a Vector Search index.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)

    Returns:
        Dictionary with:
        - name: Index name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails
    """
    client = get_workspace_client()

    try:
        client.vector_search_indexes.delete_index(index_name=index_name)
        return {
            "name": index_name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if (
            "not found" in error_msg.lower()
            or "does not exist" in error_msg.lower()
            or "404" in error_msg
        ):
            return {
                "name": index_name,
                "status": "NOT_FOUND",
                "error": f"Index '{index_name}' not found",
            }
        raise Exception(
            f"Failed to delete vector search index '{index_name}': {error_msg}"
        )


def sync_vs_index(index_name: str) -> Dict[str, Any]:
    """
    Trigger a sync for a TRIGGERED Delta Sync index.

    Only applicable for Delta Sync indexes with pipeline_type=TRIGGERED.
    Continuous indexes sync automatically.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)

    Returns:
        Dictionary with sync status

    Raises:
        Exception: If sync trigger fails
    """
    client = get_workspace_client()

    try:
        client.vector_search_indexes.sync_index(index_name=index_name)
        return {
            "name": index_name,
            "status": "SYNC_TRIGGERED",
            "message": f"Sync triggered for index '{index_name}'. Use get_vs_index() to check progress.",
        }
    except Exception as e:
        raise Exception(f"Failed to sync index '{index_name}': {str(e)}")


def query_vs_index(
    index_name: str,
    columns: List[str],
    query_text: Optional[str] = None,
    query_vector: Optional[List[float]] = None,
    num_results: int = 5,
    filters_json: Optional[str] = None,
    filter_string: Optional[str] = None,
    query_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Query a Vector Search index for similar documents.

    Provide either query_text (for indexes with managed or attached embeddings)
    or query_vector (for pre-computed query embeddings).

    For filters:
    - Standard endpoints use filters_json (dict format): '{"category": "ai"}'
    - Storage-Optimized endpoints use filter_string (SQL syntax): "category = 'ai'"

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        columns: List of column names to return in results
        query_text: Text query (for managed/attached embedding models)
        query_vector: Pre-computed query embedding vector
        num_results: Number of results to return (default: 5)
        filters_json: JSON string of filters for Standard endpoints
        filter_string: SQL-like filter for Storage-Optimized endpoints
        query_type: Search algorithm: "ANN" (default) or "HYBRID" (vector + keyword)

    Returns:
        Dictionary with:
        - columns: Column names in results
        - data: List of result rows (similarity score is appended as last column)
        - num_results: Number of results returned

    Raises:
        Exception: If query fails
    """
    client = get_workspace_client()

    kwargs: Dict[str, Any] = {
        "index_name": index_name,
        "columns": columns,
        "num_results": num_results,
    }

    if query_text is not None:
        kwargs["query_text"] = query_text
    elif query_vector is not None:
        kwargs["query_vector"] = query_vector
    else:
        raise ValueError("Must provide either query_text or query_vector")

    if filters_json is not None:
        kwargs["filters_json"] = filters_json

    if filter_string is not None:
        kwargs["filter_string"] = filter_string

    if query_type is not None:
        kwargs["query_type"] = query_type

    try:
        response = client.vector_search_indexes.query_index(**kwargs)
    except Exception as e:
        raise Exception(f"Failed to query index '{index_name}': {str(e)}")

    result: Dict[str, Any] = {}

    # Column names from manifest (SDK doesn't put them on result directly)
    try:
        if response.manifest and response.manifest.columns:
            result["columns"] = [c.name for c in response.manifest.columns]
    except (AttributeError, KeyError):
        pass

    if response.result:
        if response.result.data_array:
            result["data"] = response.result.data_array
            result["num_results"] = len(response.result.data_array)
        else:
            result["data"] = []
            result["num_results"] = 0

    if response.manifest:
        result["manifest"] = {
            "column_count": response.manifest.column_count,
        }

    return result


def upsert_vs_data(
    index_name: str,
    inputs_json: str,
) -> Dict[str, Any]:
    """
    Upsert data into a Direct Access Vector Search index.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        inputs_json: JSON string of records to upsert. Each record must include
            the primary key and embedding vector columns.
            Example: '[{"id": "1", "text": "hello", "embedding": [0.1, 0.2, ...]}]'

    Returns:
        Dictionary with:
        - name: Index name
        - status: Upsert result status
        - num_records: Number of records upserted

    Raises:
        Exception: If upsert fails
    """
    client = get_workspace_client()

    try:
        # Parse to validate JSON and count records
        records = (
            json.loads(inputs_json) if isinstance(inputs_json, str) else inputs_json
        )
        num_records = len(records) if isinstance(records, list) else 1

        response = client.vector_search_indexes.upsert_data_vector_index(
            index_name=index_name,
            inputs_json=inputs_json,
        )

        result: Dict[str, Any] = {
            "name": index_name,
            "status": "SUCCESS",
            "num_records": num_records,
        }

        if response and response.status:
            result["status"] = (
                response.status.value
                if hasattr(response.status, "value")
                else str(response.status)
            )

        return result
    except Exception as e:
        raise Exception(f"Failed to upsert data into index '{index_name}': {str(e)}")


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
        Dictionary with:
        - name: Index name
        - status: Delete result status
        - num_deleted: Number of records requested for deletion

    Raises:
        Exception: If delete fails
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_indexes.delete_data_vector_index(
            index_name=index_name,
            primary_keys=primary_keys,
        )

        result: Dict[str, Any] = {
            "name": index_name,
            "status": "SUCCESS",
            "num_deleted": len(primary_keys),
        }

        if response and response.status:
            result["status"] = (
                response.status.value
                if hasattr(response.status, "value")
                else str(response.status)
            )

        return result
    except Exception as e:
        raise Exception(f"Failed to delete data from index '{index_name}': {str(e)}")


def scan_vs_index(
    index_name: str,
    num_results: int = 100,
) -> Dict[str, Any]:
    """
    Scan a Vector Search index to retrieve all entries.

    Useful for debugging, exporting, or verifying index contents.

    Args:
        index_name: Fully qualified index name (catalog.schema.index_name)
        num_results: Maximum number of entries to return (default: 100)

    Returns:
        Dictionary with:
        - columns: Column names
        - data: List of index entries
        - num_results: Number of entries returned

    Raises:
        Exception: If scan fails
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_indexes.scan_index(
            index_name=index_name,
            num_results=num_results,
        )
    except Exception as e:
        raise Exception(f"Failed to scan index '{index_name}': {str(e)}")

    result: Dict[str, Any] = {}

    # ScanVectorIndexResponse has .data (list of entries) and .last_primary_key
    # not .result like QueryVectorIndexResponse
    try:
        data = response.data
        if data:
            # data is a list of Struct/dict objects
            if isinstance(data, list) and len(data) > 0:
                # Extract column names from first entry
                first = data[0]
                if hasattr(first, "as_dict"):
                    rows = [d.as_dict() for d in data]
                elif isinstance(first, dict):
                    rows = data
                else:
                    rows = data

                if rows and isinstance(rows[0], dict):
                    result["columns"] = list(rows[0].keys())
                result["data"] = rows
                result["num_results"] = len(rows)
            else:
                result["data"] = []
                result["num_results"] = 0
        else:
            result["data"] = []
            result["num_results"] = 0
    except (AttributeError, KeyError):
        # Fallback: try the old .result pattern in case SDK changes
        try:
            if response.result:
                if (
                    hasattr(response.result, "column_names")
                    and response.result.column_names
                ):
                    result["columns"] = response.result.column_names
                if response.result.data_array:
                    result["data"] = response.result.data_array
                    result["num_results"] = len(response.result.data_array)
                else:
                    result["data"] = []
                    result["num_results"] = 0
        except (AttributeError, KeyError):
            result["data"] = []
            result["num_results"] = 0

    return result
