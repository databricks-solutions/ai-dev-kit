"""
Unity Catalog - Schema Operations

Functions for managing schemas (databases) in Unity Catalog.
"""
from typing import List, Optional
from databricks.sdk.service.catalog import SchemaInfo

from ..auth import get_workspace_client


def list_schemas(catalog_name: str) -> list[SchemaInfo]:
    """
    List all schemas in a catalog.

    Args:
        catalog_name: Name of the catalog

    Returns:
        List of SchemaInfo objects with schema metadata

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(w.schemas.list(catalog_name=catalog_name))


def get_schema(full_schema_name: str) -> SchemaInfo:
    """
    Get detailed information about a specific schema.

    Args:
        full_schema_name: Full schema name (catalog.schema format)

    Returns:
        SchemaInfo object with schema metadata including:
        - name, full_name, catalog_name, owner, comment
        - created_at, updated_at
        - storage_location

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.schemas.get(full_name=full_schema_name)


def create_schema(
    catalog_name: str,
    schema_name: str,
    comment: str | None = None
) -> SchemaInfo:
    """
    Create a new schema in Unity Catalog.

    Args:
        catalog_name: Name of the catalog
        schema_name: Name of the schema to create
        comment: Optional description of the schema

    Returns:
        SchemaInfo object with created schema metadata

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.schemas.create(
        name=schema_name,
        catalog_name=catalog_name,
        comment=comment
    )


def update_schema(
    full_schema_name: str,
    new_name: str | None = None,
    comment: str | None = None,
    owner: str | None = None
) -> SchemaInfo:
    """
    Update an existing schema in Unity Catalog.

    Args:
        full_schema_name: Full schema name (catalog.schema format)
        new_name: New name for the schema
        comment: New comment/description
        owner: New owner

    Returns:
        SchemaInfo object with updated schema metadata

    Raises:
        ValueError: If no fields are provided to update
        DatabricksError: If API request fails
    """
    if not any([new_name, comment, owner]):
        raise ValueError("At least one field (new_name, comment, or owner) must be provided")

    w = get_workspace_client()
    return w.schemas.update(
        full_name=full_schema_name,
        new_name=new_name,
        comment=comment,
        owner=owner
    )


def delete_schema(full_schema_name: str) -> None:
    """
    Delete a schema from Unity Catalog.

    Args:
        full_schema_name: Full schema name (catalog.schema format)

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.schemas.delete(full_name=full_schema_name)
