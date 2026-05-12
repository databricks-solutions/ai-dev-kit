"""User tools - Get information about the current Databricks user."""

from typing import Dict, Any

from databricks_tools_core.auth import get_current_username

from ..server import mcp


@mcp.tool(timeout=30)
def get_current_user() -> Dict[str, Any]:
    """Get current Databricks user identity.

    Returns: {username (email), home_path (/Workspace/Users/user@example.com/)}."""
    username = get_current_username()
    home_path = f"/Workspace/Users/{username}/" if username else None
    return {
        "username": username,
        "home_path": home_path,
    }
