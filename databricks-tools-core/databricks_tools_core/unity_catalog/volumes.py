"""
Unity Catalog - Volume Operations

Functions for managing volumes in Unity Catalog.
"""
from typing import Dict, List, Optional
from databricks.sdk.service.catalog import VolumeInfo, VolumeType

from ..auth import get_workspace_client


def list_volumes(catalog_name: str, schema_name: str) -> list[VolumeInfo]:
    """
    List all volumes in a schema.

    Args:
        catalog_name: Name of the catalog
        schema_name: Name of the schema

    Returns:
        List of VolumeInfo objects with volume metadata

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(w.volumes.list(
        catalog_name=catalog_name,
        schema_name=schema_name,
    ))


def get_volume(full_volume_name: str) -> VolumeInfo:
    """
    Get detailed information about a specific volume.

    Args:
        full_volume_name: Full volume name (catalog.schema.volume format)

    Returns:
        VolumeInfo object with volume metadata including:
        - name, full_name, catalog_name, schema_name
        - volume_type, owner, comment
        - created_at, updated_at
        - storage_location

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.volumes.read(name=full_volume_name)


def create_volume(
    catalog_name: str,
    schema_name: str,
    name: str,
    volume_type: str = "MANAGED",
    comment: str | None = None,
    storage_location: str | None = None,
) -> VolumeInfo:
    """
    Create a new volume in Unity Catalog.

    Args:
        catalog_name: Name of the catalog
        schema_name: Name of the schema
        name: Name of the volume to create
        volume_type: "MANAGED" or "EXTERNAL" (default: "MANAGED")
        comment: Optional description
        storage_location: Required for EXTERNAL volumes (cloud storage URL)

    Returns:
        VolumeInfo object with created volume metadata

    Raises:
        ValueError: If EXTERNAL volume without storage_location
        DatabricksError: If API request fails
    """
    vtype = VolumeType(volume_type)
    if vtype == VolumeType.EXTERNAL and not storage_location:
        raise ValueError("storage_location is required for EXTERNAL volumes")

    w = get_workspace_client()
    kwargs: dict = {
        "catalog_name": catalog_name,
        "schema_name": schema_name,
        "name": name,
        "volume_type": vtype,
    }
    if comment is not None:
        kwargs["comment"] = comment
    if storage_location is not None:
        kwargs["storage_location"] = storage_location
    return w.volumes.create(**kwargs)


def update_volume(
    full_volume_name: str,
    new_name: str | None = None,
    comment: str | None = None,
    owner: str | None = None,
) -> VolumeInfo:
    """
    Update an existing volume.

    Args:
        full_volume_name: Full volume name (catalog.schema.volume format)
        new_name: New name for the volume
        comment: New comment/description
        owner: New owner

    Returns:
        VolumeInfo object with updated volume metadata

    Raises:
        ValueError: If no fields are provided to update
        DatabricksError: If API request fails
    """
    if not any([new_name, comment, owner]):
        raise ValueError("At least one field must be provided to update")

    w = get_workspace_client()
    kwargs: dict = {"name": full_volume_name}
    if new_name is not None:
        kwargs["new_name"] = new_name
    if comment is not None:
        kwargs["comment"] = comment
    if owner is not None:
        kwargs["owner"] = owner
    return w.volumes.update(**kwargs)


def delete_volume(full_volume_name: str) -> None:
    """
    Delete a volume from Unity Catalog.

    Args:
        full_volume_name: Full volume name (catalog.schema.volume format)

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.volumes.delete(name=full_volume_name)
