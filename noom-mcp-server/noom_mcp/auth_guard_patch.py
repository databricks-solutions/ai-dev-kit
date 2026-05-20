"""PAT rejection guard.

Enforces that the calling user authenticates via OAuth (browser flow or
OAuth M2M), never via a Personal Access Token.  Called once at server
startup before any tool is invoked.
"""

import logging

logger = logging.getLogger(__name__)


def check_pat_rejected() -> None:
    """Fail fast if the current Databricks auth resolved to a PAT token.

    Makes a live API call (current_user.me) to force the SDK to resolve
    and cache auth_type on the config, then inspects it.  Only
    "databricks-cli" (browser OAuth) and "oauth-m2m" are accepted.

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
