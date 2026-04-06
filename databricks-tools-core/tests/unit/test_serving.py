"""Unit tests for Model Serving core functions and consolidated MCP tool."""

from unittest import mock

import pytest
from databricks.sdk.errors import NotFound, ResourceDoesNotExist

from databricks_tools_core.serving import (
    create_serving_endpoint,
    delete_serving_endpoint,
    export_serving_endpoint_metrics,
    get_serving_endpoint_build_logs,
    get_serving_endpoint_permissions,
    get_serving_endpoint_server_logs,
    update_serving_endpoint,
    update_serving_endpoint_permissions,
)
from databricks_tools_core.serving.endpoints import _parse_prometheus_metrics

_GET_CLIENT = "databricks_tools_core.serving.endpoints.get_workspace_client"


# ============================================================================
# Helpers
# ============================================================================


def _mock_endpoint(name="test-ep", state_ready="READY", config_update=None, served_entities=None):
    """Build a mock endpoint object."""
    ep = mock.Mock()
    ep.name = name
    ep.id = "abc123"
    ep.creation_timestamp = 1700000000

    ep.state = mock.Mock()
    ep.state.ready = mock.Mock(value=state_ready) if state_ready else None
    ep.state.config_update = mock.Mock(value=config_update) if config_update else None

    if served_entities is None:
        entity = mock.Mock()
        entity.name = "model-1"
        entity.entity_name = "main.ml.model"
        entity.entity_version = "1"
        entity.workload_size = "Small"
        entity.workload_type = None
        entity.environment_vars = None
        entity.instance_profile_arn = None
        entity.min_provisioned_concurrency = None
        entity.max_provisioned_concurrency = None
        entity.min_provisioned_throughput = None
        entity.max_provisioned_throughput = None
        entity.state = None
        served_entities = [entity]

    config = mock.Mock()
    config.served_entities = served_entities
    ep.config = config
    ep.pending_config = None

    return ep


# ============================================================================
# CRUD tests
# ============================================================================


class TestCreateServingEndpoint:
    """Tests for create_serving_endpoint."""

    @mock.patch(_GET_CLIENT)
    def test_create_wait_true(self, mock_get_client):
        """create with wait=True returns READY endpoint."""
        mock_client = mock.Mock()
        mock_endpoint_obj = _mock_endpoint()
        mock_client.serving_endpoints.create_and_wait.return_value = mock_endpoint_obj
        mock_get_client.return_value = mock_client

        result = create_serving_endpoint(
            name="test-ep",
            served_entities=[{"entity_name": "main.ml.model", "entity_version": "1"}],
            wait=True,
        )
        assert result["name"] == "test-ep"
        assert result["state"] == "READY"
        assert result["wait_needed"] is False
        mock_client.serving_endpoints.create_and_wait.assert_called_once()

    @mock.patch(_GET_CLIENT)
    def test_create_wait_false(self, mock_get_client):
        """create with wait=False returns CREATING."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_serving_endpoint(
            name="test-ep",
            served_entities=[{"entity_name": "main.ml.model", "entity_version": "1"}],
            wait=False,
        )
        assert result["name"] == "test-ep"
        assert result["state"] == "CREATING"
        assert result["wait_needed"] is True
        mock_client.serving_endpoints.create.assert_called_once()

    @mock.patch(_GET_CLIENT)
    def test_create_already_exists(self, mock_get_client):
        """create raises when endpoint already exists."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.create_and_wait.side_effect = Exception("RESOURCE_ALREADY_EXISTS")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="already exists"):
            create_serving_endpoint(
                name="test-ep",
                served_entities=[{"entity_name": "main.ml.model", "entity_version": "1"}],
            )


class TestUpdateServingEndpoint:
    """Tests for update_serving_endpoint."""

    @mock.patch(_GET_CLIENT)
    def test_update_wait_true(self, mock_get_client):
        """update with wait=True returns updated endpoint."""
        mock_client = mock.Mock()
        mock_endpoint_obj = _mock_endpoint(config_update=None)
        mock_wait = mock.Mock()
        mock_wait.result.return_value = mock_endpoint_obj
        mock_client.serving_endpoints.update_config.return_value = mock_wait
        mock_get_client.return_value = mock_client

        result = update_serving_endpoint(
            name="test-ep",
            served_entities=[{"entity_name": "main.ml.model", "entity_version": "2"}],
            wait=True,
        )
        assert result["name"] == "test-ep"
        assert "message" in result

    @mock.patch(_GET_CLIENT)
    def test_update_not_found(self, mock_get_client):
        """update raises when endpoint not found."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.side_effect = ResourceDoesNotExist("not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            update_serving_endpoint(
                name="missing-ep",
                served_entities=[{"entity_name": "main.ml.model", "entity_version": "1"}],
            )

    @mock.patch(_GET_CLIENT)
    def test_update_wait_false(self, mock_get_client):
        """update with wait=False returns UPDATING state."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.update_config.return_value = mock.Mock()
        mock_get_client.return_value = mock_client

        result = update_serving_endpoint(
            name="test-ep",
            served_entities=[{"entity_name": "main.ml.model", "entity_version": "2"}],
            wait=False,
        )
        assert result["state"] == "UPDATING"
        assert result["config_update"] == "IN_PROGRESS"


class TestDeleteServingEndpoint:
    """Tests for delete_serving_endpoint."""

    @mock.patch(_GET_CLIENT)
    def test_delete_success(self, mock_get_client):
        """delete returns deleted status."""
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = delete_serving_endpoint(name="test-ep")
        assert result["status"] == "deleted"
        assert result["name"] == "test-ep"
        mock_client.serving_endpoints.delete.assert_called_once_with(name="test-ep")

    @mock.patch(_GET_CLIENT)
    def test_delete_not_found(self, mock_get_client):
        """delete returns not_found when endpoint missing."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.side_effect = ResourceDoesNotExist("not found")
        mock_get_client.return_value = mock_client

        result = delete_serving_endpoint(name="missing-ep")
        assert result["status"] == "not_found"


# ============================================================================
# Logs tests
# ============================================================================


class TestBuildLogs:
    """Tests for get_serving_endpoint_build_logs."""

    @mock.patch(_GET_CLIENT)
    def test_build_logs_explicit_model(self, mock_get_client):
        """Returns build logs with explicit served model name."""
        mock_client = mock.Mock()
        mock_response = mock.Mock()
        mock_response.logs = "Building container..."
        mock_client.serving_endpoints.build_logs.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_build_logs(name="test-ep", served_model_name="model-1")
        assert result["logs"] == "Building container..."
        assert result["served_model_name"] == "model-1"

    @mock.patch(_GET_CLIENT)
    def test_build_logs_auto_resolve(self, mock_get_client):
        """Auto-resolves served model name from endpoint config."""
        mock_client = mock.Mock()
        mock_endpoint_obj = _mock_endpoint()
        mock_client.serving_endpoints.get.return_value = mock_endpoint_obj
        mock_response = mock.Mock()
        mock_response.logs = "Logs here"
        mock_client.serving_endpoints.build_logs.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_build_logs(name="test-ep")
        assert result["served_model_name"] == "model-1"

    @mock.patch(_GET_CLIENT)
    def test_build_logs_not_found(self, mock_get_client):
        """Raises when served model not found."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.build_logs.side_effect = ResourceDoesNotExist("not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            get_serving_endpoint_build_logs(name="test-ep", served_model_name="missing-model")


class TestServerLogs:
    """Tests for get_serving_endpoint_server_logs."""

    @mock.patch(_GET_CLIENT)
    def test_server_logs(self, mock_get_client):
        """Returns server logs."""
        mock_client = mock.Mock()
        mock_response = mock.Mock()
        mock_response.logs = "Server output..."
        mock_client.serving_endpoints.logs.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_server_logs(name="test-ep", served_model_name="model-1")
        assert result["logs"] == "Server output..."


# ============================================================================
# Metrics tests
# ============================================================================


class TestExportMetrics:
    """Tests for export_serving_endpoint_metrics."""

    @mock.patch(_GET_CLIENT)
    def test_export_metrics(self, mock_get_client):
        """Returns structured metrics and raw text."""
        raw = (
            "# HELP cpu_usage_percentage CPU usage.\n"
            "# TYPE cpu_usage_percentage gauge\n"
            'cpu_usage_percentage{model="m1"} 12.5\n'
        )
        mock_client = mock.Mock()
        mock_response = mock.Mock()
        mock_response.contents.read.return_value = raw.encode("utf-8")
        mock_client.serving_endpoints.export_metrics.return_value = mock_response
        mock_get_client.return_value = mock_client

        result = export_serving_endpoint_metrics(name="test-ep")
        assert result["name"] == "test-ep"
        assert len(result["metrics"]) == 1
        assert result["metrics"][0]["name"] == "cpu_usage_percentage"
        assert result["metrics"][0]["value"] == 12.5
        assert result["metrics"][0]["labels"] == {"model": "m1"}
        assert "cpu_usage_percentage" in result["raw"]

    @mock.patch(_GET_CLIENT)
    def test_export_metrics_not_found(self, mock_get_client):
        """Raises when endpoint not found."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.export_metrics.side_effect = NotFound("not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            export_serving_endpoint_metrics(name="missing-ep")


class TestParsePrometheusMetrics:
    """Tests for _parse_prometheus_metrics."""

    def test_basic_metric(self):
        text = 'cpu_usage{host="a"} 42.0\n'
        metrics = _parse_prometheus_metrics(text)
        assert len(metrics) == 1
        assert metrics[0]["name"] == "cpu_usage"
        assert metrics[0]["value"] == 42.0
        assert metrics[0]["labels"] == {"host": "a"}

    def test_help_and_type(self):
        text = "# HELP mem Memory usage.\n# TYPE mem gauge\nmem 128.0\n"
        metrics = _parse_prometheus_metrics(text)
        assert metrics[0]["help"] == "Memory usage."
        assert metrics[0]["type"] == "gauge"

    def test_empty_input(self):
        assert _parse_prometheus_metrics("") == []
        assert _parse_prometheus_metrics("# just comments\n") == []


# ============================================================================
# Permissions tests
# ============================================================================


class TestGetPermissions:
    """Tests for get_serving_endpoint_permissions."""

    @mock.patch(_GET_CLIENT)
    def test_get_permissions(self, mock_get_client):
        """Returns structured permissions."""
        mock_client = mock.Mock()
        mock_endpoint_obj = _mock_endpoint()
        mock_client.serving_endpoints.get.return_value = mock_endpoint_obj

        # Build mock ACL response
        acl_entry = mock.Mock()
        acl_entry.user_name = "user@example.com"
        acl_entry.group_name = None
        acl_entry.service_principal_name = None
        perm = mock.Mock()
        perm.permission_level = mock.Mock(value="CAN_MANAGE")
        perm.inherited = False
        acl_entry.all_permissions = [perm]

        perms_response = mock.Mock()
        perms_response.access_control_list = [acl_entry]
        mock_client.serving_endpoints.get_permissions.return_value = perms_response
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_permissions(name="test-ep")
        assert result["name"] == "test-ep"
        assert len(result["permissions"]) == 1
        assert result["permissions"][0]["principal"] == "user@example.com"
        assert result["permissions"][0]["permission_level"] == "CAN_MANAGE"

    @mock.patch(_GET_CLIENT)
    def test_get_permissions_not_found(self, mock_get_client):
        """Raises when endpoint not found."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.side_effect = ResourceDoesNotExist("not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            get_serving_endpoint_permissions(name="missing-ep")


class TestUpdatePermissions:
    """Tests for update_serving_endpoint_permissions."""

    @mock.patch(_GET_CLIENT)
    def test_update_permissions(self, mock_get_client):
        """Updates permissions and returns count."""
        mock_client = mock.Mock()
        mock_endpoint_obj = _mock_endpoint()
        mock_client.serving_endpoints.get.return_value = mock_endpoint_obj
        mock_get_client.return_value = mock_client

        result = update_serving_endpoint_permissions(
            name="test-ep",
            access_control_list=[
                {"user_name": "user@example.com", "permission_level": "CAN_QUERY"},
            ],
        )
        assert result["updated"] == 1
        assert "Permissions updated" in result["message"]
        mock_client.serving_endpoints.update_permissions.assert_called_once()
