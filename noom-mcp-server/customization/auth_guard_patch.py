"""Startup OAuth authentication.

Authenticates the calling user via OAuth before the MCP server starts.
Uses the Databricks SDK's external-browser flow, which:

- Checks a local token cache first — silent start if a valid token exists
- Auto-refreshes expired tokens silently using the stored refresh token
- Opens a browser tab only when no usable token is cached (first run, or
  after a long period of inactivity where the refresh token has also expired)

DATABRICKS_TOKEN (PAT) in the environment is completely ignored — the
explicit auth_type bypasses all env-var credential resolution.

No Databricks CLI installation is required.
"""

import logging
import os

logger = logging.getLogger(__name__)


def ensure_oauth_authenticated() -> None:
    """Authenticate the calling user via OAuth, opening a browser if needed.

    Execution:
    1. Creates a WorkspaceClient with auth_type="external-browser".
    2. The SDK checks its local token cache:
       - Cache hit + token valid or refreshable → silent, no browser
       - Cache miss or refresh token expired → opens browser tab, logs the
         URL to stderr (visible in the Cursor MCP output panel), waits for
         the user to complete the OAuth flow
    3. Calls current_user.me() to confirm identity and log it.

    On headless systems where the browser cannot be opened, the exception
    is caught and re-raised as a RuntimeError with manual instructions.

    Raises:
        RuntimeError: If OAuth authentication fails (browser unavailable,
            network unreachable, or user denies consent).
    """
    from databricks.sdk import WorkspaceClient

    host = os.environ.get("DATABRICKS_HOST", "")

    try:
        # explicit auth_type bypasses DATABRICKS_TOKEN and all other env-var
        # credentials — only the SDK's own OAuth token cache is consulted
        client = WorkspaceClient(host=host, auth_type="external-browser")
        me = client.current_user.me()
    except Exception as exc:
        raise RuntimeError(
            "Databricks OAuth authentication failed.\n"
            "If a browser could not open, run this in a terminal instead:\n"
            f"  databricks auth login --host {host}\n"
            "Then restart the MCP server.\n"
            f"  (Original error: {exc})"
        ) from exc

    logger.info("OAuth authenticated as %s", me.user_name)
