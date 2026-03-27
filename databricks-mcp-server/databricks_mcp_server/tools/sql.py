"""SQL tools - Execute SQL queries and get table information."""

from typing import Any, Dict, List, Optional, Union

from databricks_tools_core.sql import (
    execute_sql as _execute_sql,
    execute_sql_multi as _execute_sql_multi,
    list_warehouses as _list_warehouses,
    get_best_warehouse as _get_best_warehouse,
    get_table_details as _get_table_details,
    get_volume_folder_details as _get_volume_folder_details,
    TableStatLevel,
)

from ..server import mcp


def _format_results_markdown(rows: List[Dict[str, Any]]) -> str:
    """Format SQL results as a markdown table.

    Markdown tables state column names once in the header instead of repeating
    them on every row (as JSON does), reducing token usage by ~50%.

    Args:
        rows: List of row dicts from the SQL executor.

    Returns:
        Markdown table string, or "(no results)" if empty.
    """
    if not rows:
        return "(no results)"

    columns = list(rows[0].keys())

    # Build header
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"

    # Build rows — convert None to empty string, stringify everything
    data_lines = []
    for row in rows:
        cells = []
        for col in columns:
            val = row.get(col)
            cell = "" if val is None else str(val)
            # Escape pipe characters inside cell values
            cell = cell.replace("|", "\\|")
            cells.append(cell)
        data_lines.append("| " + " | ".join(cells) + " |")

    parts = [header, separator] + data_lines
    # Append row count for awareness
    parts.append(f"\n({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return "\n".join(parts)


@mcp.tool
def execute_sql(
    sql_query: str,
    warehouse_id: str = None,
    catalog: str = None,
    schema: str = None,
    timeout: int = 180,
    query_tags: str = None,
    output_format: str = "markdown",
) -> Union[str, List[Dict[str, Any]]]:
    """
    Execute a SQL query on a Databricks SQL Warehouse.

    If no warehouse_id is provided, automatically selects the best available warehouse.

    IMPORTANT: For creating or dropping schemas, catalogs, and volumes, use the
    manage_uc_objects tool instead of SQL DDL. Only use execute_sql for queries
    (SELECT, INSERT, UPDATE) and table DDL (CREATE TABLE, DROP TABLE).

    Args:
        sql_query: SQL query to execute
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.
        catalog: Optional catalog context for unqualified table names.
        schema: Optional schema context for unqualified table names.
        timeout: Timeout in seconds (default: 180)
        query_tags: Optional query tags for cost attribution (e.g., "team:eng,cost_center:701").
            Appears in system.query.history and Query History UI.
        output_format: Result format — "markdown" (default) or "json".
            Markdown tables are ~50% smaller than JSON because column names appear
            only once in the header instead of on every row. Use "json" when you
            need machine-parseable output.

    Returns:
        Markdown table string (default) or list of row dictionaries (if output_format="json").
    """
    rows = _execute_sql(
        sql_query=sql_query,
        warehouse_id=warehouse_id,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
        query_tags=query_tags,
    )
    if output_format == "json":
        return rows
    return _format_results_markdown(rows)


@mcp.tool
def execute_sql_multi(
    sql_content: str,
    warehouse_id: str = None,
    catalog: str = None,
    schema: str = None,
    timeout: int = 180,
    max_workers: int = 4,
    query_tags: str = None,
    output_format: str = "markdown",
) -> Dict[str, Any]:
    """
    Execute multiple SQL statements with dependency-aware parallelism.

    Parses SQL content into statements, analyzes dependencies, and executes
    in optimal order. Independent queries run in parallel.

    IMPORTANT: For creating or dropping schemas, catalogs, and volumes, use the
    manage_uc_objects tool instead of SQL DDL. Only use execute_sql/execute_sql_multi
    for queries (SELECT, INSERT, UPDATE) and table DDL (CREATE TABLE, DROP TABLE).

    Args:
        sql_content: SQL content with multiple statements separated by ;
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.
        catalog: Optional catalog context for unqualified table names.
        schema: Optional schema context for unqualified table names.
        timeout: Timeout per query in seconds (default: 180)
        max_workers: Maximum parallel queries per group (default: 4)
        query_tags: Optional query tags for cost attribution (e.g., "team:eng,cost_center:701").
        output_format: Result format — "markdown" (default) or "json".
            Markdown tables are ~50% smaller than JSON because column names appear
            only once in the header instead of on every row.

    Returns:
        Dictionary with results per query and execution summary.
    """
    result = _execute_sql_multi(
        sql_content=sql_content,
        warehouse_id=warehouse_id,
        catalog=catalog,
        schema=schema,
        timeout=timeout,
        max_workers=max_workers,
        query_tags=query_tags,
    )
    # Format sample_results in each query result if markdown requested
    if output_format != "json" and "results" in result:
        for query_result in result["results"].values():
            sample = query_result.get("sample_results")
            if sample and isinstance(sample, list) and len(sample) > 0:
                query_result["sample_results"] = _format_results_markdown(sample)
    return result


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
    return result.model_dump(exclude_none=True) if hasattr(result, "model_dump") else result


@mcp.tool
def get_volume_folder_details(
    volume_path: str,
    format: str = "parquet",
    table_stat_level: str = "SIMPLE",
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    Get schema and statistics for data files in a Databricks Volume folder.

    Similar to get_table_details but for raw files stored in Volumes.

    Args:
        volume_path: Path to the volume folder. Can be:
            - "catalog/schema/volume/path" (e.g., "ai_dev_kit/demo/raw_data/customers")
            - "/Volumes/catalog/schema/volume/path"
        format: Data format - "parquet", "csv", "json", "delta", or "file" (just list files).
        table_stat_level: Level of statistics - "NONE", "SIMPLE" (default), or "DETAILED".
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.

    Returns:
        Dictionary with schema, row count, column stats, and sample data.
    """
    level = TableStatLevel[table_stat_level.upper()]
    result = _get_volume_folder_details(
        volume_path=volume_path,
        format=format,
        table_stat_level=level,
        warehouse_id=warehouse_id,
    )
    return result.model_dump(exclude_none=True) if hasattr(result, "model_dump") else result
