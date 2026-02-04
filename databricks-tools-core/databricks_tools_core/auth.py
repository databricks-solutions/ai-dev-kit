"""Authentication context for Databricks WorkspaceClient.

Uses Python contextvars to pass authentication through the async call stack
without threading parameters through every function.

Usage in FastAPI:
    # In request handler or middleware
    set_databricks_auth(host, token)
    try:
        # Any code here can call get_workspace_client()
        result = some_databricks_function()
    finally:
        clear_databricks_auth()

Usage in functions:
    from databricks_tools_core.auth import get_workspace_client

    def my_function():
        client = get_workspace_client()  # Uses context auth or env vars
        # ...
"""

import os
from contextvars import ContextVar
from typing import Optional

from databricks.sdk import WorkspaceClient


def _has_oauth_credentials() -> bool:
    """Check if OAuth credentials (SP) are configured in environment."""
    return bool(os.environ.get('DATABRICKS_CLIENT_ID') and os.environ.get('DATABRICKS_CLIENT_SECRET'))

# Context variables for per-request authentication
_host_ctx: ContextVar[Optional[str]] = ContextVar('databricks_host', default=None)
_token_ctx: ContextVar[Optional[str]] = ContextVar('databricks_token', default=None)


def set_databricks_auth(host: Optional[str], token: Optional[str]) -> None:
    """Set Databricks authentication for the current async context.

    Call this at the start of a request to set per-user credentials.
    The credentials will be used by all get_workspace_client() calls
    within this async context.

    Args:
        host: Databricks workspace URL (e.g., https://xxx.cloud.databricks.com)
        token: Databricks access token
    """
    _host_ctx.set(host)
    _token_ctx.set(token)


def clear_databricks_auth() -> None:
    """Clear Databricks authentication from the current context.

    Call this at the end of a request to clean up.
    """
    _host_ctx.set(None)
    _token_ctx.set(None)


def get_workspace_client() -> WorkspaceClient:
    """Get a WorkspaceClient using context auth or environment variables.

    Authentication priority:
    1. If OAuth credentials exist in env, use explicit OAuth M2M auth (Databricks Apps)
       - This explicitly sets auth_type to prevent conflicts with other auth methods
    2. Context variables with explicit token (PAT auth for development)
    3. Fall back to default authentication (env vars, config file)

    Returns:
        Configured WorkspaceClient instance
    """
    host = _host_ctx.get()
    token = _token_ctx.get()

    # In Databricks Apps (OAuth credentials in env), explicitly use OAuth M2M
    # This prevents the SDK from detecting other auth methods like PAT or config file
    if _has_oauth_credentials():
        oauth_host = host or os.environ.get('DATABRICKS_HOST', '')
        client_id = os.environ.get('DATABRICKS_CLIENT_ID', '')
        client_secret = os.environ.get('DATABRICKS_CLIENT_SECRET', '')

        # Explicitly configure OAuth M2M to prevent auth conflicts
        return WorkspaceClient(
            host=oauth_host,
            client_id=client_id,
            client_secret=client_secret,
        )

    # Development mode: use explicit token if provided
    if host and token:
        return WorkspaceClient(host=host, token=token)

    if host:
        return WorkspaceClient(host=host)

    # Fall back to default authentication (env vars, config file)
    return WorkspaceClient()
