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
    "ColumnDetail",
    "DataSourceInfo",
    "HistogramBin",
    "SQLDependencyAnalyzer",
    "SQLExecutionError",
    "SQLExecutor",
    "SQLParallelExecutor",
    "TableInfo",  # Alias for DataSourceInfo
    "TableSchemaResult",
    "TableStatLevel",
    "TableStatsCollector",
    "VolumeFileInfo",
    "VolumeFolderResult",  # Alias for DataSourceInfo
]
