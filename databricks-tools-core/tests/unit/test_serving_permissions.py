"""Unit tests for Model Serving endpoint permissions."""

from unittest import mock

import pytest
from databricks.sdk.errors import ResourceDoesNotExist

from databricks_tools_core.serving import (
    get_serving_endpoint_permissions,
    update_serving_endpoint_permissions,
)

_GET_CLIENT = "databricks_tools_core.serving.endpoints.get_workspace_client"


def _mock_endpoint(name="test-ep", endpoint_id="abc123def456"):
    """Build a mock endpoint with an ID."""
    ep = mock.Mock()
    ep.name = name
    ep.id = endpoint_id
    return ep


def _mock_acl_entry(user_name=None, group_name=None, service_principal_name=None, level="CAN_MANAGE", inherited=False):
    """Build a mock ACL entry."""
    entry = mock.Mock()
    entry.user_name = user_name
    entry.group_name = group_name
    entry.service_principal_name = service_principal_name

    perm = mock.Mock()
    perm.permission_level = mock.Mock(value=level)
    perm.inherited = inherited
    entry.all_permissions = [perm]

    return entry


class TestGetServingEndpointPermissions:
    """Tests for get_serving_endpoint_permissions."""

    @mock.patch(_GET_CLIENT)
    def test_get_permissions_success(self, mock_get_client):
        """get_permissions returns structured ACL list."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.return_value = _mock_endpoint()

        perms_response = mock.Mock()
        perms_response.access_control_list = [
            _mock_acl_entry(user_name="user@example.com", level="CAN_QUERY"),
            _mock_acl_entry(group_name="admins", level="CAN_MANAGE", inherited=True),
        ]
        mock_client.serving_endpoints.get_permissions.return_value = perms_response
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_permissions(name="test-ep")

        assert result["name"] == "test-ep"
        assert len(result["permissions"]) == 2

        user_perm = result["permissions"][0]
        assert user_perm["principal"] == "user@example.com"
        assert user_perm["principal_type"] == "user"
        assert user_perm["permission_level"] == "CAN_QUERY"
        assert user_perm["inherited"] is False

        group_perm = result["permissions"][1]
        assert group_perm["principal"] == "admins"
        assert group_perm["principal_type"] == "group"
        assert group_perm["inherited"] is True

    @mock.patch(_GET_CLIENT)
    def test_get_permissions_service_principal(self, mock_get_client):
        """get_permissions handles service principal entries."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.return_value = _mock_endpoint()

        perms_response = mock.Mock()
        perms_response.access_control_list = [
            _mock_acl_entry(service_principal_name="my-sp", level="CAN_VIEW"),
        ]
        mock_client.serving_endpoints.get_permissions.return_value = perms_response
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_permissions(name="test-ep")

        assert result["permissions"][0]["principal"] == "my-sp"
        assert result["permissions"][0]["principal_type"] == "service_principal"

    @mock.patch(_GET_CLIENT)
    def test_get_permissions_empty(self, mock_get_client):
        """get_permissions returns empty list when no ACL."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.return_value = _mock_endpoint()

        perms_response = mock.Mock()
        perms_response.access_control_list = None
        mock_client.serving_endpoints.get_permissions.return_value = perms_response
        mock_get_client.return_value = mock_client

        result = get_serving_endpoint_permissions(name="test-ep")

        assert result["permissions"] == []

    @mock.patch(_GET_CLIENT)
    def test_get_permissions_endpoint_not_found(self, mock_get_client):
        """get_permissions raises for non-existent endpoint."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            get_serving_endpoint_permissions(name="missing-ep")


class TestUpdateServingEndpointPermissions:
    """Tests for update_serving_endpoint_permissions."""

    @mock.patch(_GET_CLIENT)
    def test_update_permissions_success(self, mock_get_client):
        """update_permissions sends ACL entries to SDK."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.return_value = _mock_endpoint()
        mock_get_client.return_value = mock_client

        result = update_serving_endpoint_permissions(
            name="test-ep",
            access_control_list=[
                {"user_name": "user@example.com", "permission_level": "CAN_QUERY"},
                {"group_name": "data-team", "permission_level": "CAN_VIEW"},
            ],
        )

        assert result["name"] == "test-ep"
        assert result["updated"] == 2
        mock_client.serving_endpoints.update_permissions.assert_called_once()

        call_kwargs = mock_client.serving_endpoints.update_permissions.call_args.kwargs
        assert call_kwargs["serving_endpoint_id"] == "abc123def456"
        assert len(call_kwargs["access_control_list"]) == 2

    @mock.patch(_GET_CLIENT)
    def test_update_permissions_endpoint_not_found(self, mock_get_client):
        """update_permissions raises for non-existent endpoint."""
        mock_client = mock.Mock()
        mock_client.serving_endpoints.get.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            update_serving_endpoint_permissions(
                name="missing-ep",
                access_control_list=[{"user_name": "user@example.com", "permission_level": "CAN_QUERY"}],
            )
