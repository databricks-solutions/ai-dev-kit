"""Volume file tools - Manage files in Unity Catalog Volumes."""

from typing import Dict, Any

from databricks_tools_core.unity_catalog import (
    list_volume_files as _list_volume_files,
    upload_to_volume as _upload_to_volume,
    download_from_volume as _download_from_volume,
    delete_from_volume as _delete_from_volume,
    create_volume_directory as _create_volume_directory,
    get_volume_file_metadata as _get_volume_file_metadata,
)

from ..server import mcp


@mcp.tool(timeout=30)
def list_volume_files(volume_path: str, max_results: int = 500) -> Dict[str, Any]:
    """
    List files and directories in a Unity Catalog volume path.

    Args:
        volume_path: Path in volume (e.g., "/Volumes/catalog/schema/volume/folder")
        max_results: Maximum number of results to return (default: 500, max: 1000)

    Returns:
        Dictionary with 'files' list and 'truncated' boolean indicating if results were limited
    """
    # Cap max_results to prevent buffer overflow (1MB JSON limit)
    max_results = min(max_results, 1000)

    # Fetch one extra to detect if there are more results
    results = _list_volume_files(volume_path, max_results=max_results + 1)
    truncated = len(results) > max_results

    # Only return up to max_results
    results = results[:max_results]

    files = [
        {
            "name": r.name,
            "path": r.path,
            "is_directory": r.is_directory,
            "file_size": r.file_size,
            "last_modified": r.last_modified,
        }
        for r in results
    ]

    return {
        "files": files,
        "returned_count": len(files),
        "truncated": truncated,
        "message": f"Results limited to {len(files)} items. Use a more specific path or subdirectory to see more files."
        if truncated
        else None,
    }


@mcp.tool(timeout=300)
def upload_to_volume(
    local_path: str,
    volume_path: str,
    max_workers: int = 4,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    Upload local file(s) or folder(s) to a Unity Catalog volume.

    Supports single files, folders, and glob patterns. Auto-creates directories.

    Args:
        local_path: Local path - file, folder, or glob (e.g., "*.csv", "/path/*")
        volume_path: Target volume path (e.g., "/Volumes/catalog/schema/volume/data")
        max_workers: Parallel upload threads (default: 4)
        overwrite: Overwrite existing files (default: True)

    Returns:
        Dictionary with total_files, successful, failed, success
    """
    result = _upload_to_volume(
        local_path=local_path,
        volume_path=volume_path,
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
def download_from_volume(
    volume_path: str,
    local_path: str,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    Download a file from a Unity Catalog volume to local path.

    Args:
        volume_path: Path in volume (e.g., "/Volumes/catalog/schema/volume/data.csv")
        local_path: Target local file path
        overwrite: Whether to overwrite existing local file (default: True)

    Returns:
        Dictionary with volume_path, local_path, success, and error (if failed)
    """
    result = _download_from_volume(
        volume_path=volume_path,
        local_path=local_path,
        overwrite=overwrite,
    )
    return {
        "volume_path": result.volume_path,
        "local_path": result.local_path,
        "success": result.success,
        "error": result.error,
    }


@mcp.tool(timeout=120)
def delete_from_volume(
    volume_path: str,
    recursive: bool = False,
    max_workers: int = 4,
) -> Dict[str, Any]:
    """
    Delete a file or directory from a Unity Catalog volume.

    For directories, use recursive=True to delete contents. Deletes in parallel (be careful with this).

    Args:
        volume_path: Path to file or directory (e.g., "/Volumes/catalog/schema/volume/folder")
        recursive: Delete directory contents (required for non-empty dirs)
        max_workers: Parallel delete threads (default: 4)

    Returns:
        Dictionary with success, files_deleted, directories_deleted, error
    """
    result = _delete_from_volume(
        volume_path=volume_path,
        recursive=recursive,
        max_workers=max_workers,
    )
    return {
        "volume_path": result.volume_path,
        "success": result.success,
        "files_deleted": result.files_deleted,
        "directories_deleted": result.directories_deleted,
        "error": result.error,
    }


@mcp.tool(timeout=30)
def create_volume_directory(volume_path: str) -> Dict[str, Any]:
    """
    Create a directory in a Unity Catalog volume.

    Creates parent directories as needed (like mkdir -p).
    Idempotent - succeeds if directory already exists.

    Args:
        volume_path: Path for new directory (e.g., "/Volumes/catalog/schema/volume/new_folder")

    Returns:
        Dictionary with volume_path and success status
    """
    try:
        _create_volume_directory(volume_path)
        return {"volume_path": volume_path, "success": True}
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}


@mcp.tool(timeout=30)
def get_volume_file_info(volume_path: str) -> Dict[str, Any]:
    """
    Get metadata for a file in a Unity Catalog volume.

    Args:
        volume_path: Path to file in volume

    Returns:
        Dictionary with name, path, is_directory, file_size, last_modified
    """
    try:
        info = _get_volume_file_metadata(volume_path)
        return {
            "name": info.name,
            "path": info.path,
            "is_directory": info.is_directory,
            "file_size": info.file_size,
            "last_modified": info.last_modified,
            "success": True,
        }
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}
