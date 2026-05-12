"""App tools - Manage Databricks Apps lifecycle.

Consolidated into 1 tool:
- manage_app: create_or_update, get, list, delete
"""

import logging
from typing import Any, Dict, Optional

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
# Tool: manage_app
# ============================================================================


@mcp.tool(timeout=180)
def manage_app(
    action: str,
    # For create_or_update/get/delete:
    name: Optional[str] = None,
    # For create_or_update:
    source_code_path: Optional[str] = None,
    description: Optional[str] = None,
    mode: Optional[str] = None,
    # For get:
    include_logs: bool = False,
    deployment_id: Optional[str] = None,
    # For list:
    name_contains: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage Databricks Apps: create, deploy, get, list, delete.

    Actions:
    - create_or_update: Idempotent create. Deploys if source_code_path provided. Requires name.
      source_code_path: Volume or workspace path to deploy from.
      description: App description. mode: Deployment mode.
      Returns: {name, created: bool, url, status, deployment}.
    - get: Get app details. Requires name.
      include_logs=True for deployment logs. deployment_id for specific deployment.
      Returns: {name, url, status, logs}.
    - list: List all apps. Optional name_contains filter.
      Returns: {apps: [{name, url, status}, ...]}.
    - delete: Delete an app. Requires name.
      Returns: {name, status}.

    See databricks-app-python skill for app development guidance."""
    act = action.lower()

    if act == "create_or_update":
        if not name:
            return {"error": "create_or_update requires: name"}
        return _create_or_update_app(
            name=name,
            source_code_path=source_code_path,
            description=description,
            mode=mode,
        )

    elif act == "get":
        if not name:
            return {"error": "get requires: name"}
        return _get_app_details(
            name=name,
            include_logs=include_logs,
            deployment_id=deployment_id,
        )

    elif act == "list":
        return {"apps": _list_apps(name_contains=name_contains)}

    elif act == "delete":
        if not name:
            return {"error": "delete requires: name"}
        return _delete_app_by_name(name=name)

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: create_or_update, get, list, delete"}


# ============================================================================
# Helper Functions
# ============================================================================


def _create_or_update_app(
    name: str,
    source_code_path: Optional[str],
    description: Optional[str],
    mode: Optional[str],
) -> Dict[str, Any]:
    """Create app if not exists, optionally deploy."""
    existing = _find_app_by_name(name)

    if existing:
        result = {**existing, "created": False}
    else:
        app_result = _create_app(name=name, description=with_description_footer(description))
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


def _get_app_details(
    name: str,
    include_logs: bool,
    deployment_id: Optional[str],
) -> Dict[str, Any]:
    """Get app details with optional logs."""
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


def _delete_app_by_name(name: str) -> Dict[str, str]:
    """Delete a Databricks App."""
    result = _delete_app(name=name)

    # Remove from tracked resources
    try:
        from ..manifest import remove_resource

        remove_resource(resource_type="app", resource_id=name)
    except Exception:
        pass  # best-effort tracking

    return result
