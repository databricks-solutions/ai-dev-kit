"""
Unity Catalog - Security Policy Operations

Functions for managing row-level security (row filters) and column masking.
All operations are SQL-based via execute_sql.
"""
import re
from typing import Any, Dict, List, Optional

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


def create_security_function(
    function_name: str,
    parameter_name: str,
    parameter_type: str,
    return_type: str,
    function_body: str,
    comment: str | None = None,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    """
    Create a SQL function for use as a row filter or column mask.

    Args:
        function_name: Full function name (catalog.schema.function)
        parameter_name: Input parameter name (e.g., "val")
        parameter_type: Input parameter type (e.g., "STRING")
        return_type: Return type ("BOOLEAN" for row filters, data type for masks)
        function_body: SQL function body (e.g., "RETURN IF(IS_ACCOUNT_GROUP_MEMBER('admins'), val, '***')")
        comment: Optional function description
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL

    Note:
        function_body accepts raw SQL. Only use with trusted input.
    """
    _validate_identifier(function_name)
    _validate_identifier(parameter_name)

    sql_parts = [
        f"CREATE OR REPLACE FUNCTION {function_name}({parameter_name} {parameter_type})",
        f"RETURNS {return_type}",
    ]
    if comment:
        escaped = comment.replace("'", "\\'")
        sql_parts.append(f"COMMENT '{escaped}'")
    sql_parts.append(function_body)

    sql = "\n".join(sql_parts)
    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "created", "function_name": function_name, "sql": sql}


def set_row_filter(
    table_name: str,
    filter_function: str,
    filter_columns: list[str],
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    """
    Apply a row filter function to a table.

    The filter function must return BOOLEAN and accept the specified columns
    as input parameters.

    Args:
        table_name: Full table name (catalog.schema.table)
        filter_function: Full function name (catalog.schema.function)
        filter_columns: Column names passed to the filter function
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL
    """
    _validate_identifier(table_name)
    _validate_identifier(filter_function)
    validated_cols = [_validate_identifier(c) for c in filter_columns]
    cols_str = ", ".join(validated_cols)

    sql = f"ALTER TABLE {table_name} SET ROW FILTER {filter_function} ON ({cols_str})"
    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "row_filter_set", "table": table_name, "function": filter_function, "sql": sql}


def drop_row_filter(
    table_name: str,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    """
    Remove the row filter from a table.

    Args:
        table_name: Full table name (catalog.schema.table)
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL
    """
    _validate_identifier(table_name)
    sql = f"ALTER TABLE {table_name} DROP ROW FILTER"
    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "row_filter_dropped", "table": table_name, "sql": sql}


def set_column_mask(
    table_name: str,
    column_name: str,
    mask_function: str,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    """
    Apply a column mask function to a specific column.

    The mask function must accept the column value and return the same type.

    Args:
        table_name: Full table name (catalog.schema.table)
        column_name: Column to mask
        mask_function: Full function name (catalog.schema.function)
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL
    """
    _validate_identifier(table_name)
    _validate_identifier(column_name)
    _validate_identifier(mask_function)

    sql = f"ALTER TABLE {table_name} ALTER COLUMN `{column_name}` SET MASK {mask_function}"
    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "column_mask_set", "table": table_name, "column": column_name, "function": mask_function, "sql": sql}


def drop_column_mask(
    table_name: str,
    column_name: str,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    """
    Remove the column mask from a specific column.

    Args:
        table_name: Full table name (catalog.schema.table)
        column_name: Column to unmask
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL
    """
    _validate_identifier(table_name)
    _validate_identifier(column_name)

    sql = f"ALTER TABLE {table_name} ALTER COLUMN `{column_name}` DROP MASK"
    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "column_mask_dropped", "table": table_name, "column": column_name, "sql": sql}
