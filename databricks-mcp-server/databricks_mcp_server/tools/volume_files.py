"""Volume file tools - Manage files in Unity Catalog Volumes.

Consolidated into 1 tool:
- manage_volume_files: list, upload, download, delete, mkdir, get_info
"""

from typing import Dict, Any, Optional

from databricks_tools_core.unity_catalog import (
    list_volume_files as _list_volume_files,
    upload_to_volume as _upload_to_volume,
    download_from_volume as _download_from_volume,
    delete_from_volume as _delete_from_volume,
    create_volume_directory as _create_volume_directory,
    get_volume_file_metadata as _get_volume_file_metadata,
)

from ..server import mcp


@mcp.tool(timeout=300)
def manage_volume_files(
    action: str,
    volume_path: str,
    # For upload:
    local_path: Optional[str] = None,
    # For download:
    local_destination: Optional[str] = None,
    # For list:
    max_results: int = 500,
    # For delete:
    recursive: bool = False,
    # Common:
    max_workers: int = 4,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Manage Unity Catalog Volume files: list, upload, download, delete, mkdir, get_info.

    Actions:
    - list: List files in volume path. Returns: {files: [{name, path, is_directory, file_size}], truncated}.
      max_results: Limit results (default 500, max 1000).
    - upload: Upload local file/folder/glob to volume. Auto-creates directories.
      Requires volume_path, local_path. Returns: {total_files, successful, failed}.
    - download: Download file from volume to local path.
      Requires volume_path, local_destination. Returns: {success, error}.
    - delete: Delete file/directory from volume.
      recursive=True for non-empty directories. Returns: {files_deleted, directories_deleted}.
    - mkdir: Create directory in volume (like mkdir -p). Idempotent.
      Returns: {success}.
    - get_info: Get file/directory metadata.
      Returns: {name, path, is_directory, file_size, last_modified}.

    volume_path format: /Volumes/catalog/schema/volume/path/to/file_or_dir
    Supports tilde expansion (~) and glob patterns for local_path."""
    act = action.lower()

    if act == "list":
        # Cap max_results to prevent buffer overflow (1MB JSON limit)
        capped_max = min(max_results, 1000)

        # Fetch one extra to detect if there are more results
        results = _list_volume_files(volume_path, max_results=capped_max + 1)
        truncated = len(results) > capped_max

        # Only return up to max_results
        results = results[:capped_max]

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
            "message": f"Results limited to {len(files)} items. Use a more specific path to see more."
            if truncated
            else None,
        }

    elif act == "upload":
        if not local_path:
            return {"error": "upload requires: local_path"}

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

    elif act == "download":
        if not local_destination:
            return {"error": "download requires: local_destination"}

        result = _download_from_volume(
            volume_path=volume_path,
            local_path=local_destination,
            overwrite=overwrite,
        )
        return {
            "volume_path": result.volume_path,
            "local_path": result.local_path,
            "success": result.success,
            "error": result.error,
        }

    elif act == "delete":
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

    elif act == "mkdir":
        try:
            _create_volume_directory(volume_path)
            return {"volume_path": volume_path, "success": True}
        except Exception as e:
            return {"volume_path": volume_path, "success": False, "error": str(e)}

    elif act == "get_info":
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

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: list, upload, download, delete, mkdir, get_info"}
