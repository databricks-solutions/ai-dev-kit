"""
File - Workspace File Operations

Functions for uploading files and folders to Databricks Workspace.
Uses Databricks Workspace API via SDK.
"""

import glob
import io
import os
import re
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
    error: Optional[str] = None


@dataclass
class FolderUploadResult:
    """Result from uploading a folder or multiple files"""

    local_folder: str
    remote_folder: str
    total_files: int
    successful: int
    failed: int
    results: List[UploadResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Returns True if all files were uploaded successfully"""
        return self.failed == 0 and self.total_files > 0

    def get_failed_uploads(self) -> List[UploadResult]:
        """Returns list of failed uploads"""
        return [r for r in self.results if not r.success]


@dataclass
class DeleteResult:
    """Result from a workspace delete operation"""

    workspace_path: str
    success: bool
    error: Optional[str] = None


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
        error_msg = str(e).lower()
        # Handle type mismatch errors (e.g., overwriting notebook with file or vice versa)
        # When overwrite=True, delete the existing item and retry
        if overwrite and "type mismatch" in error_msg:
            try:
                w.workspace.delete(remote_path)
                w.workspace.upload(
                    path=remote_path,
                    content=io.BytesIO(content),
                    format=ImportFormat.AUTO,
                    overwrite=False,
                )
                return UploadResult(local_path=local_path, remote_path=remote_path, success=True)
            except Exception as retry_error:
                return UploadResult(
                    local_path=local_path, remote_path=remote_path, success=False, error=str(retry_error)
                )
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


def upload_folder(
    local_folder: str, workspace_folder: str, max_workers: int = 10, overwrite: bool = True
) -> FolderUploadResult:
    """
    Upload an entire local folder to Databricks workspace.

    Uses parallel uploads with ThreadPoolExecutor for performance.
    Automatically handles all file types using ImportFormat.AUTO.

    Follows `cp -r` semantics:
    - With trailing slash or /* (e.g., "pipeline/" or "pipeline/*"): copies contents into workspace_folder
    - Without trailing slash (e.g., "pipeline"): creates workspace_folder/pipeline/

    Args:
        local_folder: Path to local folder to upload. Add trailing slash to copy
            contents only, omit to preserve folder name.
        workspace_folder: Target path in Databricks workspace
            (e.g., "/Workspace/Users/user@example.com/my-project")
        max_workers: Maximum number of parallel upload threads (default: 10)
        overwrite: Whether to overwrite existing files (default: True)

    Returns:
        FolderUploadResult with upload statistics and individual results

    Raises:
        FileNotFoundError: If local folder doesn't exist
        ValueError: If local folder is not a directory

    Example:
        >>> # Copy folder preserving name: creates /Workspace/.../dest/my-project/
        >>> result = upload_folder(
        ...     local_folder="/path/to/my-project",
        ...     workspace_folder="/Workspace/Users/me@example.com/dest"
        ... )
        >>> # Copy contents only: files go directly into /Workspace/.../dest/
        >>> result = upload_folder(
        ...     local_folder="/path/to/my-project/",
        ...     workspace_folder="/Workspace/Users/me@example.com/dest"
        ... )
        >>> print(f"Uploaded {result.successful}/{result.total_files} files")
        >>> if not result.success:
        ...     for failed in result.get_failed_uploads():
        ...         print(f"Failed: {failed.local_path} - {failed.error}")
    """
    # Check if user wants to copy contents only (trailing slash or /*) or preserve folder name
    # Supports: "folder/", "folder/*", "folder\\*" (Windows)
    copy_contents_suffixes = ("/", os.sep, "/*", os.sep + "*")
    copy_contents_only = local_folder.endswith(copy_contents_suffixes)

    # Strip /* or * suffix before validation
    clean_local_folder = local_folder.rstrip("*").rstrip("/").rstrip(os.sep)

    # Validate local folder
    local_folder_abs = os.path.abspath(clean_local_folder)
    if not os.path.exists(local_folder_abs):
        raise FileNotFoundError(f"Local folder not found: {local_folder_abs}")
    if not os.path.isdir(local_folder_abs):
        raise ValueError(f"Path is not a directory: {local_folder_abs}")

    # Normalize workspace path (remove trailing slash)
    workspace_folder = workspace_folder.rstrip("/")

    # If not copying contents only, append the source folder name to destination
    if not copy_contents_only:
        folder_name = os.path.basename(local_folder_abs)
        workspace_folder = f"{workspace_folder}/{folder_name}"

    # Use absolute path for file collection
    local_folder = local_folder_abs

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
            local_folder=local_folder,
            remote_folder=workspace_folder,
            total_files=0,
            successful=0,
            failed=0,
            results=[],
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
            local_path=local_path,
            remote_path=workspace_path,
            success=False,
            error=f"Path is not a file: {local_path}",
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


def _is_protected_path(workspace_path: str) -> bool:
    """
    Check if a workspace path is protected from deletion.

    Protected paths include:
    - Root paths (/, /Workspace, /Users, /Repos)
    - User home folders (/Workspace/Users/user@example.com, /Users/user@example.com)
    - Repos user roots (/Workspace/Repos/user@example.com, /Repos/user@example.com)
    - Shared folder root (/Workspace/Shared)

    Args:
        workspace_path: Path to check

    Returns:
        True if the path is protected, False otherwise
    """
    # Normalize path: remove trailing slashes
    path = workspace_path.rstrip("/")

    # Root paths are always protected
    protected_roots = {
        "",
        "/",
        "/Workspace",
        "/Workspace/Users",
        "/Workspace/Repos",
        "/Workspace/Shared",
        "/Users",
        "/Repos",
    }
    if path in protected_roots:
        return True

    # User home folders: /Workspace/Users/user@example.com or /Users/user@example.com
    # Pattern: exactly one level below Users (the email)
    user_home_pattern = r"^(/Workspace)?/Users/[^/]+$"
    if re.match(user_home_pattern, path):
        return True

    # Repos user roots: /Workspace/Repos/user@example.com or /Repos/user@example.com
    repos_pattern = r"^(/Workspace)?/Repos/[^/]+$"
    if re.match(repos_pattern, path):
        return True

    return False


def upload_to_workspace(
    local_path: str,
    workspace_path: str,
    max_workers: int = 10,
    overwrite: bool = True,
) -> FolderUploadResult:
    """
    Upload files or folders to Databricks workspace.

    Handles single files, folders, and glob patterns. This is the unified upload
    function that replaces both upload_file and upload_folder.

    Args:
        local_path: Path to local file, folder, or glob pattern.
            - Single file: "/path/to/file.py"
            - Folder: "/path/to/folder" (preserves folder name)
            - Folder contents: "/path/to/folder/" or "/path/to/folder/*"
            - Glob pattern: "/path/to/*.py"
            - Tilde expansion: "~/projects/file.py"
        workspace_path: Target path in Databricks workspace
        max_workers: Maximum parallel upload threads (default: 10)
        overwrite: Whether to overwrite existing files (default: True)

    Returns:
        FolderUploadResult with upload statistics

    Example:
        >>> # Upload single file
        >>> result = upload_to_workspace(
        ...     local_path="/path/to/script.py",
        ...     workspace_path="/Workspace/Users/me@example.com/script.py",
        ... )
        >>> # Upload folder preserving name
        >>> result = upload_to_workspace(
        ...     local_path="/path/to/project",
        ...     workspace_path="/Workspace/Users/me@example.com/dest",
        ... )
        >>> # Upload folder contents only
        >>> result = upload_to_workspace(
        ...     local_path="/path/to/project/",
        ...     workspace_path="/Workspace/Users/me@example.com/dest",
        ... )
        >>> # Upload with glob pattern
        >>> result = upload_to_workspace(
        ...     local_path="/path/to/*.py",
        ...     workspace_path="/Workspace/Users/me@example.com/scripts",
        ... )
    """
    # Expand ~ in path
    local_path = os.path.expanduser(local_path)

    # Normalize workspace path (remove trailing slash)
    workspace_path = workspace_path.rstrip("/")

    # Check if this is a glob pattern (contains * or ?)
    has_glob = "*" in local_path or "?" in local_path

    if has_glob:
        return _upload_glob_pattern(local_path, workspace_path, max_workers, overwrite)

    # Check if path exists
    if not os.path.exists(local_path.rstrip("/")):
        error_result = UploadResult(
            local_path=local_path,
            remote_path=workspace_path,
            success=False,
            error=f"Path not found: {local_path}",
        )
        return FolderUploadResult(
            local_folder=local_path,
            remote_folder=workspace_path,
            total_files=1,
            successful=0,
            failed=1,
            results=[error_result],
        )

    # Single file
    if os.path.isfile(local_path):
        result = upload_file(local_path, workspace_path, overwrite)
        return FolderUploadResult(
            local_folder=local_path,
            remote_folder=workspace_path,
            total_files=1,
            successful=1 if result.success else 0,
            failed=0 if result.success else 1,
            results=[result],
        )

    # Directory - use existing upload_folder logic
    return upload_folder(local_path, workspace_path, max_workers, overwrite)


def _upload_glob_pattern(
    pattern: str,
    workspace_path: str,
    max_workers: int = 10,
    overwrite: bool = True,
) -> FolderUploadResult:
    """
    Upload files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g., "*.py", "**/*.sql")
        workspace_path: Target workspace folder
        max_workers: Maximum parallel upload threads
        overwrite: Whether to overwrite existing files

    Returns:
        FolderUploadResult with upload statistics
    """
    # Expand the glob pattern
    matches = glob.glob(pattern, recursive=True)

    if not matches:
        error_result = UploadResult(
            local_path=pattern,
            remote_path=workspace_path,
            success=False,
            error=f"No files match pattern: {pattern}",
        )
        return FolderUploadResult(
            local_folder=pattern,
            remote_folder=workspace_path,
            total_files=1,
            successful=0,
            failed=1,
            results=[error_result],
        )

    # Separate files and directories
    files = [m for m in matches if os.path.isfile(m)]
    dirs = [m for m in matches if os.path.isdir(m)]

    # Get the base directory from the pattern for relative path calculation
    pattern_base = os.path.dirname(pattern.split("*")[0].rstrip("/")) or "."
    pattern_base = os.path.abspath(pattern_base)

    w = get_workspace_client()

    # Create workspace directory
    try:
        w.workspace.mkdirs(workspace_path)
    except Exception:
        pass

    results = []
    successful = 0
    failed = 0

    # Upload files from matched directories
    for dir_path in dirs:
        dir_files = _collect_files(dir_path)
        for local_file, rel_path in dir_files:
            # Calculate relative path from pattern base
            dir_name = os.path.basename(dir_path)
            remote_path = f"{workspace_path}/{dir_name}/{rel_path.replace(os.sep, '/')}"

            # Create parent directory
            parent_dir = str(Path(remote_path).parent)
            try:
                w.workspace.mkdirs(parent_dir)
            except Exception:
                pass

            result = _upload_single_file(w, local_file, remote_path, overwrite)
            results.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1

    # Upload individual files
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {}
        for local_file in files:
            # Use just the filename for the remote path
            filename = os.path.basename(local_file)
            remote_path = f"{workspace_path}/{filename}"
            future = executor.submit(_upload_single_file, w, local_file, remote_path, overwrite)
            future_to_file[future] = (local_file, remote_path)

        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)
            if result.success:
                successful += 1
            else:
                failed += 1

    return FolderUploadResult(
        local_folder=pattern,
        remote_folder=workspace_path,
        total_files=len(results),
        successful=successful,
        failed=failed,
        results=results,
    )


def delete_from_workspace(
    workspace_path: str,
    recursive: bool = False,
) -> DeleteResult:
    """
    Delete a file or folder from Databricks workspace.

    Includes safety checks to prevent accidental deletion of protected paths
    like user home folders, repos roots, and shared folder roots.

    Args:
        workspace_path: Path to delete in Databricks workspace
        recursive: If True, delete folder and all contents (default: False)

    Returns:
        DeleteResult with success status

    Example:
        >>> # Delete a single file
        >>> result = delete_from_workspace(
        ...     workspace_path="/Workspace/Users/me@example.com/old_file.py",
        ... )
        >>> # Delete a folder recursively
        >>> result = delete_from_workspace(
        ...     workspace_path="/Workspace/Users/me@example.com/old_project",
        ...     recursive=True,
        ... )
    """
    # Normalize path
    workspace_path = workspace_path.rstrip("/")

    # Safety check: prevent deletion of protected paths
    if _is_protected_path(workspace_path):
        return DeleteResult(
            workspace_path=workspace_path,
            success=False,
            error=f"Cannot delete protected path: {workspace_path}. "
            "User home folders, repos roots, and system folders are protected.",
        )

    try:
        w = get_workspace_client()
        w.workspace.delete(workspace_path, recursive=recursive)
        return DeleteResult(
            workspace_path=workspace_path,
            success=True,
        )
    except Exception as e:
        return DeleteResult(
            workspace_path=workspace_path,
            success=False,
            error=str(e),
        )
