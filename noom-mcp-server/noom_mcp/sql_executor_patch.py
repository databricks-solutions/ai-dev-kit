"""SQLExecutor patches: SP client override and user identity tagging.

Two class-level patches applied to SQLExecutor at startup:

1. SP client override (patch_sql_executor → __init__ patch)
   Every SQL query is executed using a pre-configured Service Principal
   fetched from the dbrix_mcp_secret Databricks secret scope, regardless
   of which credentials the calling user has configured.

2. User identity tagging (patch_sql_executor → execute patch)
   The calling user's email (or "sp:<client_id>" for M2M callers) is
   appended to query_tags as "mcp_user:<identity>" on every SQL statement.
   This surfaces in system.query.history for audit and cost attribution.

Patching strategy
-----------------
Both patches target SQLExecutor at the class level.  This is the single
chokepoint for all SQL execution: execute_sql calls SQLExecutor directly,
and execute_sql_multi delegates to SQLExecutor via SQLParallelExecutor.
The tool functions look up SQLExecutor at call time (not import time), so
patching the class before the first invocation is sufficient.
"""

import logging
import os
from functools import wraps
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Process-lifetime cache — one SP client per server process.
_sql_sp_client = None

# Fixed secret scope and key names — not user-configurable.
_SECRET_SCOPE = "dbrix_mcp_secret"
_SECRET_KEY_CLIENT_ID = "sql-sp-client-id"
_SECRET_KEY_CLIENT_SECRET = "sql-sp-client-secret"


# ---------------------------------------------------------------------------
# SP credential helpers
# ---------------------------------------------------------------------------


def _fetch_sp_credentials_from_secrets() -> tuple[str, str]:
    """Fetch SQL SP credentials from the Databricks secret scope.

    Uses the fixed scope ``dbrix_mcp_secret`` and fetches two fixed keys:
      - sql-sp-client-id
      - sql-sp-client-secret

    Uses the calling user's own credentials to fetch the secrets — they need
    READ permission on the scope, but never see the raw secret values (the
    SDK decodes them and they stay in process memory only).

    Returns:
        Tuple of (client_id, client_secret).

    Raises:
        RuntimeError: If the scope or keys are missing or inaccessible.
    """
    import base64
    from databricks_tools_core.auth import get_workspace_client

    scope = _SECRET_SCOPE
    key_client_id = _SECRET_KEY_CLIENT_ID
    key_client_secret = _SECRET_KEY_CLIENT_SECRET

    client = get_workspace_client()

    def _get(key: str) -> str:
        try:
            response = client.secrets.get_secret(scope=scope, key=key)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch secret '{key}' from scope '{scope}': {exc}\n"
                f"Ensure the scope exists and you have READ permission on it."
            ) from exc
        if not response.value:
            raise RuntimeError(f"Secret '{key}' in scope '{scope}' is empty.")
        # Databricks returns secret values base64-encoded
        return base64.b64decode(response.value).decode("utf-8")

    logger.info("Fetching SQL SP credentials from Databricks secret scope %r", scope)
    client_id = _get(key_client_id)
    client_secret = _get(key_client_secret)
    logger.info("SQL SP credentials fetched from Databricks Secrets successfully")
    return client_id, client_secret


def _build_sql_sp_client():
    """Construct the SQL Service Principal WorkspaceClient.

    Credential resolution order:
    1. Databricks Secrets (default) — fetches from the fixed scope
       ``dbrix_mcp_secret``.  Users need READ on the scope but never see
       the raw values.
    2. Env vars (dev / CI override) — if DATABRICKS_MCP_SQL_CLIENT_ID is
       set, use it along with DATABRICKS_MCP_SQL_CLIENT_SECRET directly.
       See DEVELOPMENT.md.

    DATABRICKS_MCP_SQL_HOST is always required.

    Returns:
        Tagged WorkspaceClient configured for OAuth M2M with the SQL SP.

    Raises:
        RuntimeError: If credentials or host are not configured.
    """
    from databricks.sdk import WorkspaceClient
    from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION, tag_client

    if os.environ.get("DATABRICKS_MCP_SQL_CLIENT_ID"):
        # Dev / CI override: credentials supplied directly as env vars.
        # See DEVELOPMENT.md for when to use this.
        client_id = os.environ["DATABRICKS_MCP_SQL_CLIENT_ID"]
        client_secret = os.environ.get("DATABRICKS_MCP_SQL_CLIENT_SECRET", "")
        if not client_secret:
            raise RuntimeError(
                "DATABRICKS_MCP_SQL_CLIENT_ID is set but "
                "DATABRICKS_MCP_SQL_CLIENT_SECRET is missing."
            )
    else:
        client_id, client_secret = _fetch_sp_credentials_from_secrets()

    host = os.environ.get("DATABRICKS_MCP_SQL_HOST")
    if not host:
        raise RuntimeError(
            "DATABRICKS_MCP_SQL_HOST is not set.\n"
            "Set it to the prod workspace URL to ensure SQL always runs "
            "against prod, regardless of which workspace the user is logged into.\n"
            "Example: DATABRICKS_MCP_SQL_HOST=https://noom-prod.cloud.databricks.com"
        )

    return tag_client(
        WorkspaceClient(
            host=host,
            client_id=client_id,
            client_secret=client_secret,
            auth_type="oauth-m2m",
            product=PRODUCT_NAME,
            product_version=PRODUCT_VERSION,
        )
    )


def get_sql_sp_client():
    """Return the cached SQL SP client, initialising it on first call.

    Returns:
        WorkspaceClient configured with the SQL Service Principal.
    """
    global _sql_sp_client
    if _sql_sp_client is None:
        _sql_sp_client = _build_sql_sp_client()
    return _sql_sp_client


# ---------------------------------------------------------------------------
# Warehouse ID
# ---------------------------------------------------------------------------


def get_sql_warehouse_id() -> str:
    """Return the configured SQL warehouse ID.

    Reads DATABRICKS_WAREHOUSE_ID from the environment.  This overrides
    whatever warehouse_id the AI client passes to execute_sql, ensuring all
    SQL always runs on the designated prod warehouse.

    Raises:
        RuntimeError: If DATABRICKS_WAREHOUSE_ID is not set.
    """
    wh = os.environ.get("DATABRICKS_WAREHOUSE_ID")
    if not wh:
        raise RuntimeError(
            "DATABRICKS_WAREHOUSE_ID is not set.\n"
            "Set it to the prod SQL warehouse ID in your .env file."
        )
    return wh


# ---------------------------------------------------------------------------
# User identity
# ---------------------------------------------------------------------------


def get_mcp_user_identity() -> str:
    """Return the calling user's identity string for SQL query tagging.

    Resolution order:
    - OAuth browser / CLI users  → their email address (from current_user.me())
    - OAuth M2M service accounts → "sp:<DATABRICKS_CLIENT_ID>"
    - Unresolvable                → "unknown"

    Must be called while the user's own credentials are still in context
    (i.e. before switching to the SQL SP client inside an executor).

    Returns:
        Identity string, never None.
    """
    from databricks_tools_core.auth import get_current_username

    username = get_current_username()
    if username:
        return username

    client_id = os.environ.get("DATABRICKS_CLIENT_ID")
    if client_id:
        return f"sp:{client_id}"

    return "unknown"


# ---------------------------------------------------------------------------
# SQLExecutor patches
# ---------------------------------------------------------------------------


def patch_sql_executor() -> None:
    """Patch SQLExecutor to enforce SP client and inject user identity tags.

    __init__ patch
        Ignores both the ``warehouse_id`` and ``client`` arguments passed by
        the caller.  Always substitutes the governed warehouse ID (from
        DATABRICKS_WAREHOUSE_ID) and the governed SP client.  This ensures
        the AI cannot direct SQL to an arbitrary warehouse.

    execute patch
        Appends "mcp_user:<identity>" to query_tags on every statement.
        The user's identity is resolved *before* the SP client is used,
        so it still reflects the calling user's credentials.
    """
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor

    _original_init = SQLExecutor.__init__
    _original_execute = SQLExecutor.execute

    @wraps(_original_init)
    def _patched_init(self, warehouse_id: str, client=None) -> None:
        _original_init(self, get_sql_warehouse_id(), client=get_sql_sp_client())

    @wraps(_original_execute)
    def _patched_execute(
        self,
        sql_query: str,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
        row_limit: Optional[int] = None,
        timeout: int = 180,
        query_tags: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        user_tag = f"mcp_user:{get_mcp_user_identity()}"
        effective_tags = f"{query_tags},{user_tag}" if query_tags else user_tag
        return _original_execute(
            self,
            sql_query,
            catalog=catalog,
            schema=schema,
            row_limit=row_limit,
            timeout=timeout,
            query_tags=effective_tags,
        )

    SQLExecutor.__init__ = _patched_init
    SQLExecutor.execute = _patched_execute
    logger.info(
        "SQLExecutor patched: warehouse override (%s), SP client override, "
        "user identity tagging active",
        get_sql_warehouse_id(),
    )
