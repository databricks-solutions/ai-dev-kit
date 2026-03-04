"""Authentication context for Databricks WorkspaceClient.

Uses Python contextvars to pass authentication through the async call stack
without threading parameters through every function.

All clients are tagged with a custom product identifier and auto-detected
project name so that API calls are attributable in ``system.access.audit``.

Usage in FastAPI:
    # In request handler or middleware
    set_databricks_auth(host, token)
    try:
        # Any code here can call get_workspace_client()
        result = some_databricks_function()
    finally:
        clear_databricks_auth()

Cross-workspace (force explicit token over env OAuth):
    set_databricks_auth(target_host, target_token, force_token=True)

Usage in functions:
    from databricks_tools_core.auth import get_workspace_client

    def my_function():
        client = get_workspace_client()  # Uses context auth or env vars
        # ...
"""

import logging
import os
from contextvars import ContextVar
from typing import Optional

from databricks.sdk import WorkspaceClient

from .identity import PRODUCT_NAME, PRODUCT_VERSION, tag_client

logger = logging.getLogger(__name__)

# Cached current username — only fetched once per process
_current_username: Optional[str] = None
_current_username_fetched: bool = False

# Server-level active workspace override (set by manage_workspace tool).
# Module-level globals are appropriate here: the standalone MCP server is
# single-user over stdio, so there is no per-request isolation needed.
_active_profile: Optional[str] = None
_active_host: Optional[str] = None


def set_active_workspace(profile: Optional[str] = None, host: Optional[str] = None) -> None:
    """Set the active workspace for all subsequent tool calls.

    Adds a step 0 to get_workspace_client() that overrides the default SDK
    auth chain. Used by the manage_workspace MCP tool to switch workspaces
    at runtime without restarting the MCP server.

    Args:
        profile: Profile name from ~/.databrickscfg to activate.
        host: Workspace URL to activate (used when no profile is available).
    """
    global _active_profile, _active_host, _current_username, _current_username_fetched
    _active_profile = profile
    _active_host = host
    # Reset cached username — it belongs to the previous workspace
    _current_username = None
    _current_username_fetched = False


def clear_active_workspace() -> None:
    """Reset to the default workspace from environment / config file."""
    set_active_workspace(None, None)


def get_active_workspace() -> dict:
    """Return the current server-level workspace override state.

    Returns:
        Dict with 'profile' and 'host' keys (either or both may be None).
    """
    return {"profile": _active_profile, "host": _active_host}


def _has_oauth_credentials() -> bool:
    """Check if OAuth credentials (SP) are configured in environment."""
    return bool(os.environ.get("DATABRICKS_CLIENT_ID") and os.environ.get("DATABRICKS_CLIENT_SECRET"))


# Context variables for per-request authentication
_host_ctx: ContextVar[Optional[str]] = ContextVar("databricks_host", default=None)
_token_ctx: ContextVar[Optional[str]] = ContextVar("databricks_token", default=None)
_force_token_ctx: ContextVar[bool] = ContextVar("force_token", default=False)


def set_databricks_auth(
    host: Optional[str],
    token: Optional[str],
    *,
    force_token: bool = False,
) -> None:
    """Set Databricks authentication for the current async context.

    Call this at the start of a request to set per-user credentials.
    The credentials will be used by all get_workspace_client() calls
    within this async context.

    Args:
        host: Databricks workspace URL (e.g., https://xxx.cloud.databricks.com)
        token: Databricks access token
        force_token: When True, the explicit token takes priority over
            environment OAuth credentials. Use for cross-workspace requests
            where the token belongs to a different workspace's SP.
    """
    _host_ctx.set(host)
    _token_ctx.set(token)
    _force_token_ctx.set(force_token)


def clear_databricks_auth() -> None:
    """Clear Databricks authentication from the current context.

    Call this at the end of a request to clean up.
    """
    _host_ctx.set(None)
    _token_ctx.set(None)
    _force_token_ctx.set(False)


def get_workspace_client() -> WorkspaceClient:
    """Get a WorkspaceClient using context auth or environment variables.

    Authentication priority:
    0. Server-level active workspace override (set by manage_workspace tool)
    1. If force_token is set (cross-workspace), use the explicit token from context
    2. If OAuth credentials exist in env, use explicit OAuth M2M auth (Databricks Apps)
       - This explicitly sets auth_type to prevent conflicts with other auth methods
    3. Context variables with explicit token (PAT auth for development)
    4. Fall back to default authentication (env vars, config file)

    Returns:
        Configured WorkspaceClient instance
    """
    host = _host_ctx.get()
    token = _token_ctx.get()
    force = _force_token_ctx.get()

    # Common kwargs for product identification in user-agent
    product_kwargs = dict(product=PRODUCT_NAME, product_version=PRODUCT_VERSION)

    # Server-level workspace override set by the manage_workspace MCP tool.
    # Profile takes precedence over host when both are set.
    # Skipped when force_token is active (Builder App cross-workspace path wins)
    # or when OAuth M2M credentials are present (Databricks Apps runtime).
    if not force and not _has_oauth_credentials():
        if _active_profile:
            return tag_client(WorkspaceClient(profile=_active_profile, **product_kwargs))
        if _active_host:
            return tag_client(WorkspaceClient(host=_active_host, **product_kwargs))

    # Cross-workspace: explicit token overrides env OAuth so tool operations
    # target the caller-specified workspace instead of the app's own workspace
    if force and host and token:
        return tag_client(WorkspaceClient(host=host, token=token, **product_kwargs))

    # In Databricks Apps (OAuth credentials in env), explicitly use OAuth M2M
    # This prevents the SDK from detecting other auth methods like PAT or config file
    if _has_oauth_credentials():
        oauth_host = host or os.environ.get("DATABRICKS_HOST", "")
        client_id = os.environ.get("DATABRICKS_CLIENT_ID", "")
        client_secret = os.environ.get("DATABRICKS_CLIENT_SECRET", "")

        # Explicitly configure OAuth M2M to prevent auth conflicts
        return tag_client(
            WorkspaceClient(
                host=oauth_host,
                client_id=client_id,
                client_secret=client_secret,
                **product_kwargs,
            )
        )

    # Development mode: use explicit token if provided
    if host and token:
        return tag_client(WorkspaceClient(host=host, token=token, **product_kwargs))

    if host:
        return tag_client(WorkspaceClient(host=host, **product_kwargs))

    # Fall back to default authentication (env vars, config file)
    return tag_client(WorkspaceClient(**product_kwargs))


def get_current_username() -> Optional[str]:
    """Get the current authenticated user's username (email).

    Cached after first successful call — the authenticated user doesn't
    change mid-session. Returns None if the API call fails, allowing
    callers to degrade gracefully (e.g., skip user-based filtering).

    Returns:
        Username string (typically an email), or None on failure.
    """
    global _current_username, _current_username_fetched
    if _current_username_fetched:
        return _current_username
    try:
        w = get_workspace_client()
        _current_username = w.current_user.me().user_name
        _current_username_fetched = True
        return _current_username
    except Exception as e:
        logger.debug(f"Failed to fetch current username: {e}")
        _current_username_fetched = True
        return None
