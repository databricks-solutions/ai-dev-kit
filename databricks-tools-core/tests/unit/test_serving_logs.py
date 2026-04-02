"""Unit tests for Model Serving log retrieval functions."""

from unittest import mock

import pytest
from databricks.sdk.errors import ResourceDoesNotExist

from databricks_tools_core.serving import (
    get_serving_endpoint_build_logs,
    get_serving_endpoint_server_logs,
)

_GET_CLIENT = "databricks_tools_core.serving.endpoints.get_workspace_client"


def _mock_endpoint(name="test-ep", served_entities=None):
    """Build a mock endpoint object."""
    ep = mock.Mock()
    ep.name = name

    if served_entities is None:
        entity = mock.Mock()
        entity.name = "model-1"
        entity.entity_name = "main.ml.model"
        entity.entity_version = "1"
        served_entities = [entity]

    config = mock.Mock()
    config.served_entities = served_entities
    ep.config = config

    return ep


class TestGetServingEndpointBuildLogs:
    """Tests for get_serving_endpoint_build_logs."""

    @mock.patch(_GET_CLIENT)
    def test_build_logs_with_explicit_model_name(self, mock_get_client):
        """build_logs returns logs when served_model_name is provided."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.build_logs.return_value = mock.Mock(logs="Building image...\nDone.")
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_build_logs(name="test-ep", served_model_name="model-1")

        assert result["name"] == "test-ep"
        assert result["served_model_name"] == "model-1"
        assert "Building image" in result["logs"]
        mock_client.serving_endpoints.build_logs.assert_called_once_with(
            name="test-ep", served_model_name="model-1"
        )

    @mock.patch(_GET_CLIENT)
    def test_build_logs_auto_resolve_model_name(self, mock_get_client):
        """build_logs auto-resolves served_model_name from endpoint config."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.return_value = _mock_endpoint(name="test-ep")
        mock_client.serving_endpoints.build_logs.return_value = mock.Mock(logs="Build output")
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_build_logs(name="test-ep")

        assert result["served_model_name"] == "model-1"
        mock_client.serving_endpoints.get.assert_called_once_with(name="test-ep")

    @mock.patch(_GET_CLIENT)
    def test_build_logs_endpoint_not_found(self, mock_get_client):
        """build_logs raises when endpoint doesn't exist."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            get_serving_endpoint_build_logs(name="missing-ep")

    @mock.patch(_GET_CLIENT)
    def test_build_logs_empty(self, mock_get_client):
        """build_logs returns empty string when no logs available."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.build_logs.return_value = mock.Mock(logs=None)
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_build_logs(name="test-ep", served_model_name="model-1")

        assert result["logs"] == ""


class TestGetServingEndpointServerLogs:
    """Tests for get_serving_endpoint_server_logs."""

    @mock.patch(_GET_CLIENT)
    def test_server_logs_with_explicit_model_name(self, mock_get_client):
        """server_logs returns logs when served_model_name is provided."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.logs.return_value = mock.Mock(logs="Processing request...\n200 OK")
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_server_logs(name="test-ep", served_model_name="model-1")

        assert result["name"] == "test-ep"
        assert result["served_model_name"] == "model-1"
        assert "Processing request" in result["logs"]
        mock_client.serving_endpoints.logs.assert_called_once_with(
            name="test-ep", served_model_name="model-1"
        )

    @mock.patch(_GET_CLIENT)
    def test_server_logs_auto_resolve_model_name(self, mock_get_client):
        """server_logs auto-resolves served_model_name from endpoint config."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.return_value = _mock_endpoint(name="test-ep")
        mock_client.serving_endpoints.logs.return_value = mock.Mock(logs="Server output")
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_server_logs(name="test-ep")

        assert result["served_model_name"] == "model-1"

    @mock.patch(_GET_CLIENT)
    def test_server_logs_endpoint_not_found(self, mock_get_client):
        """server_logs raises when endpoint doesn't exist."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            get_serving_endpoint_server_logs(name="missing-ep")

    @mock.patch(_GET_CLIENT)
    def test_server_logs_served_model_not_found(self, mock_get_client):
        """server_logs raises when served model doesn't exist on endpoint."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.logs.side_effect = ResourceDoesNotExist("Served model not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            get_serving_endpoint_server_logs(name="test-ep", served_model_name="wrong-model")
