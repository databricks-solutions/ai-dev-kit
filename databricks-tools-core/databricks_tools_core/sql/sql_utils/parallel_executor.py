"""
SQL Parallel Executor

Executes multiple SQL queries with dependency-aware parallelism.
Queries within a group run in parallel; groups run sequentially.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

from databricks.sdk import WorkspaceClient

from ...auth import get_workspace_client
from .dependency_analyzer import SQLDependencyAnalyzer
from .executor import SQLExecutor, SQLExecutionError

logger = logging.getLogger(__name__)


class SQLParallelExecutor:
    """Execute multiple SQL queries with dependency-aware parallelism.

    Analyzes query dependencies and executes them in optimal order:
    - Queries with no dependencies on each other run in parallel
    - Queries that depend on others wait for their dependencies
    - Execution stops on first error (fail-fast)
    """

    def __init__(
        self,
        warehouse_id: str,
        max_workers: int = 4,
        client: Optional[WorkspaceClient] = None,
    ):
        """
        Initialize the parallel executor.

        Args:
            warehouse_id: SQL warehouse ID to use for queries
            max_workers: Maximum parallel queries per group (default: 4)
            client: Optional WorkspaceClient (creates new one if not provided)
        """
        self.warehouse_id = warehouse_id
        self.max_workers = max_workers
        self.client = client or get_workspace_client()
        self.analyzer = SQLDependencyAnalyzer()
        self.sql_executor = SQLExecutor(warehouse_id=warehouse_id, client=self.client)

    def execute(
        self,
        sql_content: str,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        timeout: int = 180,
    ) -> Dict[str, Any]:
        """
        Execute multiple SQL statements with dependency-aware parallelism.

        Args:
            sql_content: SQL content with multiple statements separated by ;
            catalog: Optional catalog context for queries
            schema: Optional schema context for queries
            timeout: Timeout per query in seconds (default: 180)

        Returns:
            Dictionary with:
            - results: Dict mapping query index to result dict
            - execution_summary: Overall execution statistics

        Raises:
            SQLExecutionError: If parsing fails or no queries found
        """
        logger.info("Starting SQL parallel execution")
        start_time = time.time()

        # Parse and analyze
        queries = self.analyzer.parse_sql_content(sql_content)
        if not queries:
            raise SQLExecutionError(
                "No valid SQL statements found in the provided content. "
                "Check that statements are properly terminated with semicolons."
            )

        logger.info(f"Parsed {len(queries)} queries")

        execution_groups = self.analyzer.analyze_dependencies(queries)
        logger.info(f"Found {len(execution_groups)} execution groups")

        results: Dict[int, Dict[str, Any]] = {}
        stopped_after_group: Optional[int] = None

        # Execute groups sequentially
        for group_idx, group in enumerate(execution_groups):
            group_num = group_idx + 1
            logger.info(
                f"Executing group {group_num}/{len(execution_groups)} "
                f"with {len(group)} queries"
            )

            # Log query previews
            for query_idx in group:
                preview = queries[query_idx][:80].replace("\n", " ").replace("  ", " ")
                logger.debug(f"  [Q{query_idx + 1}] {preview}...")

            # Execute queries in this group (parallel if multiple)
            group_results = self._execute_group(
                queries=queries,
                query_indices=group,
                group_num=group_num,
                catalog=catalog,
                schema=schema,
                timeout=timeout,
            )

            # Store results and check for errors
            error_in_group = False
            for query_idx, result in group_results.items():
                results[query_idx] = result
                if result.get("status") == "error":
                    error_in_group = True

            # Stop on first error
            if error_in_group:
                stopped_after_group = group_num
                logger.warning(
                    f"Stopping execution after group {group_num} due to errors; "
                    f"subsequent groups will be skipped."
                )
                break

        total_time = round(time.time() - start_time, 2)
        logger.info(f"SQL parallel execution completed in {total_time:.2f}s")

        # Build summary
        execution_summary = self._build_summary(
            execution_groups=execution_groups,
            stopped_after_group=stopped_after_group,
            total_time=total_time,
        )

        return {
            "results": results,
            "execution_summary": execution_summary,
        }

    def _execute_group(
        self,
        queries: List[str],
        query_indices: List[int],
        group_num: int,
        catalog: Optional[str],
        schema: Optional[str],
        timeout: int,
    ) -> Dict[int, Dict[str, Any]]:
        """Execute a group of queries in parallel using ThreadPoolExecutor."""
        results: Dict[int, Dict[str, Any]] = {}
        is_parallel = len(query_indices) > 1

        def execute_single(query_idx: int) -> Dict[str, Any]:
            query_text = queries[query_idx]
            query_preview = (
                query_text[:100] + "..." if len(query_text) > 100 else query_text
            )
            query_preview = query_preview.replace("\n", " ").replace("  ", " ")

            try:
                logger.info(f"[SQL] Executing query {query_idx + 1}: {query_preview}")
                t0 = time.time()

                result_data = self.sql_executor.execute(
                    sql_query=query_text,
                    catalog=catalog,
                    schema=schema,
                    timeout=timeout,
                )

                dt = round(time.time() - t0, 2)
                row_count = len(result_data) if result_data else 0
                logger.info(
                    f"Query {query_idx + 1} completed ({dt}s, {row_count} rows)"
                )

                return {
                    "query_index": query_idx,
                    "status": "success",
                    "execution_time": dt,
                    "query_preview": query_preview,
                    "result_rows": row_count,
                    "sample_results": result_data[:5] if result_data else [],
                    "group_number": group_num,
                    "group_size": len(query_indices),
                    "is_parallel": is_parallel,
                }

            except Exception as e:
                error_str = str(e)
                error_category, suggestion = self._categorize_error(error_str)

                logger.error(
                    f"Query {query_idx + 1} failed: {error_category} - {error_str}"
                )

                return {
                    "query_index": query_idx,
                    "status": "error",
                    "error": error_str,
                    "error_category": error_category,
                    "suggestion": suggestion,
                    "execution_time": 0,
                    "query_preview": query_preview,
                    "group_number": group_num,
                    "group_size": len(query_indices),
                    "is_parallel": is_parallel,
                }

        # Use ThreadPoolExecutor for parallel execution within group
        max_workers = min(self.max_workers, len(query_indices))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(execute_single, idx): idx for idx in query_indices
            }

            for future in as_completed(future_to_idx):
                query_idx = future_to_idx[future]
                try:
                    results[query_idx] = future.result()
                except Exception as e:
                    # Unexpected error in thread
                    results[query_idx] = {
                        "query_index": query_idx,
                        "status": "error",
                        "error": f"Unexpected execution error: {str(e)}",
                        "error_category": "UNEXPECTED_ERROR",
                        "suggestion": "Check the query syntax and try again",
                        "execution_time": 0,
                        "group_number": group_num,
                        "group_size": len(query_indices),
                        "is_parallel": is_parallel,
                    }

        return results

    def _categorize_error(self, error_str: str) -> tuple:
        """Categorize error for better LLM understanding."""
        error_lower = error_str.lower()

        if "table or view not found" in error_lower or "table not found" in error_lower:
            return (
                "MISSING_TABLE",
                "Check if the table exists in the specified catalog and schema",
            )
        elif "column not found" in error_lower or "cannot resolve" in error_lower:
            return (
                "MISSING_COLUMN",
                "Verify column names and check for typos",
            )
        elif "syntax error" in error_lower or "parse error" in error_lower:
            return (
                "SYNTAX_ERROR",
                "Review SQL syntax for errors",
            )
        elif "permission denied" in error_lower or "access denied" in error_lower:
            return (
                "PERMISSION_ERROR",
                "Check user permissions on the table or catalog",
            )
        elif "timeout" in error_lower:
            return (
                "TIMEOUT_ERROR",
                "Query took too long; consider optimizing or increasing timeout",
            )
        elif "warehouse" in error_lower:
            return (
                "WAREHOUSE_ERROR",
                "Check that the SQL warehouse is running and accessible",
            )
        else:
            return (
                "GENERAL_ERROR",
                "Review the error message for details",
            )

    def _build_summary(
        self,
        execution_groups: List[List[int]],
        stopped_after_group: Optional[int],
        total_time: float,
    ) -> Dict[str, Any]:
        """Build execution summary with group details."""
        groups_summary: List[Dict[str, Any]] = []

        for group_idx, group in enumerate(execution_groups):
            group_num = group_idx + 1
            ran = stopped_after_group is None or group_num <= stopped_after_group

            groups_summary.append(
                {
                    "group_number": group_num,
                    "group_size": len(group),
                    "query_indices": [i + 1 for i in group],  # 1-based for display
                    "is_parallel": len(group) > 1,
                    "status": "executed" if ran else "skipped",
                }
            )

        return {
            "total_queries": sum(len(g) for g in execution_groups),
            "total_groups": len(execution_groups),
            "total_time": total_time,
            "stopped_after_group": stopped_after_group,
            "groups": groups_summary,
        }
