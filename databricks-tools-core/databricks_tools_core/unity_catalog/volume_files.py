"""
Volume Files - Unity Catalog Volume File Operations

Functions for working with files in Unity Catalog Volumes.
Uses Databricks Files API via SDK (w.files).

Volume paths use the format: /Volumes/<catalog>/<schema>/<volume>/<path>
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from databricks.sdk.service.files import DirectoryEntry

from ..auth import get_workspace_client


@dataclass
class VolumeFileInfo:
    """Information about a file or directory in a volume."""

    name: str
    path: str
    is_directory: bool
    file_size: int | None = None
    last_modified: str | None = None


@dataclass
class VolumeUploadResult:
    """Result from uploading a file to a volume."""

    local_path: str
    volume_path: str
    success: bool
    error: str | None = None


@dataclass
class VolumeDownloadResult:
    """Result from downloading a file from a volume."""

    volume_path: str
    local_path: str
    success: bool
    error: str | None = None


def list_volume_files(volume_path: str, max_results: int | None = None) -> list[VolumeFileInfo]:
    """
    List files and directories in a volume path.

    Args:
        volume_path: Path in volume (e.g., "/Volumes/catalog/schema/volume/folder")
        max_results: Optional maximum number of results to return (None = no limit)

    Returns:
        List of VolumeFileInfo objects

    Raises:
        Exception: If path doesn't exist or access denied

    Example:
        >>> files = list_volume_files("/Volumes/main/default/my_volume/data")
        >>> for f in files:
        ...     print(f"{f.name}: {'dir' if f.is_directory else 'file'}")
    """
    w = get_workspace_client()

    # Ensure path ends with / for directory listing
    if not volume_path.endswith("/"):
        volume_path = volume_path + "/"

    results = []
    for entry in w.files.list_directory_contents(volume_path):
        results.append(
            VolumeFileInfo(
                name=entry.name,
                path=entry.path,
                is_directory=entry.is_directory,
                file_size=entry.file_size,
                last_modified=entry.last_modified.isoformat() if entry.last_modified else None,
            )
        )
        # Early exit if we've hit the limit
        if max_results is not None and len(results) >= max_results:
            break

    return results


def upload_to_volume(local_path: str, volume_path: str, overwrite: bool = True) -> VolumeUploadResult:
    """
    Upload a local file to a Unity Catalog volume.

    Args:
        local_path: Path to local file
        volume_path: Target path in volume (e.g., "/Volumes/catalog/schema/volume/file.csv")
        overwrite: Whether to overwrite existing file (default: True)

    Returns:
        VolumeUploadResult with success status

    Example:
        >>> result = upload_to_volume(
        ...     local_path="/tmp/data.csv",
        ...     volume_path="/Volumes/main/default/my_volume/data.csv"
        ... )
        >>> if result.success:
        ...     print("Upload complete")
    """
    if not os.path.exists(local_path):
        return VolumeUploadResult(
            local_path=local_path, volume_path=volume_path, success=False, error=f"Local file not found: {local_path}"
        )

    if not os.path.isfile(local_path):
        return VolumeUploadResult(
            local_path=local_path, volume_path=volume_path, success=False, error=f"Path is not a file: {local_path}"
        )

    try:
        w = get_workspace_client()

        # Use upload_from for direct file-to-volume upload
        w.files.upload_from(file_path=volume_path, source_path=local_path, overwrite=overwrite)

        return VolumeUploadResult(local_path=local_path, volume_path=volume_path, success=True)

    except Exception as e:
        return VolumeUploadResult(local_path=local_path, volume_path=volume_path, success=False, error=str(e))


def download_from_volume(volume_path: str, local_path: str, overwrite: bool = True) -> VolumeDownloadResult:
    """
    Download a file from a Unity Catalog volume to local path.

    Args:
        volume_path: Path in volume (e.g., "/Volumes/catalog/schema/volume/file.csv")
        local_path: Target local file path
        overwrite: Whether to overwrite existing local file (default: True)

    Returns:
        VolumeDownloadResult with success status

    Example:
        >>> result = download_from_volume(
        ...     volume_path="/Volumes/main/default/my_volume/data.csv",
        ...     local_path="/tmp/downloaded.csv"
        ... )
        >>> if result.success:
        ...     print("Download complete")
    """
    # Check if local file exists and overwrite is False
    if os.path.exists(local_path) and not overwrite:
        return VolumeDownloadResult(
            volume_path=volume_path,
            local_path=local_path,
            success=False,
            error=f"Local file already exists: {local_path}",
        )

    try:
        w = get_workspace_client()

        # Create parent directory if needed
        parent_dir = str(Path(local_path).parent)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir)

        # Use download_to for direct volume-to-file download
        w.files.download_to(file_path=volume_path, destination=local_path, overwrite=overwrite)

        return VolumeDownloadResult(volume_path=volume_path, local_path=local_path, success=True)

    except Exception as e:
        return VolumeDownloadResult(volume_path=volume_path, local_path=local_path, success=False, error=str(e))


def delete_volume_file(volume_path: str) -> None:
    """
    Delete a file from a Unity Catalog volume.

    Args:
        volume_path: Path to file in volume (e.g., "/Volumes/catalog/schema/volume/file.csv")

    Raises:
        Exception: If file doesn't exist or access denied

    Example:
        >>> delete_volume_file("/Volumes/main/default/my_volume/old_data.csv")
    """
    w = get_workspace_client()
    w.files.delete(volume_path)


def delete_volume_directory(volume_path: str) -> None:
    """
    Delete an empty directory from a Unity Catalog volume.

    Note: Directory must be empty. Delete all contents first.

    Args:
        volume_path: Path to directory in volume

    Raises:
        Exception: If directory not empty, doesn't exist, or access denied

    Example:
        >>> delete_volume_directory("/Volumes/main/default/my_volume/old_folder/")
    """
    w = get_workspace_client()
    w.files.delete_directory(volume_path)


def create_volume_directory(volume_path: str) -> None:
    """
    Create a directory in a Unity Catalog volume.

    Creates parent directories as needed (like mkdir -p).
    Idempotent - succeeds if directory already exists.

    Args:
        volume_path: Path for new directory (e.g., "/Volumes/catalog/schema/volume/new_folder")

    Example:
        >>> create_volume_directory("/Volumes/main/default/my_volume/data/2024/01")
    """
    w = get_workspace_client()
    w.files.create_directory(volume_path)


def get_volume_file_metadata(volume_path: str) -> VolumeFileInfo:
    """
    Get metadata for a file in a Unity Catalog volume.

    Args:
        volume_path: Path to file in volume

    Returns:
        VolumeFileInfo with file metadata

    Raises:
        Exception: If file doesn't exist or access denied

    Example:
        >>> info = get_volume_file_metadata("/Volumes/main/default/my_volume/data.csv")
        >>> print(f"Size: {info.file_size} bytes")
    """
    w = get_workspace_client()
    metadata = w.files.get_metadata(volume_path)

    return VolumeFileInfo(
        name=Path(volume_path).name,
        path=volume_path,
        is_directory=False,
        file_size=metadata.content_length,
        last_modified=metadata.last_modified.isoformat() if metadata.last_modified else None,
    )
