"""User tools - Get information about the current Databricks user."""

from typing import Dict, Any

from databricks_tools_core.auth import get_current_username

from ..server import mcp


@mcp.tool
def get_current_user() -> Dict[str, Any]:
    """
    Get the current authenticated Databricks user's identity.

    Returns the username (email) and the user's home path in the workspace.
    Useful for determining where to create files, notebooks, and other
    user-specific resources.

    Returns:
        Dictionary with:
        - username: The user's email address (or None if unavailable)
        - home_path: The user's workspace home directory (e.g. /Workspace/Users/user@example.com/)
    """
    username = get_current_username()
    home_path = f"/Workspace/Users/{username}/" if username else None
    return {
        "username": username,
        "home_path": home_path,
    }
