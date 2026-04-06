"""
Model Serving Endpoints Operations

Functions for managing Databricks Model Serving endpoints: status, query, create,
update, delete, logs, metrics, and permissions.
"""

import logging
import re
from datetime import timedelta
from typing import Any, Dict, List, Optional

from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from databricks.sdk.service.serving import (
    ChatMessage,
    EndpointCoreConfigInput,
    Route,
    ServedEntityInput,
    ServingEndpointAccessControlRequest,
    TrafficConfig,
)

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


# ============================================================================
# CRUD helpers
# ============================================================================


def _build_served_entity_inputs(served_entities: List[Dict[str, Any]]) -> List[ServedEntityInput]:
    """Convert list of dicts to ServedEntityInput objects.

    Supports all ServedEntityInput fields: basic config (entity_name, entity_version),
    scaling (workload_size OR min/max_provisioned_concurrency), GPU (workload_type),
    environment variables, provisioned throughput, and instance profiles.

    Three scaling modes are mutually exclusive:
    - workload_size: "Small"/"Medium"/"Large" (predefined)
    - min/max_provisioned_concurrency: custom concurrency (multiples of 4)
    - min/max_provisioned_throughput: tokens/sec for foundation models
    """
    result = []
    for e in served_entities:
        kwargs: Dict[str, Any] = {
            "entity_name": e.get("entity_name"),
            "entity_version": e.get("entity_version"),
            "scale_to_zero_enabled": e.get("scale_to_zero_enabled", True),
        }

        # Scaling: workload_size vs custom concurrency (mutually exclusive)
        if "min_provisioned_concurrency" in e or "max_provisioned_concurrency" in e:
            kwargs["min_provisioned_concurrency"] = e.get("min_provisioned_concurrency")
            kwargs["max_provisioned_concurrency"] = e.get("max_provisioned_concurrency")
        else:
            kwargs["workload_size"] = e.get("workload_size", "Small")

        # Provisioned throughput (foundation models)
        if "min_provisioned_throughput" in e:
            kwargs["min_provisioned_throughput"] = e["min_provisioned_throughput"]
        if "max_provisioned_throughput" in e:
            kwargs["max_provisioned_throughput"] = e["max_provisioned_throughput"]

        # GPU workload type
        if "workload_type" in e:
            kwargs["workload_type"] = e["workload_type"]

        # Environment variables (supports secret references)
        if "environment_vars" in e:
            kwargs["environment_vars"] = e["environment_vars"]

        # Custom entity name
        if "name" in e:
            kwargs["name"] = e["name"]

        # AWS instance profile
        if "instance_profile_arn" in e:
            kwargs["instance_profile_arn"] = e["instance_profile_arn"]

        result.append(ServedEntityInput(**kwargs))
    return result


def _build_traffic_config(traffic_config: Optional[Dict[str, Any]]) -> Optional[TrafficConfig]:
    """Convert traffic config dict to TrafficConfig object, or None."""
    if not traffic_config or not traffic_config.get("routes"):
        return None
    return TrafficConfig(
        routes=[
            Route(
                served_model_name=r.get("served_model_name"),
                traffic_percentage=r.get("traffic_percentage", 100),
            )
            for r in traffic_config["routes"]
        ]
    )


def _extract_endpoint_summary(endpoint: Any) -> Dict[str, Any]:
    """Extract common fields from an endpoint object into a dict."""
    state = None
    if endpoint.state and endpoint.state.ready:
        state = endpoint.state.ready.value

    served_entities = []
    if endpoint.config and endpoint.config.served_entities:
        for e in endpoint.config.served_entities:
            entity_info: Dict[str, Any] = {
                "name": e.name,
                "entity_name": e.entity_name,
                "entity_version": e.entity_version,
                "workload_size": getattr(e, "workload_size", None),
            }
            # Include extended fields when present
            for field in (
                "workload_type",
                "environment_vars",
                "instance_profile_arn",
                "min_provisioned_concurrency",
                "max_provisioned_concurrency",
                "min_provisioned_throughput",
                "max_provisioned_throughput",
            ):
                val = getattr(e, field, None)
                if val is not None:
                    entity_info[field] = val
            served_entities.append(entity_info)

    return {
        "name": endpoint.name,
        "state": state,
        "creation_timestamp": endpoint.creation_timestamp,
        "served_entities": served_entities,
    }


# ============================================================================
# CRUD operations
# ============================================================================


def create_serving_endpoint(
    name: str,
    served_entities: List[Dict[str, Any]],
    traffic_config: Optional[Dict[str, Any]] = None,
    timeout_minutes: int = 30,
    wait: bool = True,
    tags: Optional[Dict[str, str]] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new Model Serving endpoint.

    Args:
        name: Unique endpoint name (lowercase, alphanumeric, hyphens).
        served_entities: List of entities to serve. Each dict should contain:
            - entity_name: UC model path (e.g. "catalog.schema.model")
            - entity_version: Model version string (e.g. "1")
            - workload_size: "Small", "Medium", or "Large" (default: "Small")
            - scale_to_zero_enabled: bool (default: True)
            - workload_type: "CPU", "GPU_SMALL", "GPU_MEDIUM", "GPU_LARGE",
                or "MULTIGPU_MEDIUM" (default: CPU)
            - environment_vars: dict of env vars
            - min/max_provisioned_concurrency: custom concurrency
            - min/max_provisioned_throughput: tokens/sec (foundation models)
            - name: custom served entity name
            - instance_profile_arn: AWS IAM instance profile ARN
        traffic_config: Optional traffic routing with "routes" list for A/B testing.
        timeout_minutes: Max wait time when wait=True (default: 30).
        wait: If True, block until READY. If False, return immediately.
        tags: Optional dict of key-value tags.
        description: Optional human-readable description.

    Returns:
        Dictionary with:
        - name: Endpoint name
        - state: READY or CREATING
        - creation_timestamp: When created
        - served_entities: Configured entities
        - wait_needed: True if still deploying

    Raises:
        Exception: If endpoint already exists or creation fails
    """
    client = get_workspace_client()

    entity_inputs = _build_served_entity_inputs(served_entities)
    traffic_cfg = _build_traffic_config(traffic_config)
    config = EndpointCoreConfigInput(
        name=name,
        served_entities=entity_inputs,
        traffic_config=traffic_cfg,
    )

    # Build optional SDK tag objects
    sdk_tags = None
    if tags:
        from databricks.sdk.service.serving import EndpointTag

        sdk_tags = [EndpointTag(key=k, value=v) for k, v in tags.items()]

    try:
        if wait:
            endpoint = client.serving_endpoints.create_and_wait(
                name=name,
                config=config,
                tags=sdk_tags,
                description=description,
                timeout=timedelta(minutes=timeout_minutes),
            )
            result = _extract_endpoint_summary(endpoint)
            result["wait_needed"] = False
            return result

        # Return immediately for async deployment (agents take ~15 min)
        client.serving_endpoints.create(name=name, config=config, tags=sdk_tags, description=description)
        return {
            "name": name,
            "state": "CREATING",
            "creation_timestamp": None,
            "served_entities": served_entities,
            "wait_needed": True,
            "message": f"Endpoint '{name}' is being created. Poll with get_serving_endpoint_status('{name}').",
        }

    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            raise Exception(f"Endpoint '{name}' already exists. Use update_serving_endpoint() to modify it.")
        raise Exception(f"Failed to create serving endpoint '{name}': {error_msg}")


def update_serving_endpoint(
    name: str,
    served_entities: List[Dict[str, Any]],
    traffic_config: Optional[Dict[str, Any]] = None,
    timeout_minutes: int = 30,
    wait: bool = True,
) -> Dict[str, Any]:
    """
    Update an existing Model Serving endpoint configuration.

    Args:
        name: Name of the existing endpoint.
        served_entities: Updated entity list (same fields as create_serving_endpoint).
        traffic_config: Optional traffic routing with "routes" list.
        timeout_minutes: Max wait time when wait=True (default: 30).
        wait: If True, block until update completes. If False, return immediately.

    Returns:
        Dictionary with:
        - name: Endpoint name
        - state: Current state
        - config_update: Update status
        - served_entities: Updated entities
        - message: Status message

    Raises:
        Exception: If endpoint not found or update fails
    """
    client = get_workspace_client()

    # Verify endpoint exists
    try:
        client.serving_endpoints.get(name=name)
    except (ResourceDoesNotExist, NotFound):
        raise Exception(f"Endpoint '{name}' not found. Use create_serving_endpoint() to create it first.")

    entity_inputs = _build_served_entity_inputs(served_entities)
    traffic_cfg = _build_traffic_config(traffic_config)

    try:
        wait_obj = client.serving_endpoints.update_config(
            name=name,
            served_entities=entity_inputs,
            traffic_config=traffic_cfg,
        )

        if wait:
            endpoint = wait_obj.result(timeout=timedelta(minutes=timeout_minutes))
            result = _extract_endpoint_summary(endpoint)
            config_update = None
            if endpoint.state and endpoint.state.config_update:
                config_update = endpoint.state.config_update.value
            result["config_update"] = config_update
            result["message"] = f"Endpoint '{name}' updated successfully."
            return result

        return {
            "name": name,
            "state": "UPDATING",
            "config_update": "IN_PROGRESS",
            "pending_config": {"served_entities": served_entities},
            "message": f"Endpoint '{name}' update started. Poll with get_serving_endpoint_status('{name}').",
        }

    except Exception as e:
        raise Exception(f"Failed to update serving endpoint '{name}': {str(e)}")


def delete_serving_endpoint(name: str) -> Dict[str, Any]:
    """
    Delete a Model Serving endpoint.

    The underlying model in Unity Catalog is NOT deleted.

    Args:
        name: Name of the endpoint to delete.

    Returns:
        Dictionary with:
        - name: Endpoint name
        - status: "deleted" or "not_found"
        - message: Confirmation or error message
    """
    client = get_workspace_client()

    # Check existence first for a clear not-found message
    try:
        client.serving_endpoints.get(name=name)
    except (ResourceDoesNotExist, NotFound):
        return {
            "name": name,
            "status": "not_found",
            "message": f"Endpoint '{name}' not found. It may have already been deleted.",
        }

    try:
        client.serving_endpoints.delete(name=name)
        return {
            "name": name,
            "status": "deleted",
            "message": f"Endpoint '{name}' deleted successfully.",
        }
    except Exception as e:
        raise Exception(f"Failed to delete serving endpoint '{name}': {str(e)}")


# ============================================================================
# Logs
# ============================================================================


def _resolve_served_model_name(client: Any, name: str, served_model_name: Optional[str]) -> str:
    """
    Resolve served_model_name from endpoint config if not provided.

    Args:
        client: Workspace client.
        name: Endpoint name.
        served_model_name: Explicit served model name, or None to auto-resolve.

    Returns:
        The resolved served model name.

    Raises:
        Exception: If endpoint not found or has no served entities.
    """
    if served_model_name:
        return served_model_name

    try:
        endpoint = client.serving_endpoints.get(name=name)
    except (ResourceDoesNotExist, NotFound):
        raise Exception(f"Endpoint '{name}' not found.")

    if endpoint.config and endpoint.config.served_entities:
        resolved = endpoint.config.served_entities[0].name
        if resolved:
            return resolved

    raise Exception(f"Endpoint '{name}' has no served entities. Provide served_model_name explicitly.")


def get_serving_endpoint_build_logs(
    name: str,
    served_model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get build logs for a served model in an endpoint.

    Build logs contain container image creation output, dependency installation,
    and model download steps. Use this to debug failed or stuck deployments.

    Args:
        name: Name of the serving endpoint.
        served_model_name: Name of the served model. If omitted, auto-resolved
            from the first served entity in the endpoint config.

    Returns:
        Dictionary with:
        - name: Endpoint name
        - served_model_name: Resolved served model name
        - logs: Build log text (may be empty if no build has run)
    """
    client = get_workspace_client()
    resolved_name = _resolve_served_model_name(client, name, served_model_name)

    try:
        response = client.serving_endpoints.build_logs(
            name=name,
            served_model_name=resolved_name,
        )
        return {
            "name": name,
            "served_model_name": resolved_name,
            "logs": response.logs or "",
        }
    except (ResourceDoesNotExist, NotFound):
        raise Exception(
            f"Served model '{resolved_name}' not found on endpoint '{name}'. "
            "Check the served model name with get_serving_endpoint_status()."
        )


def get_serving_endpoint_server_logs(
    name: str,
    served_model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get runtime server logs for a served model in an endpoint.

    Server logs contain recent stdout/stderr from the model server, including
    inference request processing and application-level logging. Use this to
    debug prediction errors or unexpected model behavior.

    Args:
        name: Name of the serving endpoint.
        served_model_name: Name of the served model. If omitted, auto-resolved
            from the first served entity in the endpoint config.

    Returns:
        Dictionary with:
        - name: Endpoint name
        - served_model_name: Resolved served model name
        - logs: Recent server log lines (may be empty if no requests processed)
    """
    client = get_workspace_client()
    resolved_name = _resolve_served_model_name(client, name, served_model_name)

    try:
        response = client.serving_endpoints.logs(
            name=name,
            served_model_name=resolved_name,
        )
        return {
            "name": name,
            "served_model_name": resolved_name,
            "logs": response.logs or "",
        }
    except (ResourceDoesNotExist, NotFound):
        raise Exception(
            f"Served model '{resolved_name}' not found on endpoint '{name}'. "
            "Check the served model name with get_serving_endpoint_status()."
        )


# ============================================================================
# Metrics
# ============================================================================


def _parse_prometheus_metrics(text: str) -> List[Dict[str, Any]]:
    """
    Parse Prometheus exposition format into structured dicts.

    Args:
        text: Raw Prometheus/OpenMetrics text.

    Returns:
        List of metric dicts, each with:
        - name: Metric name
        - labels: Dict of label key-value pairs
        - value: Numeric metric value
        - help: Metric description (from HELP comment)
        - type: Prometheus type (gauge, histogram, counter)
    """
    metrics = []
    help_map: Dict[str, str] = {}
    type_map: Dict[str, str] = {}

    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("# HELP "):
            parts = line[7:].split(" ", 1)
            if len(parts) == 2:
                help_map[parts[0]] = parts[1]
            continue
        if line.startswith("# TYPE "):
            parts = line[7:].split(" ", 1)
            if len(parts) == 2:
                type_map[parts[0]] = parts[1]
            continue
        if line.startswith("#"):
            continue

        # Parse: metric_name{label="val",...} value [timestamp]
        match = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)\{?(.*?)\}?\s+(.+)$", line)
        if not match:
            continue

        name = match.group(1)
        labels_str = match.group(2)
        # Value may be followed by optional timestamp — take first token only
        value_str = match.group(3).split()[0]

        labels = {}
        if labels_str:
            for pair in re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"', labels_str):
                labels[pair[0]] = pair[1]

        try:
            value = float(value_str)
        except ValueError:
            value = value_str

        metrics.append(
            {
                "name": name,
                "labels": labels,
                "value": value,
                "help": help_map.get(name),
                "type": type_map.get(name),
            }
        )

    return metrics


def export_serving_endpoint_metrics(name: str) -> Dict[str, Any]:
    """
    Export health metrics for a serving endpoint.

    Returns metrics in structured format, parsed from the Prometheus/OpenMetrics
    exposition format returned by the API. Includes CPU, memory, request latency,
    request counts, error rates, and GPU metrics (if applicable).

    Args:
        name: Name of the serving endpoint.

    Returns:
        Dictionary with:
        - name: Endpoint name
        - metrics: List of metric dicts (name, labels, value, help, type)
        - raw: Raw Prometheus text (for direct scraping use)
    """
    client = get_workspace_client()

    try:
        response = client.serving_endpoints.export_metrics(name=name)
        raw_text = response.contents.read().decode("utf-8")
    except (ResourceDoesNotExist, NotFound):
        raise Exception(f"Endpoint '{name}' not found.")
    except Exception as e:
        raise Exception(f"Failed to export metrics for endpoint '{name}': {str(e)}")

    metrics = _parse_prometheus_metrics(raw_text)

    return {
        "name": name,
        "metrics": metrics,
        "raw": raw_text,
    }


# ============================================================================
# Permissions
# ============================================================================


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
