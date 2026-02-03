"""Volume file tools - Manage files in Unity Catalog Volumes."""

from typing import Dict, Any, List

from databricks_tools_core.unity_catalog import (
    list_volume_files as _list_volume_files,
    upload_to_volume as _upload_to_volume,
    download_from_volume as _download_from_volume,
    delete_volume_file as _delete_volume_file,
    delete_volume_directory as _delete_volume_directory,
    create_volume_directory as _create_volume_directory,
    get_volume_file_metadata as _get_volume_file_metadata,
)

from ..server import mcp


@mcp.tool
def list_volume_files(volume_path: str) -> List[Dict[str, Any]]:
    """
    List files and directories in a Unity Catalog volume path.

    Args:
        volume_path: Path in volume (e.g., "/Volumes/catalog/schema/volume/folder")

    Returns:
        List of file/directory info with name, path, is_directory, file_size, last_modified
    """
    results = _list_volume_files(volume_path)
    return [
        {
            "name": r.name,
            "path": r.path,
            "is_directory": r.is_directory,
            "file_size": r.file_size,
            "last_modified": r.last_modified,
        }
        for r in results
    ]


@mcp.tool
def upload_to_volume(
    local_path: str,
    volume_path: str,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """
    Upload a local file to a Unity Catalog volume.

    Args:
        local_path: Path to local file to upload
        volume_path: Target path in volume (e.g., "/Volumes/catalog/schema/volume/data.csv")
        overwrite: Whether to overwrite existing file (default: True)

    Returns:
        Dictionary with local_path, volume_path, success, and error (if failed)
    """
    result = _upload_to_volume(
        local_path=local_path,
        volume_path=volume_path,
        overwrite=overwrite,
    )
    return {
        "local_path": result.local_path,
        "volume_path": result.volume_path,
        "success": result.success,
        "error": result.error,
    }


@mcp.tool
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


@mcp.tool
def delete_volume_file(volume_path: str) -> Dict[str, Any]:
    """
    Delete a file from a Unity Catalog volume.

    Args:
        volume_path: Path to file in volume (e.g., "/Volumes/catalog/schema/volume/file.csv")

    Returns:
        Dictionary with volume_path and success status
    """
    try:
        _delete_volume_file(volume_path)
        return {"volume_path": volume_path, "success": True}
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}


@mcp.tool
def delete_volume_directory(volume_path: str) -> Dict[str, Any]:
    """
    Delete an empty directory from a Unity Catalog volume.

    Note: Directory must be empty. Delete all contents first.

    Args:
        volume_path: Path to directory in volume

    Returns:
        Dictionary with volume_path and success status
    """
    try:
        _delete_volume_directory(volume_path)
        return {"volume_path": volume_path, "success": True}
    except Exception as e:
        return {"volume_path": volume_path, "success": False, "error": str(e)}


@mcp.tool
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


@mcp.tool
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
