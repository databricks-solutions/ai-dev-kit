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

    pass


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
    ) -> List[Dict[str, Any]]:
        """
        Execute a SQL query and return results as a list of dictionaries.

        Args:
            sql_query: SQL query to execute
            catalog: Optional catalog context for the query
            schema: Optional schema context for the query
            row_limit: Optional maximum number of rows to return
            timeout: Timeout in seconds (default: 180)

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

        # Poll for completion
        poll_interval = 2
        elapsed = 0

        while elapsed < timeout:
            try:
                status = self.client.statement_execution.get_statement(
                    statement_id=statement_id
                )
            except Exception as e:
                raise SQLExecutionError(
                    f"Failed to check status of statement '{statement_id}': {str(e)}"
                )

            state = status.status.state

            if state == StatementState.SUCCEEDED:
                return self._extract_results(status)

            if state == StatementState.FAILED:
                error_msg = self._get_error_message(status)
                raise SQLExecutionError(
                    f"SQL query failed: {error_msg}\n"
                    f"Query: {sql_query[:500]}{'...' if len(sql_query) > 500 else ''}"
                )

            if state == StatementState.CANCELED:
                raise SQLExecutionError(
                    f"SQL query was canceled before completion. "
                    f"Statement ID: {statement_id}"
                )

            if state == StatementState.CLOSED:
                raise SQLExecutionError(
                    f"SQL statement was closed unexpectedly. "
                    f"Statement ID: {statement_id}"
                )

            # Still running, wait and poll again
            time.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout reached - cancel the statement
        self._cancel_statement(statement_id)
        raise SQLExecutionError(
            f"SQL query timed out after {timeout} seconds and was canceled. "
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
        if (
            response.manifest
            and response.manifest.schema
            and response.manifest.schema.columns
        ):
            columns = [col.name for col in response.manifest.schema.columns]

        # Convert rows to dicts
        for row in response.result.data_array:
            if columns:
                results.append(dict(zip(columns, row)))
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
