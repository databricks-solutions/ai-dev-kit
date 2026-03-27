"""
Unit tests for consolidated compute tools.

Tests the MCP tool wrapper routing logic without hitting Databricks APIs.
"""

import pytest
from unittest.mock import patch, MagicMock
from databricks_mcp_server.tools.compute import (
    execute_code,
    manage_cluster,
    manage_sql_warehouse,
    list_compute,
)


# ---------------------------------------------------------------------------
# execute_code routing tests
# ---------------------------------------------------------------------------


class TestExecuteCodeRouting:
    """Test that execute_code routes to the correct backend."""

    def test_requires_code_or_file_path(self):
        result = execute_code()
        assert result["success"] is False
        assert "code" in result["error"].lower() or "file_path" in result["error"].lower()

    def test_empty_strings_treated_as_none(self):
        result = execute_code(code="", file_path="")
        assert result["success"] is False
        assert "code" in result["error"].lower() or "file_path" in result["error"].lower()

    @patch("databricks_mcp_server.tools.compute._run_code_on_serverless")
    def test_auto_routes_to_serverless_for_python(self, mock_serverless):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True, "output": "hello"}
        mock_serverless.return_value = mock_result

        execute_code(code="print('hi')", compute_type="auto")

        mock_serverless.assert_called_once()
        call_kwargs = mock_serverless.call_args[1]
        assert call_kwargs["code"] == "print('hi')"
        assert call_kwargs["language"] == "python"

    @patch("databricks_mcp_server.tools.compute._execute_databricks_command")
    def test_auto_routes_to_cluster_with_cluster_id(self, mock_cluster):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_cluster.return_value = mock_result

        execute_code(code="print('hi')", cluster_id="abc-123")

        mock_cluster.assert_called_once()
        assert mock_cluster.call_args[1]["cluster_id"] == "abc-123"

    @patch("databricks_mcp_server.tools.compute._execute_databricks_command")
    def test_auto_routes_to_cluster_with_context_id(self, mock_cluster):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_cluster.return_value = mock_result

        execute_code(code="print('hi')", context_id="ctx-456")

        mock_cluster.assert_called_once()
        assert mock_cluster.call_args[1]["context_id"] == "ctx-456"

    @patch("databricks_mcp_server.tools.compute._execute_databricks_command")
    def test_auto_routes_to_cluster_for_scala(self, mock_cluster):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_cluster.return_value = mock_result

        execute_code(code="println(42)", language="scala")

        mock_cluster.assert_called_once()
        assert mock_cluster.call_args[1]["language"] == "scala"

    @patch("databricks_mcp_server.tools.compute._execute_databricks_command")
    def test_auto_routes_to_cluster_for_r(self, mock_cluster):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_cluster.return_value = mock_result

        execute_code(code="print(42)", language="r")

        mock_cluster.assert_called_once()

    @patch("databricks_mcp_server.tools.compute._run_code_on_serverless")
    def test_explicit_serverless(self, mock_serverless):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_serverless.return_value = mock_result

        execute_code(code="print('hi')", compute_type="serverless")

        mock_serverless.assert_called_once()

    @patch("databricks_mcp_server.tools.compute._execute_databricks_command")
    def test_explicit_cluster(self, mock_cluster):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_cluster.return_value = mock_result

        execute_code(code="print('hi')", compute_type="cluster")

        mock_cluster.assert_called_once()

    @patch("databricks_mcp_server.tools.compute._run_code_on_serverless")
    def test_serverless_default_timeout(self, mock_serverless):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_serverless.return_value = mock_result

        execute_code(code="x", compute_type="serverless")

        assert mock_serverless.call_args[1]["timeout"] == 1800

    @patch("databricks_mcp_server.tools.compute._execute_databricks_command")
    def test_cluster_default_timeout(self, mock_cluster):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_cluster.return_value = mock_result

        execute_code(code="x", compute_type="cluster")

        assert mock_cluster.call_args[1]["timeout"] == 120

    @patch("databricks_mcp_server.tools.compute._run_code_on_serverless")
    def test_workspace_path_passed_to_serverless(self, mock_serverless):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_serverless.return_value = mock_result

        execute_code(code="x", compute_type="serverless", workspace_path="/Workspace/Users/a/b")

        call_kwargs = mock_serverless.call_args[1]
        assert call_kwargs["workspace_path"] == "/Workspace/Users/a/b"
        assert call_kwargs["cleanup"] is False

    @patch("databricks_mcp_server.tools.compute._run_file_on_databricks")
    def test_file_path_on_cluster(self, mock_run_file):
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"success": True}
        mock_run_file.return_value = mock_result

        execute_code(file_path="/tmp/test.py", compute_type="cluster")

        mock_run_file.assert_called_once()
        assert mock_run_file.call_args[1]["file_path"] == "/tmp/test.py"

    def test_file_path_not_found_serverless(self):
        result = execute_code(file_path="/nonexistent/file.py", compute_type="serverless")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @patch("databricks_mcp_server.tools.compute._execute_databricks_command")
    def test_no_running_cluster_error(self, mock_cluster):
        from databricks_tools_core.compute import NoRunningClusterError
        mock_cluster.side_effect = NoRunningClusterError(
            available_clusters=[],
            skipped_clusters=[],
            startable_clusters=[{"cluster_id": "abc", "cluster_name": "test", "state": "TERMINATED"}],
        )

        result = execute_code(code="x", compute_type="cluster")

        assert result["success"] is False
        assert "startable_clusters" in result
        assert len(result["startable_clusters"]) == 1


# ---------------------------------------------------------------------------
# manage_cluster routing tests
# ---------------------------------------------------------------------------


class TestManageCluster:
    """Test manage_cluster action routing."""

    def test_invalid_action(self):
        result = manage_cluster(action="explode")
        assert result["success"] is False
        assert "unknown action" in result["error"].lower()

    def test_create_requires_name(self):
        result = manage_cluster(action="create")
        assert result["success"] is False
        assert "name" in result["error"].lower()

    def test_modify_requires_cluster_id(self):
        result = manage_cluster(action="modify")
        assert result["success"] is False
        assert "cluster_id" in result["error"].lower()

    def test_start_requires_cluster_id(self):
        result = manage_cluster(action="start")
        assert result["success"] is False
        assert "cluster_id" in result["error"].lower()

    def test_terminate_requires_cluster_id(self):
        result = manage_cluster(action="terminate")
        assert result["success"] is False
        assert "cluster_id" in result["error"].lower()

    def test_delete_requires_cluster_id(self):
        result = manage_cluster(action="delete")
        assert result["success"] is False
        assert "cluster_id" in result["error"].lower()

    @patch("databricks_mcp_server.tools.compute._create_cluster")
    def test_create_routes_correctly(self, mock_create):
        mock_create.return_value = {"cluster_id": "abc", "state": "PENDING"}

        result = manage_cluster(action="create", name="test-cluster", num_workers=2)

        mock_create.assert_called_once()
        assert mock_create.call_args[1]["name"] == "test-cluster"
        assert mock_create.call_args[1]["num_workers"] == 2

    @patch("databricks_mcp_server.tools.compute._modify_cluster")
    def test_modify_routes_correctly(self, mock_modify):
        mock_modify.return_value = {"cluster_id": "abc"}

        manage_cluster(action="modify", cluster_id="abc", num_workers=4)

        mock_modify.assert_called_once()
        assert mock_modify.call_args[1]["cluster_id"] == "abc"
        assert mock_modify.call_args[1]["num_workers"] == 4

    @patch("databricks_mcp_server.tools.compute._start_cluster")
    def test_start_routes_correctly(self, mock_start):
        mock_start.return_value = {"cluster_id": "abc", "state": "PENDING"}

        manage_cluster(action="start", cluster_id="abc")

        mock_start.assert_called_once_with("abc")

    @patch("databricks_mcp_server.tools.compute._terminate_cluster")
    def test_terminate_routes_correctly(self, mock_terminate):
        mock_terminate.return_value = {"cluster_id": "abc", "state": "TERMINATING"}

        manage_cluster(action="terminate", cluster_id="abc")

        mock_terminate.assert_called_once_with("abc")

    @patch("databricks_mcp_server.tools.compute._delete_cluster")
    def test_delete_routes_correctly(self, mock_delete):
        mock_delete.return_value = {"cluster_id": "abc", "state": "DELETED"}

        manage_cluster(action="delete", cluster_id="abc")

        mock_delete.assert_called_once_with("abc")

    @patch("databricks_mcp_server.tools.compute._create_cluster")
    def test_create_defaults(self, mock_create):
        mock_create.return_value = {"cluster_id": "abc"}

        manage_cluster(action="create", name="test")

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["num_workers"] == 1
        assert call_kwargs["autotermination_minutes"] == 120

    @patch("databricks_mcp_server.tools.compute._create_cluster")
    def test_create_with_spark_conf_json(self, mock_create):
        mock_create.return_value = {"cluster_id": "abc"}

        manage_cluster(
            action="create",
            name="test",
            spark_conf='{"spark.sql.shuffle.partitions": "8"}',
        )

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["spark_conf"] == {"spark.sql.shuffle.partitions": "8"}


# ---------------------------------------------------------------------------
# manage_sql_warehouse routing tests
# ---------------------------------------------------------------------------


class TestManageSqlWarehouse:
    """Test manage_sql_warehouse action routing."""

    def test_invalid_action(self):
        result = manage_sql_warehouse(action="explode")
        assert result["success"] is False

    def test_create_requires_name(self):
        result = manage_sql_warehouse(action="create")
        assert result["success"] is False
        assert "name" in result["error"].lower()

    def test_modify_requires_warehouse_id(self):
        result = manage_sql_warehouse(action="modify")
        assert result["success"] is False
        assert "warehouse_id" in result["error"].lower()

    def test_delete_requires_warehouse_id(self):
        result = manage_sql_warehouse(action="delete")
        assert result["success"] is False
        assert "warehouse_id" in result["error"].lower()

    @patch("databricks_mcp_server.tools.compute._create_sql_warehouse")
    def test_create_routes_correctly(self, mock_create):
        mock_create.return_value = {"warehouse_id": "abc"}

        manage_sql_warehouse(action="create", name="test-wh", size="Medium")

        mock_create.assert_called_once()
        assert mock_create.call_args[1]["name"] == "test-wh"
        assert mock_create.call_args[1]["size"] == "Medium"

    @patch("databricks_mcp_server.tools.compute._modify_sql_warehouse")
    def test_modify_routes_correctly(self, mock_modify):
        mock_modify.return_value = {"warehouse_id": "abc"}

        manage_sql_warehouse(action="modify", warehouse_id="abc", size="Large")

        mock_modify.assert_called_once()
        assert mock_modify.call_args[1]["size"] == "Large"

    @patch("databricks_mcp_server.tools.compute._delete_sql_warehouse")
    def test_delete_routes_correctly(self, mock_delete):
        mock_delete.return_value = {"warehouse_id": "abc"}

        manage_sql_warehouse(action="delete", warehouse_id="abc")

        mock_delete.assert_called_once_with("abc")


# ---------------------------------------------------------------------------
# list_compute routing tests
# ---------------------------------------------------------------------------


class TestListCompute:
    """Test list_compute resource routing."""

    @patch("databricks_mcp_server.tools.compute._list_clusters")
    def test_default_lists_clusters(self, mock_list):
        mock_list.return_value = [{"cluster_id": "abc", "cluster_name": "test"}]

        result = list_compute()

        mock_list.assert_called_once()
        assert "clusters" in result

    @patch("databricks_mcp_server.tools.compute._get_cluster_status")
    def test_cluster_id_gets_status(self, mock_status):
        mock_status.return_value = {"cluster_id": "abc", "state": "RUNNING"}

        result = list_compute(cluster_id="abc")

        mock_status.assert_called_once_with("abc")
        assert result["state"] == "RUNNING"

    @patch("databricks_mcp_server.tools.compute._get_best_cluster")
    def test_auto_select(self, mock_best):
        mock_best.return_value = "best-cluster-id"

        result = list_compute(auto_select=True)

        mock_best.assert_called_once()
        assert result["cluster_id"] == "best-cluster-id"

    @patch("databricks_mcp_server.tools.compute._list_node_types")
    def test_node_types(self, mock_nodes):
        mock_nodes.return_value = [{"node_type_id": "i3.xlarge"}]

        result = list_compute(resource="node_types")

        mock_nodes.assert_called_once()
        assert "node_types" in result

    @patch("databricks_mcp_server.tools.compute._list_spark_versions")
    def test_spark_versions(self, mock_versions):
        mock_versions.return_value = [{"key": "15.4.x-scala2.12"}]

        result = list_compute(resource="spark_versions")

        mock_versions.assert_called_once()
        assert "spark_versions" in result

    def test_invalid_resource(self):
        result = list_compute(resource="invalid")
        assert result["success"] is False
        assert "unknown resource" in result["error"].lower()
