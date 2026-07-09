"""Resource tracking manifest tools.

Exposes the resource manifest as MCP tools so agents can list and clean up
resources created across sessions.
"""

import logging
from typing import Any, Dict, Optional

from ..manifest import _RESOURCE_DELETERS, list_resources, remove_resource
from ..server import mcp

logger = logging.getLogger(__name__)


def _delete_from_databricks(resource_type: str, resource_id: str) -> Optional[str]:
    """Delete a resource from Databricks using the registered deleter.

    Returns error string or None on success.
    """
    deleter = _RESOURCE_DELETERS.get(resource_type)
    if not deleter:
        return f"Unsupported resource type for deletion: {resource_type}"
    try:
        deleter(resource_id)
        return None
    except Exception as exc:
        return str(exc)


@mcp.tool(timeout=30)
def list_tracked_resources(type: Optional[str] = None) -> Dict[str, Any]:
    """List resources tracked in project manifest (dashboards, jobs, pipelines, genie_space, etc.).

    type: Filter by resource type (optional). Returns: {resources: [...], count}."""
    resources = list_resources(resource_type=type)
    return {
        "resources": resources,
        "count": len(resources),
    }


@mcp.tool(timeout=60)
def delete_tracked_resource(
    type: str,
    resource_id: str,
    delete_from_databricks: bool = False,
) -> Dict[str, Any]:
    """Delete resource from manifest, optionally from Databricks too.

    delete_from_databricks: If True, deletes from Databricks first (default: False, manifest-only).
    Returns: {success, removed_from_manifest, deleted_from_databricks, error}."""
    result: Dict[str, Any] = {
        "success": True,
        "removed_from_manifest": False,
        "deleted_from_databricks": False,
        "error": None,
    }

    # Optionally delete from Databricks first
    if delete_from_databricks:
        error = _delete_from_databricks(type, resource_id)
        if error:
            result["error"] = f"Databricks deletion failed: {error}"
            result["success"] = False
            # Still remove from manifest even if Databricks deletion failed
        else:
            result["deleted_from_databricks"] = True

    # Remove from manifest
    removed = remove_resource(resource_type=type, resource_id=resource_id)
    result["removed_from_manifest"] = removed

    if not removed and not result.get("error"):
        result["error"] = f"Resource {type}/{resource_id} not found in manifest"
        result["success"] = result.get("deleted_from_databricks", False)

    return result
