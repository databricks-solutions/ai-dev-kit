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
        RuntimeError: If auth_type is "pat", or if the API call fails
            (wraps transport/auth errors with a clear startup message).
    """
    from databricks_tools_core.auth import get_workspace_client

    client = get_workspace_client()

    # Force auth resolution — SDK validates credentials lazily on first call.
    try:
        me = client.current_user.me()
    except Exception as exc:
        raise RuntimeError(
            f"Startup auth check failed — could not reach Databricks or credentials are invalid.\n"
            f"  Host: {getattr(client.config, 'host', '<unset>')}\n"
            f"  Error: {exc}\n"
            "Ensure DATABRICKS_HOST is set and your credentials are valid "
            "('databricks auth login' or DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET)."
        ) from exc

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
