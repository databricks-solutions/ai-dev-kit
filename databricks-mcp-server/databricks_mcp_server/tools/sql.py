"""SQL tools - Execute SQL queries and get table information."""
from typing import Any, Dict, List, Optional

from databricks_tools_core.sql import (
    execute_sql as _execute_sql,
    execute_sql_multi as _execute_sql_multi,
    list_warehouses as _list_warehouses,
    get_best_warehouse as _get_best_warehouse,
    get_table_details as _get_table_details,
    TableStatLevel,
)

from ..server import mcp


@mcp.tool
def execute_sql(
    sql_query: str,
    warehouse_id: str = None,
    catalog: str = None,
    schema: str = None,
    timeout: int = 180,
) -> List[Dict[str, Any]]:
    """
    Execute a SQL query on a Databricks SQL Warehouse.

    If no warehouse_id is provided, automatically selects the best available warehouse.

    Args:
        sql_query: SQL query to execute
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.
        catalog: Optional catalog context for unqualified table names.
        schema: Optional schema context for unqualified table names.
        timeout: Timeout in seconds (default: 180)

    Returns:
        List of dictionaries, each representing a row with column names as keys.
    """
    return _execute_sql(
        sql_query=sql_query,
        warehouse_id=warehouse_id,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
    )


@mcp.tool
def execute_sql_multi(
    sql_content: str,
    warehouse_id: str = None,
    catalog: str = None,
    schema: str = None,
    timeout: int = 180,
    max_workers: int = 4,
) -> Dict[str, Any]:
    """
    Execute multiple SQL statements with dependency-aware parallelism.

    Parses SQL content into statements, analyzes dependencies, and executes
    in optimal order. Independent queries run in parallel.

    Args:
        sql_content: SQL content with multiple statements separated by ;
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.
        catalog: Optional catalog context for unqualified table names.
        schema: Optional schema context for unqualified table names.
        timeout: Timeout per query in seconds (default: 180)
        max_workers: Maximum parallel queries per group (default: 4)

    Returns:
        Dictionary with results per query and execution summary.
    """
    return _execute_sql_multi(
        sql_content=sql_content,
        warehouse_id=warehouse_id,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
        max_workers=max_workers,
    )


@mcp.tool
def list_warehouses() -> List[Dict[str, Any]]:
    """
    List all SQL warehouses in the workspace.

    Returns:
        List of warehouse info dicts with id, name, state, size, etc.
    """
    return _list_warehouses()


@mcp.tool
def get_best_warehouse() -> Optional[str]:
    """
    Get the ID of the best available SQL warehouse.

    Prioritizes running warehouses, then starting ones, preferring smaller sizes.

    Returns:
        Warehouse ID string, or None if no warehouses available.
    """
    return _get_best_warehouse()


@mcp.tool
def get_table_details(
    catalog: str,
    schema: str,
    table_names: List[str] = None,
    table_stat_level: str = "SIMPLE",
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    Get table schema and statistics for one or more tables.

    Args:
        catalog: Unity Catalog name
        schema: Schema name
        table_names: List of table names or GLOB patterns (e.g., ["bronze_*", "silver_orders"]).
                    If None, returns all tables in the schema.
        table_stat_level: Level of statistics to collect:
            - "NONE": Schema only, no statistics
            - "SIMPLE": Row count and basic info (default)
            - "DETAILED": Column-level statistics including histograms
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.

    Returns:
        Dictionary with tables list containing schema and statistics per table.
    """
    # Convert string to enum
    level = TableStatLevel[table_stat_level.upper()]
    result = _get_table_details(
        catalog=catalog,
        schema=schema,
        table_names=table_names,
        table_stat_level=level,
        warehouse_id=warehouse_id,
    )
    # Convert to dict for JSON serialization
    return result.model_dump() if hasattr(result, 'model_dump') else result
