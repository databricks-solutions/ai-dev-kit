"""
File - Workspace File Operations

Functions for uploading files and folders to Databricks Workspace.
Uses Databricks Workspace API via SDK.
"""

import io
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat

from ..auth import get_workspace_client


@dataclass
class UploadResult:
    """Result from a single file upload"""

    local_path: str
    remote_path: str
    success: bool
    error: str | None = None


@dataclass
class FolderUploadResult:
    """Result from uploading a folder"""

    local_folder: str
    remote_folder: str
    total_files: int
    successful: int
    failed: int
    results: list[UploadResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Returns True if all files were uploaded successfully"""
        return self.failed == 0

    def get_failed_uploads(self) -> list[UploadResult]:
        """Returns list of failed uploads"""
        return [r for r in self.results if not r.success]


def _upload_single_file(w: WorkspaceClient, local_path: str, remote_path: str, overwrite: bool = True) -> UploadResult:
    """
    Upload a single file to Databricks workspace.

    Args:
        w: WorkspaceClient instance
        local_path: Path to local file
        remote_path: Target path in workspace
        overwrite: Whether to overwrite existing files

    Returns:
        UploadResult with success status
    """
    try:
        with open(local_path, "rb") as f:
            content = f.read()

        # Use workspace.upload with AUTO format to handle all file types
        # AUTO will detect notebooks vs regular files based on extension/content
        w.workspace.upload(path=remote_path, content=io.BytesIO(content), format=ImportFormat.AUTO, overwrite=overwrite)

        return UploadResult(local_path=local_path, remote_path=remote_path, success=True)

    except Exception as e:
        return UploadResult(local_path=local_path, remote_path=remote_path, success=False, error=str(e))


def _collect_files(local_folder: str) -> list[tuple]:
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


def _collect_directories(local_folder: str) -> list[str]:
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


def upload_folder(
    local_folder: str, workspace_folder: str, max_workers: int = 10, overwrite: bool = True
) -> FolderUploadResult:
    """
    Upload an entire local folder to Databricks workspace.

    Uses parallel uploads with ThreadPoolExecutor for performance.
    Automatically handles all file types using ImportFormat.AUTO.

    Args:
        local_folder: Path to local folder to upload
        workspace_folder: Target path in Databricks workspace
            (e.g., "/Users/user@example.com/my-project")
        max_workers: Maximum number of parallel upload threads (default: 10)
        overwrite: Whether to overwrite existing files (default: True)

    Returns:
        FolderUploadResult with upload statistics and individual results

    Raises:
        FileNotFoundError: If local folder doesn't exist
        ValueError: If local folder is not a directory

    Example:
        >>> result = upload_folder(
        ...     local_folder="/path/to/my-project",
        ...     workspace_folder="/Users/me@example.com/my-project"
        ... )
        >>> print(f"Uploaded {result.successful}/{result.total_files} files")
        >>> if not result.success:
        ...     for failed in result.get_failed_uploads():
        ...         print(f"Failed: {failed.local_path} - {failed.error}")
    """
    # Validate local folder
    local_folder = os.path.abspath(local_folder)
    if not os.path.exists(local_folder):
        raise FileNotFoundError(f"Local folder not found: {local_folder}")
    if not os.path.isdir(local_folder):
        raise ValueError(f"Path is not a directory: {local_folder}")

    # Normalize workspace path (remove trailing slash)
    workspace_folder = workspace_folder.rstrip("/")

    # Initialize client
    w = get_workspace_client()

    # Create all directories first
    directories = _collect_directories(local_folder)
    for dir_path in directories:
        remote_dir = f"{workspace_folder}/{dir_path}"
        try:
            w.workspace.mkdirs(remote_dir)
        except Exception:
            # Directory might already exist, ignore
            pass

    # Create the root directory too
    try:
        w.workspace.mkdirs(workspace_folder)
    except Exception:
        pass

    # Collect all files
    files = _collect_files(local_folder)

    if not files:
        return FolderUploadResult(
            local_folder=local_folder, remote_folder=workspace_folder, total_files=0, successful=0, failed=0, results=[]
        )

    # Upload files in parallel
    results = []
    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all upload tasks
        future_to_file = {}
        for local_path, rel_path in files:
            # Convert Windows paths to forward slashes for workspace
            remote_path = f"{workspace_folder}/{rel_path.replace(os.sep, '/')}"
            future = executor.submit(_upload_single_file, w, local_path, remote_path, overwrite)
            future_to_file[future] = (local_path, remote_path)

        # Collect results as they complete
        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1

    return FolderUploadResult(
        local_folder=local_folder,
        remote_folder=workspace_folder,
        total_files=len(files),
        successful=successful,
        failed=failed,
        results=results,
    )


def upload_file(local_path: str, workspace_path: str, overwrite: bool = True) -> UploadResult:
    """
    Upload a single file to Databricks workspace.

    Args:
        local_path: Path to local file
        workspace_path: Target path in Databricks workspace
        overwrite: Whether to overwrite existing file (default: True)

    Returns:
        UploadResult with success status

    Example:
        >>> result = upload_file(
        ...     local_path="/path/to/script.py",
        ...     workspace_path="/Users/me@example.com/scripts/script.py"
        ... )
        >>> if result.success:
        ...     print("Upload complete")
        ... else:
        ...     print(f"Error: {result.error}")
    """
    if not os.path.exists(local_path):
        return UploadResult(
            local_path=local_path,
            remote_path=workspace_path,
            success=False,
            error=f"Local file not found: {local_path}",
        )

    if not os.path.isfile(local_path):
        return UploadResult(
            local_path=local_path, remote_path=workspace_path, success=False, error=f"Path is not a file: {local_path}"
        )

    w = get_workspace_client()

    # Create parent directory if needed
    parent_dir = str(Path(workspace_path).parent)
    if parent_dir != "/":
        try:
            w.workspace.mkdirs(parent_dir)
        except Exception:
            pass

    return _upload_single_file(w, local_path, workspace_path, overwrite)
