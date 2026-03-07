"""Unit tests for workspace switching auth state management."""

import os
from unittest import mock

import pytest

from databricks_tools_core.auth import (
    clear_active_workspace,
    clear_databricks_auth,
    get_active_workspace,
    get_current_username,
    get_workspace_client,
    set_active_workspace,
    set_databricks_auth,
)

_WS_CLIENT = "databricks_tools_core.auth.WorkspaceClient"
_TAG_CLIENT = "databricks_tools_core.auth.tag_client"
_HAS_OAUTH = "databricks_tools_core.auth._has_oauth_credentials"


@pytest.fixture(autouse=True)
def clean_state():
    """Reset auth state before and after every test."""
    clear_active_workspace()
    clear_databricks_auth()
    yield
    clear_active_workspace()
    clear_databricks_auth()


# ---------------------------------------------------------------------------
# set_active_workspace / get_active_workspace / clear_active_workspace
# ---------------------------------------------------------------------------


def test_default_no_active_workspace():
    """With no active workspace set, get_workspace_client falls through to the default SDK path."""
    with (
        mock.patch(_HAS_OAUTH, return_value=False),
        mock.patch(_TAG_CLIENT, side_effect=lambda c: c),
        mock.patch(_WS_CLIENT) as mock_ws,
    ):
        get_workspace_client()
        call_kwargs = mock_ws.call_args.kwargs
        assert "profile" not in call_kwargs
        assert "host" not in call_kwargs


def test_set_active_profile():
    """After set_active_workspace(profile=...), WorkspaceClient is called with that profile."""
    set_active_workspace(profile="prod")
    with mock.patch(_TAG_CLIENT, side_effect=lambda c: c), mock.patch(_WS_CLIENT) as mock_ws:
        get_workspace_client()
        assert mock_ws.call_args.kwargs.get("profile") == "prod"


def test_set_active_host():
    """After set_active_workspace(host=...), WorkspaceClient is called with that host."""
    set_active_workspace(host="https://adb-123.azuredatabricks.net")
    with (
        mock.patch(_HAS_OAUTH, return_value=False),
        mock.patch(_TAG_CLIENT, side_effect=lambda c: c),
        mock.patch(_WS_CLIENT) as mock_ws,
    ):
        get_workspace_client()
        assert mock_ws.call_args.kwargs.get("host") == "https://adb-123.azuredatabricks.net"
        assert "profile" not in mock_ws.call_args.kwargs


def test_profile_takes_precedence_over_host():
    """When both profile and host are set, profile wins."""
    set_active_workspace(profile="myprofile", host="https://ignored.azuredatabricks.net")
    with mock.patch(_TAG_CLIENT, side_effect=lambda c: c), mock.patch(_WS_CLIENT) as mock_ws:
        get_workspace_client()
        assert mock_ws.call_args.kwargs.get("profile") == "myprofile"
        assert "host" not in mock_ws.call_args.kwargs


def test_clear_resets_to_default():
    """After clear_active_workspace(), falls through to the default SDK path."""
    set_active_workspace(profile="prod")
    clear_active_workspace()
    with (
        mock.patch(_HAS_OAUTH, return_value=False),
        mock.patch(_TAG_CLIENT, side_effect=lambda c: c),
        mock.patch(_WS_CLIENT) as mock_ws,
    ):
        get_workspace_client()
        call_kwargs = mock_ws.call_args.kwargs
        assert "profile" not in call_kwargs
        assert "host" not in call_kwargs


def test_get_active_workspace_reflects_state():
    """get_active_workspace() returns the current module-level state."""
    assert get_active_workspace() == {"profile": None, "host": None}
    set_active_workspace(profile="staging")
    assert get_active_workspace() == {"profile": "staging", "host": None}
    set_active_workspace(host="https://adb-456.net")
    assert get_active_workspace() == {"profile": None, "host": "https://adb-456.net"}
    clear_active_workspace()
    assert get_active_workspace() == {"profile": None, "host": None}


def test_set_active_workspace_is_idempotent():
    """Calling set_active_workspace twice replaces the previous value."""
    set_active_workspace(profile="first")
    set_active_workspace(profile="second")
    assert get_active_workspace()["profile"] == "second"


# ---------------------------------------------------------------------------
# Priority: force_token and OAuth M2M override active workspace
# ---------------------------------------------------------------------------


def test_force_token_overrides_active_workspace():
    """set_databricks_auth(force_token=True) bypasses the active workspace override."""
    set_active_workspace(profile="should-be-ignored")
    set_databricks_auth("https://force-host.net", "force-token", force_token=True)
    with mock.patch(_TAG_CLIENT, side_effect=lambda c: c), mock.patch(_WS_CLIENT) as mock_ws:
        get_workspace_client()
        assert mock_ws.call_args.kwargs.get("host") == "https://force-host.net"
        assert mock_ws.call_args.kwargs.get("token") == "force-token"
        assert "profile" not in mock_ws.call_args.kwargs


def test_active_workspace_bypassed_when_oauth_m2m():
    """When OAuth M2M credentials are in env, they take precedence over active workspace."""
    set_active_workspace(profile="should-be-ignored")
    env = {
        "DATABRICKS_CLIENT_ID": "my-client-id",
        "DATABRICKS_CLIENT_SECRET": "my-client-secret",
        "DATABRICKS_HOST": "https://apps-host.azuredatabricks.net",
    }
    with (
        mock.patch.dict(os.environ, env, clear=False),
        mock.patch(_TAG_CLIENT, side_effect=lambda c: c),
        mock.patch(_WS_CLIENT) as mock_ws,
    ):
        get_workspace_client()
        assert mock_ws.call_args.kwargs.get("client_id") == "my-client-id"
        assert mock_ws.call_args.kwargs.get("client_secret") == "my-client-secret"
        assert "profile" not in mock_ws.call_args.kwargs


# ---------------------------------------------------------------------------
# Username cache reset on workspace switch
# ---------------------------------------------------------------------------


def test_username_cache_reset_on_switch():
    """set_active_workspace() resets the cached username so it's re-fetched for the new workspace."""
    mock_client_a = mock.MagicMock()
    mock_client_a.current_user.me.return_value = mock.MagicMock(user_name="user-a@example.com")
    mock_client_b = mock.MagicMock()
    mock_client_b.current_user.me.return_value = mock.MagicMock(user_name="user-b@example.com")

    with mock.patch(_TAG_CLIENT, side_effect=lambda c: c), mock.patch(_WS_CLIENT, return_value=mock_client_a):
        set_active_workspace(profile="workspace-a")
        username_a = get_current_username()
        assert username_a == "user-a@example.com"

    # Switch workspace — cache should be invalidated
    with mock.patch(_TAG_CLIENT, side_effect=lambda c: c), mock.patch(_WS_CLIENT, return_value=mock_client_b):
        set_active_workspace(profile="workspace-b")
        username_b = get_current_username()
        assert username_b == "user-b@example.com"
