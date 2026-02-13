"""
Databricks Apps - App Lifecycle Management

Functions for managing Databricks Apps lifecycle using the Databricks SDK.
"""

from typing import Any, Dict, List, Optional

from databricks.sdk.service.apps import AppDeployment

from ..auth import get_workspace_client


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
    w = get_workspace_client()
    app = w.apps.create(name=name, description=description)
    return _app_to_dict(app)


def get_app(name: str) -> Dict[str, Any]:
    """
    Get details for a Databricks App.

    Args:
        name: App name.

    Returns:
        Dictionary with app details including name, url, status, and active deployment.
    """
    w = get_workspace_client()
    app = w.apps.get(name=name)
    return _app_to_dict(app)


def list_apps(
    name_contains: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    List Databricks Apps in the workspace.

    Returns a limited number of apps, optionally filtered by name substring.
    Apps are returned in API order (most recently created first).

    Args:
        name_contains: Optional substring filter applied to app names
            (case-insensitive). Only apps whose name contains this string
            are returned.
        limit: Maximum number of apps to return (default: 20).
            Use 0 for no limit (returns all apps).

    Returns:
        List of dictionaries with app details.
    """
    w = get_workspace_client()
    results: List[Dict[str, Any]] = []

    for app in w.apps.list():
        if name_contains and name_contains.lower() not in (getattr(app, "name", "") or "").lower():
            continue
        results.append(_app_to_dict(app))
        if limit and len(results) >= limit:
            break

    return results


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
    w = get_workspace_client()
    deployment = w.apps.deploy(
        app_name=app_name,
        app_deployment=AppDeployment(
            source_code_path=source_code_path,
            mode=mode,
        ),
    )
    return _deployment_to_dict(deployment)


def delete_app(name: str) -> Dict[str, str]:
    """
    Delete a Databricks App.

    Args:
        name: App name to delete.

    Returns:
        Dictionary confirming deletion.
    """
    w = get_workspace_client()
    w.apps.delete(name=name)
    return {"name": name, "status": "deleted"}


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
    w = get_workspace_client()

    # If no deployment_id, get the active one
    if not deployment_id:
        app = w.apps.get(name=app_name)
        if app.active_deployment:
            deployment_id = app.active_deployment.deployment_id
        else:
            return {"app_name": app_name, "error": "No active deployment found"}

    # Use the REST client to fetch logs since SDK may not have direct method
    from ..client import get_api_client

    client = get_api_client()
    response = client.do(
        "GET",
        f"/api/2.0/apps/{app_name}/deployments/{deployment_id}/logs",
    )
    return {
        "app_name": app_name,
        "deployment_id": deployment_id,
        "logs": response.get("logs", ""),
    }


def _app_to_dict(app: Any) -> Dict[str, Any]:
    """Convert an App SDK object to a dictionary."""
    result = {
        "name": getattr(app, "name", None),
        "description": getattr(app, "description", None),
        "url": getattr(app, "url", None),
        "status": None,
        "create_time": str(getattr(app, "create_time", None)),
        "update_time": str(getattr(app, "update_time", None)),
    }

    # Extract status from compute_status or status
    compute_status = getattr(app, "compute_status", None)
    if compute_status:
        result["status"] = getattr(compute_status, "state", None)
        if result["status"]:
            result["status"] = str(result["status"])

    # Extract active deployment info
    active_deployment = getattr(app, "active_deployment", None)
    if active_deployment:
        result["active_deployment"] = _deployment_to_dict(active_deployment)

    return result


def _deployment_to_dict(deployment: Any) -> Dict[str, Any]:
    """Convert an AppDeployment SDK object to a dictionary."""
    result = {
        "deployment_id": getattr(deployment, "deployment_id", None),
        "source_code_path": getattr(deployment, "source_code_path", None),
        "mode": str(getattr(deployment, "mode", None)),
        "create_time": str(getattr(deployment, "create_time", None)),
    }

    status = getattr(deployment, "status", None)
    if status:
        result["state"] = str(getattr(status, "state", None))
        result["message"] = getattr(status, "message", None)

    return result
