"""
Lakebase Provisioned Instance Operations

Functions for creating, managing, and connecting to Lakebase Provisioned
(managed PostgreSQL) database instances.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_lakebase_instance(
    name: str,
    capacity: str = "CU_1",
    stopped: bool = False,
) -> Dict[str, Any]:
    """
    Create a Lakebase Provisioned database instance.

    Args:
        name: Instance name (1-63 characters, letters and hyphens only)
        capacity: Compute capacity: "CU_1", "CU_2", "CU_4", or "CU_8"
        stopped: If True, create in stopped state (default: False)

    Returns:
        Dictionary with:
        - name: Instance name
        - capacity: Compute capacity
        - state: Instance state
        - read_write_dns: DNS endpoint for connections (if available)

    Raises:
        Exception: If creation fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.database import DatabaseInstance

        instance = client.database.create_database_instance(
            DatabaseInstance(
                name=name,
                capacity=capacity,
                stopped=stopped,
            )
        )

        result: Dict[str, Any] = {
            "name": name,
            "capacity": capacity,
            "status": "CREATING",
            "message": f"Instance '{name}' creation initiated. Use get_lakebase_instance('{name}') to check status.",
        }

        if instance:
            try:
                if instance.state:
                    result["state"] = str(instance.state)
            except (KeyError, AttributeError):
                pass
            try:
                if instance.read_write_dns:
                    result["read_write_dns"] = instance.read_write_dns
            except (KeyError, AttributeError):
                pass

        return result
    except Exception as e:
        error_msg = str(e)
        if (
            "ALREADY_EXISTS" in error_msg
            or "already exists" in error_msg.lower()
            or "not unique" in error_msg.lower()
        ):
            return {
                "name": name,
                "status": "ALREADY_EXISTS",
                "error": f"Instance '{name}' already exists",
            }
        raise Exception(f"Failed to create Lakebase instance '{name}': {error_msg}")


def get_lakebase_instance(name: str) -> Dict[str, Any]:
    """
    Get Lakebase Provisioned instance details.

    Args:
        name: Instance name

    Returns:
        Dictionary with:
        - name: Instance name
        - state: Current state (e.g., RUNNING, STOPPED, CREATING)
        - capacity: Compute capacity (CU_1, CU_2, CU_4, CU_8)
        - read_write_dns: DNS endpoint for read-write connections
        - read_only_dns: DNS endpoint for read-only connections (if available)
        - creator: Who created the instance
        - creation_time: When instance was created

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        instance = client.database.get_database_instance(name=name)
    except Exception as e:
        error_msg = str(e)
        if (
            "not found" in error_msg.lower()
            or "does not exist" in error_msg.lower()
            or "404" in error_msg
        ):
            return {
                "name": name,
                "state": "NOT_FOUND",
                "error": f"Instance '{name}' not found",
            }
        raise Exception(f"Failed to get Lakebase instance '{name}': {error_msg}")

    result: Dict[str, Any] = {"name": instance.name}

    # Use try/except for SDK response objects where hasattr is unreliable
    for attr, key, transform in [
        ("state", "state", str),
        ("capacity", "capacity", str),
        ("read_write_dns", "read_write_dns", None),
        ("read_only_dns", "read_only_dns", None),
        ("creator", "creator", None),
        ("creation_time", "creation_time", str),
        ("uid", "uid", None),
    ]:
        try:
            val = getattr(instance, attr)
            if val is not None:
                result[key] = transform(val) if transform else val
        except (KeyError, AttributeError):
            pass

    # stopped can be False, so check explicitly
    try:
        if instance.stopped is not None:
            result["stopped"] = instance.stopped
    except (KeyError, AttributeError):
        pass

    return result


def list_lakebase_instances() -> List[Dict[str, Any]]:
    """
    List all Lakebase Provisioned instances in the workspace.

    Returns:
        List of instance dictionaries with:
        - name: Instance name
        - state: Current state
        - capacity: Compute capacity
        - stopped: Whether instance is stopped

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        response = client.database.list_database_instances()
    except Exception as e:
        raise Exception(f"Failed to list Lakebase instances: {str(e)}")

    result = []
    instances = list(response) if response else []
    for inst in instances:
        entry: Dict[str, Any] = {"name": inst.name}

        for attr, key, transform in [
            ("state", "state", str),
            ("capacity", "capacity", str),
            ("read_write_dns", "read_write_dns", None),
        ]:
            try:
                val = getattr(inst, attr)
                if val is not None:
                    entry[key] = transform(val) if transform else val
            except (KeyError, AttributeError):
                pass

        try:
            if inst.stopped is not None:
                entry["stopped"] = inst.stopped
        except (KeyError, AttributeError):
            pass

        result.append(entry)

    return result


def update_lakebase_instance(
    name: str,
    capacity: Optional[str] = None,
    stopped: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Update a Lakebase Provisioned instance (resize or start/stop).

    Args:
        name: Instance name
        capacity: New compute capacity: "CU_1", "CU_2", "CU_4", or "CU_8"
        stopped: True to stop instance (saves cost), False to start it

    Returns:
        Dictionary with updated instance details

    Raises:
        Exception: If update fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.database import DatabaseInstance

        update_fields: Dict[str, Any] = {"name": name}
        if capacity is not None:
            update_fields["capacity"] = capacity
        if stopped is not None:
            update_fields["stopped"] = stopped

        instance = client.database.update_database_instance(
            name=name,
            database_instance=DatabaseInstance(**update_fields),
            update_mask="*",
        )

        result: Dict[str, Any] = {
            "name": name,
            "status": "UPDATED",
        }

        if capacity is not None:
            result["capacity"] = capacity
        if stopped is not None:
            result["stopped"] = stopped

        if instance:
            if hasattr(instance, "state") and instance.state:
                result["state"] = str(instance.state)

        return result
    except Exception as e:
        raise Exception(f"Failed to update Lakebase instance '{name}': {str(e)}")


def delete_lakebase_instance(
    name: str,
    force: bool = False,
    purge: bool = True,
) -> Dict[str, Any]:
    """
    Delete a Lakebase Provisioned instance.

    Args:
        name: Instance name to delete
        force: If True, delete child instances as well (default: False)
        purge: Required to be True to confirm deletion (default: True)

    Returns:
        Dictionary with:
        - name: Instance name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails
    """
    client = get_workspace_client()

    try:
        client.database.delete_database_instance(
            name=name,
            force=force,
            purge=purge,
        )
        return {
            "name": name,
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
                "name": name,
                "status": "NOT_FOUND",
                "error": f"Instance '{name}' not found",
            }
        raise Exception(f"Failed to delete Lakebase instance '{name}': {error_msg}")


def generate_lakebase_credential(
    instance_names: List[str],
) -> Dict[str, Any]:
    """
    Generate an OAuth token for connecting to Lakebase instances.

    The token is valid for 1 hour. Use it as the password in PostgreSQL
    connection strings with sslmode=require.

    Args:
        instance_names: List of instance names to generate credentials for

    Returns:
        Dictionary with:
        - token: OAuth token (use as password in connection string)
        - expiration: Token expiration info
        - instance_names: Instances the token is valid for

    Raises:
        Exception: If credential generation fails
    """
    client = get_workspace_client()

    try:
        cred = client.database.generate_database_credential(
            request_id=str(uuid.uuid4()),
            instance_names=instance_names,
        )

        result: Dict[str, Any] = {
            "instance_names": instance_names,
        }

        if hasattr(cred, "token") and cred.token:
            result["token"] = cred.token

        if hasattr(cred, "expiration_time") and cred.expiration_time:
            result["expiration_time"] = str(cred.expiration_time)

        result["message"] = (
            "Token generated. Valid for ~1 hour. Use as password with sslmode=require."
        )

        return result
    except Exception as e:
        raise Exception(f"Failed to generate Lakebase credentials: {str(e)}")
