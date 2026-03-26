"""
Volume Files - Unity Catalog Volume File Operations

Functions for working with files in Unity Catalog Volumes.
Uses Databricks Files API via SDK (w.files).

Volume paths use the format: /Volumes/<catalog>/<schema>/<volume>/<path>
"""

import glob as glob_module
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from databricks.sdk import WorkspaceClient

from ..auth import get_workspace_client


@dataclass
class VolumeFileInfo:
    """Information about a file or directory in a volume."""

    name: str
    path: str
    is_directory: bool
    file_size: Optional[int] = None
    last_modified: Optional[str] = None


@dataclass
class VolumeUploadResult:
    """Result from uploading a single file to a volume."""

    local_path: str
    volume_path: str
    success: bool
    error: Optional[str] = None


@dataclass
class VolumeFolderUploadResult:
    """Result from uploading multiple files to a volume."""

    local_folder: str
    remote_folder: str
    total_files: int
    successful: int
    failed: int
    results: List[VolumeUploadResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Returns True if all files were uploaded successfully"""
        return self.failed == 0

    def get_failed_uploads(self) -> List[VolumeUploadResult]:
        """Returns list of failed uploads"""
        return [r for r in self.results if not r.success]


@dataclass
class VolumeDownloadResult:
    """Result from downloading a file from a volume."""

    volume_path: str
    local_path: str
    success: bool
    error: Optional[str] = None


@dataclass
class VolumeDeleteResult:
    """Result from deleting a file or directory from a volume."""

    volume_path: str
    success: bool
    files_deleted: int = 0
    directories_deleted: int = 0
    error: Optional[str] = None


def list_volume_files(volume_path: str, max_results: Optional[int] = None) -> List[VolumeFileInfo]:
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
        # Handle last_modified - can be datetime, int (Unix timestamp), or None
        last_modified = None
        if entry.last_modified is not None:
            if isinstance(entry.last_modified, int):
                # Unix timestamp - convert to ISO format string
                last_modified = str(entry.last_modified)
            else:
                # datetime object - convert to ISO format string
                last_modified = entry.last_modified.isoformat()

        results.append(
            VolumeFileInfo(
                name=entry.name,
                path=entry.path,
                is_directory=entry.is_directory,
                file_size=entry.file_size,
                last_modified=last_modified,
            )
        )
        # Early exit if we've hit the limit
        if max_results is not None and len(results) >= max_results:
            break

    return results


def _collect_local_files(local_folder: str) -> List[tuple]:
    """
    Collect all files in a folder recursively.

    Args:
        local_folder: Path to local folder

    Returns:
        List of (local_path, relative_path) tuples
    """
    files = []
    local_folder = os.path.abspath(local_folder)

    for dirpath, _, filenames in os.walk(local_folder):
        for filename in filenames:
            # Skip hidden files and __pycache__
            if filename.startswith(".") or "__pycache__" in dirpath:
                continue

            local_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(local_path, local_folder)
            files.append((local_path, rel_path))

    return files


def _collect_local_directories(local_folder: str) -> List[str]:
    """
    Collect all directories in a folder recursively.

    Args:
        local_folder: Path to local folder

    Returns:
        List of relative directory paths
    """
    directories = set()
    local_folder = os.path.abspath(local_folder)

    for dirpath, dirnames, _ in os.walk(local_folder):
        # Skip hidden directories and __pycache__
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d != "__pycache__"]

        for dirname in dirnames:
            full_path = os.path.join(dirpath, dirname)
            rel_path = os.path.relpath(full_path, local_folder)
            directories.add(rel_path)
            # Also add parent directories
            parent = Path(rel_path).parent
            while str(parent) != ".":
                directories.add(str(parent))
                parent = parent.parent

    return sorted(directories)


def _upload_single_file_to_volume(
    w: WorkspaceClient, local_path: str, volume_path: str, overwrite: bool
) -> VolumeUploadResult:
    """Upload a single file to volume using w.files API."""
    try:
        w.files.upload_from(file_path=volume_path, source_path=local_path, overwrite=overwrite)
        return VolumeUploadResult(local_path=local_path, volume_path=volume_path, success=True)
    except Exception as e:
        return VolumeUploadResult(local_path=local_path, volume_path=volume_path, success=False, error=str(e))


def _create_volume_directory_safe(w: WorkspaceClient, volume_path: str) -> None:
    """Create a directory in volume, ignoring errors if it already exists."""
    try:
        w.files.create_directory(volume_path)
    except Exception:
        pass  # Directory may already exist


def upload_to_volume(
    local_path: str, volume_path: str, max_workers: int = 4, overwrite: bool = True
) -> VolumeFolderUploadResult:
    """
    Upload local file(s) or folder(s) to a Unity Catalog volume.

    Works like the `cp` command - handles single files, folders, and glob patterns.
    Automatically creates parent directories in volume as needed.

    Args:
        local_path: Path to local file, folder, or glob pattern. Examples:
            - "/path/to/file.csv" - single file
            - "/path/to/folder" - entire folder (recursive)
            - "/path/to/folder/*" - all files/folders in folder
            - "/path/to/*.json" - glob pattern
        volume_path: Target path in Unity Catalog volume
            (e.g., "/Volumes/catalog/schema/volume/folder")
        max_workers: Maximum parallel upload threads (default: 4)
        overwrite: Whether to overwrite existing files (default: True)

    Returns:
        VolumeFolderUploadResult with upload statistics and individual results

    Example:
        >>> # Upload a single file
        >>> result = upload_to_volume(
        ...     local_path="/tmp/data.csv",
        ...     volume_path="/Volumes/main/default/my_volume/data.csv"
        ... )

        >>> # Upload a folder
        >>> result = upload_to_volume(
        ...     local_path="/tmp/my_data",
        ...     volume_path="/Volumes/main/default/my_volume/my_data"
        ... )

        >>> # Upload folder contents (not the folder itself)
        >>> result = upload_to_volume(
        ...     local_path="/tmp/my_data/*",
        ...     volume_path="/Volumes/main/default/my_volume/destination"
        ... )
    """
    local_path = os.path.expanduser(local_path)
    volume_path = volume_path.rstrip("/")

    w = get_workspace_client()

    # Determine what we're uploading
    has_glob = "*" in local_path or "?" in local_path

    if has_glob:
        return _upload_glob_to_volume(w, local_path, volume_path, max_workers, overwrite)
    elif os.path.isfile(local_path):
        return _upload_single_to_volume(w, local_path, volume_path, overwrite)
    elif os.path.isdir(local_path):
        return _upload_folder_to_volume(w, local_path, volume_path, max_workers, overwrite)
    else:
        return VolumeFolderUploadResult(
            local_folder=local_path,
            remote_folder=volume_path,
            total_files=0,
            successful=0,
            failed=1,
            results=[
                VolumeUploadResult(
                    local_path=local_path,
                    volume_path=volume_path,
                    success=False,
                    error=f"Path not found: {local_path}",
                )
            ],
        )


def _upload_single_to_volume(
    w: WorkspaceClient, local_path: str, volume_path: str, overwrite: bool
) -> VolumeFolderUploadResult:
    """Upload a single file to volume."""
    # Create parent directory if needed
    parent_dir = str(Path(volume_path).parent)
    _create_volume_directory_safe(w, parent_dir)

    result = _upload_single_file_to_volume(w, local_path, volume_path, overwrite)
    return VolumeFolderUploadResult(
        local_folder=os.path.dirname(local_path),
        remote_folder=os.path.dirname(volume_path),
        total_files=1,
        successful=1 if result.success else 0,
        failed=0 if result.success else 1,
        results=[result],
    )


def _upload_glob_to_volume(
    w: WorkspaceClient, pattern: str, volume_path: str, max_workers: int, overwrite: bool
) -> VolumeFolderUploadResult:
    """Upload files matching a glob pattern to volume."""
    matches = glob_module.glob(pattern)
    if not matches:
        return VolumeFolderUploadResult(
            local_folder=os.path.dirname(pattern),
            remote_folder=volume_path,
            total_files=0,
            successful=0,
            failed=1,
            results=[
                VolumeUploadResult(
                    local_path=pattern,
                    volume_path=volume_path,
                    success=False,
                    error=f"No files match pattern: {pattern}",
                )
            ],
        )

    # Get the base directory
    pattern_dir = os.path.dirname(pattern)
    if pattern_dir:
        base_dir = os.path.abspath(pattern_dir)
    else:
        base_dir = os.getcwd()

    # Create volume root directory
    _create_volume_directory_safe(w, volume_path)

    # Collect all files from all matches
    all_files = []
    all_dirs = set()

    for match in matches:
        match = os.path.abspath(match)
        if os.path.isfile(match):
            rel_path = os.path.basename(match)
            all_files.append((match, rel_path))
        elif os.path.isdir(match):
            folder_name = os.path.basename(match)
            for local_file, rel_in_folder in _collect_local_files(match):
                rel_path = os.path.join(folder_name, rel_in_folder)
                all_files.append((local_file, rel_path))
                parent = str(Path(rel_path).parent)
                while parent != ".":
                    all_dirs.add(parent)
                    parent = str(Path(parent).parent)
            for subdir in _collect_local_directories(match):
                all_dirs.add(os.path.join(folder_name, subdir))
            all_dirs.add(folder_name)

    # Create all directories
    for dir_path in sorted(all_dirs):
        _create_volume_directory_safe(w, f"{volume_path}/{dir_path}")

    if not all_files:
        return VolumeFolderUploadResult(
            local_folder=base_dir,
            remote_folder=volume_path,
            total_files=0,
            successful=0,
            failed=0,
            results=[],
        )

    return _parallel_upload_to_volume(w, all_files, base_dir, volume_path, max_workers, overwrite)


def _upload_folder_to_volume(
    w: WorkspaceClient, local_folder: str, volume_folder: str, max_workers: int, overwrite: bool
) -> VolumeFolderUploadResult:
    """Upload an entire folder to volume."""
    local_folder = os.path.abspath(local_folder)

    # Create root directory
    _create_volume_directory_safe(w, volume_folder)

    # Create all subdirectories
    directories = _collect_local_directories(local_folder)
    for dir_path in directories:
        _create_volume_directory_safe(w, f"{volume_folder}/{dir_path}")

    # Collect all files
    files = _collect_local_files(local_folder)

    if not files:
        return VolumeFolderUploadResult(
            local_folder=local_folder,
            remote_folder=volume_folder,
            total_files=0,
            successful=0,
            failed=0,
            results=[],
        )

    return _parallel_upload_to_volume(w, files, local_folder, volume_folder, max_workers, overwrite)


def _parallel_upload_to_volume(
    w: WorkspaceClient,
    files: List[tuple],
    local_base: str,
    volume_base: str,
    max_workers: int,
    overwrite: bool,
) -> VolumeFolderUploadResult:
    """Upload files in parallel to volume."""
    results = []
    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {}
        for local_path, rel_path in files:
            remote_path = f"{volume_base}/{rel_path.replace(os.sep, '/')}"
            future = executor.submit(_upload_single_file_to_volume, w, local_path, remote_path, overwrite)
            future_to_file[future] = (local_path, remote_path)

        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1

    return VolumeFolderUploadResult(
        local_folder=local_base,
        remote_folder=volume_base,
        total_files=len(files),
        successful=successful,
        failed=failed,
        results=results,
    )


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


def _delete_single_file(w: WorkspaceClient, volume_path: str) -> bool:
    """Delete a single file, returns True if successful."""
    try:
        w.files.delete(volume_path)
        return True
    except Exception:
        return False


def _delete_single_directory(w: WorkspaceClient, volume_path: str) -> bool:
    """Delete a single empty directory, returns True if successful."""
    try:
        w.files.delete_directory(volume_path)
        return True
    except Exception:
        return False


def _collect_volume_contents(w: WorkspaceClient, volume_path: str) -> tuple[List[str], List[str]]:
    """
    Recursively collect all files and directories in a volume path.

    Returns:
        Tuple of (files, directories) where directories are sorted deepest-first
        for proper deletion order.
    """
    files = []
    directories = []

    def _scan(path: str):
        try:
            if not path.endswith("/"):
                path = path + "/"
            for entry in w.files.list_directory_contents(path):
                if entry.is_directory:
                    directories.append(entry.path)
                    _scan(entry.path)
                else:
                    files.append(entry.path)
        except Exception:
            pass

    _scan(volume_path)

    # Sort directories by depth (deepest first) for proper deletion order
    directories.sort(key=lambda x: x.count("/"), reverse=True)

    return files, directories


def delete_from_volume(volume_path: str, recursive: bool = False, max_workers: int = 4) -> VolumeDeleteResult:
    """
    Delete a file or directory from a Unity Catalog volume.

    For files, deletes the file directly.
    For directories, requires recursive=True to delete non-empty directories.
    When recursive=True, deletes all files in parallel, then directories deepest-first.

    Args:
        volume_path: Path to file or directory in volume
            (e.g., "/Volumes/catalog/schema/volume/folder")
        recursive: If True, delete directory and all contents. Required for non-empty directories.
            (default: False)
        max_workers: Maximum parallel delete threads (default: 4)

    Returns:
        VolumeDeleteResult with success status and counts

    Example:
        >>> # Delete a single file
        >>> result = delete_from_volume("/Volumes/main/default/my_volume/old_file.csv")

        >>> # Delete a folder and all contents
        >>> result = delete_from_volume(
        ...     "/Volumes/main/default/my_volume/old_folder",
        ...     recursive=True
        ... )
    """
    volume_path = volume_path.rstrip("/")
    w = get_workspace_client()

    # Check if path is a file or directory
    try:
        w.files.get_metadata(volume_path)
        is_directory = False
    except Exception:
        # get_metadata fails for directories, try listing
        try:
            list(w.files.list_directory_contents(volume_path + "/"))
            is_directory = True
        except Exception as e:
            return VolumeDeleteResult(
                volume_path=volume_path,
                success=False,
                error=f"Path not found or access denied: {volume_path}. {str(e)}",
            )

    if not is_directory:
        # Simple file deletion
        try:
            w.files.delete(volume_path)
            return VolumeDeleteResult(volume_path=volume_path, success=True, files_deleted=1)
        except Exception as e:
            return VolumeDeleteResult(volume_path=volume_path, success=False, error=str(e))

    # It's a directory
    if not recursive:
        # Try to delete empty directory
        try:
            w.files.delete_directory(volume_path)
            return VolumeDeleteResult(volume_path=volume_path, success=True, directories_deleted=1)
        except Exception as e:
            return VolumeDeleteResult(
                volume_path=volume_path,
                success=False,
                error=f"Directory not empty. Use recursive=True to delete all contents. {str(e)}",
            )

    # Recursive deletion
    files, directories = _collect_volume_contents(w, volume_path)

    files_deleted = 0
    directories_deleted = 0

    # Delete all files in parallel
    if files:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_delete_single_file, w, f): f for f in files}
            for future in as_completed(futures):
                if future.result():
                    files_deleted += 1

    # Delete directories sequentially (deepest first)
    for dir_path in directories:
        if _delete_single_directory(w, dir_path):
            directories_deleted += 1

    # Finally delete the root directory
    try:
        w.files.delete_directory(volume_path)
        directories_deleted += 1
        success = True
        error = None
    except Exception as e:
        success = False
        error = f"Failed to delete root directory: {str(e)}"

    return VolumeDeleteResult(
        volume_path=volume_path,
        success=success,
        files_deleted=files_deleted,
        directories_deleted=directories_deleted,
        error=error,
    )


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
