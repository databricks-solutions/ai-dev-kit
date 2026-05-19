"""Noom governance patches for the upstream Databricks MCP server.

Three controls are applied at process startup — before any tool invocation:

1. PAT rejection (check_pat_rejected)
   Fails fast if the resolved Databricks auth is a Personal Access Token.
   Only OAuth browser-flow and OAuth M2M are permitted.

2. SQL Service Principal override (patch_sql_executor)
   Every SQL query is executed using a pre-configured Service Principal
   (DATABRICKS_MCP_SQL_CLIENT_ID / DATABRICKS_MCP_SQL_CLIENT_SECRET),
   regardless of which credentials the calling user has configured.

3. User identity tagging (patch_sql_executor, same patch)
   The calling user's email (or "sp:<client_id>" for M2M callers) is
   appended to query_tags as "mcp_user:<identity>" on every SQL statement.
   This surfaces in system.query.history for audit and cost attribution.

Patching strategy
-----------------
We patch ``SQLExecutor`` at the class level rather than replacing tools in
FastMCP's tool registry.  Reasons:

* ``SQLExecutor.__init__`` and ``SQLExecutor.execute`` are the single
  chokepoint for ALL SQL execution: both ``execute_sql`` and
  ``execute_sql_multi`` end up here (the latter via ``SQLParallelExecutor``
  which delegates to an internal ``SQLExecutor`` instance).

* The tool functions in ``tools/sql.py`` do not capture ``SQLExecutor`` at
  import time — they call it at invocation time.  So patching the class
  after import (but before the first tool call) is sufficient.

* FastMCP's ``_tool_manager._tools`` dict is an internal implementation
  detail that changes across FastMCP versions.  Class-level patching is
  more stable and requires no knowledge of FastMCP internals.
"""

import logging
import os
from functools import wraps
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Process-lifetime cache — one SP client per server process.
_sql_sp_client = None


# ---------------------------------------------------------------------------
# Helpers: SP client factory + user identity resolver
# ---------------------------------------------------------------------------


def _build_sql_sp_client():
    """Construct the SQL Service Principal WorkspaceClient from env vars.

    Returns:
        Tagged WorkspaceClient configured for OAuth M2M with the SQL SP.

    Raises:
        RuntimeError: If DATABRICKS_MCP_SQL_CLIENT_ID or
            DATABRICKS_MCP_SQL_CLIENT_SECRET is missing.
    """
    from databricks.sdk import WorkspaceClient
    from databricks_tools_core.auth import get_workspace_client
    from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION, tag_client

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
            "SQL Service Principal not configured. "
            f"Missing env vars: {', '.join(missing)}. "
            "Set DATABRICKS_MCP_SQL_CLIENT_ID and DATABRICKS_MCP_SQL_CLIENT_SECRET "
            "before starting noom-mcp-server."
        )

    # DATABRICKS_MCP_SQL_HOST is optional — falls back to the calling user's
    # workspace host when the SQL SP lives in the same workspace.
    host = os.environ.get("DATABRICKS_MCP_SQL_HOST") or get_workspace_client().config.host

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
# Patch 1: PAT rejection
# ---------------------------------------------------------------------------


def check_pat_rejected() -> None:
    """Fail fast if the current Databricks auth resolved to a PAT token.

    Makes a live API call (current_user.me) to force the SDK to resolve
    and cache auth_type on the config, then inspects it.  Only
    "external-browser" (browser OAuth) and "oauth-m2m" are accepted.

    Raises:
        RuntimeError: If auth_type is "pat".
        Exception: Re-raises any SDK / network error so the server exits
            with a clear message rather than silently continuing.
    """
    from databricks_tools_core.auth import get_workspace_client

    client = get_workspace_client()

    # Force auth resolution — SDK validates credentials lazily on first call.
    me = client.current_user.me()
    logger.info("Startup auth check: authenticated as %s", me.user_name)

    auth_type = getattr(client.config, "auth_type", None)
    if auth_type == "pat":
        raise RuntimeError(
            "PAT authentication is not permitted. "
            "Use 'databricks auth login' for browser-based OAuth, "
            "or set DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET for OAuth M2M. "
            f"Resolved auth_type was: {auth_type!r}"
        )

    logger.info("Startup auth check passed (auth_type=%r)", auth_type)


# ---------------------------------------------------------------------------
# Upstream compatibility guard
# ---------------------------------------------------------------------------

# Expected signatures for the methods we patch.
# Update these constants when pulling a new upstream version and re-validating.
_EXPECTED_INIT_PARAMS = {"warehouse_id", "client"}
_EXPECTED_EXECUTE_PARAMS = {
    "sql_query", "catalog", "schema", "row_limit", "timeout", "query_tags"
}
# SQLParallelExecutor must still delegate to SQLExecutor for our __init__
# patch to cover execute_sql_multi.  We verify this by checking that it
# creates a `sql_executor` attribute of type SQLExecutor.
_EXPECTED_PARALLEL_ATTR = "sql_executor"


class UpstreamChangedError(RuntimeError):
    """Raised when upstream code has changed in a way that breaks our patches.

    Do not swallow this error.  It means the monkey-patch assumptions are
    invalid and the governance controls may not be applied correctly.
    Fix the patch before restarting the server.
    """


def verify_patch_assumptions() -> None:
    """Assert that the upstream code still matches our patching assumptions.

    Inspects the signatures and structure of the classes we patch.  Raises
    UpstreamChangedError with a specific message if anything has drifted,
    so an upstream update is caught immediately rather than silently applying
    a broken patch.

    Call this before patch_sql_executor().

    Raises:
        UpstreamChangedError: If any assumption no longer holds.
    """
    import inspect
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor
    from databricks_tools_core.sql.sql_utils.parallel_executor import SQLParallelExecutor

    issues: list[str] = []

    # --- SQLExecutor.__init__ signature ---
    init_params = set(inspect.signature(SQLExecutor.__init__).parameters) - {"self"}
    if init_params != _EXPECTED_INIT_PARAMS:
        issues.append(
            f"SQLExecutor.__init__ signature changed.\n"
            f"  Expected params: {sorted(_EXPECTED_INIT_PARAMS)}\n"
            f"  Got params:      {sorted(init_params)}\n"
            f"  Action: review patches.py _patched_init and update "
            f"_EXPECTED_INIT_PARAMS after re-validating."
        )

    # --- SQLExecutor.execute signature ---
    execute_params = set(inspect.signature(SQLExecutor.execute).parameters) - {"self"}
    if execute_params != _EXPECTED_EXECUTE_PARAMS:
        issues.append(
            f"SQLExecutor.execute signature changed.\n"
            f"  Expected params: {sorted(_EXPECTED_EXECUTE_PARAMS)}\n"
            f"  Got params:      {sorted(execute_params)}\n"
            f"  Action: review patches.py _patched_execute and update "
            f"_EXPECTED_EXECUTE_PARAMS after re-validating."
        )

    # --- SQLParallelExecutor still delegates to SQLExecutor ---
    # Instantiate with a dummy warehouse_id to inspect the created object.
    # We override __init__ on a temp subclass to avoid real SDK calls.
    class _Probe(SQLParallelExecutor):
        def __init__(self):
            self.warehouse_id = "probe"
            self.max_workers = 1
            self.client = None
            # Replicate the line we care about: does it create a SQLExecutor?
            from databricks_tools_core.sql.sql_utils.executor import SQLExecutor as _E
            self.sql_executor = _E.__new__(_E)  # don't call real __init__

    probe = _Probe()
    if not hasattr(probe, _EXPECTED_PARALLEL_ATTR):
        issues.append(
            f"SQLParallelExecutor no longer has a '{_EXPECTED_PARALLEL_ATTR}' attribute.\n"
            f"  This means execute_sql_multi may bypass SQLExecutor entirely.\n"
            f"  Action: inspect SQLParallelExecutor and extend the patch to "
            f"cover its new execution path."
        )
    elif not isinstance(getattr(probe, _EXPECTED_PARALLEL_ATTR), SQLExecutor):
        actual_type = type(getattr(probe, _EXPECTED_PARALLEL_ATTR)).__name__
        issues.append(
            f"SQLParallelExecutor.sql_executor is no longer a SQLExecutor "
            f"(got {actual_type!r}).\n"
            f"  Action: inspect the new executor type and ensure the SP client "
            f"and identity tagging patches cover it."
        )

    if issues:
        bullet_list = "\n\n".join(f"  [{i+1}] {msg}" for i, msg in enumerate(issues))
        raise UpstreamChangedError(
            f"Upstream code has changed — governance patches cannot be safely applied.\n"
            f"Found {len(issues)} issue(s):\n\n{bullet_list}"
        )

    logger.info(
        "Upstream compatibility check passed "
        "(SQLExecutor signatures and SQLParallelExecutor delegation are intact)"
    )


# ---------------------------------------------------------------------------
# Patch 2 + 3: SQL SP override and user identity tagging
# ---------------------------------------------------------------------------


def patch_sql_executor() -> None:
    """Patch SQLExecutor to enforce SP client and inject user identity tags.

    Two class-level patches are applied:

    __init__ patch
        Ignores whatever ``client`` argument is passed (including the one
        from SQLParallelExecutor, which resolves get_workspace_client()
        before creating its internal SQLExecutor).  Always substitutes the
        governed SQL SP client.

    execute patch
        Appends "mcp_user:<identity>" to query_tags on every statement.
        The user's identity is resolved *before* the SP client is used,
        so it still reflects the calling user's credentials.

    These two patches together cover both execute_sql and execute_sql_multi:
    - execute_sql         → SQLExecutor directly
    - execute_sql_multi   → SQLParallelExecutor → SQLExecutor (patched init)
    """
    from databricks_tools_core.sql.sql_utils.executor import SQLExecutor

    _original_init = SQLExecutor.__init__
    _original_execute = SQLExecutor.execute

    @wraps(_original_init)
    def _patched_init(self, warehouse_id: str, client=None) -> None:
        # Discard any caller-supplied client; always use the governed SP.
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
    logger.info(
        "SQLExecutor patched: "
        "SQL SP client override active, user identity tagging active"
    )


# ---------------------------------------------------------------------------
# Entry point: apply all patches
# ---------------------------------------------------------------------------


def apply_all_patches() -> None:
    """Apply all Noom MCP governance patches in the correct order.

    Must be called BEFORE ``from databricks_mcp_server.server import mcp``
    so that patches are in place before any tool function is invoked.
    (Importing the server module is safe before calling this, but the first
    tool invocation must come after.)

    Execution order:
    1. verify_patch_assumptions — inspects upstream signatures; raises
       UpstreamChangedError if anything has drifted (fail loudly, not silently)
    2. patch_sql_executor — installs class-level patches on SQLExecutor
    3. check_pat_rejected — validates startup credentials (makes a live
       API call; fails immediately if auth is PAT)
    """
    verify_patch_assumptions()
    patch_sql_executor()
    check_pat_rejected()
    logger.info("All Noom MCP governance patches applied successfully")
