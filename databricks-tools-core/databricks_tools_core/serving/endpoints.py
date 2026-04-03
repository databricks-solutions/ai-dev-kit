"""
Model Serving Endpoints Operations

Functions for checking status and querying Databricks Model Serving endpoints.
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from databricks.sdk.service.serving import ChatMessage, ServingEndpointAccessControlRequest

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def get_serving_endpoint_status(name: str) -> Dict[str, Any]:
    """
    Get the status of a Model Serving endpoint.

    Args:
        name: The name of the serving endpoint

    Returns:
        Dictionary with endpoint status:
        - name: Endpoint name
        - state: Current state (READY, NOT_READY, etc.)
        - config_update: Config update state if updating
        - creation_timestamp: When endpoint was created
        - last_updated_timestamp: When endpoint was last updated
        - pending_config: Details of pending config update if any
        - served_entities: List of served models/entities with their states
        - error: Error message if endpoint is in error state

    Raises:
        Exception: If endpoint not found or API request fails
    """
    client = get_workspace_client()

    try:
        endpoint = client.serving_endpoints.get(name=name)
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"Endpoint '{name}' not found",
            }
        raise Exception(f"Failed to get serving endpoint '{name}': {error_msg}")

    # Extract state information
    state_info = {}
    if endpoint.state:
        state_info["state"] = endpoint.state.ready.value if endpoint.state.ready else None
        state_info["config_update"] = endpoint.state.config_update.value if endpoint.state.config_update else None

    # Extract served entities status
    served_entities = []
    if endpoint.config and endpoint.config.served_entities:
        for entity in endpoint.config.served_entities:
            entity_info = {
                "name": entity.name,
                "entity_name": entity.entity_name,
                "entity_version": entity.entity_version,
            }
            if entity.state:
                entity_info["deployment_state"] = entity.state.deployment.value if entity.state.deployment else None
                entity_info["deployment_state_message"] = entity.state.deployment_state_message
            served_entities.append(entity_info)

    # Check for pending config
    pending_config = None
    if endpoint.pending_config:
        pending_config = {
            "served_entities": [
                {
                    "name": e.name,
                    "entity_name": e.entity_name,
                    "entity_version": e.entity_version,
                }
                for e in (endpoint.pending_config.served_entities or [])
            ]
        }

    return {
        "name": endpoint.name,
        "state": state_info.get("state"),
        "config_update": state_info.get("config_update"),
        "creation_timestamp": endpoint.creation_timestamp,
        "last_updated_timestamp": endpoint.last_updated_timestamp,
        "served_entities": served_entities,
        "pending_config": pending_config,
        "error": None,
    }


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

    Supports multiple input formats:
    - messages: For chat/agent endpoints (OpenAI-compatible format)
    - inputs: For custom pyfunc models
    - dataframe_records: For traditional ML models (pandas DataFrame format)

    Args:
        name: The name of the serving endpoint
        messages: List of chat messages [{"role": "user", "content": "..."}]
        inputs: Dictionary of inputs for custom models
        dataframe_records: List of records for DataFrame input
        max_tokens: Maximum tokens for chat/completion endpoints
        temperature: Temperature for chat/completion endpoints

    Returns:
        Dictionary with query response:
        - For chat endpoints: Contains 'choices' with assistant response
        - For ML endpoints: Contains 'predictions'
        - Always includes 'usage' if available

    Raises:
        Exception: If query fails or endpoint not ready
    """
    client = get_workspace_client()

    # Build query kwargs
    query_kwargs: Dict[str, Any] = {"name": name}

    if messages is not None:
        # Chat/Agent endpoint - convert dicts to ChatMessage objects
        query_kwargs["messages"] = [ChatMessage.from_dict(m) for m in messages]
        if max_tokens is not None:
            query_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            query_kwargs["temperature"] = temperature
    elif inputs is not None:
        # Custom pyfunc model - use instances format
        query_kwargs["instances"] = [inputs]
    elif dataframe_records is not None:
        # Traditional ML model - DataFrame format
        query_kwargs["dataframe_records"] = dataframe_records
    else:
        raise ValueError(
            "Must provide one of: messages (for chat/agents), "
            "inputs (for custom models), or dataframe_records (for ML models)"
        )

    try:
        response = client.serving_endpoints.query(**query_kwargs)
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg:
            raise Exception(f"Endpoint '{name}' not found")
        if "NOT_READY" in error_msg or "PENDING" in error_msg:
            raise Exception(f"Endpoint '{name}' is not ready. Check status with get_serving_endpoint_status('{name}')")
        raise Exception(f"Failed to query endpoint '{name}': {error_msg}")

    # Convert response to dict
    result: Dict[str, Any] = {}

    # Handle chat response format
    if hasattr(response, "choices") and response.choices:
        result["choices"] = [
            {
                "index": c.index,
                "message": {
                    "role": c.message.role if c.message else None,
                    "content": c.message.content if c.message else None,
                },
                "finish_reason": c.finish_reason,
            }
            for c in response.choices
        ]

    # Handle predictions format (ML models)
    if hasattr(response, "predictions") and response.predictions:
        result["predictions"] = response.predictions

    # Handle generic output
    if hasattr(response, "output") and response.output:
        result["output"] = response.output

    # Include usage if available
    if hasattr(response, "usage") and response.usage:
        result["usage"] = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }

    # If empty, return raw response as dict
    if not result:
        result = response.as_dict() if hasattr(response, "as_dict") else {"raw": str(response)}

    return result


def list_serving_endpoints(limit: Optional[int] = 50) -> List[Dict[str, Any]]:
    """
    List Model Serving endpoints in the workspace.

    Args:
        limit: Maximum number of endpoints to return (default: 50). Pass None for all.

    Returns:
        List of endpoint dictionaries with keys:
        - name: Endpoint name
        - state: Current state (READY, NOT_READY, etc.)
        - creation_timestamp: When endpoint was created
        - creator: Who created the endpoint
        - served_entities_count: Number of served models

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        endpoints = list(client.serving_endpoints.list())
    except Exception as e:
        raise Exception(f"Failed to list serving endpoints: {str(e)}")

    result = []
    for ep in endpoints[:limit]:
        state = None
        if ep.state:
            state = ep.state.ready.value if ep.state.ready else None

        served_count = 0
        if ep.config and ep.config.served_entities:
            served_count = len(ep.config.served_entities)

        result.append(
            {
                "name": ep.name,
                "state": state,
                "creation_timestamp": ep.creation_timestamp,
                "creator": ep.creator,
                "served_entities_count": served_count,
            }
        )

    return result


def _resolve_endpoint_id(client: Any, name: str) -> str:
    """
    Resolve serving endpoint name to its ID.

    Args:
        client: Workspace client.
        name: Endpoint name.

    Returns:
        The endpoint's hex ID string.

    Raises:
        Exception: If endpoint not found.
    """
    try:
        endpoint = client.serving_endpoints.get(name=name)
    except (ResourceDoesNotExist, NotFound):
        raise Exception(f"Endpoint '{name}' not found.")
    return endpoint.id


def get_serving_endpoint_permissions(name: str) -> Dict[str, Any]:
    """
    Get the access control list for a serving endpoint.

    Args:
        name: Name of the serving endpoint.

    Returns:
        Dictionary with:
        - name: Endpoint name
        - permissions: List of ACL entries, each with:
            - principal: User email, group name, or service principal name
            - principal_type: "user", "group", or "service_principal"
            - permission_level: CAN_VIEW, CAN_QUERY, or CAN_MANAGE
            - inherited: Whether inherited from parent
    """
    client = get_workspace_client()
    endpoint_id = _resolve_endpoint_id(client, name)

    perms = client.serving_endpoints.get_permissions(serving_endpoint_id=endpoint_id)

    result_perms = []
    if perms.access_control_list:
        for acl in perms.access_control_list:
            # Determine principal type and name
            if acl.user_name:
                principal, principal_type = acl.user_name, "user"
            elif acl.group_name:
                principal, principal_type = acl.group_name, "group"
            elif acl.service_principal_name:
                principal, principal_type = acl.service_principal_name, "service_principal"
            else:
                continue

            if acl.all_permissions:
                for perm in acl.all_permissions:
                    level = perm.permission_level.value if perm.permission_level else None
                    result_perms.append(
                        {
                            "principal": principal,
                            "principal_type": principal_type,
                            "permission_level": level,
                            "inherited": perm.inherited or False,
                        }
                    )

    return {
        "name": name,
        "permissions": result_perms,
    }


def update_serving_endpoint_permissions(
    name: str,
    access_control_list: List[Dict[str, str]],
) -> Dict[str, Any]:
    """
    Update permissions for a serving endpoint (additive merge).

    Grants or modifies permissions for users, groups, or service principals.
    Existing permissions not in the list are left unchanged.

    Args:
        name: Name of the serving endpoint.
        access_control_list: List of permission entries. Each dict should have:
            - permission_level: "CAN_VIEW", "CAN_QUERY", or "CAN_MANAGE"
            - One of: user_name, group_name, or service_principal_name

    Returns:
        Dictionary with:
        - name: Endpoint name
        - updated: Number of ACL entries applied
        - message: Confirmation message
    """
    client = get_workspace_client()
    endpoint_id = _resolve_endpoint_id(client, name)

    acl_requests = [
        ServingEndpointAccessControlRequest(
            user_name=entry.get("user_name"),
            group_name=entry.get("group_name"),
            service_principal_name=entry.get("service_principal_name"),
            permission_level=entry.get("permission_level"),
        )
        for entry in access_control_list
    ]

    client.serving_endpoints.update_permissions(
        serving_endpoint_id=endpoint_id,
        access_control_list=acl_requests,
    )

    return {
        "name": name,
        "updated": len(acl_requests),
        "message": f"Permissions updated for endpoint '{name}'.",
    }
