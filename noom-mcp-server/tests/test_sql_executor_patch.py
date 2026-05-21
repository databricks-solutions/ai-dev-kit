"""Unit tests for customization.sql_executor_patch.

All tests mock Databricks SDK calls so no live workspace is needed.
The SQLExecutor class-level patches are restored after each test that
applies them, so tests are fully isolated.

Patching strategy
-----------------
sql_executor_patch.py imports helpers lazily inside functions.  This means
``patch("customization.sql_executor_patch.X")`` only works for names that are
defined at module level (e.g. ``get_sql_sp_client``, ``get_mcp_user_identity``,
``_fetch_sp_credentials_from_secrets``).

For names imported inside functions, patch at the source module instead:
  - databricks_tools_core.auth.get_workspace_client
  - databricks_tools_core.auth.get_current_username
  - databricks_tools_core.identity.tag_client
"""

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_sp_client_cache() -> None:
    """Reset the process-level SP client cache between tests."""
    import customization.sql_executor_patch as m

    m._sql_sp_client = None


def _save_executor_methods() -> tuple:
    """Return current (orig_init, orig_execute) for later restoration."""
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor

    return SQLExecutor.__init__, SQLExecutor.execute


def _restore_executor_methods(orig_init, orig_execute) -> None:
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor

    SQLExecutor.__init__ = orig_init
    SQLExecutor.execute = orig_execute


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
            from customization.sql_executor_patch import get_mcp_user_identity

            assert get_mcp_user_identity() == "alice@noom.com"

    def test_falls_back_to_sp_client_id(self, monkeypatch):
        """sp:<client_id> returned when username is None but CLIENT_ID is set."""
        monkeypatch.setenv("DATABRICKS_CLIENT_ID", "my-sp-id")
        with patch(
            "databricks_tools_core.auth.get_current_username",
            return_value=None,
        ):
            from customization.sql_executor_patch import get_mcp_user_identity

            assert get_mcp_user_identity() == "sp:my-sp-id"

    def test_falls_back_to_unknown(self, monkeypatch):
        """'unknown' when both username and CLIENT_ID are absent."""
        monkeypatch.delenv("DATABRICKS_CLIENT_ID", raising=False)
        with patch(
            "databricks_tools_core.auth.get_current_username",
            return_value=None,
        ):
            from customization.sql_executor_patch import get_mcp_user_identity

            assert get_mcp_user_identity() == "unknown"


# ---------------------------------------------------------------------------
# patch_sql_executor: SP client injection
# ---------------------------------------------------------------------------


class TestPatchSqlExecutorWarehouseId:
    @pytest.fixture(autouse=True)
    def isolate(self):
        orig = _save_executor_methods()
        yield
        _restore_executor_methods(*orig)
        _reset_sp_client_cache()

    def test_patched_init_uses_configured_warehouse(self):
        """After patching, SQLExecutor always uses the configured warehouse ID."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from customization.sql_executor_patch import patch_sql_executor

        mock_sp = MagicMock()
        with (
            patch("customization.sql_executor_patch.get_sql_sp_client", return_value=mock_sp),
            patch("customization.sql_executor_patch.get_sql_warehouse_id", return_value="wh-prod"),
        ):
            patch_sql_executor()
            executor = SQLExecutor.__new__(SQLExecutor)
            SQLExecutor.__init__(executor, "wh-caller-supplied", client=None)
            assert executor.warehouse_id == "wh-prod"

    def test_patched_init_ignores_caller_supplied_warehouse(self):
        """Configured warehouse overrides whatever warehouse the AI passes in."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from customization.sql_executor_patch import patch_sql_executor

        mock_sp = MagicMock()
        with (
            patch("customization.sql_executor_patch.get_sql_sp_client", return_value=mock_sp),
            patch("customization.sql_executor_patch.get_sql_warehouse_id", return_value="wh-prod"),
        ):
            patch_sql_executor()
            executor = SQLExecutor.__new__(SQLExecutor)
            SQLExecutor.__init__(executor, "wh-some-random-id", client=None)
            assert executor.warehouse_id == "wh-prod"
            assert executor.warehouse_id != "wh-some-random-id"

    def test_get_sql_warehouse_id_reads_env(self, monkeypatch):
        """get_sql_warehouse_id returns the env var value."""
        monkeypatch.setenv("DATABRICKS_WAREHOUSE_ID", "wh-abc123")
        from customization.sql_executor_patch import get_sql_warehouse_id

        assert get_sql_warehouse_id() == "wh-abc123"

    def test_get_sql_warehouse_id_raises_when_unset(self, monkeypatch):
        """get_sql_warehouse_id raises RuntimeError when env var is missing."""
        monkeypatch.delenv("DATABRICKS_WAREHOUSE_ID", raising=False)
        from customization.sql_executor_patch import get_sql_warehouse_id

        with pytest.raises(RuntimeError, match="DATABRICKS_WAREHOUSE_ID is not set"):
            get_sql_warehouse_id()


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
        from customization.sql_executor_patch import patch_sql_executor

        mock_sp = MagicMock()
        with (
            patch("customization.sql_executor_patch.get_sql_sp_client", return_value=mock_sp),
            patch("customization.sql_executor_patch.get_sql_warehouse_id", return_value="wh-prod"),
        ):
            patch_sql_executor()
            executor = SQLExecutor.__new__(SQLExecutor)
            SQLExecutor.__init__(executor, "wh-123", client=None)
            assert executor.client is mock_sp

    def test_patched_init_ignores_caller_supplied_client(self):
        """SP client overrides any client the caller passes in."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from customization.sql_executor_patch import patch_sql_executor

        caller_client = MagicMock(name="caller_client")
        sp_client = MagicMock(name="sp_client")

        with (
            patch("customization.sql_executor_patch.get_sql_sp_client", return_value=sp_client),
            patch("customization.sql_executor_patch.get_sql_warehouse_id", return_value="wh-prod"),
        ):
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
        assert "mcp_user:sp:my-client-id" == "mcp_user:sp:my-client-id"

    def test_unknown_identity_tagged_gracefully(self):
        """'unknown' identity still produces a valid tag."""
        assert "mcp_user:unknown" == "mcp_user:unknown"

    def test_patched_execute_injects_tag_and_calls_through(self):
        """End-to-end: patched execute injects tag and calls original."""
        from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
        from customization.sql_executor_patch import patch_sql_executor

        received: dict = {}
        mock_sp = MagicMock()

        # Install a recording spy as the "original" before applying the patch.
        def _spy(
            self,
            sql_query,
            catalog=None,
            schema=None,
            row_limit=None,
            timeout=180,
            query_tags=None,
        ):
            received["query_tags"] = query_tags
            received["sql_query"] = sql_query
            return []

        SQLExecutor.execute = _spy

        # Keep mocks active for the actual call — get_mcp_user_identity is
        # resolved at call time, not at patch-install time.
        with (
            patch("customization.sql_executor_patch.get_sql_sp_client", return_value=mock_sp),
            patch("customization.sql_executor_patch.get_sql_warehouse_id", return_value="wh-prod"),
            patch(
                "customization.sql_executor_patch.get_mcp_user_identity",
                return_value="bob@noom.com",
            ),
        ):
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
        from customization.sql_executor_patch import patch_sql_executor

        received: dict = {}
        mock_sp = MagicMock()

        def _spy(
            self,
            sql_query,
            catalog=None,
            schema=None,
            row_limit=None,
            timeout=180,
            query_tags=None,
        ):
            received["query_tags"] = query_tags
            return []

        SQLExecutor.execute = _spy

        with (
            patch("customization.sql_executor_patch.get_sql_sp_client", return_value=mock_sp),
            patch("customization.sql_executor_patch.get_sql_warehouse_id", return_value="wh-prod"),
            patch(
                "customization.sql_executor_patch.get_mcp_user_identity",
                return_value="carol@noom.com",
            ),
        ):
            patch_sql_executor()

            executor = SQLExecutor.__new__(SQLExecutor)
            executor.warehouse_id = "wh-1"
            executor.client = mock_sp
            SQLExecutor.execute(executor, "SELECT 2")

        assert received["query_tags"] == "mcp_user:carol@noom.com"


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

        mock_client = MagicMock()
        mock_client.secrets.get_secret.side_effect = [
            self._secret_response("my-client-id"),
            self._secret_response("my-client-secret"),
        ]

        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=mock_client,
        ):
            from customization.sql_executor_patch import _fetch_sp_credentials_from_secrets

            client_id, client_secret = _fetch_sp_credentials_from_secrets()

        assert client_id == "my-client-id"
        assert client_secret == "my-client-secret"

    def test_uses_fixed_key_names(self, monkeypatch):
        """Fixed keys sql-sp-client-id and sql-sp-client-secret are always used."""

        mock_client = MagicMock()
        mock_client.secrets.get_secret.side_effect = [
            self._secret_response("id"),
            self._secret_response("secret"),
        ]

        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=mock_client,
        ):
            from customization.sql_executor_patch import _fetch_sp_credentials_from_secrets

            _fetch_sp_credentials_from_secrets()

        calls = mock_client.secrets.get_secret.call_args_list
        assert calls[0] == call(scope="dbrix_mcp_secret", key="sql-sp-client-id")
        assert calls[1] == call(scope="dbrix_mcp_secret", key="sql-sp-client-secret")

    def test_sdk_error_raises_runtime_error(self, monkeypatch):
        """SDK failure fetching a secret raises RuntimeError with context."""

        mock_client = MagicMock()
        mock_client.secrets.get_secret.side_effect = Exception("permission denied")

        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=mock_client,
        ):
            from customization.sql_executor_patch import _fetch_sp_credentials_from_secrets

            with pytest.raises(RuntimeError, match="Failed to fetch secret"):
                _fetch_sp_credentials_from_secrets()

    def test_empty_secret_raises_runtime_error(self, monkeypatch):
        """Empty secret value raises RuntimeError."""

        mock_client = MagicMock()
        empty = MagicMock()
        empty.value = None
        mock_client.secrets.get_secret.return_value = empty

        with patch(
            "databricks_tools_core.auth.get_workspace_client",
            return_value=mock_client,
        ):
            from customization.sql_executor_patch import _fetch_sp_credentials_from_secrets

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

    def test_uses_secrets_by_default(self, monkeypatch):
        """Secrets are used when DATABRICKS_MCP_SQL_CLIENT_ID is not set."""
        monkeypatch.delenv("DATABRICKS_MCP_SQL_CLIENT_ID", raising=False)
        monkeypatch.setenv("DATABRICKS_MCP_SQL_HOST", "https://noom-prod.cloud.databricks.com")

        with (
            patch(
                "customization.sql_executor_patch._fetch_sp_credentials_from_secrets",
                return_value=("secrets-id", "secrets-secret"),
            ) as mock_fetch,
            patch("databricks_tools_core.identity.tag_client", side_effect=lambda c: c),
            patch("databricks.sdk.WorkspaceClient", return_value=MagicMock()),
        ):
            from customization.sql_executor_patch import _build_sql_sp_client

            _build_sql_sp_client()
            mock_fetch.assert_called_once()

    def test_env_vars_override_secrets(self, monkeypatch):
        """Env vars are used as a dev/CI override when CLIENT_ID is set."""
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_ID", "env-id")
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_SECRET", "env-secret")
        monkeypatch.setenv("DATABRICKS_MCP_SQL_HOST", "https://noom-prod.cloud.databricks.com")

        with (
            patch(
                "customization.sql_executor_patch._fetch_sp_credentials_from_secrets",
            ) as mock_fetch,
            patch("databricks_tools_core.identity.tag_client", side_effect=lambda c: c),
            patch("databricks.sdk.WorkspaceClient", return_value=MagicMock()),
        ):
            from customization.sql_executor_patch import _build_sql_sp_client

            _build_sql_sp_client()
            mock_fetch.assert_not_called()

    def test_raises_when_client_id_set_but_secret_missing(self, monkeypatch):
        """RuntimeError when CLIENT_ID is set but CLIENT_SECRET is missing."""
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_ID", "env-id")
        monkeypatch.delenv("DATABRICKS_MCP_SQL_CLIENT_SECRET", raising=False)
        monkeypatch.setenv("DATABRICKS_MCP_SQL_HOST", "https://noom-prod.cloud.databricks.com")

        from customization.sql_executor_patch import _build_sql_sp_client

        with pytest.raises(RuntimeError, match="DATABRICKS_MCP_SQL_CLIENT_SECRET is missing"):
            _build_sql_sp_client()

    def test_raises_when_host_not_configured(self, monkeypatch):
        """RuntimeError when DATABRICKS_MCP_SQL_HOST is not set."""
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_ID", "env-id")
        monkeypatch.setenv("DATABRICKS_MCP_SQL_CLIENT_SECRET", "env-secret")
        monkeypatch.delenv("DATABRICKS_MCP_SQL_HOST", raising=False)

        from customization.sql_executor_patch import _build_sql_sp_client

        with pytest.raises(RuntimeError, match="DATABRICKS_MCP_SQL_HOST is not set"):
            _build_sql_sp_client()
