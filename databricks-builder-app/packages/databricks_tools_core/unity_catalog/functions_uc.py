"""
Unity Catalog - Function Operations

Functions for managing UC functions (UDFs).
Note: Creating functions requires SQL (CREATE FUNCTION statement).
Use execute_sql or the security_policies module for function creation.
"""

from typing import List
from databricks.sdk.service.catalog import FunctionInfo

from ..auth import get_workspace_client


def list_functions(catalog_name: str, schema_name: str) -> List[FunctionInfo]:
    """
    List all functions in a schema.

    Args:
        catalog_name: Name of the catalog
        schema_name: Name of the schema

    Returns:
        List of FunctionInfo objects with function metadata

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(
        w.functions.list(
            catalog_name=catalog_name,
            schema_name=schema_name,
        )
    )


def get_function(full_function_name: str) -> FunctionInfo:
    """
    Get detailed information about a specific function.

    Args:
        full_function_name: Full function name (catalog.schema.function format)

    Returns:
        FunctionInfo object with function metadata including:
        - name, full_name, catalog_name, schema_name
        - input_params, return_params, routine_body
        - owner, comment, created_at

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.functions.get(name=full_function_name)


def delete_function(full_function_name: str, force: bool = False) -> None:
    """
    Delete a function from Unity Catalog.

    Args:
        full_function_name: Full function name (catalog.schema.function format)
        force: If True, force deletion

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.functions.delete(name=full_function_name, force=force)
