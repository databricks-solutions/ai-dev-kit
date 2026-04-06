"""Tests for the manage_secrets MCP tool."""

from unittest.mock import patch

import pytest

from databricks_mcp_server.tools.secrets import _manage_secrets_impl as manage_secrets

# Patch targets (core lib functions imported with _ prefix)
_CREATE_SCOPE = "databricks_mcp_server.tools.secrets._create_secret_scope"
_LIST_SCOPES = "databricks_mcp_server.tools.secrets._list_secret_scopes"
_DELETE_SCOPE = "databricks_mcp_server.tools.secrets._delete_secret_scope"
_PUT_SECRET = "databricks_mcp_server.tools.secrets._put_secret"
_GET_SECRET = "databricks_mcp_server.tools.secrets._get_secret"
_LIST_SECRETS = "databricks_mcp_server.tools.secrets._list_secrets"
_DELETE_SECRET = "databricks_mcp_server.tools.secrets._delete_secret"
_TRACK_RESOURCE = "databricks_mcp_server.tools.secrets.track_resource"
_REMOVE_RESOURCE = "databricks_mcp_server.tools.secrets.remove_resource"


# ---------------------------------------------------------------------------
# create_scope
# ---------------------------------------------------------------------------


def test_create_scope_success():
    """action='create_scope' calls core lib and returns result."""
    expected = {"scope": "my-scope", "status": "created", "created": True}
    with patch(_CREATE_SCOPE, return_value=expected) as mock_create, patch(_TRACK_RESOURCE):
        result = manage_secrets(action="create_scope", scope="my-scope")

    mock_create.assert_called_once_with(scope="my-scope", initial_manage_principal=None)
    assert result["scope"] == "my-scope"
    assert result["created"] is True


def test_create_scope_already_exists():
    """action='create_scope' returns existing scope without tracking."""
    expected = {"scope": "my-scope", "status": "already_exists", "created": False}
    with patch(_CREATE_SCOPE, return_value=expected), patch(_TRACK_RESOURCE) as mock_track:
        result = manage_secrets(action="create_scope", scope="my-scope")

    assert result["created"] is False
    mock_track.assert_not_called()


def test_create_scope_tracks_resource():
    """action='create_scope' calls track_resource on successful creation."""
    expected = {"scope": "my-scope", "status": "created", "created": True}
    with patch(_CREATE_SCOPE, return_value=expected), patch(_TRACK_RESOURCE) as mock_track:
        manage_secrets(action="create_scope", scope="my-scope")

    mock_track.assert_called_once_with(resource_type="secret_scope", name="my-scope", resource_id="my-scope")


def test_create_scope_missing_scope():
    """action='create_scope' without scope returns error."""
    result = manage_secrets(action="create_scope")
    assert "error" in result
    assert "scope" in result["error"].lower()


# ---------------------------------------------------------------------------
# list_scopes
# ---------------------------------------------------------------------------


def test_list_scopes_success():
    """action='list_scopes' returns all scopes."""
    expected = [{"name": "scope-a", "backend_type": "DATABRICKS"}, {"name": "scope-b", "backend_type": "DATABRICKS"}]
    with patch(_LIST_SCOPES, return_value=expected):
        result = manage_secrets(action="list_scopes")

    assert len(result) == 2
    assert result[0]["name"] == "scope-a"


def test_list_scopes_empty():
    """action='list_scopes' returns empty list when no scopes exist."""
    with patch(_LIST_SCOPES, return_value=[]):
        result = manage_secrets(action="list_scopes")

    assert result == []


# ---------------------------------------------------------------------------
# delete_scope
# ---------------------------------------------------------------------------


def test_delete_scope_success():
    """action='delete_scope' calls core lib and removes from manifest."""
    expected = {"scope": "old-scope", "status": "deleted", "message": "Scope deleted"}
    with patch(_DELETE_SCOPE, return_value=expected), patch(_REMOVE_RESOURCE) as mock_remove:
        result = manage_secrets(action="delete_scope", scope="old-scope")

    assert result["status"] == "deleted"
    mock_remove.assert_called_once_with(resource_type="secret_scope", resource_id="old-scope")


def test_delete_scope_not_found():
    """action='delete_scope' with nonexistent scope returns not_found without removing."""
    expected = {"scope": "gone", "status": "not_found", "message": "Scope not found"}
    with patch(_DELETE_SCOPE, return_value=expected), patch(_REMOVE_RESOURCE) as mock_remove:
        result = manage_secrets(action="delete_scope", scope="gone")

    assert result["status"] == "not_found"
    mock_remove.assert_not_called()


def test_delete_scope_missing_scope():
    """action='delete_scope' without scope returns error."""
    result = manage_secrets(action="delete_scope")
    assert "error" in result
    assert "scope" in result["error"].lower()


# ---------------------------------------------------------------------------
# put
# ---------------------------------------------------------------------------


def test_put_with_value():
    """action='put' with value param calls core lib with string_value."""
    expected = {"scope": "s", "key": "k", "status": "created", "message": "Secret stored"}
    with patch(_PUT_SECRET, return_value=expected) as mock_put:
        result = manage_secrets(action="put", scope="s", key="k", value="secret123")

    mock_put.assert_called_once_with(scope="s", key="k", string_value="secret123", bytes_value=None)
    assert result["status"] == "created"


def test_put_with_string_value():
    """action='put' with string_value param calls core lib correctly."""
    expected = {"scope": "s", "key": "k", "status": "created", "message": "Secret stored"}
    with patch(_PUT_SECRET, return_value=expected) as mock_put:
        result = manage_secrets(action="put", scope="s", key="k", string_value="my-secret")

    mock_put.assert_called_once_with(scope="s", key="k", string_value="my-secret", bytes_value=None)
    assert result["status"] == "created"


def test_put_with_bytes_value():
    """action='put' with bytes_value param calls core lib correctly."""
    expected = {"scope": "s", "key": "k", "status": "created", "message": "Secret stored"}
    with patch(_PUT_SECRET, return_value=expected) as mock_put:
        result = manage_secrets(action="put", scope="s", key="k", bytes_value="c2VjcmV0")

    mock_put.assert_called_once_with(scope="s", key="k", string_value=None, bytes_value="c2VjcmV0")
    assert result["status"] == "created"


def test_put_missing_scope():
    """action='put' without scope returns error."""
    result = manage_secrets(action="put", key="k", value="v")
    assert "error" in result
    assert "scope" in result["error"].lower()


def test_put_missing_key():
    """action='put' without key returns error."""
    result = manage_secrets(action="put", scope="s", value="v")
    assert "error" in result
    assert "key" in result["error"].lower()


def test_put_missing_value():
    """action='put' without any value param returns error."""
    result = manage_secrets(action="put", scope="s", key="k")
    assert "error" in result
    assert "value" in result["error"].lower()


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_success():
    """action='get' returns secret metadata."""
    expected = {"scope": "s", "key": "k", "exists": True, "value_length": 42}
    with patch(_GET_SECRET, return_value=expected) as mock_get:
        result = manage_secrets(action="get", scope="s", key="k")

    mock_get.assert_called_once_with(scope="s", key="k", return_value=False)
    assert result["exists"] is True
    assert result["value_length"] == 42


def test_get_missing_scope():
    """action='get' without scope returns error."""
    result = manage_secrets(action="get", key="k")
    assert "error" in result
    assert "scope" in result["error"].lower()


def test_get_missing_key():
    """action='get' without key returns error."""
    result = manage_secrets(action="get", scope="s")
    assert "error" in result
    assert "key" in result["error"].lower()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_success():
    """action='list' returns secret keys in a scope."""
    expected = [{"key": "api-key", "last_updated_timestamp": 1700000000000}]
    with patch(_LIST_SECRETS, return_value=expected) as mock_list:
        result = manage_secrets(action="list", scope="my-scope")

    mock_list.assert_called_once_with(scope="my-scope")
    assert len(result) == 1
    assert result[0]["key"] == "api-key"


def test_list_missing_scope():
    """action='list' without scope returns error."""
    result = manage_secrets(action="list")
    assert "error" in result
    assert "scope" in result["error"].lower()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_success():
    """action='delete' calls core lib with scope and key."""
    expected = {"scope": "s", "key": "k", "status": "deleted", "message": "Secret deleted"}
    with patch(_DELETE_SECRET, return_value=expected) as mock_del:
        result = manage_secrets(action="delete", scope="s", key="k")

    mock_del.assert_called_once_with(scope="s", key="k")
    assert result["status"] == "deleted"


def test_delete_missing_scope():
    """action='delete' without scope returns error."""
    result = manage_secrets(action="delete", key="k")
    assert "error" in result
    assert "scope" in result["error"].lower()


def test_delete_missing_key():
    """action='delete' without key returns error."""
    result = manage_secrets(action="delete", scope="s")
    assert "error" in result
    assert "key" in result["error"].lower()


# ---------------------------------------------------------------------------
# invalid action
# ---------------------------------------------------------------------------


def test_invalid_action():
    """An unrecognised action returns an error listing valid actions."""
    result = manage_secrets(action="badaction")
    assert "error" in result
    for valid in ("create_scope", "list_scopes", "delete_scope", "put", "get", "list", "delete"):
        assert valid in result["error"]


def test_action_case_insensitive():
    """Actions are case-insensitive."""
    expected = [{"name": "scope-a", "backend_type": "DATABRICKS"}]
    with patch(_LIST_SCOPES, return_value=expected):
        result = manage_secrets(action="LIST_SCOPES")

    assert len(result) == 1
