"""Unit tests for customization.auth_guard_patch.

All tests mock WorkspaceClient so no live Databricks connection is needed.

Patching strategy
-----------------
ensure_oauth_authenticated imports WorkspaceClient lazily inside the function.
Patch at the source:  databricks.sdk.WorkspaceClient
"""

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEnsureOauthAuthenticated:
    """Tests for ensure_oauth_authenticated()."""

    def test_cached_token_starts_silently(self):
        """Valid cached token: current_user.me() succeeds, no error raised."""
        mock_me = MagicMock()
        mock_me.user_name = "alice@noom.com"

        mock_client = MagicMock()
        mock_client.current_user.me.return_value = mock_me

        with patch("databricks.sdk.WorkspaceClient", return_value=mock_client) as mock_wc:
            from customization.auth_guard_patch import ensure_oauth_authenticated

            ensure_oauth_authenticated()

        mock_wc.assert_called_once_with(
            host=mock_wc.call_args.kwargs.get(
                "host", mock_wc.call_args.args[0] if mock_wc.call_args.args else ""
            ),
            auth_type="external-browser",
        )
        mock_client.current_user.me.assert_called_once()

    def test_browser_flow_succeeds(self):
        """No cached token but browser flow completes: server starts normally."""
        mock_me = MagicMock()
        mock_me.user_name = "bob@noom.com"

        mock_client = MagicMock()
        mock_client.current_user.me.return_value = mock_me

        # WorkspaceClient construction itself triggers the browser flow
        # when auth_type="external-browser" and no cache exists.
        # We model this as: construction succeeds, me() succeeds.
        with patch("databricks.sdk.WorkspaceClient", return_value=mock_client):
            from customization.auth_guard_patch import ensure_oauth_authenticated

            ensure_oauth_authenticated()  # must not raise

        mock_client.current_user.me.assert_called_once()

    def test_browser_unavailable_raises_runtime_error(self):
        """Browser cannot open (headless/SSH): RuntimeError with manual instructions."""
        with patch(
            "databricks.sdk.WorkspaceClient",
            side_effect=Exception("cannot open browser: no display"),
        ):
            from customization.auth_guard_patch import ensure_oauth_authenticated

            with pytest.raises(RuntimeError) as exc_info:
                ensure_oauth_authenticated()

        msg = str(exc_info.value)
        assert "databricks auth login" in msg
        assert "restart the MCP server" in msg

    def test_me_call_fails_raises_runtime_error(self):
        """WorkspaceClient constructs but current_user.me() fails: RuntimeError raised."""
        mock_client = MagicMock()
        mock_client.current_user.me.side_effect = Exception("network error")

        with patch("databricks.sdk.WorkspaceClient", return_value=mock_client):
            from customization.auth_guard_patch import ensure_oauth_authenticated

            with pytest.raises(RuntimeError) as exc_info:
                ensure_oauth_authenticated()

        assert "databricks auth login" in str(exc_info.value)

    def test_uses_databricks_host_env(self, monkeypatch):
        """DATABRICKS_HOST env var is passed as host to WorkspaceClient."""
        monkeypatch.setenv("DATABRICKS_HOST", "https://test.cloud.databricks.com")

        mock_me = MagicMock()
        mock_me.user_name = "carol@noom.com"
        mock_client = MagicMock()
        mock_client.current_user.me.return_value = mock_me

        with patch("databricks.sdk.WorkspaceClient", return_value=mock_client) as mock_wc:
            from customization.auth_guard_patch import ensure_oauth_authenticated

            ensure_oauth_authenticated()

        call_kwargs = mock_wc.call_args.kwargs
        assert call_kwargs.get("host") == "https://test.cloud.databricks.com"
        assert call_kwargs.get("auth_type") == "external-browser"

    def test_pat_token_in_env_does_not_block(self, monkeypatch):
        """DATABRICKS_TOKEN in environment does not prevent startup.

        The explicit auth_type="external-browser" bypasses env-var credentials,
        so a PAT in DATABRICKS_TOKEN is silently ignored.
        """
        monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-some-pat-token")

        mock_me = MagicMock()
        mock_me.user_name = "dave@noom.com"
        mock_client = MagicMock()
        mock_client.current_user.me.return_value = mock_me

        with patch("databricks.sdk.WorkspaceClient", return_value=mock_client):
            from customization.auth_guard_patch import ensure_oauth_authenticated

            ensure_oauth_authenticated()  # must not raise

        mock_client.current_user.me.assert_called_once()
