"""Unit tests for SQL execution functions."""

from unittest import mock

import pytest
from databricks.sdk.service.sql import StatementState

from databricks_tools_core.sql import execute_sql, execute_sql_multi
from databricks_tools_core.sql.sql_utils import SQLExecutor


class TestExecuteSQLQueryTags:
    """Tests for query_tags parameter passthrough."""

    @mock.patch("databricks_tools_core.sql.sql.get_best_warehouse", return_value="wh-123")
    @mock.patch("databricks_tools_core.sql.sql.SQLExecutor")
    def test_execute_sql_passes_query_tags_to_executor(self, mock_executor_cls, mock_warehouse):
        """query_tags should be passed through to SQLExecutor.execute()."""
        mock_executor = mock.Mock()
        mock_executor.execute.return_value = [{"num": 1}]
        mock_executor_cls.return_value = mock_executor

        execute_sql(
            sql_query="SELECT 1",
            warehouse_id="wh-123",
            query_tags="team:eng,cost_center:701",
        )

        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs["query_tags"] == "team:eng,cost_center:701"

    @mock.patch("databricks_tools_core.sql.sql.get_best_warehouse", return_value="wh-123")
    @mock.patch("databricks_tools_core.sql.sql.SQLExecutor")
    def test_execute_sql_without_query_tags(self, mock_executor_cls, mock_warehouse):
        """When query_tags not provided, executor should not receive it (or receive None)."""
        mock_executor = mock.Mock()
        mock_executor.execute.return_value = [{"num": 1}]
        mock_executor_cls.return_value = mock_executor

        execute_sql(sql_query="SELECT 1", warehouse_id="wh-123")

        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs.get("query_tags") is None

    @mock.patch("databricks_tools_core.sql.sql.get_best_warehouse", return_value="wh-123")
    @mock.patch("databricks_tools_core.sql.sql.SQLParallelExecutor")
    def test_execute_sql_multi_passes_query_tags(self, mock_parallel_cls, mock_warehouse):
        """query_tags should be passed through to SQLParallelExecutor.execute()."""
        mock_executor = mock.Mock()
        mock_executor.execute.return_value = {
            "results": {0: {"status": "success", "query_index": 0}},
            "execution_summary": {"total_queries": 1, "total_groups": 1},
        }
        mock_parallel_cls.return_value = mock_executor

        execute_sql_multi(
            sql_content="SELECT 1;",
            warehouse_id="wh-123",
            query_tags="app:agent,env:dev",
        )

        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args.kwargs
        assert call_kwargs["query_tags"] == "app:agent,env:dev"


class TestSQLExecutorQueryTags:
    """Tests for SQLExecutor passing query_tags to the API."""

    @mock.patch("databricks_tools_core.sql.sql_utils.executor.get_workspace_client")
    def test_executor_passes_query_tags_to_api(self, mock_get_client):
        """SQLExecutor.execute() should include query_tags in execute_statement call."""
        mock_client = mock.Mock()
        mock_response = mock.Mock()
        mock_response.statement_id = "stmt-1"
        mock_client.statement_execution.execute_statement.return_value = mock_response

        # Simulate SUCCEEDED state on get_statement
        mock_status = mock.Mock()
        mock_status.status.state = StatementState.SUCCEEDED
        mock_status.result = mock.Mock()
        mock_status.result.data_array = []
        mock_status.manifest = None
        mock_client.statement_execution.get_statement.return_value = mock_status

        mock_get_client.return_value = mock_client

        executor = SQLExecutor(warehouse_id="wh-123", client=mock_client)
        executor.execute(
            sql_query="SELECT 1",
            query_tags="team:eng,cost_center:701",
        )

        call_kwargs = mock_client.statement_execution.execute_statement.call_args.kwargs
        assert call_kwargs.get("query_tags") == "team:eng,cost_center:701"

    @mock.patch("databricks_tools_core.sql.sql_utils.executor.get_workspace_client")
    def test_executor_without_query_tags_omits_from_api(self, mock_get_client):
        """When query_tags not provided, it should not be in the API call."""
        mock_client = mock.Mock()
        mock_response = mock.Mock()
        mock_response.statement_id = "stmt-1"
        mock_client.statement_execution.execute_statement.return_value = mock_response

        mock_status = mock.Mock()
        mock_status.status.state = StatementState.SUCCEEDED
        mock_status.result = mock.Mock()
        mock_status.result.data_array = []
        mock_status.manifest = None
        mock_client.statement_execution.get_statement.return_value = mock_status

        mock_get_client.return_value = mock_client

        executor = SQLExecutor(warehouse_id="wh-123", client=mock_client)
        executor.execute(sql_query="SELECT 1")

        call_kwargs = mock_client.statement_execution.execute_statement.call_args.kwargs
        assert "query_tags" not in call_kwargs
