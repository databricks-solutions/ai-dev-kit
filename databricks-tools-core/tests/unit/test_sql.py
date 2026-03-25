"""Unit tests for SQL execution functions."""

from unittest import mock

from databricks.sdk.service.sql import State, StatementState

from databricks_tools_core.sql import execute_sql, execute_sql_multi
from databricks_tools_core.sql.sql_utils import SQLExecutor
from databricks_tools_core.sql.warehouse import _sort_within_tier, get_best_warehouse


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


def _make_warehouse(id, name, state, creator_name="other@example.com", enable_serverless_compute=False):
    """Helper to create a mock warehouse object."""
    w = mock.Mock()
    w.id = id
    w.name = name
    w.state = state
    w.creator_name = creator_name
    w.enable_serverless_compute = enable_serverless_compute
    w.cluster_size = "Small"
    w.auto_stop_mins = 10
    return w


class TestSortWithinTier:
    """Tests for _sort_within_tier serverless and user-owned preference."""

    def test_serverless_first(self):
        """Serverless warehouses should come before classic ones."""
        classic = _make_warehouse("c1", "Classic WH", State.RUNNING)
        serverless = _make_warehouse("s1", "Serverless WH", State.RUNNING, enable_serverless_compute=True)
        result = _sort_within_tier([classic, serverless], current_user=None)
        assert result[0].id == "s1"
        assert result[1].id == "c1"

    def test_serverless_before_user_owned(self):
        """Serverless should be preferred over user-owned classic."""
        classic_owned = _make_warehouse("c1", "My WH", State.RUNNING, creator_name="me@example.com")
        serverless_other = _make_warehouse(
            "s1", "Other WH", State.RUNNING, creator_name="other@example.com", enable_serverless_compute=True
        )
        result = _sort_within_tier([classic_owned, serverless_other], current_user="me@example.com")
        assert result[0].id == "s1"

    def test_serverless_user_owned_first(self):
        """Among serverless, user-owned should come first."""
        serverless_other = _make_warehouse(
            "s1", "Other Serverless", State.RUNNING, creator_name="other@example.com", enable_serverless_compute=True
        )
        serverless_owned = _make_warehouse(
            "s2", "My Serverless", State.RUNNING, creator_name="me@example.com", enable_serverless_compute=True
        )
        result = _sort_within_tier([serverless_other, serverless_owned], current_user="me@example.com")
        assert result[0].id == "s2"
        assert result[1].id == "s1"

    def test_empty_list(self):
        assert _sort_within_tier([], current_user="me@example.com") == []

    def test_no_current_user(self):
        """Without a current user, only serverless preference applies."""
        classic = _make_warehouse("c1", "Classic", State.RUNNING)
        serverless = _make_warehouse("s1", "Serverless", State.RUNNING, enable_serverless_compute=True)
        result = _sort_within_tier([classic, serverless], current_user=None)
        assert result[0].id == "s1"


class TestGetBestWarehouseServerless:
    """Tests for serverless preference in get_best_warehouse."""

    @mock.patch("databricks_tools_core.sql.warehouse.get_current_username", return_value="me@example.com")
    @mock.patch("databricks_tools_core.sql.warehouse.get_workspace_client")
    def test_prefers_serverless_within_running_shared(self, mock_client_fn, mock_user):
        """Among running shared warehouses, serverless should be picked."""
        classic_shared = _make_warehouse("c1", "Shared WH", State.RUNNING)
        serverless_shared = _make_warehouse("s1", "Shared Serverless", State.RUNNING, enable_serverless_compute=True)
        mock_client = mock.Mock()
        mock_client.warehouses.list.return_value = [classic_shared, serverless_shared]
        mock_client_fn.return_value = mock_client

        result = get_best_warehouse()
        assert result == "s1"

    @mock.patch("databricks_tools_core.sql.warehouse.get_current_username", return_value="me@example.com")
    @mock.patch("databricks_tools_core.sql.warehouse.get_workspace_client")
    def test_prefers_serverless_within_running_other(self, mock_client_fn, mock_user):
        """Among running non-shared warehouses, serverless should be picked."""
        classic = _make_warehouse("c1", "My WH", State.RUNNING)
        serverless = _make_warehouse("s1", "Fast WH", State.RUNNING, enable_serverless_compute=True)
        mock_client = mock.Mock()
        mock_client.warehouses.list.return_value = [classic, serverless]
        mock_client_fn.return_value = mock_client

        result = get_best_warehouse()
        assert result == "s1"

    @mock.patch("databricks_tools_core.sql.warehouse.get_current_username", return_value="me@example.com")
    @mock.patch("databricks_tools_core.sql.warehouse.get_workspace_client")
    def test_tier_order_preserved_over_serverless(self, mock_client_fn, mock_user):
        """A running shared classic should still beat a stopped serverless."""
        running_shared_classic = _make_warehouse("c1", "Shared WH", State.RUNNING)
        stopped_serverless = _make_warehouse("s1", "Fast WH", State.STOPPED, enable_serverless_compute=True)
        mock_client = mock.Mock()
        mock_client.warehouses.list.return_value = [stopped_serverless, running_shared_classic]
        mock_client_fn.return_value = mock_client

        result = get_best_warehouse()
        assert result == "c1"
