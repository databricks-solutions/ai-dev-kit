"""
Table Stats Collector - Collects column statistics for tables with caching.
"""

import fnmatch
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from databricks.sdk import WorkspaceClient

from ...auth import get_workspace_client
from .executor import SQLExecutor
from .models import (
    ColumnDetail,
    HistogramBin,
    TableInfo,
    HISTOGRAM_BINS,
    ID_PATTERNS,
    MAX_CATEGORICAL_VALUES,
    NUMERIC_TYPES,
    SAMPLE_ROW_COUNT,
)

logger = logging.getLogger(__name__)

# Module-level cache for table information
# Key: "catalog.schema", Value: Dict[table_name, (updated_at_timestamp, TableInfo)]
_table_cache: Dict[str, Dict[str, Tuple[Optional[int], TableInfo]]] = {}
_table_cache_lock = threading.Lock()

# Locks per table to prevent duplicate fetches
# Key: "catalog.schema.table", Value: threading.Lock
_table_locks: Dict[str, threading.Lock] = {}
_table_locks_creation_lock = threading.Lock()


def _get_table_lock(full_table_name: str) -> threading.Lock:
    """Get or create a lock for a specific table."""
    if full_table_name not in _table_locks:
        with _table_locks_creation_lock:
            if full_table_name not in _table_locks:
                _table_locks[full_table_name] = threading.Lock()
    return _table_locks[full_table_name]


def _get_schema_cache(
    catalog: str, schema: str
) -> Dict[str, Tuple[Optional[int], TableInfo]]:
    """Get or create cache for a schema."""
    schema_key = f"{catalog}.{schema}"
    if schema_key not in _table_cache:
        with _table_cache_lock:
            if schema_key not in _table_cache:
                _table_cache[schema_key] = {}
    return _table_cache[schema_key]


def _check_cache(
    catalog: str, schema: str, table_name: str, updated_at_ms: Optional[int]
) -> Optional[TableInfo]:
    """Check if table info is in cache and still valid."""
    schema_cache = _get_schema_cache(catalog, schema)
    if table_name in schema_cache:
        cached_updated_at, cached_info = schema_cache[table_name]
        if updated_at_ms == cached_updated_at:
            return cached_info
    return None


def _update_cache(
    catalog: str,
    schema: str,
    table_name: str,
    updated_at_ms: Optional[int],
    table_info: TableInfo,
) -> None:
    """Update cache with table info."""
    schema_cache = _get_schema_cache(catalog, schema)
    with _table_cache_lock:
        schema_cache[table_name] = (updated_at_ms, table_info)


class TableStatsCollector:
    """Collects table statistics with caching support."""

    def __init__(
        self,
        warehouse_id: str,
        max_workers: int = 10,
        client: Optional[WorkspaceClient] = None,
    ):
        """
        Initialize the stats collector.

        Args:
            warehouse_id: SQL warehouse ID to use for queries
            max_workers: Maximum parallel table fetches (default: 10)
            client: Optional WorkspaceClient (creates new one if not provided)
        """
        self.warehouse_id = warehouse_id
        self.max_workers = max_workers
        self.client = client or get_workspace_client()
        self.executor = SQLExecutor(warehouse_id=warehouse_id, client=self.client)

    def list_tables(self, catalog: str, schema: str) -> List[Dict[str, Any]]:
        """
        List all tables in a schema.

        Returns:
            List of table info dicts with 'name' and 'updated_at' keys
        """
        try:
            tables = list(
                self.client.tables.list(
                    catalog_name=catalog,
                    schema_name=schema,
                )
            )
            return [
                {
                    "name": t.name,
                    "updated_at": getattr(t, "updated_at", None),
                    "comment": getattr(t, "comment", None),
                }
                for t in tables
                if t.name
            ]
        except Exception as e:
            raise Exception(
                f"Failed to list tables in {catalog}.{schema}: {str(e)}. "
                f"Check that the catalog and schema exist and you have access."
            )

    def filter_tables_by_patterns(
        self, tables: List[Dict[str, Any]], patterns: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Filter tables by glob patterns.

        Args:
            tables: List of table info dicts
            patterns: List of glob patterns (e.g., ["raw_*", "silver_customers"])

        Returns:
            Filtered list of tables matching any pattern
        """
        if not patterns:
            return tables

        filtered = []
        for table in tables:
            table_name = table["name"]
            for pattern in patterns:
                if fnmatch.fnmatch(table_name, pattern):
                    filtered.append(table)
                    break
        return filtered

    def get_table_ddl(self, catalog: str, schema: str, table_name: str) -> str:
        """Get the DDL (CREATE TABLE statement) for a table."""
        full_table_name = f"{catalog}.{schema}.{table_name}"
        query = f"SHOW CREATE TABLE {full_table_name}"

        try:
            result = self.executor.execute(
                sql_query=query,
                catalog=catalog,
                schema=schema,
                timeout=45,
            )

            if not result:
                return ""

            row = result[0]
            create_statement = ""

            # Try different possible column names
            for col_name in [
                "createtab_stmt",
                "create_statement",
                "Create Table",
                "create_table_statement",
            ]:
                if col_name in row:
                    create_statement = row[col_name]
                    break

            if not create_statement:
                # Use first string value containing CREATE
                for value in row.values():
                    if isinstance(value, str) and "CREATE" in value.upper():
                        create_statement = value
                        break

            # Clean up the CREATE statement
            if create_statement:
                # Remove TBLPROPERTIES section
                tblprops_pos = create_statement.upper().find("TBLPROPERTIES")
                if tblprops_pos != -1:
                    create_statement = create_statement[:tblprops_pos].strip()
                    if create_statement.endswith(","):
                        create_statement = create_statement[:-1]
                    if not create_statement.endswith(")"):
                        create_statement += ")"

                # Remove USING delta section
                using_pos = create_statement.upper().find("USING ")
                if using_pos != -1:
                    create_statement = create_statement[:using_pos].strip()

                # Clean formatting
                create_statement = (
                    create_statement.replace("\n", " ").replace("  ", " ").strip()
                )

            return create_statement

        except Exception as e:
            logger.warning(f"Failed to get DDL for {full_table_name}: {e}")
            return ""

    def collect_column_stats(
        self, catalog: str, schema: str, table_name: str
    ) -> Tuple[Dict[str, ColumnDetail], int, List[Dict[str, Any]]]:
        """
        Collect enhanced column statistics for a UC table.

        Returns:
            Tuple of (column_details dict, total_rows, sample_data)
        """
        full_table_name = f"{catalog}.{schema}.{table_name}"
        return self._collect_stats_for_ref(
            table_ref=full_table_name,
            catalog=catalog,
            schema=schema,
            use_describe_table=True,
            fetch_value_counts_table=f"{catalog}.{schema}.{table_name}",
        )

    def collect_volume_stats(
        self, volume_path: str, format: str
    ) -> Tuple[Dict[str, ColumnDetail], int, List[Dict[str, Any]]]:
        """
        Collect enhanced column statistics for volume folder data.

        Args:
            volume_path: Full volume path (e.g., /Volumes/catalog/schema/volume/path)
            format: Data format (parquet, csv, json, delta)

        Returns:
            Tuple of (column_details dict, total_rows, sample_data)
        """
        table_ref = f"read_files('{volume_path}', format => '{format}')"
        return self._collect_stats_for_ref(
            table_ref=table_ref,
            catalog=None,
            schema=None,
            use_describe_table=False,
            fetch_value_counts_table=None,
        )

    def _collect_stats_for_ref(
        self,
        table_ref: str,
        catalog: Optional[str],
        schema: Optional[str],
        use_describe_table: bool,
        fetch_value_counts_table: Optional[str],
    ) -> Tuple[Dict[str, ColumnDetail], int, List[Dict[str, Any]]]:
        """
        Internal method to collect column statistics for any table reference.

        Args:
            table_ref: SQL table reference (UC table name or read_files(...))
            catalog: Catalog for query context (optional)
            schema: Schema for query context (optional)
            use_describe_table: If True, use DESCRIBE TABLE; otherwise infer from SELECT
            fetch_value_counts_table: Table name for value counts query (None to skip)

        Returns:
            Tuple of (column_details dict, total_rows, sample_data)
        """
        try:
            # Step 1: Get column information
            if use_describe_table:
                describe_result = self.executor.execute(
                    sql_query=f"DESCRIBE TABLE {table_ref}",
                    catalog=catalog,
                    schema=schema,
                    timeout=45,
                )
                if not describe_result:
                    return {}, 0, []
            else:
                # For read_files, infer schema from a sample query
                sample_query = f"SELECT * FROM {table_ref} LIMIT 1"
                sample_row = self.executor.execute(sql_query=sample_query, timeout=60)
                if not sample_row:
                    return {}, 0, []
                # Build describe_result-like structure from first row
                describe_result = []
                for col_name, value in sample_row[0].items():
                    if col_name == "_rescued_data":
                        continue
                    # Infer type from Python value
                    if isinstance(value, bool):
                        data_type = "boolean"
                    elif isinstance(value, int):
                        data_type = "bigint"
                    elif isinstance(value, float):
                        data_type = "double"
                    else:
                        data_type = "string"
                    describe_result.append(
                        {"col_name": col_name, "data_type": data_type}
                    )

            # Step 2: Get row count
            count_result = self.executor.execute(
                sql_query=f"SELECT COUNT(*) as total_rows FROM {table_ref}",
                catalog=catalog,
                schema=schema,
                timeout=45,
            )
            total_rows = count_result[0]["total_rows"] if count_result else 0

            # Step 3: Build unified stats query
            union_queries = []
            column_types: Dict[str, str] = {}
            columns_needing_value_counts: List[Tuple[str, str]] = []

            base_ref = "base"
            base_cte = f"WITH {base_ref} AS (SELECT * FROM {table_ref})\n"

            for col_info in describe_result:
                col_name = col_info.get("col_name", "")
                if not col_name or col_name.startswith("#") or col_name.startswith("_"):
                    continue

                data_type = col_info.get("data_type", "").lower()
                escaped_col = f"`{col_name}`"

                # Determine column type
                is_numeric = any(t in data_type for t in NUMERIC_TYPES)
                is_timestamp = "timestamp" in data_type
                is_array = "array" in data_type
                is_boolean = "boolean" in data_type
                is_id = any(p in col_name.lower() for p in ID_PATTERNS) and (
                    "bigint" in data_type or "string" in data_type
                )

                if is_array:
                    col_type = "array"
                elif is_timestamp:
                    col_type = "timestamp"
                elif is_boolean:
                    col_type = "boolean"
                elif is_id:
                    col_type = "id"
                elif is_numeric:
                    col_type = "numeric"
                else:
                    col_type = "categorical"

                column_types[col_name] = col_type

                # Build query based on type
                query = self._build_column_stats_query(
                    col_name, escaped_col, data_type, col_type, base_ref
                )
                union_queries.append(query)

                if col_type == "boolean":
                    columns_needing_value_counts.append((col_name, "boolean"))

            if not union_queries:
                return {}, total_rows, []

            # Execute combined stats query
            combined_query = base_cte + "\nUNION ALL\n".join(union_queries)
            stats_result = self.executor.execute(
                sql_query=combined_query,
                catalog=catalog,
                schema=schema,
                timeout=60,
            )

            # Step 4: Get sample data
            sample_result = self.executor.execute(
                sql_query=f"SELECT * FROM {table_ref} LIMIT {SAMPLE_ROW_COUNT}",
                catalog=catalog,
                schema=schema,
                timeout=45,
            )
            # Filter out _rescued_data column from samples
            if sample_result:
                sample_result = [
                    {k: v for k, v in row.items() if k != "_rescued_data"}
                    for row in sample_result
                ]

            # Step 5: Build column samples from sample data
            column_samples = self._extract_column_samples(
                describe_result, sample_result
            )

            # Step 6: Parse stats results
            column_details = self._parse_stats_results(
                stats_result, column_types, column_samples
            )

            # Step 7: Get value counts for categorical columns (only for UC tables)
            if fetch_value_counts_table:
                for col_name, detail in column_details.items():
                    if column_types.get(col_name) == "categorical":
                        approx_unique = detail.unique_count or 0
                        if 0 < approx_unique < MAX_CATEGORICAL_VALUES:
                            columns_needing_value_counts.append(
                                (col_name, "categorical")
                            )

                # Parse catalog.schema.table from fetch_value_counts_table
                parts = fetch_value_counts_table.split(".")
                if len(parts) == 3:
                    self._fetch_value_counts(
                        parts[0],
                        parts[1],
                        parts[2],
                        columns_needing_value_counts,
                        column_details,
                    )

            return column_details, total_rows, sample_result or []

        except Exception as e:
            logger.warning(f"Failed to collect stats for {table_ref}: {e}")
            return {}, 0, []

    def _build_column_stats_query(
        self,
        col_name: str,
        escaped_col: str,
        data_type: str,
        col_type: str,
        base_ref: str,
    ) -> str:
        """Build stats query for a column based on its type."""
        if col_type == "array":
            return f"""
                SELECT
                    '{col_name}' AS column_name,
                    '{data_type}' AS data_type,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN {escaped_col} IS NULL THEN 1 ELSE 0 END) AS null_count,
                    NULL AS unique_count,
                    NULL AS min_val, NULL AS max_val,
                    NULL AS mean_val, NULL AS stddev_val,
                    NULL AS q1_val, NULL AS median_val, NULL AS q3_val,
                    NULL AS histogram_data
                FROM {base_ref}
            """
        elif col_type == "numeric":
            return f"""
                SELECT
                    '{col_name}' AS column_name,
                    '{data_type}' AS data_type,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN {escaped_col} IS NULL THEN 1 ELSE 0 END) AS null_count,
                    approx_count_distinct({escaped_col}) AS unique_count,
                    CAST(MIN({escaped_col}) AS STRING) AS min_val,
                    CAST(MAX({escaped_col}) AS STRING) AS max_val,
                    CAST(AVG({escaped_col}) AS STRING) AS mean_val,
                    CAST(STDDEV({escaped_col}) AS STRING) AS stddev_val,
                    CAST(approx_percentile({escaped_col}, 0.25) AS STRING) AS q1_val,
                    CAST(approx_percentile({escaped_col}, 0.5) AS STRING) AS median_val,
                    CAST(approx_percentile({escaped_col}, 0.75) AS STRING) AS q3_val,
                    to_json(histogram_numeric({escaped_col}, {HISTOGRAM_BINS})) AS histogram_data
                FROM {base_ref}
            """
        elif col_type == "timestamp":
            return f"""
                SELECT
                    '{col_name}' AS column_name,
                    '{data_type}' AS data_type,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN {escaped_col} IS NULL THEN 1 ELSE 0 END) AS null_count,
                    approx_count_distinct({escaped_col}) AS unique_count,
                    CAST(MIN({escaped_col}) AS STRING) AS min_val,
                    CAST(MAX({escaped_col}) AS STRING) AS max_val,
                    NULL AS mean_val, NULL AS stddev_val,
                    NULL AS q1_val, NULL AS median_val, NULL AS q3_val,
                    to_json(histogram_numeric(unix_timestamp({escaped_col}), {HISTOGRAM_BINS})) AS histogram_data
                FROM {base_ref}
            """
        else:
            # boolean, id, categorical, date
            return f"""
                SELECT
                    '{col_name}' AS column_name,
                    '{data_type}' AS data_type,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN {escaped_col} IS NULL THEN 1 ELSE 0 END) AS null_count,
                    approx_count_distinct({escaped_col}) AS unique_count,
                    {"CAST(MIN(" + escaped_col + ") AS STRING)" if col_type == "date" else "NULL"} AS min_val,
                    {"CAST(MAX(" + escaped_col + ") AS STRING)" if col_type == "date" else "NULL"} AS max_val,
                    NULL AS mean_val, NULL AS stddev_val,
                    NULL AS q1_val, NULL AS median_val, NULL AS q3_val,
                    NULL AS histogram_data
                FROM {base_ref}
            """

    def _extract_column_samples(
        self, columns_info: List[Dict], sample_data: Optional[List[Dict]]
    ) -> Dict[str, List[str]]:
        """Extract sample values for each column."""
        column_samples: Dict[str, List[str]] = {}
        if not sample_data:
            return column_samples

        for col_info in columns_info:
            col_name = col_info.get("col_name", "")
            if not col_name or col_name.startswith("#") or col_name.startswith("_"):
                continue

            seen = set()
            samples = []
            for row in sample_data:
                if col_name in row and row[col_name] is not None:
                    val_str = str(row[col_name])
                    if len(val_str) > 15:
                        val_str = val_str[:15] + "..."
                    if val_str not in seen:
                        seen.add(val_str)
                        samples.append(val_str)
                        if len(samples) >= 3:
                            break
            column_samples[col_name] = samples

        return column_samples

    def _parse_stats_results(
        self,
        stats_result: List[Dict],
        column_types: Dict[str, str],
        column_samples: Dict[str, List[str]],
    ) -> Dict[str, ColumnDetail]:
        """Parse stats query results into ColumnDetail objects."""
        column_details: Dict[str, ColumnDetail] = {}

        for row in stats_result:
            col_name = row.get("column_name")
            if not col_name:
                continue

            col_type = column_types.get(col_name, "categorical")
            row.get("data_type", "unknown")
            samples = column_samples.get(col_name, [])
            approx_unique = (
                int(row.get("unique_count") or 0)
                if row.get("unique_count") is not None
                else None
            )

            # Parse histogram if present
            histogram_bins = None
            if row.get("histogram_data"):
                try:
                    hist_str = row.get("histogram_data")
                    if hist_str and hist_str != "null":
                        hist_data = json.loads(hist_str)
                        if isinstance(hist_data, list) and hist_data:
                            histogram_bins = [
                                HistogramBin(
                                    bin_center=float(item.get("x") or 0),
                                    count=int(item.get("y") or 0),
                                )
                                for item in hist_data
                            ]
                except Exception as e:
                    logger.debug(f"Failed to parse histogram for {col_name}: {e}")

            # Build ColumnDetail based on type
            if col_type == "numeric":
                detail = ColumnDetail(
                    name=col_name,
                    data_type="numeric",
                    samples=samples,
                    total_count=int(row.get("total_count") or 0),
                    null_count=int(row.get("null_count") or 0),
                    unique_count=approx_unique,
                    min=float(row["min_val"]) if row.get("min_val") else None,
                    max=float(row["max_val"]) if row.get("max_val") else None,
                    avg=float(row["mean_val"]) if row.get("mean_val") else None,
                    mean=float(row["mean_val"]) if row.get("mean_val") else None,
                    stddev=float(row["stddev_val"]) if row.get("stddev_val") else None,
                    q1=float(row["q1_val"]) if row.get("q1_val") else None,
                    median=float(row["median_val"]) if row.get("median_val") else None,
                    q3=float(row["q3_val"]) if row.get("q3_val") else None,
                    histogram=histogram_bins,
                )
            elif col_type == "timestamp":
                detail = ColumnDetail(
                    name=col_name,
                    data_type="timestamp",
                    samples=samples,
                    total_count=int(row.get("total_count") or 0),
                    null_count=int(row.get("null_count") or 0),
                    unique_count=approx_unique,
                    min_date=str(row["min_val"]) if row.get("min_val") else None,
                    max_date=str(row["max_val"]) if row.get("max_val") else None,
                    histogram=histogram_bins,
                )
            elif col_type == "array":
                detail = ColumnDetail(
                    name=col_name,
                    data_type="array",
                    samples=samples,
                    total_count=int(row.get("total_count") or 0),
                    null_count=int(row.get("null_count") or 0),
                )
            else:
                # boolean, id, categorical, date
                final_type = col_type
                if (
                    col_type == "categorical"
                    and approx_unique
                    and approx_unique >= MAX_CATEGORICAL_VALUES
                ):
                    final_type = "string"

                detail = ColumnDetail(
                    name=col_name,
                    data_type=final_type,
                    samples=samples,
                    total_count=int(row.get("total_count") or 0),
                    null_count=int(row.get("null_count") or 0),
                    unique_count=approx_unique,
                    min=str(row["min_val"]) if row.get("min_val") else None,
                    max=str(row["max_val"]) if row.get("max_val") else None,
                )

            column_details[col_name] = detail

        return column_details

    def _fetch_value_counts(
        self,
        catalog: str,
        schema: str,
        table_name: str,
        columns: List[Tuple[str, str]],
        column_details: Dict[str, ColumnDetail],
    ) -> None:
        """Fetch exact value counts for small-cardinality columns."""
        full_table_name = f"{catalog}.{schema}.{table_name}"

        for col_name, col_type in columns:
            if col_name not in column_details:
                continue

            escaped_col = f"`{col_name}`"
            query = f"""
                SELECT {escaped_col} AS value, COUNT(*) AS count
                FROM {full_table_name}
                WHERE {escaped_col} IS NOT NULL
                GROUP BY {escaped_col}
                ORDER BY COUNT(*) DESC
            """

            try:
                result = self.executor.execute(
                    sql_query=query,
                    catalog=catalog,
                    schema=schema,
                    timeout=45,
                )
                if result:
                    actual_count = len(result)
                    if actual_count <= MAX_CATEGORICAL_VALUES:
                        value_counts = {
                            str(row.get("value", "")): int(row.get("count") or 0)
                            for row in result
                        }
                        column_details[col_name].value_counts = value_counts
                        column_details[col_name].unique_count = actual_count
            except Exception as e:
                logger.debug(f"Failed to get value counts for {col_name}: {e}")

    def get_table_info(
        self,
        catalog: str,
        schema: str,
        table_name: str,
        updated_at_ms: Optional[int],
        comment: Optional[str],
        collect_stats: bool = True,
    ) -> TableInfo:
        """
        Get complete info for a single table.

        Args:
            catalog: Catalog name
            schema: Schema name
            table_name: Table name
            updated_at_ms: Table's updated_at timestamp (for cache validation)
            comment: Table comment
            collect_stats: Whether to collect column statistics

        Returns:
            TableInfo with DDL and optionally column stats
        """
        full_table_name = f"{catalog}.{schema}.{table_name}"
        table_lock = _get_table_lock(full_table_name)

        with table_lock:
            # Check cache (only if collecting stats)
            if collect_stats:
                cached = _check_cache(catalog, schema, table_name, updated_at_ms)
                if cached:
                    logger.debug(f"Using cached info for {full_table_name}")
                    return cached

            # Get DDL
            ddl = self.get_table_ddl(catalog, schema, table_name)

            # Collect stats if requested
            column_details = None
            total_rows = None
            sample_data = None

            if collect_stats:
                try:
                    column_details, total_rows, sample_data = self.collect_column_stats(
                        catalog, schema, table_name
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to collect stats for {full_table_name}: {e}"
                    )

            table_info = TableInfo(
                name=full_table_name,
                comment=comment,
                ddl=ddl,
                column_details=column_details,
                updated_at=updated_at_ms,
                total_rows=total_rows,
                sample_data=sample_data,
            )

            # Update cache (only if we collected stats)
            if collect_stats and not table_info.error:
                _update_cache(catalog, schema, table_name, updated_at_ms, table_info)

            return table_info

    def get_tables_info_parallel(
        self,
        catalog: str,
        schema: str,
        tables: List[Dict[str, Any]],
        collect_stats: bool = True,
    ) -> List[TableInfo]:
        """
        Get info for multiple tables in parallel.

        Args:
            catalog: Catalog name
            schema: Schema name
            tables: List of table info dicts with 'name', 'updated_at', 'comment'
            collect_stats: Whether to collect column statistics

        Returns:
            List of TableInfo objects
        """
        if not tables:
            return []

        def process_table(table_info: Dict) -> TableInfo:
            table_name = table_info["name"]
            updated_at = table_info.get("updated_at")
            updated_at_ms = int(updated_at) if updated_at else None
            comment = table_info.get("comment")

            try:
                return self.get_table_info(
                    catalog, schema, table_name, updated_at_ms, comment, collect_stats
                )
            except Exception as e:
                logger.error(
                    f"Failed to get info for {catalog}.{schema}.{table_name}: {e}"
                )
                return TableInfo(
                    name=f"{catalog}.{schema}.{table_name}",
                    ddl="",
                    error=str(e),
                )

        results = []
        max_workers = min(self.max_workers, len(tables))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_table = {executor.submit(process_table, t): t for t in tables}
            for future in as_completed(future_to_table):
                try:
                    results.append(future.result())
                except Exception as e:
                    table = future_to_table[future]
                    logger.error(f"Unexpected error for {table['name']}: {e}")
                    results.append(
                        TableInfo(
                            name=f"{catalog}.{schema}.{table['name']}",
                            ddl="",
                            error=str(e),
                        )
                    )

        return results
