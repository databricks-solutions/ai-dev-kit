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

from contextvars import ContextVar
from typing import Optional

from databricks.sdk import WorkspaceClient

# Context variables for per-request authentication
_host_ctx: ContextVar[Optional[str]] = ContextVar("databricks_host", default=None)
_token_ctx: ContextVar[Optional[str]] = ContextVar("databricks_token", default=None)


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
    1. Context variables (set via set_databricks_auth)
    2. Environment variables (DATABRICKS_HOST, DATABRICKS_TOKEN)
    3. Databricks config file (~/.databrickscfg)

    Returns:
        Configured WorkspaceClient instance
    """
    host = _host_ctx.get()
    token = _token_ctx.get()

    if host and token:
        return WorkspaceClient(host=host, token=token)

    # Fall back to default authentication (env vars, config file)
    return WorkspaceClient()
