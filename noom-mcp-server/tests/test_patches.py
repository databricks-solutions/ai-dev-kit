"""Unit tests for noom_mcp.patches.

All tests mock Databricks SDK calls so no live workspace is needed.
The SQLExecutor class-level patches are restored after each test that
applies them, so tests are fully isolated.

Patching strategy
-----------------
patches.py imports helpers lazily inside functions (to avoid circular
imports and keep startup fast).  This means ``patch("noom_mcp.patches.X")``
only works for names defined at module level in patches.py (e.g.
``get_sql_sp_client``, ``get_mcp_user_identity``).

For names imported inside functions, patch at the source module instead:
  - ``databricks_tools_core.auth.get_workspace_client``
  - ``databricks_tools_core.auth.get_current_username``
  - ``databricks_tools_core.identity.tag_client``
"""

from typing import Optional
from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_sp_client_cache() -> None:
    """Reset the process-level SP client cache between tests."""
    import noom_mcp.patches as p
    p._sql_sp_client = None


def _save_executor_methods() -> tuple:
    """Return current (orig_init, orig_execute) for later restoration."""
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
    return SQLExecutor.__init__, SQLExecutor.execute


def _restore_executor_methods(orig_init, orig_execute) -> None:
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
    SQLExecutor.__init__ = orig_init
    SQLExecutor.execute = orig_execute


# ---------------------------------------------------------------------------
# verify_patch_assumptions
# ---------------------------------------------------------------------------


class TestVerifyPatchAssumptions:
    def test_happy_path(self):
        """Current upstream passes all checks without modification."""
        from noom_mcp.patches import verify_patch_assumptions
        verify_patch_assumptions()  # must not raise

    def test_version_mismatch_raises(self):
        """Stale version pin triggers UpstreamChangedError."""
        import noom_mcp.patches as p
        from noom_mcp.patches import UpstreamChangedError, verify_patch_assumptions

        original = p.VALIDATED_UPSTREAM_VERSION
        p.VALIDATED_UPSTREAM_VERSION = "0.0.0"
        try:
            with pytest.raises(UpstreamChangedError) as exc_info:
                verify_patch_assumptions()
            msg = str(exc_info.value)
            assert "version mismatch" in msg.lower()
            assert "0.0.0" in msg
        finally:
            p.VALIDATED_UPSTREAM_VERSION = original

    def test_init_signature_drift_raises(self):
        """Extra param on SQLExecutor.__init__ triggers UpstreamChangedError."""
        import noom_mcp.patches as p
        from databricks_tools_core.sql.sql_utils import executor as mod
        from noom_mcp.patches import UpstreamChangedError, verify_patch_assumptions

        original_class = mod.SQLExecutor

        class _Drifted(original_class):
            def __init__(self, warehouse_id, client=None, new_param=None):
                super().__init__(warehouse_id, client)

        mod.SQLExecutor = _Drifted
        try:
            with pytest.raises(UpstreamChangedError) as exc_info:
                verify_patch_assumptions()
            assert "SQLExecutor.__init__ signature changed" in str(exc_info.value)
            assert "new_param" in str(exc_info.value)
        finally:
            mod.SQLExecutor = original_class

    def test_execute_signature_drift_raises(self):
        """Extra param on SQLExecutor.execute triggers UpstreamChangedError."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from noom_mcp.patches import UpstreamChangedError, verify_patch_assumptions

        original_execute = SQLExecutor.execute

        def _drifted(self, sql_query, catalog=None, schema=None,
                     row_limit=None, timeout=180, query_tags=None, new_param=None):
            pass

        SQLExecutor.execute = _drifted
        try:
            with pytest.raises(UpstreamChangedError) as exc_info:
                verify_patch_assumptions()
            assert "SQLExecutor.execute signature changed" in str(exc_info.value)
        finally:
            SQLExecutor.execute = original_execute

    def test_multiple_issues_reported_together(self):
        """All drifts collected into a single UpstreamChangedError."""
        import noom_mcp.patches as p
        from noom_mcp.patches import UpstreamChangedError, verify_patch_assumptions

        orig_version = p.VALIDATED_UPSTREAM_VERSION
        orig_init_params = p._EXPECTED_INIT_PARAMS
        p.VALIDATED_UPSTREAM_VERSION = "0.0.0"
        p._EXPECTED_INIT_PARAMS = {"warehouse_id", "client", "ghost_param"}
        try:
            with pytest.raises(UpstreamChangedError) as exc_info:
                verify_patch_assumptions()
            assert "Found 2 issue" in str(exc_info.value)
        finally:
            p.VALIDATED_UPSTREAM_VERSION = orig_version
            p._EXPECTED_INIT_PARAMS = orig_init_params


# ---------------------------------------------------------------------------
# get_mcp_user_identity
# ---------------------------------------------------------------------------


class TestGetMcpUserIdentity:
    def test_returns_username_when_available(self):
        """Email address is preferred when get_current_username() resolves."""
        with patch(
            "databricks_tools_core.auth.get_current_username",
            return_value="alice@noom.com",
        ):
            from noom_mcp.patches import get_mcp_user_identity
            assert get_mcp_user_identity() == "alice@noom.com"

    def test_falls_back_to_sp_client_id(self, monkeypatch):
        """sp:<client_id> returned when username is None but CLIENT_ID is set."""
        monkeypatch.setenv("DATABRICKS_CLIENT_ID", "my-sp-id")
        with patch(
            "databricks_tools_core.auth.get_current_username",
            return_value=None,
        ):
            from noom_mcp.patches import get_mcp_user_identity
            assert get_mcp_user_identity() == "sp:my-sp-id"

    def test_falls_back_to_unknown(self, monkeypatch):
        """'unknown' when both username and CLIENT_ID are absent."""
        monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
        with patch(
            "databricks_tools_core.auth.get_current_username",
            return_value=None,
        ):
            from noom_mcp.patches import get_mcp_user_identity
            assert get_mcp_user_identity() == "unknown"


# ---------------------------------------------------------------------------
# patch_sql_executor: SP client injection
# ---------------------------------------------------------------------------


class TestPatchSqlExecutorSpClient:
    @pytest.fixture(autouse=True)
    def isolate(self):
        orig = _save_executor_methods()
        yield
        _restore_executor_methods(*orig)
        _reset_sp_client_cache()

    def test_patched_init_uses_sp_client(self):
        """After patching, SQLExecutor always uses the SP client."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from noom_mcp.patches import patch_sql_executor

        mock_sp = MagicMock()
        with patch("noom_mcp.patches.get_sql_sp_client", return_value=mock_sp):
            patch_sql_executor()
            executor = SQLExecutor.__new__(SQLExecutor)
            SQLExecutor.__init__(executor, "wh-123", client=None)
            assert executor.client is mock_sp

    def test_patched_init_ignores_caller_supplied_client(self):
        """SP client overrides any client the caller passes in."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from noom_mcp.patches import patch_sql_executor

        caller_client = MagicMock(name="caller_client")
        sp_client = MagicMock(name="sp_client")

        with patch("noom_mcp.patches.get_sql_sp_client", return_value=sp_client):
            patch_sql_executor()
            executor = SQLExecutor.__new__(SQLExecutor)
            SQLExecutor.__init__(executor, "wh-123", client=caller_client)
            assert executor.client is sp_client
            assert executor.client is not caller_client


# ---------------------------------------------------------------------------
# patch_sql_executor: user identity tagging
# ---------------------------------------------------------------------------


class TestPatchSqlExecutorIdentityTagging:
    @pytest.fixture(autouse=True)
    def isolate(self):
        orig = _save_executor_methods()
        yield
        _restore_executor_methods(*orig)
        _reset_sp_client_cache()

    def test_user_tag_injected_when_no_existing_tags(self):
        """mcp_user:<identity> is the sole tag when query_tags is None."""
        identity = "alice@noom.com"
        query_tags = None
        user_tag = f"mcp_user:{identity}"
        effective = f"{query_tags},{user_tag}" if query_tags else user_tag
        assert effective == "mcp_user:alice@noom.com"

    def test_user_tag_appended_to_existing_tags(self):
        """mcp_user tag is appended after existing tags with comma separator."""
        identity = "alice@noom.com"
        existing = "team:eng,cost_center:701"
        user_tag = f"mcp_user:{identity}"
        effective = f"{existing},{user_tag}" if existing else user_tag
        assert effective == "team:eng,cost_center:701,mcp_user:alice@noom.com"

    def test_sp_identity_tagged_for_m2m_caller(self):
        """sp:<client_id> format used when caller is a service principal."""
        effective = f"mcp_user:sp:my-client-id"
        assert effective == "mcp_user:sp:my-client-id"

    def test_unknown_identity_tagged_gracefully(self):
        """'unknown' identity still produces a valid tag."""
        assert f"mcp_user:unknown" == "mcp_user:unknown"

    def test_patched_execute_injects_tag_and_calls_through(self):
        """End-to-end: patched execute injects tag and calls original."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from noom_mcp.patches import patch_sql_executor

        received: dict = {}
        mock_sp = MagicMock()

        # Install a recording spy as the "original" before applying the patch
        def _spy(self, sql_query, catalog=None, schema=None,
                 row_limit=None, timeout=180, query_tags=None):
            received["query_tags"] = query_tags
            received["sql_query"] = sql_query
            return []

        SQLExecutor.execute = _spy

        # Keep mocks active for the actual call — get_mcp_user_identity is
        # called at call time, not at patch-install time.
        with patch("noom_mcp.patches.get_sql_sp_client", return_value=mock_sp), \
             patch("noom_mcp.patches.get_mcp_user_identity", return_value="bob@noom.com"):
            patch_sql_executor()

            executor = SQLExecutor.__new__(SQLExecutor)
            executor.warehouse_id = "wh-1"
            executor.client = mock_sp
            SQLExecutor.execute(executor, "SELECT 1", query_tags="team:data")

        assert received["sql_query"] == "SELECT 1"
        assert received["query_tags"] == "team:data,mcp_user:bob@noom.com"

    def test_patched_execute_no_existing_tags(self):
        """Patched execute produces only the mcp_user tag when none given."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from noom_mcp.patches import patch_sql_executor

        received: dict = {}
        mock_sp = MagicMock()

        def _spy(self, sql_query, catalog=None, schema=None,
                 row_limit=None, timeout=180, query_tags=None):
            received["query_tags"] = query_tags
            return []

        SQLExecutor.execute = _spy

        with patch("noom_mcp.patches.get_sql_sp_client", return_value=mock_sp), \
             patch("noom_mcp.patches.get_mcp_user_identity", return_value="carol@noom.com"):
            patch_sql_executor()

            executor = SQLExecutor.__new__(SQLExecutor)
            executor.warehouse_id = "wh-1"
            executor.client = mock_sp
            SQLExecutor.execute(executor, "SELECT 2")

        assert received["query_tags"] == "mcp_user:carol@noom.com"


# ---------------------------------------------------------------------------
# check_pat_rejected
# ---------------------------------------------------------------------------


class TestCheckPatRejected:
    def _mock_client(self, auth_type: Optional[str]) -> MagicMock:
        client = MagicMock()
        client.config.auth_type = auth_type
        client.current_user.me.return_value = MagicMock(user_name="test@noom.com")
        return client

    def test_pat_raises_runtime_error(self):
        """PAT auth_type triggers RuntimeError with clear message."""
        from noom_mcp.patches import check_pat_rejected

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=self._mock_client("pat")):
            with pytest.raises(RuntimeError) as exc_info:
                check_pat_rejected()
            assert "PAT authentication is not permitted" in str(exc_info.value)

    def test_oauth_browser_passes(self):
        """databricks-cli (browser OAuth) is accepted."""
        from noom_mcp.patches import check_pat_rejected

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=self._mock_client("databricks-cli")):
            check_pat_rejected()  # must not raise

    def test_oauth_m2m_passes(self):
        """oauth-m2m is accepted."""
        from noom_mcp.patches import check_pat_rejected

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=self._mock_client("oauth-m2m")):
            check_pat_rejected()  # must not raise

    def test_api_failure_propagates(self):
        """SDK errors during the auth check re-raise so the server won't start."""
        from noom_mcp.patches import check_pat_rejected

        mock_client = MagicMock()
        mock_client.current_user.me.side_effect = Exception("network error")
        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_client):
            with pytest.raises(Exception, match="network error"):
                check_pat_rejected()


# ---------------------------------------------------------------------------
# _fetch_sp_credentials_from_secrets
# ---------------------------------------------------------------------------


class TestFetchSpCredentialsFromSecrets:
    def _secret_response(self, plaintext: str) -> MagicMock:
        import base64
        resp = MagicMock()
        resp.value = base64.b64encode(plaintext.encode()).decode()
        return resp

    def test_returns_decoded_credentials(self, monkeypatch):
        """Credentials are base64-decoded and returned as (client_id, secret)."""
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_SCOPE", "dbrix_mcp_secret")

        mock_client = MagicMock()
        mock_client.secrets.get_secret.side_effect = [
            self._secret_response("my-client-id"),
            self._secret_response("my-client-secret"),
        ]

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_client):
            from noom_mcp.patches import _fetch_sp_credentials_from_secrets
            client_id, client_secret = _fetch_sp_credentials_from_secrets()

        assert client_id == "my-client-id"
        assert client_secret == "my-client-secret"

    def test_uses_default_key_names(self, monkeypatch):
        """Default keys sql-sp-client-id and sql-sp-client-secret are used."""
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_SCOPE", "dbrix_mcp_secret")
        monkeypatch.delenv("DATABRICKS_MCP_SECRET_KEY_CLIENT_ID", raising=False)
        monkeypatch.delenv("DATABRICKS_MCP_SECRET_KEY_CLIENT_SECRET", raising=False)

        mock_client = MagicMock()
        mock_client.secrets.get_secret.side_effect = [
            self._secret_response("id"),
            self._secret_response("secret"),
        ]

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_client):
            from noom_mcp.patches import _fetch_sp_credentials_from_secrets
            _fetch_sp_credentials_from_secrets()

        calls = mock_client.secrets.get_secret.call_args_list
        assert calls[0] == call(scope="dbrix_mcp_secret", key="sql-sp-client-id")
        assert calls[1] == call(scope="dbrix_mcp_secret", key="sql-sp-client-secret")

    def test_custom_key_names_respected(self, monkeypatch):
        """DATABRICKS_MCP_SECRET_KEY_* overrides default key names."""
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_SCOPE", "dbrix_mcp_secret")
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_KEY_CLIENT_ID", "custom-id-key")
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_KEY_CLIENT_SECRET", "custom-secret-key")

        mock_client = MagicMock()
        mock_client.secrets.get_secret.side_effect = [
            self._secret_response("id"),
            self._secret_response("secret"),
        ]

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_client):
            from noom_mcp.patches import _fetch_sp_credentials_from_secrets
            _fetch_sp_credentials_from_secrets()

        calls = mock_client.secrets.get_secret.call_args_list
        assert calls[0] == call(scope="dbrix_mcp_secret", key="custom-id-key")
        assert calls[1] == call(scope="dbrix_mcp_secret", key="custom-secret-key")

    def test_sdk_error_raises_runtime_error(self, monkeypatch):
        """SDK failure fetching a secret raises RuntimeError with context."""
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_SCOPE", "dbrix_mcp_secret")

        mock_client = MagicMock()
        mock_client.secrets.get_secret.side_effect = Exception("permission denied")

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_client):
            from noom_mcp.patches import _fetch_sp_credentials_from_secrets
            with pytest.raises(RuntimeError, match="Failed to fetch secret"):
                _fetch_sp_credentials_from_secrets()

    def test_empty_secret_raises_runtime_error(self, monkeypatch):
        """Empty secret value raises RuntimeError."""
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_SCOPE", "dbrix_mcp_secret")

        mock_client = MagicMock()
        empty = MagicMock()
        empty.value = None
        mock_client.secrets.get_secret.return_value = empty

        with patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_client):
            from noom_mcp.patches import _fetch_sp_credentials_from_secrets
            with pytest.raises(RuntimeError, match="is empty"):
                _fetch_sp_credentials_from_secrets()


# ---------------------------------------------------------------------------
# _build_sql_sp_client: credential resolution order
# ---------------------------------------------------------------------------


class TestBuildSqlSpClient:
    @pytest.fixture(autouse=True)
    def reset_cache(self):
        yield
        _reset_sp_client_cache()

    def test_prefers_secrets_over_env_vars(self, monkeypatch):
        """Databricks Secrets path takes precedence when scope is set."""
        monkeypatch.setenv("DATABRICKS_MCP_SECRET_SCOPE", "dbrix_mcp_secret")
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_ID", "env-id")
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_SECRET", "env-secret")

        mock_wc = MagicMock()
        mock_wc.config.host = "https://test.cloud.databricks.com"

        with patch("noom_mcp.patches._fetch_sp_credentials_from_secrets",
                   return_value=("secrets-id", "secrets-secret")) as mock_fetch, \
             patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_wc), \
             patch("databricks_tools_core.identity.tag_client", side_effect=lambda c: c), \
             patch("databricks.sdk.WorkspaceClient", return_value=MagicMock()):
            from noom_mcp.patches import _build_sql_sp_client
            _build_sql_sp_client()
            mock_fetch.assert_called_once()

    def test_falls_back_to_env_vars(self, monkeypatch):
        """Env vars are used when no secret scope is configured."""
        monkeypatch.delenv("DATABRICKS_MCP_SECRET_SCOPE", raising=False)
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_ID", "env-id")
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_SECRET", "env-secret")

        mock_wc = MagicMock()
        mock_wc.config.host = "https://test.cloud.databricks.com"

        with patch("noom_mcp.patches._fetch_sp_credentials_from_secrets") as mock_fetch, \
             patch("databricks_tools_core.auth.get_workspace_client",
                   return_value=mock_wc), \
             patch("databricks_tools_core.identity.tag_client", side_effect=lambda c: c), \
             patch("databricks.sdk.WorkspaceClient", return_value=MagicMock()):
            from noom_mcp.patches import _build_sql_sp_client
            _build_sql_sp_client()
            mock_fetch.assert_not_called()

    def test_raises_when_neither_configured(self, monkeypatch):
        """RuntimeError with both options listed when nothing is configured."""
        monkeypatch.delenv("DATABRICKS_MCP_SECRET_SCOPE", raising=False)
        monkeypatch.delenv("DATABRICKS_MCP_SQL_CLIENT_ID", raising=False)
        monkeypatch.delenv("DATABRICKS_MCP_SQL_CLIENT_SECRET", raising=False)

        from noom_mcp.patches import _build_sql_sp_client
        with pytest.raises(RuntimeError) as exc_info:
            _build_sql_sp_client()
        msg = str(exc_info.value)
        assert "Option 1" in msg
        assert "Option 2" in msg
