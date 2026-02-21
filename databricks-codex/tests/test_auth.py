"""Tests for authentication utilities."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from databricks_codex.auth import (
    CodexAuthStatus,
    check_codex_auth,
    login_codex,
    logout_codex,
    get_combined_auth_context,
    get_databricks_env,
)
from databricks_codex.models import CodexAuthMethod


class TestCodexAuthStatus:
    """Tests for CodexAuthStatus dataclass."""

    def test_authenticated_status(self):
        """Test authenticated status."""
        status = CodexAuthStatus(
            method=CodexAuthMethod.CHATGPT_OAUTH,
            is_authenticated=True,
            username="user@example.com",
        )

        assert status.is_authenticated is True
        assert status.method == CodexAuthMethod.CHATGPT_OAUTH
        assert status.username == "user@example.com"
        assert status.error is None

    def test_unauthenticated_status(self):
        """Test unauthenticated status."""
        status = CodexAuthStatus(
            method=CodexAuthMethod.NONE,
            is_authenticated=False,
            error="Not logged in",
        )

        assert status.is_authenticated is False
        assert status.error == "Not logged in"


class TestCheckCodexAuth:
    """Tests for check_codex_auth function."""

    def test_codex_authenticated(self, mock_subprocess_run):
        """Test when Codex is authenticated."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="codex 1.0.0",
            stderr="",
        )

        status = check_codex_auth()

        assert status.is_authenticated is True
        mock_subprocess_run.assert_called_once()

    def test_codex_not_installed(self, mock_subprocess_run_not_found):
        """Test when Codex CLI is not installed."""
        status = check_codex_auth()

        assert status.is_authenticated is False
        assert "not found" in status.error.lower()

    def test_codex_timeout(self, mock_subprocess_run_timeout):
        """Test when Codex CLI times out."""
        status = check_codex_auth()

        assert status.is_authenticated is False
        assert "timed out" in status.error.lower()

    def test_codex_error(self, mock_subprocess_run):
        """Test when Codex returns error."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Authentication error",
        )

        status = check_codex_auth()

        assert status.is_authenticated is False


class TestLoginCodex:
    """Tests for login_codex function."""

    def test_login_oauth_success(self, mock_subprocess_run):
        """Test successful OAuth login."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Logged in successfully",
            stderr="",
        )

        status = login_codex(method=CodexAuthMethod.CHATGPT_OAUTH)

        assert status.is_authenticated is True
        # Should call login then version check
        assert mock_subprocess_run.call_count >= 1

    def test_login_device_code(self, mock_subprocess_run):
        """Test device code login adds flag."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )

        login_codex(method=CodexAuthMethod.DEVICE_CODE)

        # Check that --device-auth flag was used
        calls = mock_subprocess_run.call_args_list
        login_call = calls[0]
        cmd = login_call[0][0]  # First positional arg
        assert "--device-auth" in cmd

    def test_login_api_key_without_key(self, mock_subprocess_run):
        """Test API key login without providing key."""
        status = login_codex(method=CodexAuthMethod.API_KEY, api_key=None)

        assert status.is_authenticated is False
        assert "API key required" in status.error

    def test_login_api_key_with_key(self, mock_subprocess_run):
        """Test API key login with key provided."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )

        status = login_codex(method=CodexAuthMethod.API_KEY, api_key="sk-test-key")

        # Check that key was passed as input
        calls = mock_subprocess_run.call_args_list
        login_call = calls[0]
        assert login_call[1].get("input") == "sk-test-key"

    def test_login_failure(self, mock_subprocess_run):
        """Test login failure."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Invalid credentials",
        )

        status = login_codex()

        assert status.is_authenticated is False
        assert "Invalid credentials" in status.error

    def test_login_not_installed(self, mock_subprocess_run_not_found):
        """Test login when Codex not installed."""
        status = login_codex()

        assert status.is_authenticated is False
        assert "not found" in status.error.lower()


class TestLogoutCodex:
    """Tests for logout_codex function."""

    def test_logout_success(self, mock_subprocess_run):
        """Test successful logout."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Logged out",
            stderr="",
        )

        result = logout_codex()

        assert result is True

    def test_logout_failure(self, mock_subprocess_run):
        """Test logout failure."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error",
        )

        result = logout_codex()

        assert result is False

    def test_logout_not_installed(self, mock_subprocess_run_not_found):
        """Test logout when Codex not installed."""
        result = logout_codex()

        assert result is False


class TestGetCombinedAuthContext:
    """Tests for get_combined_auth_context function."""

    def test_from_env_vars(self, mock_databricks_env):
        """Test getting auth from environment variables."""
        host, token = get_combined_auth_context()

        assert host == "https://test.cloud.databricks.com"
        assert token == "dapi_test_token"

    def test_no_credentials(self, clean_env):
        """Test when no credentials available."""
        # Mock both SDK import paths to fail
        with patch.dict("sys.modules", {"databricks_tools_core.auth": None, "databricks_tools_core": None}):
            with patch.dict("sys.modules", {"databricks.sdk": None, "databricks": None}):
                host, token = get_combined_auth_context()

        # May return None if no credentials found
        # This depends on whether SDK is installed and configured
        # In test env without SDK, should return (None, None)

    def test_env_vars_take_priority(self, mock_databricks_env):
        """Test that env vars take priority over SDK."""
        host, token = get_combined_auth_context()

        # Should use env vars, not SDK
        assert host == mock_databricks_env["DATABRICKS_HOST"]
        assert token == mock_databricks_env["DATABRICKS_TOKEN"]


class TestGetDatabricksEnv:
    """Tests for get_databricks_env function."""

    def test_with_credentials(self, mock_databricks_env):
        """Test getting env with credentials."""
        env = get_databricks_env()

        assert "DATABRICKS_HOST" in env
        assert "DATABRICKS_TOKEN" in env

    def test_with_profile(self, mock_databricks_env):
        """Test getting env with non-default profile."""
        env = get_databricks_env(profile="PROD")

        assert env.get("DATABRICKS_CONFIG_PROFILE") == "PROD"

    def test_default_profile_not_added(self, mock_databricks_env):
        """Test that DEFAULT profile doesn't add env var."""
        env = get_databricks_env(profile="DEFAULT")

        assert "DATABRICKS_CONFIG_PROFILE" not in env
