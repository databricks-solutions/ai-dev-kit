"""Unit tests for noom_mcp.auth_guard_patch.

get_workspace_client is imported lazily inside check_pat_rejected, so
patch at the source module:
  - databricks_tools_core.auth.get_workspace_client
"""

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest


class TestCheckPatRejected:
    def _mock_client(self, auth_type: Optional[str]) -> MagicMock:
        client = MagicMock()
        client.config.auth_type = auth_type
        client.current_user.me.return_value = MagicMock(user_name="test@noom.com")
        return client

    def test_pat_raises_runtime_error(self):
        """PAT auth_type triggers RuntimeError with clear message."""
        from noom_mcp.auth_guard_patch import check_pat_rejected

        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=self._mock_client("pat"),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                check_pat_rejected()
            assert "PAT authentication is not permitted" in str(exc_info.value)

    def test_oauth_browser_passes(self):
        """databricks-cli (browser OAuth) is accepted."""
        from noom_mcp.auth_guard_patch import check_pat_rejected

        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=self._mock_client("databricks-cli"),
        ):
            check_pat_rejected()  # must not raise

    def test_oauth_m2m_passes(self):
        """oauth-m2m is accepted."""
        from noom_mcp.auth_guard_patch import check_pat_rejected

        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=self._mock_client("oauth-m2m"),
        ):
            check_pat_rejected()  # must not raise

    def test_api_failure_propagates(self):
        """SDK errors during the auth check re-raise so the server won't start."""
        from noom_mcp.auth_guard_patch import check_pat_rejected

        mock_client = MagicMock()
        mock_client.current_user.me.side_effect = Exception("network error")
        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=mock_client,
        ):
            with pytest.raises(Exception, match="network error"):
                check_pat_rejected()
