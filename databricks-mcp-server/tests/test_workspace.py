"""Tests for the manage_workspace MCP tool."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from databricks_mcp_server.tools.workspace import _manage_workspace_impl as manage_workspace
from databricks_tools_core.auth import clear_active_workspace, get_active_workspace

# Patch targets
_CFG_PATH = "databricks_mcp_server.tools.workspace._DATABRICKS_CFG_PATH"
_VALIDATE_AND_SWITCH = "databricks_mcp_server.tools.workspace._validate_and_switch"
_GET_WORKSPACE_CLIENT = "databricks_mcp_server.tools.workspace.get_workspace_client"
_GET_ACTIVE_WORKSPACE = "databricks_mcp_server.tools.workspace.get_active_workspace"
_SUBPROCESS_RUN = "databricks_mcp_server.tools.workspace.subprocess.run"


@pytest.fixture(autouse=True)
def reset_active_workspace():
    """Ensure active workspace is cleared before and after each test."""
    clear_active_workspace()
    yield
    clear_active_workspace()


@pytest.fixture
def tmp_databrickscfg(tmp_path):
    """Write a temporary ~/.databrickscfg with three known profiles."""
    cfg = tmp_path / ".databrickscfg"
    cfg.write_text(
        "[DEFAULT]\nhost = https://adb-111.azuredatabricks.net\n\n"
        "[prod]\nhost = https://adb-222.azuredatabricks.net\n\n"
        "[staging]\nhost = https://adb-333.azuredatabricks.net\n"
    )
    return cfg


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def test_status_returns_current_info():
    """action='status' returns host, profile, and username."""
    mock_client = MagicMock()
    mock_client.config.host = "https://adb-111.azuredatabricks.net"
    mock_client.current_user.me.return_value = MagicMock(user_name="user@example.com")

    with patch(_GET_WORKSPACE_CLIENT, return_value=mock_client), \
         patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": "DEFAULT", "host": None}):
        result = manage_workspace(action="status")

    assert result["host"] == "https://adb-111.azuredatabricks.net"
    assert result["username"] == "user@example.com"
    assert result["profile"] == "DEFAULT"


def test_status_returns_error_on_failure():
    """action='status' returns an error dict when the SDK raises."""
    with patch(_GET_WORKSPACE_CLIENT, side_effect=Exception("auth failed")):
        result = manage_workspace(action="status")

    assert "error" in result
    assert "auth failed" in result["error"]


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_list_returns_all_profiles(tmp_databrickscfg):
    """action='list' returns all profiles with host URLs and marks the active one."""
    with patch(_CFG_PATH, str(tmp_databrickscfg)), \
         patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": "prod", "host": None}):
        result = manage_workspace(action="list")

    assert "profiles" in result
    assert len(result["profiles"]) == 3
    profiles_by_name = {p["profile"]: p for p in result["profiles"]}
    assert profiles_by_name["prod"]["active"] is True
    assert profiles_by_name["DEFAULT"]["active"] is False
    assert "adb-222" in profiles_by_name["prod"]["host"]


def test_list_empty_config(tmp_path):
    """action='list' with an empty config returns empty list and a hint message."""
    empty_cfg = tmp_path / ".databrickscfg"
    empty_cfg.write_text("")
    with patch(_CFG_PATH, str(empty_cfg)), \
         patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": None, "host": None}):
        result = manage_workspace(action="list")

    assert result["profiles"] == []
    assert "message" in result


def test_list_missing_config(tmp_path):
    """action='list' when the config file doesn't exist returns empty list."""
    with patch(_CFG_PATH, str(tmp_path / "nonexistent.cfg")), \
         patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": None, "host": None}):
        result = manage_workspace(action="list")

    assert result["profiles"] == []


def test_list_profile_without_host(tmp_path):
    """action='list' with a profile that has no host key still returns the profile."""
    cfg = tmp_path / ".databrickscfg"
    cfg.write_text("[nohostprofile]\ntoken = abc123\n")
    with patch(_CFG_PATH, str(cfg)), \
         patch(_GET_ACTIVE_WORKSPACE, return_value={"profile": None, "host": None}):
        result = manage_workspace(action="list")

    assert len(result["profiles"]) == 1
    assert result["profiles"][0]["profile"] == "nohostprofile"
    assert "no host configured" in result["profiles"][0]["host"]


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------


def test_switch_valid_profile(tmp_databrickscfg):
    """action='switch' with a known profile calls _validate_and_switch and returns success."""
    success = {"host": "https://adb-222.azuredatabricks.net", "profile": "prod", "username": "user@example.com"}
    with patch(_CFG_PATH, str(tmp_databrickscfg)), \
         patch(_VALIDATE_AND_SWITCH, return_value=success) as mock_validate:
        result = manage_workspace(action="switch", profile="prod")

    mock_validate.assert_called_once_with(profile="prod", host=None)
    assert result["profile"] == "prod"
    assert "message" in result


def test_switch_nonexistent_profile(tmp_databrickscfg):
    """action='switch' with an unknown profile name returns error with available profiles."""
    with patch(_CFG_PATH, str(tmp_databrickscfg)):
        result = manage_workspace(action="switch", profile="unknown-profile")

    assert "error" in result
    assert "unknown-profile" in result["error"]
    assert "DEFAULT" in result["error"] or "prod" in result["error"]


def test_switch_with_host(tmp_databrickscfg):
    """action='switch' with a host URL calls _validate_and_switch with the host."""
    host = "https://adb-222.azuredatabricks.net"
    success = {"host": host, "profile": host, "username": "user@example.com"}
    with patch(_CFG_PATH, str(tmp_databrickscfg)), \
         patch(_VALIDATE_AND_SWITCH, return_value=success) as mock_validate:
        result = manage_workspace(action="switch", host=host)

    mock_validate.assert_called_once_with(profile=None, host=host)
    assert "message" in result


def test_switch_rollback_on_auth_failure(tmp_databrickscfg):
    """action='switch' returns error when validation fails; active workspace is NOT updated."""
    with patch(_CFG_PATH, str(tmp_databrickscfg)), \
         patch(_VALIDATE_AND_SWITCH, side_effect=Exception("invalid credentials")):
        result = manage_workspace(action="switch", profile="prod")

    assert "error" in result
    assert "invalid credentials" in result["error"]
    assert get_active_workspace()["profile"] is None


def test_switch_expired_token_returns_structured_response(tmp_databrickscfg):
    """action='switch' with an expired token returns a structured response with token_expired flag."""
    expired_msg = "default auth: databricks-cli: cannot get access token: refresh token is invalid"
    with patch(_CFG_PATH, str(tmp_databrickscfg)), \
         patch(_VALIDATE_AND_SWITCH, side_effect=Exception(expired_msg)):
        result = manage_workspace(action="switch", profile="prod")

    assert result.get("token_expired") is True
    assert result["profile"] == "prod"
    assert "adb-222" in result["host"]
    assert "login" in result["action_required"]


def test_switch_no_profile_no_host():
    """action='switch' without profile or host returns a clear error."""
    result = manage_workspace(action="switch")
    assert "error" in result
    assert "profile" in result["error"].lower() or "host" in result["error"].lower()


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


def test_login_calls_cli():
    """action='login' runs 'databricks auth login --host ...'."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    success = {"host": "https://adb-999.net", "profile": "adb-999", "username": "u@x.com"}

    with patch(_SUBPROCESS_RUN, return_value=mock_proc) as mock_run, \
         patch(_VALIDATE_AND_SWITCH, return_value=success):
        result = manage_workspace(action="login", host="https://adb-999.azuredatabricks.net")

    args = mock_run.call_args.args[0]
    assert "databricks" in args and "auth" in args and "login" in args
    assert "--host" in args and "https://adb-999.azuredatabricks.net" in args
    assert result["profile"] == "adb-999"


def test_login_passes_stdin_devnull():
    """action='login' sets stdin=DEVNULL to avoid inheriting the MCP stdio pipe."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    success = {"host": "https://adb-999.net", "profile": "adb-999", "username": "u@x.com"}

    with patch(_SUBPROCESS_RUN, return_value=mock_proc) as mock_run, \
         patch(_VALIDATE_AND_SWITCH, return_value=success):
        manage_workspace(action="login", host="https://adb-999.azuredatabricks.net")

    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs.get("stdin") == subprocess.DEVNULL


def test_login_timeout():
    """action='login' returns a clear error when the OAuth flow times out."""
    with patch(_SUBPROCESS_RUN, side_effect=subprocess.TimeoutExpired(cmd="databricks", timeout=120)):
        result = manage_workspace(action="login", host="https://adb-999.net")

    assert "error" in result
    assert "timed out" in result["error"].lower()


def test_login_cli_failure():
    """action='login' returns an error when the CLI exits non-zero."""
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.stderr = "Error: invalid workspace URL"
    mock_proc.stdout = ""

    with patch(_SUBPROCESS_RUN, return_value=mock_proc):
        result = manage_workspace(action="login", host="https://bad-host.net")

    assert "error" in result
    assert "invalid workspace URL" in result["error"]


def test_login_cli_not_installed():
    """action='login' returns a helpful error when the Databricks CLI is not found."""
    with patch(_SUBPROCESS_RUN, side_effect=FileNotFoundError):
        result = manage_workspace(action="login", host="https://adb-999.net")

    assert "error" in result
    assert "CLI" in result["error"] or "databricks" in result["error"].lower()


def test_login_switches_after_success():
    """action='login' updates the active workspace after a successful CLI call."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    success = {"host": "https://adb-999.net", "profile": "adb-999", "username": "u@x.com"}

    with patch(_SUBPROCESS_RUN, return_value=mock_proc), \
         patch(_VALIDATE_AND_SWITCH, return_value=success) as mock_validate:
        result = manage_workspace(action="login", host="https://adb-999.azuredatabricks.net")

    mock_validate.assert_called_once()
    assert result["username"] == "u@x.com"
    assert "message" in result


def test_login_no_host():
    """action='login' without a host returns a clear error."""
    result = manage_workspace(action="login")
    assert "error" in result
    assert "host" in result["error"].lower()


# ---------------------------------------------------------------------------
# invalid action
# ---------------------------------------------------------------------------


def test_invalid_action():
    """An unrecognised action returns an error listing valid actions."""
    result = manage_workspace(action="badaction")
    assert "error" in result
    for valid in ("status", "list", "switch", "login"):
        assert valid in result["error"]
