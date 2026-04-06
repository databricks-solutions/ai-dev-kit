"""Workspace object tool - Browse, read, and create workspace notebooks and directories.

Provides 1 consolidated action-based tool:
- manage_workspace_objects: list, get_status, read, create_notebook, create_directory
"""

from typing import Any, Dict, Optional

from databricks_tools_core.file import (
    create_notebook as _create_notebook,
    create_workspace_directory as _create_workspace_directory,
    delete_from_workspace as _delete_from_workspace,
    get_workspace_object_status as _get_workspace_object_status,
    list_workspace_directory as _list_workspace_directory,
    read_notebook as _read_notebook,
)

from ..manifest import register_deleter
from ..server import mcp

_VALID_ACTIONS = ("list", "get_status", "read", "create_notebook", "create_directory")


# Register deleter for manifest cleanup
def _delete_workspace_object(resource_id: str) -> None:
    _delete_from_workspace(workspace_path=resource_id)


register_deleter("workspace_object", _delete_workspace_object)


def _manage_workspace_objects_impl(
    action: str,
    path: str,
    format: Optional[str] = None,
    content: Optional[str] = None,
    language: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Business logic for manage_workspace_objects. Separated from the MCP
    decorator so it can be tested directly without FastMCP wrapping."""

    if action not in _VALID_ACTIONS:
        return {"error": f"Invalid action '{action}'. Valid actions: {', '.join(_VALID_ACTIONS)}"}

    # -----------------------------------------------------------------
    # list: browse workspace paths
    # -----------------------------------------------------------------
    if action == "list":
        return _list_workspace_directory(path=path)

    # -----------------------------------------------------------------
    # get_status: metadata for a single object
    # -----------------------------------------------------------------
    if action == "get_status":
        return _get_workspace_object_status(path=path)

    # -----------------------------------------------------------------
    # read: export notebook content
    # -----------------------------------------------------------------
    if action == "read":
        return _read_notebook(path=path, format=format or "SOURCE")

    # -----------------------------------------------------------------
    # create_notebook: create or import a notebook
    # -----------------------------------------------------------------
    if action == "create_notebook":
        if not content:
            return {"error": "Parameter 'content' is required for create_notebook action."}
        result = _create_notebook(
            path=path,
            content=content,
            language=language or "PYTHON",
            format=format or "SOURCE",
            overwrite=overwrite,
        )

        # Track resource on successful create
        if result.get("success"):
            try:
                from ..manifest import track_resource

                track_resource(
                    resource_type="workspace_object",
                    name=path.rsplit("/", 1)[-1],
                    resource_id=path,
                )
            except Exception:
                pass

        return result

    # -----------------------------------------------------------------
    # create_directory: create workspace directory (idempotent)
    # -----------------------------------------------------------------
    if action == "create_directory":
        return _create_workspace_directory(path=path)

    return {"error": f"Unhandled action '{action}'."}


@mcp.tool(timeout=60)
def manage_workspace_objects(
    action: str,
    path: str,
    format: Optional[str] = None,
    content: Optional[str] = None,
    language: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Manage workspace objects: notebooks, directories, and files.

    Actions: list, get_status, read, create_notebook, create_directory.
    See databricks-workspace skill for details.

    Args:
        action: One of "list", "get_status", "read", "create_notebook",
            or "create_directory".
        path: Workspace path (e.g. "/Users/user@example.com/my_notebook").
        format: Export/import format. For read: SOURCE (default), HTML,
            JUPYTER, DBC. For create_notebook: SOURCE (default), JUPYTER.
        content: Notebook content string (required for create_notebook).
        language: PYTHON (default), SQL, SCALA, or R (for create_notebook).
        overwrite: If true, replace existing notebook (default: false).
            Only used with create_notebook.

    Returns:
        Dictionary with action-specific results.

    Example:
        >>> manage_workspace_objects(action="list", path="/Users/me")
        {"path": "/Users/me", "objects": [...], "count": 5}
        >>> manage_workspace_objects(action="read", path="/Users/me/nb")
        {"path": "...", "content": "print('hello')", "format": "SOURCE"}
        >>> manage_workspace_objects(action="create_notebook", path="/Users/me/nb", content="print(1)")
        {"path": "...", "language": "PYTHON", "success": true}
    """
    return _manage_workspace_objects_impl(
        action=action,
        path=path,
        format=format,
        content=content,
        language=language,
        overwrite=overwrite,
    )
