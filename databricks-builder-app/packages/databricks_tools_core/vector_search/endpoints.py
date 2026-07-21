"""
Vector Search Endpoint Operations

Functions for creating, managing, and deleting Databricks Vector Search endpoints.
"""

import logging
from typing import Any, Dict, List

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_vs_endpoint(
    name: str,
    endpoint_type: str = "STANDARD",
) -> Dict[str, Any]:
    """
    Create a Vector Search endpoint.

    Endpoint creation is asynchronous. Use get_vs_endpoint() to check status.

    Args:
        name: Endpoint name (unique within workspace)
        endpoint_type: "STANDARD" (low-latency, <100ms) or
            "STORAGE_OPTIMIZED" (cost-effective, ~250ms, 1B+ vectors)

    Returns:
        Dictionary with:
        - name: Endpoint name
        - endpoint_type: Type of endpoint created
        - status: Creation status

    Raises:
        Exception: If creation fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.vectorsearch import EndpointType

        ep_type = EndpointType(endpoint_type)
        client.vector_search_endpoints.create_endpoint(
            name=name,
            endpoint_type=ep_type,
        )

        return {
            "name": name,
            "endpoint_type": endpoint_type,
            "status": "CREATING",
            "message": f"Endpoint '{name}' creation initiated. Use get_vs_endpoint('{name}') to check status.",
        }
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": name,
                "endpoint_type": endpoint_type,
                "status": "ALREADY_EXISTS",
                "error": f"Endpoint '{name}' already exists",
            }
        raise Exception(f"Failed to create vector search endpoint '{name}': {error_msg}")


def get_vs_endpoint(name: str) -> Dict[str, Any]:
    """
    Get Vector Search endpoint status and details.

    Args:
        name: Endpoint name

    Returns:
        Dictionary with:
        - name: Endpoint name
        - endpoint_type: STANDARD or STORAGE_OPTIMIZED
        - state: Current state (e.g., ONLINE, PROVISIONING, OFFLINE)
        - creation_timestamp: When endpoint was created
        - last_updated_timestamp: When endpoint was last updated
        - num_indexes: Number of indexes on this endpoint
        - error: Error message if endpoint is in error state

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        endpoint = client.vector_search_endpoints.get_endpoint(endpoint_name=name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"Endpoint '{name}' not found",
            }
        raise Exception(f"Failed to get vector search endpoint '{name}': {error_msg}")

    result: Dict[str, Any] = {
        "name": endpoint.name,
        "state": (
            endpoint.endpoint_status.state.value
            if endpoint.endpoint_status and endpoint.endpoint_status.state
            else None
        ),
        "error": None,
    }

    if endpoint.endpoint_type:
        result["endpoint_type"] = endpoint.endpoint_type.value

    if endpoint.endpoint_status and endpoint.endpoint_status.message:
        result["message"] = endpoint.endpoint_status.message

    if endpoint.creation_timestamp:
        result["creation_timestamp"] = endpoint.creation_timestamp

    if endpoint.last_updated_timestamp:
        result["last_updated_timestamp"] = endpoint.last_updated_timestamp

    if endpoint.num_indexes is not None:
        result["num_indexes"] = endpoint.num_indexes

    return result


def list_vs_endpoints() -> List[Dict[str, Any]]:
    """
    List all Vector Search endpoints in the workspace.

    Returns:
        List of endpoint dictionaries with:
        - name: Endpoint name
        - endpoint_type: STANDARD or STORAGE_OPTIMIZED
        - state: Current state
        - num_indexes: Number of indexes on endpoint

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        response = client.vector_search_endpoints.list_endpoints()
    except Exception as e:
        raise Exception(f"Failed to list vector search endpoints: {str(e)}")

    result = []
    # SDK may return a generator or an object with .endpoints attribute
    if hasattr(response, "endpoints"):
        endpoints = response.endpoints if response.endpoints else []
    else:
        endpoints = list(response) if response else []
    for ep in endpoints:
        entry: Dict[str, Any] = {"name": ep.name}

        if ep.endpoint_type:
            entry["endpoint_type"] = ep.endpoint_type.value

        if ep.endpoint_status and ep.endpoint_status.state:
            entry["state"] = ep.endpoint_status.state.value

        if ep.num_indexes is not None:
            entry["num_indexes"] = ep.num_indexes

        if ep.creation_timestamp:
            entry["creation_timestamp"] = ep.creation_timestamp

        result.append(entry)

    return result


def delete_vs_endpoint(name: str) -> Dict[str, Any]:
    """
    Delete a Vector Search endpoint.

    All indexes on the endpoint must be deleted first.

    Args:
        name: Endpoint name to delete

    Returns:
        Dictionary with:
        - name: Endpoint name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails
    """
    client = get_workspace_client()

    try:
        client.vector_search_endpoints.delete_endpoint(endpoint_name=name)
        return {
            "name": name,
            "status": "deleted",
        }
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "status": "NOT_FOUND",
                "error": f"Endpoint '{name}' not found",
            }
        raise Exception(f"Failed to delete vector search endpoint '{name}': {error_msg}")
