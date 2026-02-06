"""
SQL Execution

High-level functions for executing SQL queries on Databricks.
"""

import logging
from typing import Any, Dict, List, Optional

from .sql_utils import SQLExecutor, SQLExecutionError, SQLParallelExecutor
from .warehouse import get_best_warehouse

logger = logging.getLogger(__name__)


def execute_sql(
    sql_query: str,
    warehouse_id: str | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    timeout: int = 180,
) -> list[dict[str, Any]]:
    """
    Execute a SQL query on a Databricks SQL Warehouse.

    If no warehouse_id is provided, automatically selects the best available
    warehouse using get_best_warehouse().

    Args:
        sql_query: SQL query to execute
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.
        catalog: Optional catalog context. If not provided, use fully qualified names.
        schema: Optional schema context. If not provided, use fully qualified names.
        timeout: Timeout in seconds (default: 180)

    Returns:
        List of dictionaries, each representing a row with column names as keys.
        Example: [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    Raises:
        SQLExecutionError: If query execution fails, with detailed error message:
            - No warehouse available
            - Warehouse not accessible
            - Query syntax error
            - Query timeout
            - Permission denied
    """
    # Auto-select warehouse if not provided
    if not warehouse_id:
        logger.debug("No warehouse_id provided, selecting best available warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise SQLExecutionError(
                "No SQL warehouse available in the workspace. "
                "Please create a SQL warehouse or start an existing one, "
                "or provide a specific warehouse_id."
            )
        logger.debug(f"Auto-selected warehouse: {warehouse_id}")

    # Execute the query
    executor = SQLExecutor(warehouse_id=warehouse_id)
    return executor.execute(
        sql_query=sql_query,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
    )


def execute_sql_multi(
    sql_content: str,
    warehouse_id: str | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    timeout: int = 180,
    max_workers: int = 4,
) -> dict[str, Any]:
    """
    Execute multiple SQL statements with dependency-aware parallelism.

    Parses the SQL content into individual statements, analyzes dependencies
    between them (based on table creation and references), and executes them
    in optimal order. Queries that don't depend on each other run in parallel.

    If no warehouse_id is provided, automatically selects the best available
    warehouse using get_best_warehouse().

    Args:
        sql_content: SQL content with multiple statements separated by ;
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.
        catalog: Optional catalog context. If not provided, use fully qualified names.
        schema: Optional schema context. If not provided, use fully qualified names.
        timeout: Timeout per query in seconds (default: 180)
        max_workers: Maximum parallel queries per group (default: 4)

    Returns:
        Dictionary with:
        - results: Dict mapping query index to result dict, each containing:
            - query_index: 0-based index of the query
            - status: "success" or "error"
            - execution_time: Time taken in seconds
            - query_preview: First 100 chars of the query
            - result_rows: Number of rows returned (for success)
            - sample_results: First 5 rows (for success)
            - error: Error message (for error)
            - error_category: Error type like SYNTAX_ERROR, MISSING_TABLE (for error)
            - suggestion: Hint on how to fix (for error)
            - group_number: Which execution group this query was in
            - is_parallel: Whether it ran in parallel with other queries
        - execution_summary: Overall statistics including:
            - total_queries: Number of queries parsed
            - total_groups: Number of execution groups
            - total_time: Total execution time
            - stopped_after_group: Group number where execution stopped (if error)
            - groups: List of group details

    Raises:
        SQLExecutionError: If parsing fails or no warehouse available

    Example:
        >>> result = execute_sql_multi('''
        ...     CREATE TABLE t1 AS SELECT 1 as id;
        ...     CREATE TABLE t2 AS SELECT 2 as id;
        ...     CREATE TABLE t3 AS SELECT * FROM t1 JOIN t2;
        ... ''')
        >>> # t1 and t2 run in parallel (no dependencies)
        >>> # t3 runs after both complete (depends on t1 and t2)
    """
    # Auto-select warehouse if not provided
    if not warehouse_id:
        logger.debug("No warehouse_id provided, selecting best available warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise SQLExecutionError(
                "No SQL warehouse available in the workspace. "
                "Please create a SQL warehouse or start an existing one, "
                "or provide a specific warehouse_id."
            )
        logger.debug(f"Auto-selected warehouse: {warehouse_id}")

    # Execute with parallel executor
    executor = SQLParallelExecutor(
        warehouse_id=warehouse_id,
        max_workers=max_workers,
    )
    return executor.execute(
        sql_content=sql_content,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
    )
