"""
Lakebase Catalog Operations

Functions for registering Lakebase database instances with Unity Catalog.
"""

import logging
from typing import Any, Dict

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def create_lakebase_catalog(
    name: str,
    instance_name: str,
    database_name: str = "databricks_postgres",
    create_database_if_not_exists: bool = False,
) -> Dict[str, Any]:
    """
    Register a Lakebase database instance as a Unity Catalog catalog.

    This makes the Lakebase PostgreSQL database discoverable and
    governable through Unity Catalog. The catalog is read-only.

    Args:
        name: Catalog name in Unity Catalog
        instance_name: Lakebase instance name to register
        database_name: PostgreSQL database name to register
            (default: "databricks_postgres")
        create_database_if_not_exists: If True, create the Postgres database
            if it does not exist (default: False)

    Returns:
        Dictionary with:
        - name: Catalog name
        - instance_name: Associated instance
        - database_name: PostgreSQL database name
        - status: Registration result

    Raises:
        Exception: If registration fails
    """
    client = get_workspace_client()

    try:
        from databricks.sdk.service.database import DatabaseCatalog

        client.database.create_database_catalog(
            DatabaseCatalog(
                name=name,
                database_instance_name=instance_name,
                database_name=database_name,
                create_database_if_not_exists=create_database_if_not_exists,
            )
        )

        return {
            "name": name,
            "instance_name": instance_name,
            "database_name": database_name,
            "status": "created",
            "message": f"Catalog '{name}' registered for instance '{instance_name}', database '{database_name}'.",
        }
    except Exception as e:
        error_msg = str(e)
        if "ALREADY_EXISTS" in error_msg or "already exists" in error_msg.lower():
            return {
                "name": name,
                "instance_name": instance_name,
                "status": "ALREADY_EXISTS",
                "error": f"Catalog '{name}' already exists",
            }
        raise Exception(f"Failed to create Lakebase catalog '{name}': {error_msg}")


def get_lakebase_catalog(name: str) -> Dict[str, Any]:
    """
    Get details of a Lakebase catalog registered in Unity Catalog.

    Args:
        name: Catalog name

    Returns:
        Dictionary with catalog details

    Raises:
        Exception: If API request fails
    """
    client = get_workspace_client()

    try:
        catalog = client.database.get_database_catalog(name=name)
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
                "error": f"Catalog '{name}' not found",
            }
        raise Exception(f"Failed to get Lakebase catalog '{name}': {error_msg}")

    result: Dict[str, Any] = {"name": name}

    if hasattr(catalog, "database_instance_name") and catalog.database_instance_name:
        result["instance_name"] = catalog.database_instance_name

    if hasattr(catalog, "database_name") and catalog.database_name:
        result["database_name"] = catalog.database_name

    if hasattr(catalog, "state") and catalog.state:
        result["state"] = str(catalog.state)

    return result


def delete_lakebase_catalog(name: str) -> Dict[str, Any]:
    """
    Remove a Lakebase catalog registration from Unity Catalog.

    This does not delete the underlying database instance.

    Args:
        name: Catalog name to remove

    Returns:
        Dictionary with:
        - name: Catalog name
        - status: "deleted" or error info

    Raises:
        Exception: If deletion fails
    """
    client = get_workspace_client()

    try:
        client.database.delete_database_catalog(name=name)
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
                "error": f"Catalog '{name}' not found",
            }
        raise Exception(f"Failed to delete Lakebase catalog '{name}': {error_msg}")
