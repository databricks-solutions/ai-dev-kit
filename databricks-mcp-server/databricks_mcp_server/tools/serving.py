"""Model Serving tools - Query and manage serving endpoints.

Provides 4 tools:
- get_serving_endpoint_status: check endpoint state and config
- query_serving_endpoint: query chat/ML endpoints
- list_serving_endpoints: list all endpoints
- manage_serving_endpoint: create, update, delete, logs, metrics, permissions (8 actions)
"""

import logging
from typing import Any, Dict, List, Optional

from databricks_tools_core.serving import (
    create_serving_endpoint as _create_serving_endpoint,
    delete_serving_endpoint as _delete_serving_endpoint,
    export_serving_endpoint_metrics as _export_serving_endpoint_metrics,
    get_serving_endpoint_build_logs as _get_serving_endpoint_build_logs,
    get_serving_endpoint_permissions as _get_serving_endpoint_permissions,
    get_serving_endpoint_server_logs as _get_serving_endpoint_server_logs,
    get_serving_endpoint_status as _get_serving_endpoint_status,
    list_serving_endpoints as _list_serving_endpoints,
    query_serving_endpoint as _query_serving_endpoint,
    update_serving_endpoint as _update_serving_endpoint,
    update_serving_endpoint_permissions as _update_serving_endpoint_permissions,
)

from ..manifest import register_deleter, remove_resource, track_resource
from ..server import mcp

logger = logging.getLogger(__name__)


# ============================================================================
# Manifest integration for resource tracking
# ============================================================================


def _delete_serving_endpoint_resource(resource_id: str) -> None:
    _delete_serving_endpoint(name=resource_id)


register_deleter("serving_endpoint", _delete_serving_endpoint_resource)


# ============================================================================
# Helpers
# ============================================================================


def _find_endpoint_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Find a serving endpoint by name, returns None if not found."""
    try:
        result = _get_serving_endpoint_status(name=name)
        if result.get("state") == "NOT_FOUND":
            return None
        return result
    except Exception:
        return None


# ============================================================================
# Read-only tools (upstream's original 3 tools)
# ============================================================================


@mcp.tool(timeout=30)
def get_serving_endpoint_status(name: str) -> Dict[str, Any]:
    """
    Get the status of a Model Serving endpoint.

    Use this to check if an endpoint is ready after deployment, or to
    debug issues with a serving endpoint.

    Args:
        name: The name of the serving endpoint

    Returns:
        Dictionary with endpoint status:
        - name: Endpoint name
        - state: Current state (READY, NOT_READY, NOT_FOUND)
        - config_update: Config update state if updating (IN_PROGRESS, etc.)
        - served_entities: List of served models with their deployment states
        - error: Error message if endpoint is in error state

    Example:
        >>> get_serving_endpoint_status("my-agent-endpoint")
        {
            "name": "my-agent-endpoint",
            "state": "READY",
            "config_update": null,
            "served_entities": [
                {"name": "my-agent-1", "entity_name": "main.agents.my_agent", ...}
            ]
        }
    """
    return _get_serving_endpoint_status(name=name)


@mcp.tool(timeout=120)
def query_serving_endpoint(
    name: str,
    messages: Optional[List[Dict[str, str]]] = None,
    inputs: Optional[Dict[str, Any]] = None,
    dataframe_records: Optional[List[Dict[str, Any]]] = None,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Query a Model Serving endpoint.

    Supports multiple input formats depending on endpoint type:
    - messages: For chat/agent endpoints (OpenAI-compatible format)
    - inputs: For custom pyfunc models
    - dataframe_records: For traditional ML models (pandas DataFrame format)

    Args:
        name: The name of the serving endpoint
        messages: List of chat messages for chat/agent endpoints.
            Format: [{"role": "user", "content": "Hello"}]
        inputs: Dictionary of inputs for custom pyfunc models.
            Format depends on model signature.
        dataframe_records: List of records for ML models.
            Format: [{"feature1": 1.0, "feature2": 2.0}, ...]
        max_tokens: Maximum tokens for chat/completion endpoints
        temperature: Temperature for chat/completion endpoints (0.0-2.0)

    Returns:
        Dictionary with query response:
        - For chat endpoints: Contains 'choices' with assistant response
        - For ML endpoints: Contains 'predictions'

    Example (chat/agent endpoint):
        >>> query_serving_endpoint(
        ...     name="my-agent-endpoint",
        ...     messages=[{"role": "user", "content": "What is Databricks?"}]
        ... )
        {
            "choices": [
                {"message": {"role": "assistant", "content": "Databricks is..."}}
            ]
        }

    Example (ML model):
        >>> query_serving_endpoint(
        ...     name="sklearn-model",
        ...     dataframe_records=[{"age": 25, "income": 50000}]
        ... )
        {"predictions": [0.85]}
    """
    return _query_serving_endpoint(
        name=name,
        messages=messages,
        inputs=inputs,
        dataframe_records=dataframe_records,
        max_tokens=max_tokens,
        temperature=temperature,
    )


@mcp.tool(timeout=30)
def list_serving_endpoints(limit: int = 50) -> List[Dict[str, Any]]:
    """
    List Model Serving endpoints in the workspace.

    Args:
        limit: Maximum number of endpoints to return (default: 50)

    Returns:
        List of endpoint dictionaries with:
        - name: Endpoint name
        - state: Current state (READY, NOT_READY)
        - creation_timestamp: When created
        - creator: Who created it
        - served_entities_count: Number of served models

    Example:
        >>> list_serving_endpoints(limit=10)
        [
            {"name": "my-agent", "state": "READY", ...},
            {"name": "ml-model", "state": "READY", ...}
        ]
    """
    return _list_serving_endpoints(limit=limit)


# ============================================================================
# Consolidated management tool (8 actions)
# ============================================================================

_VALID_SERVING_ACTIONS = (
    "create",
    "update",
    "delete",
    "get_build_logs",
    "get_server_logs",
    "export_metrics",
    "get_permissions",
    "update_permissions",
)


def _manage_serving_endpoint_impl(
    action: str,
    name: str,
    # create/update params
    served_entities: Optional[List[Dict[str, Any]]] = None,
    traffic_config: Optional[Dict[str, Any]] = None,
    timeout_minutes: int = 30,
    wait: bool = True,
    # logs params
    served_model_name: Optional[str] = None,
    # permissions params
    access_control_list: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Dispatch serving endpoint actions to core lib functions."""
    act = action.lower()

    if act == "create":
        if not served_entities:
            return {"error": "create requires: served_entities (list of entity dicts with entity_name, entity_version)"}

        # Idempotent: return existing if present
        existing = _find_endpoint_by_name(name)
        if existing:
            return {**existing, "created": False}

        from databricks_tools_core.identity import get_default_tags, with_description_footer

        result = _create_serving_endpoint(
            name=name,
            served_entities=served_entities,
            traffic_config=traffic_config,
            timeout_minutes=timeout_minutes,
            wait=wait,
            tags=get_default_tags(),
            description=with_description_footer(None),
        )

        # Best-effort resource tracking
        try:
            track_resource(
                resource_type="serving_endpoint",
                name=result["name"],
                resource_id=result["name"],
            )
        except Exception:
            pass

        return {**result, "created": True}

    elif act == "update":
        if not served_entities:
            return {"error": "update requires: served_entities (list of entity dicts with entity_name, entity_version)"}
        return _update_serving_endpoint(
            name=name,
            served_entities=served_entities,
            traffic_config=traffic_config,
            timeout_minutes=timeout_minutes,
            wait=wait,
        )

    elif act == "delete":
        result = _delete_serving_endpoint(name=name)
        if result.get("status") == "deleted":
            try:
                remove_resource(resource_type="serving_endpoint", resource_id=name)
            except Exception:
                pass
        return result

    elif act == "get_build_logs":
        return _get_serving_endpoint_build_logs(name=name, served_model_name=served_model_name)

    elif act == "get_server_logs":
        return _get_serving_endpoint_server_logs(name=name, served_model_name=served_model_name)

    elif act == "export_metrics":
        return _export_serving_endpoint_metrics(name=name)

    elif act == "get_permissions":
        return _get_serving_endpoint_permissions(name=name)

    elif act == "update_permissions":
        if not access_control_list:
            return {
                "error": (
                    "update_permissions requires: access_control_list "
                    '(list of dicts with permission_level and user_name/group_name, e.g. [{"user_name": "...", '
                    '"permission_level": "CAN_QUERY"}])'
                )
            }
        return _update_serving_endpoint_permissions(name=name, access_control_list=access_control_list)

    else:
        return {"error": f"Unknown action '{action}'. Valid actions: {', '.join(_VALID_SERVING_ACTIONS)}"}


@mcp.tool(timeout=180)
def manage_serving_endpoint(
    action: str,
    name: str,
    served_entities: Optional[List[Dict[str, Any]]] = None,
    traffic_config: Optional[Dict[str, Any]] = None,
    timeout_minutes: int = 30,
    wait: bool = True,
    served_model_name: Optional[str] = None,
    access_control_list: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Manage Model Serving endpoints: create, update, delete, logs, metrics, permissions.

    Actions:
    - create: Idempotent create. Requires served_entities (list of entity dicts). Returns
      existing if already present (created=false). Uses wait=True for ML models (2-5 min),
      wait=False for agents (~15 min) then poll with get_serving_endpoint_status().
      Entity dicts: entity_name (UC path), entity_version, workload_size (Small/Medium/Large),
      scale_to_zero_enabled (default True), workload_type (CPU/GPU_SMALL/GPU_MEDIUM/GPU_LARGE).
    - update: Update endpoint config. Requires served_entities. Deploy new model versions,
      change workload size, or modify traffic routing.
    - delete: Delete endpoint. UC model is NOT deleted.
    - get_build_logs: Get build logs (container image, dependencies). Optional: served_model_name.
    - get_server_logs: Get runtime server logs (stdout/stderr). Optional: served_model_name.
    - export_metrics: Export health metrics (CPU, memory, latency, GPU). Returns structured
      metrics list and raw Prometheus text.
    - get_permissions: Get ACL with principal, principal_type, permission_level, inherited flag.
    - update_permissions: Additive merge of ACL entries. Requires access_control_list
      (list of dicts with permission_level and user_name/group_name/service_principal_name).

    See databricks-model-serving skill for deployment patterns and examples.

    Example:
        >>> manage_serving_endpoint("create", "my-model", served_entities=[{
        ...     "entity_name": "main.ml.model", "entity_version": "1",
        ...     "workload_size": "Small", "scale_to_zero_enabled": True
        ... }])
    """
    return _manage_serving_endpoint_impl(
        action=action,
        name=name,
        served_entities=served_entities,
        traffic_config=traffic_config,
        timeout_minutes=timeout_minutes,
        wait=wait,
        served_model_name=served_model_name,
        access_control_list=access_control_list,
    )
