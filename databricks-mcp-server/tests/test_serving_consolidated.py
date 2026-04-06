"""Tests for the consolidated manage_serving_endpoint MCP tool."""

from unittest import mock

from databricks_mcp_server.tools.serving import _manage_serving_endpoint_impl


_CORE = "databricks_mcp_server.tools.serving"


class TestManageServingEndpointActions:
    """Test each action dispatches correctly and validates required params."""

    def test_invalid_action(self):
        """Unknown action returns error."""
        result = _manage_serving_endpoint_impl(action="invalid", name="ep")
        assert "error" in result
        assert "Unknown action" in result["error"]
        assert "create" in result["error"]

    def test_create_missing_served_entities(self):
        """create without served_entities returns error."""
        result = _manage_serving_endpoint_impl(action="create", name="ep")
        assert "error" in result
        assert "served_entities" in result["error"]

    def test_update_missing_served_entities(self):
        """update without served_entities returns error."""
        result = _manage_serving_endpoint_impl(action="update", name="ep")
        assert "error" in result
        assert "served_entities" in result["error"]

    def test_update_permissions_missing_acl(self):
        """update_permissions without access_control_list returns error."""
        result = _manage_serving_endpoint_impl(action="update_permissions", name="ep")
        assert "error" in result
        assert "access_control_list" in result["error"]

    @mock.patch(f"{_CORE}._find_endpoint_by_name", return_value=None)
    @mock.patch(f"{_CORE}._create_serving_endpoint")
    @mock.patch(f"{_CORE}.track_resource")
    def test_create_dispatches(self, mock_track, mock_create, mock_find):
        """create action calls core create function."""
        mock_create.return_value = {"name": "ep", "state": "READY"}
        result = _manage_serving_endpoint_impl(
            action="create",
            name="ep",
            served_entities=[{"entity_name": "cat.sch.model", "entity_version": "1"}],
            wait=False,
        )
        assert result["created"] is True
        mock_create.assert_called_once()

    @mock.patch(f"{_CORE}._find_endpoint_by_name")
    def test_create_idempotent(self, mock_find):
        """create returns existing endpoint with created=False."""
        mock_find.return_value = {"name": "ep", "state": "READY"}
        result = _manage_serving_endpoint_impl(
            action="create",
            name="ep",
            served_entities=[{"entity_name": "cat.sch.model", "entity_version": "1"}],
        )
        assert result["created"] is False
        assert result["state"] == "READY"

    @mock.patch(f"{_CORE}._update_serving_endpoint")
    def test_update_dispatches(self, mock_update):
        """update action calls core update function."""
        mock_update.return_value = {"name": "ep", "state": "READY", "message": "updated"}
        result = _manage_serving_endpoint_impl(
            action="update",
            name="ep",
            served_entities=[{"entity_name": "cat.sch.model", "entity_version": "2"}],
        )
        assert result["message"] == "updated"
        mock_update.assert_called_once()

    @mock.patch(f"{_CORE}.remove_resource")
    @mock.patch(f"{_CORE}._delete_serving_endpoint")
    def test_delete_dispatches(self, mock_delete, mock_remove):
        """delete action calls core delete function and removes from manifest."""
        mock_delete.return_value = {"name": "ep", "status": "deleted"}
        result = _manage_serving_endpoint_impl(action="delete", name="ep")
        assert result["status"] == "deleted"
        mock_delete.assert_called_once_with(name="ep")
        mock_remove.assert_called_once()

    @mock.patch(f"{_CORE}._delete_serving_endpoint")
    def test_delete_not_found_skips_manifest(self, mock_delete):
        """delete with not_found status does not call remove_resource."""
        mock_delete.return_value = {"name": "ep", "status": "not_found"}
        result = _manage_serving_endpoint_impl(action="delete", name="ep")
        assert result["status"] == "not_found"

    @mock.patch(f"{_CORE}._get_serving_endpoint_build_logs")
    def test_get_build_logs_dispatches(self, mock_logs):
        """get_build_logs action calls core build_logs function."""
        mock_logs.return_value = {"name": "ep", "logs": "building..."}
        result = _manage_serving_endpoint_impl(
            action="get_build_logs",
            name="ep",
            served_model_name="model-1",
        )
        assert result["logs"] == "building..."
        mock_logs.assert_called_once_with(name="ep", served_model_name="model-1")

    @mock.patch(f"{_CORE}._get_serving_endpoint_server_logs")
    def test_get_server_logs_dispatches(self, mock_logs):
        """get_server_logs action calls core server_logs function."""
        mock_logs.return_value = {"name": "ep", "logs": "serving..."}
        result = _manage_serving_endpoint_impl(action="get_server_logs", name="ep")
        assert result["logs"] == "serving..."

    @mock.patch(f"{_CORE}._export_serving_endpoint_metrics")
    def test_export_metrics_dispatches(self, mock_metrics):
        """export_metrics action calls core metrics function."""
        mock_metrics.return_value = {"name": "ep", "metrics": [], "raw": ""}
        result = _manage_serving_endpoint_impl(action="export_metrics", name="ep")
        assert "metrics" in result

    @mock.patch(f"{_CORE}._get_serving_endpoint_permissions")
    def test_get_permissions_dispatches(self, mock_perms):
        """get_permissions action calls core permissions function."""
        mock_perms.return_value = {"name": "ep", "permissions": []}
        result = _manage_serving_endpoint_impl(action="get_permissions", name="ep")
        assert "permissions" in result

    @mock.patch(f"{_CORE}._update_serving_endpoint_permissions")
    def test_update_permissions_dispatches(self, mock_update):
        """update_permissions action calls core function."""
        mock_update.return_value = {"name": "ep", "updated": 1, "message": "done"}
        result = _manage_serving_endpoint_impl(
            action="update_permissions",
            name="ep",
            access_control_list=[{"user_name": "u@x.com", "permission_level": "CAN_QUERY"}],
        )
        assert result["updated"] == 1

    def test_action_case_insensitive(self):
        """Actions are case-insensitive."""
        result = _manage_serving_endpoint_impl(action="CREATE", name="ep")
        # Should fail on missing served_entities, not unknown action
        assert "served_entities" in result["error"]
