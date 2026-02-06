"""
Unity Catalog - Connection Operations

Functions for managing Lakehouse Federation foreign connections.
"""
import re
from typing import Any, Dict, List, Optional
from databricks.sdk.service.catalog import ConnectionInfo, ConnectionType

from ..auth import get_workspace_client

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.\-]*$")


def _validate_identifier(name: str) -> str:
    """Validate a SQL identifier to prevent injection."""
    if not _IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Invalid SQL identifier: '{name}'")
    return name


def _execute_uc_sql(sql_query: str, warehouse_id: str | None = None) -> list[dict[str, Any]]:
    """Execute SQL using the existing execute_sql infrastructure."""
    from ..sql.sql import execute_sql
    return execute_sql(sql_query=sql_query, warehouse_id=warehouse_id)


def list_connections() -> list[ConnectionInfo]:
    """
    List all foreign connections.

    Returns:
        List of ConnectionInfo objects

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(w.connections.list())


def get_connection(name: str) -> ConnectionInfo:
    """
    Get a specific foreign connection.

    Args:
        name: Name of the connection

    Returns:
        ConnectionInfo with connection details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.connections.get(name=name)


def create_connection(
    name: str,
    connection_type: str,
    options: dict[str, str],
    comment: str | None = None,
) -> ConnectionInfo:
    """
    Create a foreign connection for Lakehouse Federation.

    Args:
        name: Name for the connection
        connection_type: Type of connection. Valid values:
            "SNOWFLAKE", "POSTGRESQL", "MYSQL", "SQLSERVER", "BIGQUERY",
            "REDSHIFT", "SQLDW"
        options: Connection options dict. Common keys:
            - host: Database hostname
            - port: Database port
            - user: Username
            - password: Password (use secret('scope', 'key') for security)
            - database: Database name
            - warehouse: Snowflake warehouse
            - httpPath: For some connectors
        comment: Optional description

    Returns:
        ConnectionInfo with created connection details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: dict[str, Any] = {
        "name": name,
        "connection_type": ConnectionType(connection_type.upper()),
        "options": options,
    }
    if comment is not None:
        kwargs["comment"] = comment
    return w.connections.create(**kwargs)


def update_connection(
    name: str,
    options: dict[str, str] | None = None,
    new_name: str | None = None,
    owner: str | None = None,
) -> ConnectionInfo:
    """
    Update a foreign connection.

    Args:
        name: Current name of the connection
        options: New connection options
        new_name: New name for the connection
        owner: New owner

    Returns:
        ConnectionInfo with updated details

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    kwargs: dict[str, Any] = {"name": name}
    if options is not None:
        kwargs["options"] = options
    if new_name is not None:
        kwargs["new_name"] = new_name
    if owner is not None:
        kwargs["owner"] = owner
    return w.connections.update(**kwargs)


def delete_connection(name: str) -> None:
    """
    Delete a foreign connection.

    Args:
        name: Name of the connection to delete

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.connections.delete(name=name)


def create_foreign_catalog(
    catalog_name: str,
    connection_name: str,
    catalog_options: dict[str, str] | None = None,
    comment: str | None = None,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a foreign catalog using a connection (Lakehouse Federation).

    Args:
        catalog_name: Name for the new foreign catalog
        connection_name: Name of the connection to use
        catalog_options: Options (e.g., {"database": "my_db"})
        comment: Optional description
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL
    """
    _validate_identifier(catalog_name)
    _validate_identifier(connection_name)

    sql = f"CREATE FOREIGN CATALOG {catalog_name} USING CONNECTION {connection_name}"
    if catalog_options:
        opts = ", ".join(f"'{k}' = '{v}'" for k, v in catalog_options.items())
        sql += f" OPTIONS ({opts})"
    if comment:
        escaped = comment.replace("'", "\\'")
        sql += f" COMMENT '{escaped}'"

    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "created", "catalog_name": catalog_name, "connection_name": connection_name, "sql": sql}
