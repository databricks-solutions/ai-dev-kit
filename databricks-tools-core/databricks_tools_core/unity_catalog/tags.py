"""
Unity Catalog - Tag and Comment Operations

Functions for managing tags and comments on UC objects.
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


def _execute_uc_sql(
    sql_query: str, warehouse_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Execute SQL using the existing execute_sql infrastructure."""
    from ..sql.sql import execute_sql

    return execute_sql(sql_query=sql_query, warehouse_id=warehouse_id)


def set_tags(
    object_type: str,
    full_name: str,
    tags: Dict[str, str],
    column_name: Optional[str] = None,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set tags on a UC object or column.

    Args:
        object_type: Type of object ("catalog", "schema", "table", "column")
        full_name: Full object name (e.g., "catalog.schema.table")
        tags: Key-value tag pairs (e.g., {"pii": "true", "classification": "confidential"})
        column_name: Column name (required when object_type is "column")
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL

    Raises:
        ValueError: If object_type is "column" but column_name not provided
    """
    _validate_identifier(full_name)
    tag_pairs = ", ".join(f"'{k}' = '{v}'" for k, v in tags.items())

    if object_type.lower() == "column":
        if not column_name:
            raise ValueError("column_name is required when object_type is 'column'")
        _validate_identifier(column_name)
        sql = f"ALTER TABLE {full_name} ALTER COLUMN `{column_name}` SET TAGS ({tag_pairs})"
    else:
        obj_keyword = object_type.upper()
        if obj_keyword not in ("CATALOG", "SCHEMA", "TABLE"):
            raise ValueError(
                f"object_type must be catalog, schema, table, or column. Got: {object_type}"
            )
        sql = f"ALTER {obj_keyword} {full_name} SET TAGS ({tag_pairs})"

    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "tags_set", "object": full_name, "tags": tags, "sql": sql}


def unset_tags(
    object_type: str,
    full_name: str,
    tag_names: List[str],
    column_name: Optional[str] = None,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Remove tags from a UC object or column.

    Args:
        object_type: Type of object ("catalog", "schema", "table", "column")
        full_name: Full object name
        tag_names: List of tag keys to remove
        column_name: Column name (required when object_type is "column")
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL
    """
    _validate_identifier(full_name)
    tag_keys = ", ".join(f"'{t}'" for t in tag_names)

    if object_type.lower() == "column":
        if not column_name:
            raise ValueError("column_name is required when object_type is 'column'")
        _validate_identifier(column_name)
        sql = f"ALTER TABLE {full_name} ALTER COLUMN `{column_name}` UNSET TAGS ({tag_keys})"
    else:
        obj_keyword = object_type.upper()
        if obj_keyword not in ("CATALOG", "SCHEMA", "TABLE"):
            raise ValueError(
                f"object_type must be catalog, schema, table, or column. Got: {object_type}"
            )
        sql = f"ALTER {obj_keyword} {full_name} UNSET TAGS ({tag_keys})"

    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {
        "status": "tags_unset",
        "object": full_name,
        "tag_names": tag_names,
        "sql": sql,
    }


def set_comment(
    object_type: str,
    full_name: str,
    comment_text: str,
    column_name: Optional[str] = None,
    warehouse_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Set a comment on a UC object or column.

    Args:
        object_type: Type of object ("catalog", "schema", "table", "column")
        full_name: Full object name
        comment_text: The comment text to set
        column_name: Column name (required when object_type is "column")
        warehouse_id: Optional SQL warehouse ID

    Returns:
        Dict with status and executed SQL
    """
    _validate_identifier(full_name)
    escaped_comment = comment_text.replace("'", "\\'")

    if object_type.lower() == "column":
        if not column_name:
            raise ValueError("column_name is required when object_type is 'column'")
        _validate_identifier(column_name)
        sql = f"ALTER TABLE {full_name} ALTER COLUMN `{column_name}` COMMENT '{escaped_comment}'"
    else:
        obj_keyword = object_type.upper()
        if obj_keyword not in ("CATALOG", "SCHEMA", "TABLE"):
            raise ValueError(
                f"object_type must be catalog, schema, table, or column. Got: {object_type}"
            )
        sql = f"COMMENT ON {obj_keyword} {full_name} IS '{escaped_comment}'"

    _execute_uc_sql(sql, warehouse_id=warehouse_id)
    return {"status": "comment_set", "object": full_name, "sql": sql}


def query_table_tags(
    catalog_filter: Optional[str] = None,
    tag_name: Optional[str] = None,
    tag_value: Optional[str] = None,
    limit: int = 100,
    warehouse_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Query tags on tables from system.information_schema.table_tags.

    Args:
        catalog_filter: Filter by catalog name
        tag_name: Filter by tag name
        tag_value: Filter by tag value
        limit: Maximum rows to return (default: 100)
        warehouse_id: Optional SQL warehouse ID

    Returns:
        List of dicts with tag information
    """
    conditions = []
    if catalog_filter:
        _validate_identifier(catalog_filter)
        conditions.append(f"catalog_name = '{catalog_filter}'")
    if tag_name:
        conditions.append(f"tag_name = '{tag_name}'")
    if tag_value:
        conditions.append(f"tag_value = '{tag_value}'")

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM system.information_schema.table_tags{where} LIMIT {limit}"
    return _execute_uc_sql(sql, warehouse_id=warehouse_id)


def query_column_tags(
    catalog_filter: Optional[str] = None,
    table_name: Optional[str] = None,
    tag_name: Optional[str] = None,
    tag_value: Optional[str] = None,
    limit: int = 100,
    warehouse_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Query tags on columns from system.information_schema.column_tags.

    Args:
        catalog_filter: Filter by catalog name
        table_name: Filter by table name
        tag_name: Filter by tag name
        tag_value: Filter by tag value
        limit: Maximum rows to return (default: 100)
        warehouse_id: Optional SQL warehouse ID

    Returns:
        List of dicts with column tag information
    """
    conditions = []
    if catalog_filter:
        _validate_identifier(catalog_filter)
        conditions.append(f"catalog_name = '{catalog_filter}'")
    if table_name:
        _validate_identifier(table_name)
        conditions.append(f"table_name = '{table_name}'")
    if tag_name:
        conditions.append(f"tag_name = '{tag_name}'")
    if tag_value:
        conditions.append(f"tag_value = '{tag_value}'")

    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = f"SELECT * FROM system.information_schema.column_tags{where} LIMIT {limit}"
    return _execute_uc_sql(sql, warehouse_id=warehouse_id)
