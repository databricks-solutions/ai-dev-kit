"""File tools - Upload and delete files and folders in Databricks workspace."""

from typing import Any, Dict

from databricks_tools_core.file import (
    delete_from_workspace as _delete_from_workspace,
    upload_to_workspace as _upload_to_workspace,
)

from ..server import mcp


@mcp.tool
def upload_to_workspace(
    local_path: str,
    workspace_path: str,
    max_workers: int = 10,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    Upload files or folders to Databricks workspace.

    Handles single files, folders, and glob patterns. This is the unified upload
    function for all workspace file operations.

    Args:
        local_path: Path to local file, folder, or glob pattern.
            - Single file: "/path/to/file.py"
            - Folder: "/path/to/folder" (preserves folder name)
            - Folder contents: "/path/to/folder/" or "/path/to/folder/*"
            - Glob pattern: "/path/to/*.py"
            - Tilde expansion: "~/projects/file.py"
        workspace_path: Target path in Databricks workspace
            (e.g., "/Workspace/Users/user@example.com/my-project")
        max_workers: Maximum parallel upload threads (default: 10)
        overwrite: Whether to overwrite existing files (default: True)

    Returns:
        Dictionary with upload statistics:
        - local_folder: Source path
        - remote_folder: Target workspace path
        - total_files: Number of files found
        - successful: Number of successful uploads
        - failed: Number of failed uploads
        - success: True if all uploads succeeded
        - failed_uploads: List of failed uploads with error details (if any)
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
        "failed_uploads": [
            {"local_path": r.local_path, "error": r.error} for r in result.get_failed_uploads()
        ]
        if result.failed > 0
        else [],
    }


@mcp.tool
def delete_from_workspace(
    workspace_path: str,
    recursive: bool = False,
) -> Dict[str, Any]:
    """
    Delete a file or folder from Databricks workspace.

    Includes safety checks to prevent accidental deletion of protected paths
    like user home folders, repos roots, and shared folder roots.

    Args:
        workspace_path: Path to delete in Databricks workspace
        recursive: If True, delete folder and all contents (default: False)

    Returns:
        Dictionary with:
        - workspace_path: Path that was deleted
        - success: True if deletion succeeded
        - error: Error message if failed
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
