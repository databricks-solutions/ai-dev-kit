"""
Table Statistics

High-level functions for getting table details and statistics.
Supports both Unity Catalog tables and Volume folder data.
"""

import logging
from typing import List, Literal, Optional

from .sql_utils.models import (
    ColumnDetail,
    DataSourceInfo,
    TableSchemaResult,
    TableStatLevel,
    VolumeFileInfo,
)
from .sql_utils.table_stats_collector import TableStatsCollector
from .warehouse import get_best_warehouse
from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


def _has_glob_pattern(name: str) -> bool:
    """Check if a name contains glob pattern characters."""
    return any(c in name for c in ["*", "?", "[", "]"])


def get_table_details(
    catalog: str,
    schema: str,
    table_names: Optional[List[str]] = None,
    table_stat_level: TableStatLevel = TableStatLevel.SIMPLE,
    warehouse_id: Optional[str] = None,
) -> TableSchemaResult:
    """
    Get detailed information about tables in a schema.

    Supports three modes based on table_names:
    1. Empty list or None: List all tables in the schema
    2. Names with glob patterns (*, ?, []): List tables and filter by pattern
    3. Exact names: Get tables directly without listing (faster)

    Args:
        catalog: Catalog name
        schema: Schema name
        table_names: Optional list of table names or glob patterns.
            Examples:
            - None or []: Get all tables
            - ["customers", "orders"]: Get specific tables
            - ["raw_*"]: Get all tables starting with "raw_"
            - ["*_customers", "orders"]: Mix of patterns and exact names
        table_stat_level: Level of statistics to collect:
            - NONE: Just DDL, no stats (fast, no cache)
            - SIMPLE: Basic stats with caching (default)
            - DETAILED: Full stats including histograms, percentiles
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.

    Returns:
        TableSchemaResult containing table information with requested stat level

    Raises:
        Exception: If warehouse not available or catalog/schema doesn't exist

    Examples:
        >>> # Get all tables with basic stats
        >>> result = get_table_details("my_catalog", "my_schema")

        >>> # Get specific tables
        >>> result = get_table_details("my_catalog", "my_schema", ["customers", "orders"])

        >>> # Get tables matching pattern with full stats
        >>> result = get_table_details(
        ...     "my_catalog", "my_schema",
        ...     ["gold_*"],
        ...     table_stat_level=TableStatLevel.DETAILED
        ... )

        >>> # Quick DDL-only lookup (no stats)
        >>> result = get_table_details(
        ...     "my_catalog", "my_schema",
        ...     ["my_table"],
        ...     table_stat_level=TableStatLevel.NONE
        ... )
    """
    # Auto-select warehouse if not provided
    if not warehouse_id:
        logger.debug("No warehouse_id provided, selecting best available warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise Exception(
                "No SQL warehouse available in the workspace. "
                "Please create a SQL warehouse or start an existing one, "
                "or provide a specific warehouse_id."
            )
        logger.debug(f"Auto-selected warehouse: {warehouse_id}")

    collector = TableStatsCollector(warehouse_id=warehouse_id)

    # Determine if we need to list tables
    table_names = table_names or []
    has_patterns = any(_has_glob_pattern(name) for name in table_names)
    needs_listing = len(table_names) == 0 or has_patterns

    if needs_listing:
        # List all tables first
        logger.debug(f"Listing tables in {catalog}.{schema}")
        all_tables = collector.list_tables(catalog, schema)

        if table_names:
            # Filter by patterns
            tables_to_fetch = collector.filter_tables_by_patterns(
                all_tables, table_names
            )
            logger.debug(
                f"Filtered {len(all_tables)} tables to {len(tables_to_fetch)} "
                f"matching patterns: {table_names}"
            )
        else:
            tables_to_fetch = all_tables
            logger.debug(f"Found {len(tables_to_fetch)} tables")
    else:
        # Direct lookup - build table info without listing
        logger.debug(f"Direct lookup for tables: {table_names}")
        tables_to_fetch = [
            {"name": name, "updated_at": None, "comment": None} for name in table_names
        ]

    if not tables_to_fetch:
        return TableSchemaResult(catalog=catalog, schema_name=schema, tables=[])

    # Determine whether to collect stats
    collect_stats = table_stat_level != TableStatLevel.NONE

    # Fetch table info (with or without stats)
    logger.info(
        f"Fetching {len(tables_to_fetch)} tables with stat_level={table_stat_level.value}"
    )
    table_infos = collector.get_tables_info_parallel(
        catalog=catalog,
        schema=schema,
        tables=tables_to_fetch,
        collect_stats=collect_stats,
    )

    # Build result
    result = TableSchemaResult(
        catalog=catalog,
        schema_name=schema,
        tables=table_infos,
    )

    # Apply stat level transformation
    if table_stat_level == TableStatLevel.SIMPLE:
        return result.keep_basic_stats()
    elif table_stat_level == TableStatLevel.NONE:
        return result.remove_stats()
    else:
        # DETAILED - return everything
        return result


def _parse_volume_path(volume_path: str) -> str:
    """
    Parse volume path and return the full /Volumes/... path.

    Accepts:
    - catalog/schema/volume/path
    - /Volumes/catalog/schema/volume/path

    Returns:
        Full path in /Volumes/catalog/schema/volume/path format
    """
    path = volume_path.strip("/")
    if path.lower().startswith("volumes/"):
        return f"/{path}"
    return f"/Volumes/{path}"


def _list_volume_files(
    volume_path: str,
) -> tuple[List[VolumeFileInfo], int, Optional[str]]:
    """
    List files in a volume folder using the Files API.

    Returns:
        Tuple of (files_list, total_size_bytes, error_message)
    """
    w = get_workspace_client()
    files = []
    total_size = 0

    try:
        for entry in w.files.list_directory_contents(volume_path):
            file_info = VolumeFileInfo(
                name=entry.name,
                path=entry.path,
                size_bytes=getattr(entry, "file_size", None),
                is_directory=entry.is_directory,
                modification_time=str(getattr(entry, "last_modified", None))
                if hasattr(entry, "last_modified")
                else None,
            )
            files.append(file_info)
            if file_info.size_bytes:
                total_size += file_info.size_bytes

        return files, total_size, None

    except Exception as e:
        error_msg = str(e)
        if "NOT_FOUND" in error_msg or "404" in error_msg:
            return (
                [],
                0,
                f"Volume path not found: {volume_path}. Check that the catalog, schema, volume, and path exist.",
            )
        return [], 0, f"Failed to list volume path: {volume_path}. Error: {error_msg}"


def _extract_catalog_schema_from_volume_path(volume_path: str) -> tuple[str, str]:
    """Extract catalog and schema from a volume path like /Volumes/catalog/schema/volume/..."""
    parts = volume_path.strip("/").split("/")
    if parts[0].lower() == "volumes" and len(parts) >= 3:
        return parts[1], parts[2]
    elif len(parts) >= 2:
        return parts[0], parts[1]
    return "volumes", "data"


def get_volume_folder_details(
    volume_path: str,
    format: Literal["parquet", "csv", "json", "delta", "file"] = "parquet",
    table_stat_level: TableStatLevel = TableStatLevel.SIMPLE,
    warehouse_id: Optional[str] = None,
) -> TableSchemaResult:
    """
    Get detailed information about data files in a Databricks Volume folder.

    Similar to get_table_details but for raw files stored in Volumes.
    Uses SQL warehouse to read volume data via read_files() function.

    Args:
        volume_path: Path to the volume folder. Can be:
            - "catalog/schema/volume/path" (e.g., "ai_dev_kit/demo/raw_data/customers")
            - "/Volumes/catalog/schema/volume/path"
        format: Data format:
            - "parquet", "csv", "json", "delta": Read data and compute stats
            - "file": Just list files without reading data (fast)
        table_stat_level: Level of statistics to collect:
            - NONE: Just schema, no stats
            - SIMPLE: Basic stats (default)
            - DETAILED: Full stats including samples
        warehouse_id: Optional warehouse ID. If not provided, auto-selects one.

    Returns:
        TableSchemaResult with a single DataSourceInfo containing file info, column stats, and sample data

    Examples:
        >>> # Get stats for parquet files
        >>> result = get_volume_folder_details(
        ...     "ai_dev_kit/demo/raw_data/customers",
        ...     format="parquet"
        ... )
        >>> info = result.tables[0]
        >>> print(f"Rows: {info.total_rows}, Columns: {len(info.column_details)}")

        >>> # Just list files (fast, no data reading)
        >>> result = get_volume_folder_details(
        ...     "ai_dev_kit/demo/raw_data/customers",
        ...     format="file"
        ... )
        >>> info = result.tables[0]
        >>> print(f"Files: {info.total_files}, Size: {info.total_size_bytes}")
    """
    full_path = _parse_volume_path(volume_path)
    logger.debug(f"Getting volume folder details for: {full_path}, format={format}")

    # Extract catalog/schema for the result
    catalog, schema = _extract_catalog_schema_from_volume_path(full_path)

    def _make_result(info: DataSourceInfo) -> TableSchemaResult:
        """Helper to wrap DataSourceInfo in TableSchemaResult."""
        return TableSchemaResult(catalog=catalog, schema_name=schema, tables=[info])

    # Step 1: List files to verify folder exists and get file info
    files, total_size, error = _list_volume_files(full_path)

    if error:
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                error=error,
            )
        )

    if not files:
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                total_files=0,
                error=f"Volume path exists but is empty: {full_path}",
            )
        )

    # Count data files (not directories)
    data_files = [f for f in files if not f.is_directory]
    directories = [f for f in files if f.is_directory]
    total_files = len(data_files) if data_files else len(directories)

    # Step 2: For format="file", just return file listing
    if format == "file":
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                total_files=len(files),
                total_size_bytes=total_size,
                files=files,
            )
        )

    # Step 3: For data formats, use TableStatsCollector to read and compute stats
    # Auto-select warehouse if not provided
    if not warehouse_id:
        logger.debug("No warehouse_id provided, selecting best available warehouse")
        warehouse_id = get_best_warehouse()
        if not warehouse_id:
            raise Exception(
                "No SQL warehouse available in the workspace. "
                "Please create a SQL warehouse or start an existing one, "
                "or provide a specific warehouse_id."
            )
        logger.debug(f"Auto-selected warehouse: {warehouse_id}")

    # Determine whether to collect stats
    collect_stats = table_stat_level != TableStatLevel.NONE

    if not collect_stats:
        # Just get schema without stats - use a simple query
        from .sql_utils.executor import SQLExecutor

        executor = SQLExecutor(warehouse_id=warehouse_id)
        volume_ref = f"read_files('{full_path}', format => '{format}')"

        try:
            # Get schema from first row
            sample_query = f"SELECT * FROM {volume_ref} LIMIT 1"
            sample_result = executor.execute(sql_query=sample_query, timeout=60)

            if not sample_result:
                return _make_result(
                    DataSourceInfo(
                        name=full_path,
                        format=format,
                        total_files=total_files,
                        total_size_bytes=total_size,
                        error="Failed to read volume data - no data returned",
                    )
                )

            # Get row count
            count_result = executor.execute(
                sql_query=f"SELECT COUNT(*) as total_rows FROM {volume_ref}",
                timeout=60,
            )
            total_rows = count_result[0]["total_rows"] if count_result else 0

            # Build column details from first row
            column_details = {}
            for col_name, value in sample_result[0].items():
                if col_name == "_rescued_data":
                    continue
                if isinstance(value, bool):
                    data_type = "boolean"
                elif isinstance(value, int):
                    data_type = "bigint"
                elif isinstance(value, float):
                    data_type = "double"
                else:
                    data_type = "string"
                column_details[col_name] = ColumnDetail(
                    name=col_name, data_type=data_type
                )

            return _make_result(
                DataSourceInfo(
                    name=full_path,
                    format=format,
                    total_files=total_files,
                    total_size_bytes=total_size,
                    total_rows=total_rows,
                    column_details=column_details,
                )
            )
        except Exception as e:
            return _make_result(
                DataSourceInfo(
                    name=full_path,
                    format=format,
                    total_files=total_files,
                    total_size_bytes=total_size,
                    error=f"Failed to read volume data: {str(e)}",
                )
            )

    # Use TableStatsCollector for full stats
    collector = TableStatsCollector(warehouse_id=warehouse_id)

    try:
        column_details, total_rows, sample_data = collector.collect_volume_stats(
            volume_path=full_path,
            format=format,
        )

        if not column_details:
            return _make_result(
                DataSourceInfo(
                    name=full_path,
                    format=format,
                    total_files=total_files,
                    total_size_bytes=total_size,
                    error="Failed to collect volume stats - no columns found",
                )
            )

        volume_info = DataSourceInfo(
            name=full_path,
            format=format,
            total_files=total_files,
            total_size_bytes=total_size,
            total_rows=total_rows,
            column_details=column_details,
            sample_data=sample_data
            if table_stat_level == TableStatLevel.DETAILED
            else None,
        )

        result = _make_result(volume_info)

        # Apply stat level transformation
        if table_stat_level == TableStatLevel.SIMPLE:
            return result.keep_basic_stats()
        else:
            return result

    except Exception as e:
        return _make_result(
            DataSourceInfo(
                name=full_path,
                format=format,
                total_files=total_files,
                total_size_bytes=total_size,
                error=f"Failed to read volume data: {str(e)}",
            )
        )
