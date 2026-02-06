"""
Unity Catalog - Catalog Operations

Functions for managing catalogs in Unity Catalog.
"""
from typing import Dict, List, Optional
from databricks.sdk.service.catalog import CatalogInfo, IsolationMode

from ..auth import get_workspace_client


def list_catalogs() -> list[CatalogInfo]:
    """
    List all catalogs in Unity Catalog.

    Returns:
        List of CatalogInfo objects with catalog metadata

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(w.catalogs.list())


def get_catalog(catalog_name: str) -> CatalogInfo:
    """
    Get detailed information about a specific catalog.

    Args:
        catalog_name: Name of the catalog

    Returns:
        CatalogInfo object with catalog metadata including:
        - name, full_name, owner, comment
        - created_at, updated_at
        - storage_location

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.catalogs.get(name=catalog_name)


def create_catalog(
    name: str,
    comment: str | None = None,
    storage_root: str | None = None,
    properties: dict[str, str] | None = None,
) -> CatalogInfo:
    """
    Create a new catalog in Unity Catalog.

    Args:
        name: Name of the catalog to create
        comment: Optional description
        storage_root: Optional managed storage location (cloud URL)
        properties: Optional key-value properties

    Returns:
        CatalogInfo object with created catalog metadata

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: dict = {"name": name}
    if comment is not None:
        kwargs["comment"] = comment
    if storage_root is not None:
        kwargs["storage_root"] = storage_root
    if properties is not None:
        kwargs["properties"] = properties
    return w.catalogs.create(**kwargs)


def update_catalog(
    catalog_name: str,
    new_name: str | None = None,
    comment: str | None = None,
    owner: str | None = None,
    isolation_mode: str | None = None,
) -> CatalogInfo:
    """
    Update an existing catalog in Unity Catalog.

    Args:
        catalog_name: Current name of the catalog
        new_name: New name for the catalog
        comment: New comment/description
        owner: New owner (user or group)
        isolation_mode: Isolation mode ("OPEN" or "ISOLATED")

    Returns:
        CatalogInfo object with updated catalog metadata

    Raises:
        ValueError: If no fields are provided to update
        DatabricksError: If API request fails
    """
    if not any([new_name, comment, owner, isolation_mode]):
        raise ValueError("At least one field must be provided to update")

    w = get_workspace_client()
    kwargs: dict = {"name": catalog_name}
    if new_name is not None:
        kwargs["new_name"] = new_name
    if comment is not None:
        kwargs["comment"] = comment
    if owner is not None:
        kwargs["owner"] = owner
    if isolation_mode is not None:
        kwargs["isolation_mode"] = IsolationMode(isolation_mode)
    return w.catalogs.update(**kwargs)


def delete_catalog(catalog_name: str, force: bool = False) -> None:
    """
    Delete a catalog from Unity Catalog.

    Args:
        catalog_name: Name of the catalog to delete
        force: If True, force deletion even if catalog contains schemas

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.catalogs.delete(name=catalog_name, force=force)
