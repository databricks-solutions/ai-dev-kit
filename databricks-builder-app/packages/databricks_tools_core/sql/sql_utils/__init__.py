"""
SQL Utilities - Internal helpers for SQL operations.
"""

from .executor import SQLExecutor, SQLExecutionError
from .dependency_analyzer import SQLDependencyAnalyzer
from .parallel_executor import SQLParallelExecutor
from .models import (
    TableStatLevel,
    HistogramBin,
    ColumnDetail,
    DataSourceInfo,
    TableInfo,  # Alias for DataSourceInfo
    TableSchemaResult,
    VolumeFileInfo,
    VolumeFolderResult,  # Alias for DataSourceInfo
)
from .table_stats_collector import TableStatsCollector

__all__ = [
    "SQLExecutor",
    "SQLExecutionError",
    "SQLDependencyAnalyzer",
    "SQLParallelExecutor",
    "TableStatLevel",
    "HistogramBin",
    "ColumnDetail",
    "DataSourceInfo",
    "TableInfo",  # Alias for DataSourceInfo
    "TableSchemaResult",
    "VolumeFileInfo",
    "VolumeFolderResult",  # Alias for DataSourceInfo
    "TableStatsCollector",
]
