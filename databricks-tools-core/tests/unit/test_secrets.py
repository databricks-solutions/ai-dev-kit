"""Unit tests for secrets management functions."""

import base64
from unittest import mock

import pytest
from databricks.sdk.errors import ResourceAlreadyExists, ResourceDoesNotExist

from databricks_tools_core.secrets import (
    create_secret_scope,
    delete_secret,
    delete_secret_scope,
    get_secret,
    list_secret_scopes,
    list_secrets,
    put_secret,
)

_GET_CLIENT = "databricks_tools_core.secrets.secrets.get_workspace_client"


class TestCreateSecretScope:
    """Tests for create_secret_scope."""

    @mock.patch(_GET_CLIENT)
    def test_create_scope_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = create_secret_scope(scope="test-scope")

        assert result["scope"] == "test-scope"
        assert result["status"] == "created"
        mock_client.secrets.create_scope.assert_called_once_with(scope="test-scope", initial_manage_principal=None)

    @mock.patch(_GET_CLIENT)
    def test_create_scope_with_principal(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        create_secret_scope(scope="test-scope", initial_manage_principal="users")

        mock_client.secrets.create_scope.assert_called_once_with(scope="test-scope", initial_manage_principal="users")

    @mock.patch(_GET_CLIENT)
    def test_create_scope_already_exists(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.secrets.create_scope.side_effect = ResourceAlreadyExists("Scope exists")
        mock_get_client.return_value = mock_client

        result = create_secret_scope(scope="existing-scope")

        assert result["scope"] == "existing-scope"
        assert result["created"] is False
        assert result["status"] == "already_exists"


class TestListSecretScopes:
    """Tests for list_secret_scopes."""

    @mock.patch(_GET_CLIENT)
    def test_list_scopes(self, mock_get_client):
        mock_client = mock.Mock()
        scope1 = mock.Mock()
        scope1.name = "scope-a"
        scope1.backend_type = mock.Mock(value="DATABRICKS")
        scope2 = mock.Mock()
        scope2.name = "scope-b"
        scope2.backend_type = mock.Mock(value="AZURE_KEYVAULT")
        mock_client.secrets.list_scopes.return_value = iter([scope1, scope2])
        mock_get_client.return_value = mock_client

        result = list_secret_scopes()

        assert len(result) == 2
        assert result[0]["name"] == "scope-a"
        assert result[0]["backend_type"] == "DATABRICKS"
        assert result[1]["backend_type"] == "AZURE_KEYVAULT"


class TestDeleteSecretScope:
    """Tests for delete_secret_scope."""

    @mock.patch(_GET_CLIENT)
    def test_delete_scope_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = delete_secret_scope(scope="test-scope")

        assert result["status"] == "deleted"
        mock_client.secrets.delete_scope.assert_called_once_with(scope="test-scope")

    @mock.patch(_GET_CLIENT)
    def test_delete_scope_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.secrets.delete_scope.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        result = delete_secret_scope(scope="missing-scope")

        assert result["status"] == "not_found"


class TestPutSecret:
    """Tests for put_secret."""

    @mock.patch(_GET_CLIENT)
    def test_put_string_secret(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = put_secret(scope="test-scope", key="api-key", string_value="sk-abc123")

        assert result["status"] == "created"
        assert result["key"] == "api-key"
        mock_client.secrets.put_secret.assert_called_once_with(
            scope="test-scope", key="api-key", string_value="sk-abc123", bytes_value=None
        )

    @mock.patch(_GET_CLIENT)
    def test_put_bytes_secret(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        put_secret(scope="test-scope", key="cert", bytes_value="AQID")

        mock_client.secrets.put_secret.assert_called_once_with(
            scope="test-scope", key="cert", string_value=None, bytes_value="AQID"
        )

    def test_put_no_value_raises(self):
        with pytest.raises(Exception, match="Exactly one"):
            put_secret(scope="test-scope", key="api-key")

    def test_put_both_values_raises(self):
        with pytest.raises(Exception, match="not both"):
            put_secret(scope="test-scope", key="api-key", string_value="a", bytes_value="b")

    @mock.patch(_GET_CLIENT)
    def test_put_scope_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.secrets.put_secret.side_effect = ResourceDoesNotExist("Scope not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            put_secret(scope="missing-scope", key="key", string_value="val")


class TestGetSecret:
    """Tests for get_secret."""

    @mock.patch(_GET_CLIENT)
    def test_get_secret_metadata_only(self, mock_get_client):
        """Default mode returns metadata without value."""
        mock_client = mock.Mock()
        b64_value = base64.b64encode(b"my-secret-value").decode()
        mock_client.secrets.get_secret.return_value = mock.Mock(key="api-key", value=b64_value)
        mock_get_client.return_value = mock_client

        result = get_secret(scope="test-scope", key="api-key")

        assert result["exists"] is True
        assert result["value_length"] == len(b"my-secret-value")
        assert "value" not in result

    @mock.patch(_GET_CLIENT)
    def test_get_secret_with_value(self, mock_get_client):
        """return_value=True includes decoded value."""
        mock_client = mock.Mock()
        b64_value = base64.b64encode(b"my-secret-value").decode()
        mock_client.secrets.get_secret.return_value = mock.Mock(key="api-key", value=b64_value)
        mock_get_client.return_value = mock_client

        result = get_secret(scope="test-scope", key="api-key", return_value=True)

        assert result["value"] == "my-secret-value"
        assert result["value_length"] == len(b"my-secret-value")

    @mock.patch(_GET_CLIENT)
    def test_get_secret_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.secrets.get_secret.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            get_secret(scope="test-scope", key="missing-key")


class TestListSecrets:
    """Tests for list_secrets."""

    @mock.patch(_GET_CLIENT)
    def test_list_secrets_success(self, mock_get_client):
        mock_client = mock.Mock()
        s1 = mock.Mock()
        s1.key = "api-key"
        s1.last_updated_timestamp = 1700000000000
        s2 = mock.Mock()
        s2.key = "db-password"
        s2.last_updated_timestamp = 1700000001000
        mock_client.secrets.list_secrets.return_value = iter([s1, s2])
        mock_get_client.return_value = mock_client

        result = list_secrets(scope="test-scope")

        assert len(result) == 2
        assert result[0]["key"] == "api-key"
        assert result[1]["last_updated_timestamp"] == 1700000001000

    @mock.patch(_GET_CLIENT)
    def test_list_secrets_scope_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.secrets.list_secrets.side_effect = ResourceDoesNotExist("Scope not found")
        mock_get_client.return_value = mock_client

        with pytest.raises(Exception, match="not found"):
            list_secrets(scope="missing-scope")


class TestDeleteSecret:
    """Tests for delete_secret."""

    @mock.patch(_GET_CLIENT)
    def test_delete_secret_success(self, mock_get_client):
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client

        result = delete_secret(scope="test-scope", key="api-key")

        assert result["status"] == "deleted"

    @mock.patch(_GET_CLIENT)
    def test_delete_secret_not_found(self, mock_get_client):
        mock_client = mock.Mock()
        mock_client.secrets.delete_secret.side_effect = ResourceDoesNotExist("Not found")
        mock_get_client.return_value = mock_client

        result = delete_secret(scope="test-scope", key="missing-key")

        assert result["status"] == "not_found"
