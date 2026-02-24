"""App tools - Manage Databricks Apps lifecycle.

Provides 3 workflow-oriented tools following the Lakebase pattern:
- create_or_update_app: idempotent create + optional deploy
- get_app: get details by name (with optional logs), or list all
- delete_app: delete by name
"""

import logging
from typing import Any, Dict, List, Optional

from databricks_tools_core.apps.apps import (
    create_app as _create_app,
    get_app as _get_app,
    list_apps as _list_apps,
    deploy_app as _deploy_app,
    delete_app as _delete_app,
    get_app_logs as _get_app_logs,
)

from ..manifest import register_deleter
from ..server import mcp

logger = logging.getLogger(__name__)


def _delete_app_resource(resource_id: str) -> None:
    _delete_app(name=resource_id)


register_deleter("app", _delete_app_resource)


# ============================================================================
# Helpers
# ============================================================================


def _find_app_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Find an app by name, returns None if not found."""
    try:
        result = _get_app(name=name)
        if result.get("error"):
            return None
        return result
    except Exception:
        return None


# ============================================================================
# Tool 1: create_or_update_app
# ============================================================================


@mcp.tool
def create_or_update_app(
    name: str,
    source_code_path: Optional[str] = None,
    description: Optional[str] = None,
    mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a Databricks App if it doesn't exist, and optionally deploy it.

    If the app already exists and source_code_path is provided, deploys
    the latest code. This is the standard workflow: "make this app exist
    and be running the latest code."

    Args:
        name: App name (must be unique within the workspace).
        source_code_path: Workspace path to deploy from
            (e.g., /Workspace/Users/user@example.com/my_app).
            If provided, deploys after create/find.
        description: Optional human-readable description (used on create only).
        mode: Optional deployment mode (e.g., "snapshot").

    Returns:
        Dictionary with:
        - name: App name
        - created: True if newly created, False if already existed
        - url: App URL
        - status: App status
        - deployment: Deployment details (if source_code_path provided)

    Example:
        >>> create_or_update_app("my-app", "/Workspace/Users/me/my_app")
        {"name": "my-app", "created": True, "url": "...", "deployment": {...}}
    """
    existing = _find_app_by_name(name)

    if existing:
        result = {**existing, "created": False}
    else:
        app_result = _create_app(name=name, description=description)
        result = {**app_result, "created": True}

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

    # Deploy if source_code_path provided
    if source_code_path:
        try:
            deployment = _deploy_app(
                app_name=name,
                source_code_path=source_code_path,
                mode=mode,
            )
            result["deployment"] = deployment
        except Exception as e:
            logger.warning("Failed to deploy app '%s': %s", name, e)
            result["deployment_error"] = str(e)

    return result


# ============================================================================
# Tool 2: get_app
# ============================================================================


@mcp.tool
def get_app(
    name: Optional[str] = None,
    name_contains: Optional[str] = None,
    include_logs: bool = False,
    deployment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get app details by name, or list all apps.

    Pass a name to get one app's details (optionally with recent logs).
    Omit name to list all apps (with optional name_contains filter).

    Args:
        name: App name. If provided, returns detailed app info.
        name_contains: Filter apps by name substring (for listing).
        include_logs: If True and name is provided, include deployment logs.
        deployment_id: Specific deployment ID for logs. If omitted, uses
            the active deployment.

    Returns:
        Single app dict (if name provided) or {"apps": [...]}.

    Example:
        >>> get_app("my-app")
        {"name": "my-app", "url": "...", "status": "RUNNING", ...}
        >>> get_app("my-app", include_logs=True)
        {"name": "my-app", ..., "logs": "..."}
        >>> get_app()
        {"apps": [{"name": "my-app", ...}, ...]}
    """
    if name:
        result = _get_app(name=name)

        if include_logs:
            try:
                logs = _get_app_logs(
                    app_name=name,
                    deployment_id=deployment_id,
                )
                result["logs"] = logs.get("logs", "")
                result["logs_deployment_id"] = logs.get("deployment_id")
            except Exception as e:
                result["logs_error"] = str(e)

        return result

    return {"apps": _list_apps(name_contains=name_contains)}


# ============================================================================
# Tool 3: delete_app
# ============================================================================


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
