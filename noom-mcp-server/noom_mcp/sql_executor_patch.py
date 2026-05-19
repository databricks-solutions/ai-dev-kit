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


# ---------------------------------------------------------------------------
# SP credential helpers
# ---------------------------------------------------------------------------


def _fetch_sp_credentials_from_secrets() -> tuple[str, str]:
    """Fetch SQL SP credentials from the Databricks secret scope.

    Reads the scope name from DATABRICKS_MCP_SECRET_SCOPE and fetches
    two fixed-name secrets:
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

    scope = os.environ["DATABRICKS_MCP_SECRET_SCOPE"]
    key_client_id = "sql-sp-client-id"
    key_client_secret = "sql-sp-client-secret"

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
    1. Databricks Secrets (recommended) — set DATABRICKS_MCP_SECRET_SCOPE
       to the secret scope containing the SP credentials.  Users need READ
       on the scope but never see the values.
    2. Environment variables (dev / CI fallback) — set
       DATABRICKS_MCP_SQL_CLIENT_ID and DATABRICKS_MCP_SQL_CLIENT_SECRET.

    DATABRICKS_MCP_SQL_HOST is always required — defaults to prod in
    .env.example to prevent accidental SQL execution against dev/test.

    Returns:
        Tagged WorkspaceClient configured for OAuth M2M with the SQL SP.

    Raises:
        RuntimeError: If credentials or host are not configured.
    """
    from databricks.sdk import WorkspaceClient
    from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION, tag_client

    if os.environ.get("DATABRICKS_MCP_SECRET_SCOPE"):
        client_id, client_secret = _fetch_sp_credentials_from_secrets()
    else:
        client_id = os.environ.get("DATABRICKS_MCP_SQL_CLIENT_ID")
        client_secret = os.environ.get("DATABRICKS_MCP_SQL_CLIENT_SECRET")
        missing = [
            name
            for name, val in [
                ("DATABRICKS_MCP_SQL_CLIENT_ID", client_id),
                ("DATABRICKS_MCP_SQL_CLIENT_SECRET", client_secret),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                "SQL Service Principal credentials not configured.\n"
                "Option 1 (recommended): set DATABRICKS_MCP_SECRET_SCOPE to the "
                "Databricks secret scope that contains the SP credentials.\n"
                "Option 2 (dev/CI): set DATABRICKS_MCP_SQL_CLIENT_ID and "
                f"DATABRICKS_MCP_SQL_CLIENT_SECRET directly.\n"
                f"Missing env vars for option 2: {', '.join(missing)}"
            )

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
        Ignores whatever ``client`` argument is passed (including the one
        from SQLParallelExecutor, which resolves get_workspace_client()
        before creating its internal SQLExecutor).  Always substitutes the
        governed SQL SP client.

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
        _original_init(self, warehouse_id, client=get_sql_sp_client())

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
    logger.info("SQLExecutor patched: SP client override + user identity tagging active")
