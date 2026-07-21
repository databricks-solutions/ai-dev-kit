"""
Lakebase Autoscaling Compute (Endpoint) Operations

Functions for creating, managing, and deleting compute endpoints
within Lakebase Autoscaling branches.
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_endpoint(
    branch_name: str,
    endpoint_id: str,
    endpoint_type: str = "ENDPOINT_TYPE_READ_WRITE",
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create a compute endpoint on a branch.

    Args:
        branch_name: Branch resource name
            (e.g., "projects/my-app/branches/production")
        endpoint_id: Endpoint identifier (1-63 chars, lowercase letters,
            digits, hyphens)
        endpoint_type: Endpoint type: "ENDPOINT_TYPE_READ_WRITE" or
            "ENDPOINT_TYPE_READ_ONLY". Default: "ENDPOINT_TYPE_READ_WRITE"
        autoscaling_limit_min_cu: Minimum compute units (0.5-32)
        autoscaling_limit_max_cu: Maximum compute units (0.5-112)
        scale_to_zero_seconds: Inactivity timeout before suspending.
            Set to 0 to disable scale-to-zero.

    Returns:
        Dictionary with:
        - name: Endpoint resource name
        - host: Connection hostname
        - status: Creation status

    Raises:
        Exception: If creation fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType

        ep_type = EndpointType(endpoint_type)

        spec_kwargs: Dict[str, Any] = {
            "endpoint_type": ep_type,
        }

        if autoscaling_limit_min_cu is not None:
            spec_kwargs["autoscaling_limit_min_cu"] = autoscaling_limit_min_cu
        if autoscaling_limit_max_cu is not None:
            spec_kwargs["autoscaling_limit_max_cu"] = autoscaling_limit_max_cu
        if scale_to_zero_seconds is not None:
            from databricks.sdk.service.postgres import Duration

            spec_kwargs["suspend_timeout_duration"] = Duration(seconds=scale_to_zero_seconds)

        operation = client.postgres.create_endpoint(
            parent=branch_name,
            endpoint=Endpoint(spec=EndpointSpec(**spec_kwargs)),
            endpoint_id=endpoint_id,
        )
        result_ep = operation.wait()

        result: Dict[str, Any] = {
            "name": result_ep.name,
            "status": "CREATED",
        }

        if result_ep.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("endpoint_type", "endpoint_type", str),
                ("autoscaling_limit_min_cu", "min_cu", None),
                ("autoscaling_limit_max_cu", "max_cu", None),
            ]:
                try:
                    val = getattr(result_ep.status, attr)
                    if val is not None:
                        result[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

            try:
                if result_ep.status.hosts and result_ep.status.hosts.host:
                    result["host"] = result_ep.status.hosts.host
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": f"{branch_name}/endpoints/{endpoint_id}",
                "status": "ALREADY_EXISTS",
                "error": f"Endpoint '{endpoint_id}' already exists on branch",
            }
        raise Exception(f"Failed to create endpoint '{endpoint_id}': {error_msg}")


def get_endpoint(name: str) -> Dict[str, Any]:
    """
    Get Lakebase Autoscaling endpoint details.

    Args:
        name: Endpoint resource name
            (e.g., "projects/my-app/branches/production/endpoints/ep-primary")

    Returns:
        Dictionary with:
        - name: Endpoint resource name
        - state: Current state (ACTIVE, SUSPENDED, etc.)
        - endpoint_type: READ_WRITE or READ_ONLY
        - host: Connection hostname
        - min_cu: Minimum compute units
        - max_cu: Maximum compute units

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        endpoint = client.postgres.get_endpoint(name=name)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower() or "does not exist" in error_msg.lower() or "404" in error_msg:
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"Endpoint '{name}' not found",
            }
        raise Exception(f"Failed to get endpoint '{name}': {error_msg}")

    result: Dict[str, Any] = {"name": endpoint.name}

    if endpoint.status:
        for attr, key, transform in [
            ("current_state", "state", str),
            ("endpoint_type", "endpoint_type", str),
            ("autoscaling_limit_min_cu", "min_cu", None),
            ("autoscaling_limit_max_cu", "max_cu", None),
        ]:
            try:
                val = getattr(endpoint.status, attr)
                if val is not None:
                    result[key] = transform(val) if transform else val
            except (KeyError, AttributeError):
                pass

        try:
            if endpoint.status.hosts and endpoint.status.hosts.host:
                result["host"] = endpoint.status.hosts.host
        except (KeyError, AttributeError):
            pass

    return result


def list_endpoints(branch_name: str) -> List[Dict[str, Any]]:
    """
    List all endpoints on a branch.

    Args:
        branch_name: Branch resource name
            (e.g., "projects/my-app/branches/production")

    Returns:
        List of endpoint dictionaries with name, state, type, CU settings.

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        response = client.postgres.list_endpoints(parent=branch_name)
    except Exception as e:
        raise Exception(f"Failed to list endpoints for '{branch_name}': {str(e)}")

    result = []
    endpoints = list(response) if response else []
    for ep in endpoints:
        entry: Dict[str, Any] = {"name": ep.name}

        if ep.status:
            for attr, key, transform in [
                ("current_state", "state", str),
                ("endpoint_type", "endpoint_type", str),
                ("autoscaling_limit_min_cu", "min_cu", None),
                ("autoscaling_limit_max_cu", "max_cu", None),
            ]:
                try:
                    val = getattr(ep.status, attr)
                    if val is not None:
                        entry[key] = transform(val) if transform else val
                except (KeyError, AttributeError):
                    pass

            try:
                if ep.status.hosts and ep.status.hosts.host:
                    entry["host"] = ep.status.hosts.host
            except (KeyError, AttributeError):
                pass

        result.append(entry)

    return result


def update_endpoint(
    name: str,
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Update a Lakebase Autoscaling endpoint (resize or configure scale-to-zero).

    Args:
        name: Endpoint resource name
            (e.g., "projects/my-app/branches/production/endpoints/ep-primary")
        autoscaling_limit_min_cu: New minimum compute units (0.5-32)
        autoscaling_limit_max_cu: New maximum compute units (0.5-112)
        scale_to_zero_seconds: New inactivity timeout. 0 to disable.

    Returns:
        Dictionary with updated endpoint details

    Raises:
        Exception: If update fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.postgres import Endpoint, EndpointSpec, EndpointType, FieldMask

        spec_kwargs: Dict[str, Any] = {}
        update_fields: list[str] = []

        if autoscaling_limit_min_cu is not None:
            spec_kwargs["autoscaling_limit_min_cu"] = autoscaling_limit_min_cu
            update_fields.append("spec.autoscaling_limit_min_cu")

        if autoscaling_limit_max_cu is not None:
            spec_kwargs["autoscaling_limit_max_cu"] = autoscaling_limit_max_cu
            update_fields.append("spec.autoscaling_limit_max_cu")

        if scale_to_zero_seconds is not None:
            from databricks.sdk.service.postgres import Duration

            spec_kwargs["suspend_timeout_duration"] = Duration(seconds=scale_to_zero_seconds)
            update_fields.append("spec.suspend_timeout_duration")

        if not update_fields:
            return {
                "name": name,
                "status": "NO_CHANGES",
                "error": "No fields specified for update",
            }

        # EndpointSpec requires endpoint_type -- fetch it from the current endpoint
        existing_ep = client.postgres.get_endpoint(name=name)
        ep_type = (
            existing_ep.spec.endpoint_type
            if existing_ep.spec and existing_ep.spec.endpoint_type
            else EndpointType.ENDPOINT_TYPE_READ_WRITE
        )
        spec_kwargs["endpoint_type"] = ep_type

        operation = client.postgres.update_endpoint(
            name=name,
            endpoint=Endpoint(
                name=name,
                spec=EndpointSpec(**spec_kwargs),
            ),
            update_mask=FieldMask(field_mask=update_fields),
        )
        result_ep = operation.wait()

        result: Dict[str, Any] = {
            "name": name,
            "status": "UPDATED",
        }

        if autoscaling_limit_min_cu is not None:
            result["min_cu"] = autoscaling_limit_min_cu
        if autoscaling_limit_max_cu is not None:
            result["max_cu"] = autoscaling_limit_max_cu

        if result_ep and result_ep.status:
            try:
                if result_ep.status.current_state:
                    result["state"] = str(result_ep.status.current_state)
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        raise Exception(f"Failed to update endpoint '{name}': {str(e)}")


def delete_endpoint(name: str, max_retries: int = 6, retry_delay: int = 10) -> Dict[str, Any]:
    """
    Delete a Lakebase Autoscaling endpoint.

    Retries on ``Aborted`` errors (reconciliation in progress).

    Args:
        name: Endpoint resource name
            (e.g., "projects/my-app/branches/production/endpoints/ep-primary")
        max_retries: Maximum number of retries for transient errors.
        retry_delay: Seconds to wait between retries.

    Returns:
        Dictionary with:
        - name: Endpoint resource name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails after retries
    """
    import time

    client = get_workspace_client()

    for attempt in range(max_retries + 1):
        try:
            operation = client.postgres.delete_endpoint(name=name)
            operation.wait()
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
            if ("reconciliation" in error_msg.lower() or "aborted" in error_msg.lower()) and attempt < max_retries:
                logger.info(
                    f"Endpoint reconciliation in progress, retrying in {retry_delay}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(retry_delay)
                continue
            raise Exception(f"Failed to delete endpoint '{name}': {error_msg}")
