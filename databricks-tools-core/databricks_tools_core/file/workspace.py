"""
File - Workspace File Operations

Functions for uploading and deleting files and folders in Databricks Workspace.
Uses Databricks Workspace API via SDK.
"""

import glob
import io
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.workspace import ImportFormat

from ..auth import get_workspace_client


@dataclass
class DeleteResult:
    """Result from deleting a workspace path"""

    workspace_path: str
    success: bool
    error: Optional[str] = None


@dataclass
class UploadResult:
    """Result from a single file upload"""

    local_path: str
    remote_path: str
    success: bool
    error: Optional[str] = None


@dataclass
class FolderUploadResult:
    """Result from uploading a folder"""

    local_folder: str
    remote_folder: str
    total_files: int
    successful: int
    failed: int
    results: List[UploadResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Returns True if all files were uploaded successfully"""
        return self.failed == 0

    def get_failed_uploads(self) -> List[UploadResult]:
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
        w.workspace.upload(
            path=remote_path,
            content=io.BytesIO(content),
            format=ImportFormat.AUTO,
            overwrite=overwrite,
        )

        return UploadResult(local_path=local_path, remote_path=remote_path, success=True)

    except Exception as e:
        return UploadResult(local_path=local_path, remote_path=remote_path, success=False, error=str(e))


def _collect_files(local_folder: str) -> List[tuple]:
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


def _collect_directories(local_folder: str) -> List[str]:
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


def upload_to_workspace(
    local_path: str, workspace_path: str, max_workers: int = 10, overwrite: bool = True
) -> FolderUploadResult:
    """
    Upload local file(s) or folder(s) to Databricks workspace.

    Works like the `cp` command - handles single files, folders, and glob patterns.
    Automatically creates parent directories in workspace as needed.

    Args:
        local_path: Path to local file, folder, or glob pattern. Examples:
            - "/path/to/file.py" - single file
            - "/path/to/folder" - entire folder (recursive)
            - "/path/to/folder/*" - all files/folders in folder
            - "/path/to/*.py" - glob pattern
        workspace_path: Target path in Databricks workspace
            (e.g., "/Workspace/Users/user@example.com/my-project")
        max_workers: Maximum parallel upload threads (default: 10)
        overwrite: Whether to overwrite existing files (default: True)

    Returns:
        FolderUploadResult with upload statistics and individual results

    Example:
        >>> # Upload a single file
        >>> result = upload_to_workspace(
        ...     local_path="/path/to/script.py",
        ...     workspace_path="/Workspace/Users/me@example.com/scripts/script.py"
        ... )

        >>> # Upload a folder
        >>> result = upload_to_workspace(
        ...     local_path="/path/to/my-project",
        ...     workspace_path="/Workspace/Users/me@example.com/my-project"
        ... )

        >>> # Upload folder contents (not the folder itself)
        >>> result = upload_to_workspace(
        ...     local_path="/path/to/my-project/*",
        ...     workspace_path="/Workspace/Users/me@example.com/destination"
        ... )
    """
    local_path = os.path.expanduser(local_path)
    workspace_path = workspace_path.rstrip("/")

    # Initialize client
    w = get_workspace_client()

    # Determine what we're uploading
    has_glob = "*" in local_path or "?" in local_path

    if has_glob:
        # Handle glob patterns
        return _upload_glob(w, local_path, workspace_path, max_workers, overwrite)
    elif os.path.isfile(local_path):
        # Single file upload
        return _upload_single(w, local_path, workspace_path, overwrite)
    elif os.path.isdir(local_path):
        # Folder upload
        return _upload_folder(w, local_path, workspace_path, max_workers, overwrite)
    else:
        # Path doesn't exist
        return FolderUploadResult(
            local_folder=local_path,
            remote_folder=workspace_path,
            total_files=0,
            successful=0,
            failed=1,
            results=[
                UploadResult(
                    local_path=local_path,
                    remote_path=workspace_path,
                    success=False,
                    error=f"Path not found: {local_path}",
                )
            ],
        )


def _upload_single(
    w: WorkspaceClient, local_path: str, workspace_path: str, overwrite: bool
) -> FolderUploadResult:
    """Upload a single file."""
    # Create parent directory if needed
    parent_dir = str(Path(workspace_path).parent)
    if parent_dir != "/":
        try:
            w.workspace.mkdirs(parent_dir)
        except Exception:
            pass

    result = _upload_single_file(w, local_path, workspace_path, overwrite)
    return FolderUploadResult(
        local_folder=os.path.dirname(local_path),
        remote_folder=os.path.dirname(workspace_path),
        total_files=1,
        successful=1 if result.success else 0,
        failed=0 if result.success else 1,
        results=[result],
    )


def _upload_glob(
    w: WorkspaceClient, pattern: str, workspace_path: str, max_workers: int, overwrite: bool
) -> FolderUploadResult:
    """Upload files matching a glob pattern."""
    # Expand the glob
    matches = glob.glob(pattern)
    if not matches:
        return FolderUploadResult(
            local_folder=os.path.dirname(pattern),
            remote_folder=workspace_path,
            total_files=0,
            successful=0,
            failed=1,
            results=[
                UploadResult(
                    local_path=pattern,
                    remote_path=workspace_path,
                    success=False,
                    error=f"No files match pattern: {pattern}",
                )
            ],
        )

    # Get the base directory - this is the directory containing the glob pattern
    # e.g., for "/path/to/folder/*.py", base_dir is "/path/to/folder"
    # For "/path/to/folder/*", base_dir is "/path/to/folder"
    pattern_dir = os.path.dirname(pattern)
    if pattern_dir:
        base_dir = os.path.abspath(pattern_dir)
    else:
        base_dir = os.getcwd()

    # Create workspace root directory
    try:
        w.workspace.mkdirs(workspace_path)
    except Exception:
        pass

    # Collect all files from all matches
    all_files = []
    all_dirs = set()

    for match in matches:
        match = os.path.abspath(match)
        if os.path.isfile(match):
            # Single file - use just its filename (files are at the base_dir level)
            rel_path = os.path.basename(match)
            all_files.append((match, rel_path))
        elif os.path.isdir(match):
            # Directory - collect all files recursively
            folder_name = os.path.basename(match)
            for local_file, rel_in_folder in _collect_files(match):
                rel_path = os.path.join(folder_name, rel_in_folder)
                all_files.append((local_file, rel_path))
                # Track parent dirs
                parent = str(Path(rel_path).parent)
                while parent != ".":
                    all_dirs.add(parent)
                    parent = str(Path(parent).parent)
            # Add the folder itself and its subdirs
            for subdir in _collect_directories(match):
                all_dirs.add(os.path.join(folder_name, subdir))
            all_dirs.add(folder_name)

    # Create all directories
    for dir_path in sorted(all_dirs):
        try:
            w.workspace.mkdirs(f"{workspace_path}/{dir_path}")
        except Exception:
            pass

    if not all_files:
        return FolderUploadResult(
            local_folder=base_dir,
            remote_folder=workspace_path,
            total_files=0,
            successful=0,
            failed=0,
            results=[],
        )

    # Upload all files in parallel
    return _parallel_upload(w, all_files, base_dir, workspace_path, max_workers, overwrite)


def _upload_folder(
    w: WorkspaceClient, local_folder: str, workspace_folder: str, max_workers: int, overwrite: bool
) -> FolderUploadResult:
    """Upload an entire folder."""
    local_folder = os.path.abspath(local_folder)

    # Create all directories first
    directories = _collect_directories(local_folder)
    for dir_path in directories:
        remote_dir = f"{workspace_folder}/{dir_path}"
        try:
            w.workspace.mkdirs(remote_dir)
        except Exception:
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
            local_folder=local_folder,
            remote_folder=workspace_folder,
            total_files=0,
            successful=0,
            failed=0,
            results=[],
        )

    return _parallel_upload(w, files, local_folder, workspace_folder, max_workers, overwrite)


def _parallel_upload(
    w: WorkspaceClient,
    files: List[tuple],
    local_base: str,
    workspace_base: str,
    max_workers: int,
    overwrite: bool,
) -> FolderUploadResult:
    """Upload files in parallel."""
    results = []
    successful = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {}
        for local_path, rel_path in files:
            remote_path = f"{workspace_base}/{rel_path.replace(os.sep, '/')}"
            future = executor.submit(_upload_single_file, w, local_path, remote_path, overwrite)
            future_to_file[future] = (local_path, remote_path)

        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1

    return FolderUploadResult(
        local_folder=local_base,
        remote_folder=workspace_base,
        total_files=len(files),
        successful=successful,
        failed=failed,
        results=results,
    )


def _is_protected_path(workspace_path: str) -> bool:
    """
    Check if a path is a protected root folder that should not be deleted.

    Protected paths include:
    - /Workspace/Users/<email> (user home folders)
    - /Users/<email> (legacy user home folders)
    - /Workspace/Shared (shared folder root)
    - /Workspace/Repos/<email> (user repos root)
    - /Repos/<email> (legacy repos root)

    Args:
        workspace_path: The workspace path to check

    Returns:
        True if the path is protected, False otherwise
    """
    # Normalize path: remove trailing slashes, handle /Workspace prefix
    path = workspace_path.rstrip("/")
    if not path:
        path = "/"

    # Pattern for user home folders: /Workspace/Users/<email> or /Users/<email>
    # Must have at least one more level (subfolder) to be deletable
    user_home_patterns = [
        r"^/Workspace/Users/[^/]+$",  # /Workspace/Users/user@example.com
        r"^/Users/[^/]+$",  # /Users/user@example.com
    ]

    # Pattern for repos root: /Workspace/Repos/<email> or /Repos/<email>
    repos_patterns = [
        r"^/Workspace/Repos/[^/]+$",  # /Workspace/Repos/user@example.com
        r"^/Repos/[^/]+$",  # /Repos/user@example.com
    ]

    # Check all protected patterns
    all_patterns = user_home_patterns + repos_patterns + [
        r"^/Workspace/Shared$",  # Shared folder root
        r"^/Workspace/Users$",  # Users folder root
        r"^/Users$",  # Legacy users root
        r"^/Workspace/Repos$",  # Repos folder root
        r"^/Repos$",  # Legacy repos root
        r"^/Workspace$",  # Workspace root
        r"^/$",  # Root
    ]

    for pattern in all_patterns:
        if re.match(pattern, path):
            return True

    return False


def delete_from_workspace(workspace_path: str, recursive: bool = False) -> DeleteResult:
    """
    Delete a file or folder from Databricks workspace.

    SAFETY: Cannot delete protected paths like user home folders. Path must be
    at least one level deeper than the user folder, e.g.:
    - OK: /Workspace/Users/user@example.com/my_folder
    - BLOCKED: /Workspace/Users/user@example.com

    Args:
        workspace_path: Path to file or folder in workspace
            (e.g., "/Workspace/Users/user@example.com/my-project")
        recursive: If True, delete folder and all contents. Required for non-empty folders.
            (default: False)

    Returns:
        DeleteResult with success status

    Example:
        >>> # Delete a single file
        >>> result = delete_from_workspace(
        ...     "/Workspace/Users/me@example.com/old_script.py"
        ... )

        >>> # Delete a folder and all contents
        >>> result = delete_from_workspace(
        ...     "/Workspace/Users/me@example.com/old_project",
        ...     recursive=True
        ... )
    """
    workspace_path = workspace_path.rstrip("/")

    # Safety check: prevent deletion of protected paths
    if _is_protected_path(workspace_path):
        return DeleteResult(
            workspace_path=workspace_path,
            success=False,
            error=f"Cannot delete protected path: {workspace_path}. "
            "User home folders, repos roots, and shared folders cannot be deleted. "
            "You must specify a subfolder within these locations.",
        )

    try:
        w = get_workspace_client()
        w.workspace.delete(workspace_path, recursive=recursive)
        return DeleteResult(workspace_path=workspace_path, success=True)

    except Exception as e:
        return DeleteResult(workspace_path=workspace_path, success=False, error=str(e))
