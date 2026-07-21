"""
SQL Executor - Internal class for executing SQL queries on Databricks.
"""

import time
import logging
from typing import Any, Dict, List, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

from ...auth import get_workspace_client

logger = logging.getLogger(__name__)


class SQLExecutionError(Exception):
    """Exception raised when SQL execution fails.

    Provides detailed error messages for LLM consumption.
    """


class SQLExecutor:
    """Execute SQL queries on Databricks SQL Warehouses."""

    def __init__(self, warehouse_id: str, client: Optional[WorkspaceClient] = None):
        """
        Initialize the SQL executor.

        Args:
            warehouse_id: SQL warehouse ID to use for queries
            client: Optional WorkspaceClient (creates new one if not provided)

        Raises:
            SQLExecutionError: If no warehouse ID is provided
        """
        if not warehouse_id:
            raise SQLExecutionError(
                "No SQL warehouse ID provided. "
                "Either specify a warehouse_id or let the system select one automatically."
            )
        self.warehouse_id = warehouse_id
        self.client = client or get_workspace_client()

    def execute(
        self,
        sql_query: str,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        row_limit: Optional[int] = None,
        timeout: int = 180,
        query_tags: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results as a list of dictionaries.

        Args:
            sql_query: SQL query to execute
            catalog: Optional catalog context for the query
            schema: Optional schema context for the query
            row_limit: Optional maximum number of rows to return
            timeout: Timeout in seconds (default: 180)
            query_tags: Optional query tags for cost attribution and filtering.
                Format: "key:value,key2:value2" (e.g., "team:eng,cost_center:701").
                Appears in system.query.history and Query History UI.

        Returns:
            List of dictionaries, each representing a row with column names as keys

        Raises:
            SQLExecutionError: If query execution fails with detailed error message
        """
        logger.debug(f"Executing SQL query: {sql_query[:100]}...")

        # Build execution parameters
        exec_params = {
            "warehouse_id": self.warehouse_id,
            "statement": sql_query,
            "wait_timeout": "0s",  # Immediate return, we poll manually
        }
        if catalog:
            exec_params["catalog"] = catalog
        if schema:
            exec_params["schema"] = schema
        if row_limit is not None:
            exec_params["row_limit"] = row_limit
        if query_tags:
            from databricks.sdk.service.sql import QueryTag

            exec_params["query_tags"] = [
                QueryTag(key=k.strip(), value=v.strip())
                for pair in query_tags.split(",")
                for k, v in [pair.split(":", 1)]
                if ":" in pair
            ]

        # Submit the statement
        try:
            response = self.client.statement_execution.execute_statement(**exec_params)
        except Exception as e:
            raise SQLExecutionError(
                f"Failed to submit SQL query to warehouse '{self.warehouse_id}': {str(e)}. "
                f"Check that the warehouse exists and is accessible."
            )

        statement_id = response.statement_id
        logger.debug(f"Statement submitted with ID: {statement_id}")

        # Poll for completion.
        #
        # Use time.monotonic() for the timeout boundary instead of incrementing
        # a counter by poll_interval each iteration. The counter approach
        # tracks only sleep time and ignores how long each get_statement RPC
        # takes — under warehouse load, get_statement can take several seconds
        # per call, so the counter undercounts wall clock and the configured
        # timeout fires much later than intended (or, for very slow RPCs,
        # never fires before the statement completes naturally).
        poll_interval = 2
        start_time = time.monotonic()

        while time.monotonic() - start_time < timeout:
            try:
                status = self.client.statement_execution.get_statement(statement_id=statement_id)
            except Exception as e:
                raise SQLExecutionError(f"Failed to check status of statement '{statement_id}': {str(e)}")

            state = status.status.state

            if state == StatementState.SUCCEEDED:
                return self._extract_results(status)

            if state == StatementState.FAILED:
                error_msg = self._get_error_message(status)
                raise SQLExecutionError(
                    f"SQL query failed: {error_msg}\nQuery: {sql_query[:500]}{'...' if len(sql_query) > 500 else ''}"
                )

            if state == StatementState.CANCELED:
                raise SQLExecutionError(f"SQL query was canceled before completion. Statement ID: {statement_id}")

            if state == StatementState.CLOSED:
                raise SQLExecutionError(f"SQL statement was closed unexpectedly. Statement ID: {statement_id}")

            # Still running, wait and poll again
            time.sleep(poll_interval)

        # Timeout reached - cancel the statement
        self._cancel_statement(statement_id)
        elapsed_wall = time.monotonic() - start_time
        raise SQLExecutionError(
            f"SQL query timed out after {elapsed_wall:.1f} seconds (limit: {timeout}s) and was canceled. "
            f"Consider increasing the timeout or optimizing the query. "
            f"Statement ID: {statement_id}"
        )

    def _extract_results(self, response) -> List[Dict[str, Any]]:
        """Extract results from a successful statement response."""
        results: List[Dict[str, Any]] = []

        if not response.result or not response.result.data_array:
            return results

        # Get column names from manifest
        columns = None
        if response.manifest and response.manifest.schema and response.manifest.schema.columns:
            columns = [col.name for col in response.manifest.schema.columns]

        # Convert rows to dicts
        for row in response.result.data_array:
            if columns:
                results.append(dict(zip(columns, row, strict=False)))
            else:
                # Fallback if no schema available
                results.append({"values": list(row)})

        return results

    def _get_error_message(self, response) -> str:
        """Extract error message from a failed statement response."""
        if response.status and response.status.error:
            error = response.status.error
            msg = error.message if error.message else "Unknown error"
            if error.error_code:
                msg = f"[{error.error_code}] {msg}"
            return msg
        return "Unknown error (no error details available)"

    def _cancel_statement(self, statement_id: str) -> None:
        """Attempt to cancel a running statement."""
        try:
            self.client.statement_execution.cancel_execution(statement_id=statement_id)
            logger.debug(f"Canceled statement {statement_id}")
        except Exception as e:
            logger.warning(f"Failed to cancel statement {statement_id}: {e}")
