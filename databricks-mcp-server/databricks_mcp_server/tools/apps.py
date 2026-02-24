"""App tools - Manage Databricks Apps lifecycle."""

from typing import Any, Dict, List, Optional

from databricks_tools_core.apps.apps import (
    create_app as _create_app,
    get_app as _get_app,
    list_apps as _list_apps,
    deploy_app as _deploy_app,
    delete_app as _delete_app,
    get_app_logs as _get_app_logs,
)
from databricks_tools_core.identity import with_description_footer

from ..manifest import register_deleter
from ..server import mcp


def _delete_app_resource(resource_id: str) -> None:
    _delete_app(name=resource_id)


register_deleter("app", _delete_app_resource)


@mcp.tool
def create_app(
    name: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a new Databricks App.

    Args:
        name: App name (must be unique within the workspace).
        description: Optional human-readable description.

    Returns:
        Dictionary with app details including name, url, and status.
    """
    result = _create_app(name=name, description=with_description_footer(description))

    # Track resource on successful create
    try:
        if result.get("name"):
            from ..manifest import track_resource

            track_resource(
                resource_type="app",
                name=result["name"],
                resource_id=result["name"],
            )
    except Exception:
        pass  # best-effort tracking

    return result


@mcp.tool
def get_app(name: str) -> Dict[str, Any]:
    """
    Get details for a Databricks App.

    Args:
        name: App name.

    Returns:
        Dict with app details: name, url, status, active deployment.
    """
    return _get_app(name=name)


@mcp.tool
def list_apps(
    name_contains: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    List Databricks Apps in the workspace.

    Returns a limited set of apps (default 20). Use name_contains to
    search for a specific app by name substring.

    Args:
        name_contains: Optional substring to filter app names
            (case-insensitive).
        limit: Max apps to return (default 20, 0 for all).

    Returns:
        List of dictionaries with app details.
    """
    return _list_apps(name_contains=name_contains, limit=limit)


@mcp.tool
def deploy_app(
    app_name: str,
    source_code_path: str,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deploy a Databricks App from a workspace source path.

    Args:
        app_name: Name of the app to deploy.
        source_code_path: Workspace path to the app source code
            (e.g., /Workspace/Users/user@example.com/my_app).
        mode: Optional deployment mode (e.g., "snapshot").

    Returns:
        Dictionary with deployment details including deployment_id and status.
    """
    return _deploy_app(
        app_name=app_name,
        source_code_path=source_code_path,
        mode=mode,
    )


@mcp.tool
def delete_app(name: str) -> Dict[str, str]:
    """
    Delete a Databricks App.

    Args:
        name: App name to delete.

    Returns:
        Dictionary confirming deletion.
    """
    result = _delete_app(name=name)

    # Remove from tracked resources
    try:
        from ..manifest import remove_resource

        remove_resource(resource_type="app", resource_id=name)
    except Exception:
        pass  # best-effort tracking

    return result


@mcp.tool
def get_app_logs(
    app_name: str,
    deployment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get logs for a Databricks App deployment.

    If deployment_id is not provided, gets logs for the active deployment.

    Args:
        app_name: App name.
        deployment_id: Optional specific deployment ID. If None, uses the
            active deployment.

    Returns:
        Dictionary with deployment logs.
    """
    return _get_app_logs(app_name=app_name, deployment_id=deployment_id)
