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


@mcp.tool
def list_tracked_resources(type: Optional[str] = None) -> Dict[str, Any]:
    """List resources tracked in the project manifest.

    The manifest records every resource created through the MCP server
    (dashboards, jobs, pipelines, Genie spaces, KAs, MAS, schemas, volumes, etc.).
    Use this to see what was created across sessions.

    Args:
        type: Optional filter by resource type. One of: "dashboard", "job",
            "pipeline", "genie_space", "knowledge_assistant",
            "multi_agent_supervisor", "catalog", "schema", "volume".
            If not provided, returns all tracked resources.

    Returns:
        Dictionary with:
        - resources: List of tracked resources (type, name, id, url, timestamps)
        - count: Number of resources returned
    """
    resources = list_resources(resource_type=type)
    return {
        "resources": resources,
        "count": len(resources),
    }


@mcp.tool
def delete_tracked_resource(
    type: str,
    resource_id: str,
    delete_from_databricks: bool = False,
) -> Dict[str, Any]:
    """Delete a resource from the project manifest, and optionally from Databricks.

    Use this to clean up resources that were created during development/testing.

    Args:
        type: Resource type (e.g., "dashboard", "job", "pipeline", "genie_space",
            "knowledge_assistant", "multi_agent_supervisor", "catalog", "schema", "volume")
        resource_id: The resource ID (as shown in list_tracked_resources)
        delete_from_databricks: If True, also delete the resource from Databricks
            before removing it from the manifest. Default: False (manifest-only).

    Returns:
        Dictionary with:
        - success: Whether the operation succeeded
        - removed_from_manifest: Whether the resource was found and removed
        - deleted_from_databricks: Whether the resource was deleted from Databricks
        - error: Error message if deletion failed
    """
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
