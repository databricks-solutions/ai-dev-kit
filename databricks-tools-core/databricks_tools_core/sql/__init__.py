"""
SQL - SQL Warehouse Operations

Functions for executing SQL queries, managing SQL warehouses, and getting table statistics.
"""

from .sql import execute_sql, execute_sql_multi, execute_sql_batch
from .warehouse import list_warehouses, get_best_warehouse, invalidate_warehouse_cache
from .table_stats import get_table_details, get_volume_folder_details
from .sql_utils import (
    SQLExecutionError,
    TableStatLevel,
    TableSchemaResult,
    DataSourceInfo,
    TableInfo,  # Alias for DataSourceInfo (backwards compatibility)
    ColumnDetail,
    VolumeFileInfo,
    VolumeFolderResult,  # Alias for DataSourceInfo (backwards compatibility)
)

__all__ = [
    # SQL execution
    "execute_sql",
    "execute_sql_multi",
    "execute_sql_batch",
    # Warehouse management
    "list_warehouses",
    "get_best_warehouse",
    "invalidate_warehouse_cache",
    # Table statistics
    "get_table_details",
    "get_volume_folder_details",
    "TableStatLevel",
    "TableSchemaResult",
    "DataSourceInfo",
    "TableInfo",  # Alias for DataSourceInfo
    "ColumnDetail",
    # Volume folder statistics
    "VolumeFileInfo",
    "VolumeFolderResult",  # Alias for DataSourceInfo
    # Errors
    "SQLExecutionError",
]
