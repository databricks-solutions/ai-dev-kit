"""
SQL Models - Pydantic models for table statistics and schema information.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


class TableStatLevel(str, Enum):
    """Level of statistics to collect for tables."""

    NONE = "none"  # Just describe table structure, no stats
    SIMPLE = "simple"  # Basic stats: samples, cardinality, min/max, null counts
    DETAILED = "detailed"  # Full stats: histograms, percentiles, stddev, value counts


# Constants for column statistics
NUMERIC_TYPES = ["int", "bigint", "float", "double", "decimal", "numeric"]
TIMESTAMP_TYPES = ["timestamp", "date"]
ID_PATTERNS = ["_id", "id_", "_uuid", "uuid_", "_key", "key_"]
MAX_CATEGORICAL_VALUES = 30
SAMPLE_ROW_COUNT = 10
HISTOGRAM_BINS = 10


class HistogramBin(BaseModel):
    """Histogram bin data."""

    bin_center: float
    count: int
    date_label: Optional[str] = None  # For timestamp histograms


class ColumnDetail(BaseModel):
    """Detailed information about a table column including statistics."""

    name: str
    data_type: str
    samples: Optional[List[Any]] = None  # Up to 3 distinct sample values
    cardinality: Optional[int] = None  # count distinct for string columns
    min: Optional[Union[str, float, int]] = None  # for numeric and timestamp
    max: Optional[Union[str, float, int]] = None  # for numeric and timestamp
    avg: Optional[float] = None  # for numeric columns only
    null_count: Optional[int] = None
    total_count: Optional[int] = None
    # Enhanced statistics (DETAILED level)
    unique_count: Optional[int] = None
    mean: Optional[float] = None  # alias for avg
    stddev: Optional[float] = None
    q1: Optional[float] = None  # 25th percentile
    median: Optional[float] = None  # 50th percentile
    q3: Optional[float] = None  # 75th percentile
    min_date: Optional[str] = None  # for timestamp columns
    max_date: Optional[str] = None  # for timestamp columns
    histogram: Optional[List[HistogramBin]] = None  # histogram data
    value_counts: Optional[Dict[str, int]] = None  # value counts for categorical


class VolumeFileInfo(BaseModel):
    """Information about a file in a volume."""

    name: str
    path: str
    size_bytes: Optional[int] = None
    is_directory: bool = False
    modification_time: Optional[str] = None


def _get_basic_column_details(
    column_details: Optional[Dict[str, ColumnDetail]],
) -> Optional[Dict[str, ColumnDetail]]:
    """Return simplified column details with basic stats only.

    Removes heavy stats like histograms, stddev, percentiles.
    For categorical columns with value_counts, replaces samples with value_counts.
    """
    if not column_details:
        return None

    basic_columns = {}
    for col_name, col_detail in column_details.items():
        basic_col = ColumnDetail(
            name=col_detail.name,
            data_type=col_detail.data_type,
            samples=col_detail.samples,
            cardinality=col_detail.cardinality,
            min=col_detail.min,
            max=col_detail.max,
            avg=col_detail.avg,
            null_count=col_detail.null_count if col_detail.null_count and col_detail.null_count > 0 else None,
            total_count=col_detail.total_count,
            unique_count=col_detail.unique_count,
            # Exclude heavy stats
            mean=None,
            stddev=None,
            q1=None,
            median=None,
            q3=None,
            min_date=None,
            max_date=None,
            histogram=None,
            value_counts=col_detail.value_counts,
        )

        # For categorical columns with value_counts, use those instead of samples
        if col_detail.value_counts:
            basic_col.samples = None

        basic_columns[col_name] = basic_col

    return basic_columns


class DataSourceInfo(BaseModel):
    """Unified information about a data source (UC table or Volume folder).

    For UC tables: name is the table name, ddl is populated
    For Volume folders: name is the volume path, format and file info are populated

    When serializing, use model_dump(exclude_none=True) to omit irrelevant fields.
    """

    name: str  # Table name or volume path

    # Common fields
    column_details: Optional[Dict[str, ColumnDetail]] = None
    total_rows: Optional[int] = None
    sample_data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

    # UC Table specific fields
    comment: Optional[str] = None
    ddl: Optional[str] = None
    updated_at: Optional[int] = None  # Timestamp in epoch ms from Databricks

    # Volume folder specific fields
    format: Optional[str] = None  # "parquet", "csv", "json", "delta", "file"
    total_files: Optional[int] = None
    total_size_bytes: Optional[int] = None
    files: Optional[List["VolumeFileInfo"]] = None  # Only for format="file"

    def get_basic_column_details(self) -> Optional[Dict[str, ColumnDetail]]:
        """Return simplified column details with basic stats only."""
        return _get_basic_column_details(self.column_details)


# Backwards compatibility alias
TableInfo = DataSourceInfo


class TableSchemaResult(BaseModel):
    """Result model for data source schema information.

    Works for both UC tables and Volume folders.
    - For UC tables: catalog and schema_name identify the location
    - For Volume folders: catalog/schema_name can be extracted from volume path,
      or left as descriptive values
    """

    catalog: str
    schema_name: str
    tables: List[DataSourceInfo]  # List of tables or volume folders

    @property
    def table_count(self) -> int:
        """Get the number of data sources in this result."""
        return len(self.tables)

    def keep_basic_stats(self) -> "TableSchemaResult":
        """Return a new TableSchemaResult with only basic stats preserved.

        Creates a lightweight version suitable for SIMPLE stat level.
        Does not mutate the original cached object.
        """
        tables_with_basic = []
        for table in self.tables:
            basic_columns = table.get_basic_column_details()

            table_basic = DataSourceInfo(
                name=table.name,
                comment=table.comment,
                ddl=table.ddl,
                column_details=basic_columns,
                updated_at=None,  # Don't expose cache timestamp
                error=table.error,
                total_rows=table.total_rows,
                sample_data=None,  # Exclude sample data for lighter payload
                # Volume fields
                format=table.format,
                total_files=table.total_files,
                total_size_bytes=table.total_size_bytes,
                files=table.files,
            )
            tables_with_basic.append(table_basic)

        return TableSchemaResult(
            catalog=self.catalog,
            schema_name=self.schema_name,
            tables=tables_with_basic,
        )

    def remove_stats(self) -> "TableSchemaResult":
        """Return a new TableSchemaResult with column statistics removed.

        Keeps column names and types but removes all numeric/histogram stats.
        """
        tables_no_stats = []
        for table in self.tables:
            # Strip stats from column details if they exist
            basic_columns = None
            if table.column_details:
                basic_columns = {}
                for col_name, col_detail in table.column_details.items():
                    basic_columns[col_name] = ColumnDetail(
                        name=col_detail.name,
                        data_type=col_detail.data_type,
                    )

            table_no_stats = DataSourceInfo(
                name=table.name,
                comment=table.comment,
                ddl=table.ddl,
                column_details=basic_columns,
                updated_at=None,
                error=table.error,
                total_rows=None,
                sample_data=None,
                # Volume fields
                format=table.format,
                total_files=table.total_files,
                total_size_bytes=table.total_size_bytes,
                files=table.files,
            )
            tables_no_stats.append(table_no_stats)

        return TableSchemaResult(
            catalog=self.catalog,
            schema_name=self.schema_name,
            tables=tables_no_stats,
        )


# VolumeFolderResult is deprecated - use DataSourceInfo within TableSchemaResult instead
# Kept as alias for backwards compatibility
VolumeFolderResult = DataSourceInfo
