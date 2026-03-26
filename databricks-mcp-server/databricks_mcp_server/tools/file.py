"""File tools - Upload and delete files and folders in Databricks workspace."""

from typing import Dict, Any

from databricks_tools_core.file import (
    upload_to_workspace as _upload_to_workspace,
    delete_from_workspace as _delete_from_workspace,
)

from ..server import mcp


@mcp.tool(timeout=300)
def upload_to_workspace(
    local_path: str,
    workspace_path: str,
    max_workers: int = 10,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    Upload local file(s) or folder(s) to Databricks workspace.

    Supports single files, folders, and glob patterns. Auto-creates directories.

    Args:
        local_path: Local path - file, folder, or glob (e.g., "*.py", "/path/*")
        workspace_path: Target workspace path (e.g., "/Workspace/Users/user@example.com/project")
        max_workers: Parallel upload threads (default: 10)
        overwrite: Overwrite existing files (default: True)

    Returns:
        Dictionary with total_files, successful, failed, success
    """
    result = _upload_to_workspace(
        local_path=local_path,
        workspace_path=workspace_path,
        max_workers=max_workers,
        overwrite=overwrite,
    )
    return {
        "local_folder": result.local_folder,
        "remote_folder": result.remote_folder,
        "total_files": result.total_files,
        "successful": result.successful,
        "failed": result.failed,
        "success": result.success,
        "failed_uploads": [{"local_path": r.local_path, "error": r.error} for r in result.get_failed_uploads()]
        if result.failed > 0
        else [],
    }


@mcp.tool(timeout=60)
def delete_from_workspace(
    workspace_path: str,
    recursive: bool = False,
) -> Dict[str, Any]:
    """
    Delete a file or folder from Databricks workspace.

    SAFETY: Cannot delete protected paths (user home folders, repos roots, /Workspace/Shared).
    Path must be at least one level deeper than these protected roots.

    Args:
        workspace_path: Path to file or folder (e.g., "/Workspace/Users/user@example.com/project")
        recursive: Delete folder contents (required for non-empty folders)

    Returns:
        Dictionary with workspace_path, success, error
    """
    result = _delete_from_workspace(
        workspace_path=workspace_path,
        recursive=recursive,
    )
    return {
        "workspace_path": result.workspace_path,
        "success": result.success,
        "error": result.error,
    }
