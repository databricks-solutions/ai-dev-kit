"""Workspace object tools - Browse, read, and create workspace notebooks and directories.

Provides 5 tools:
- list_workspace_directory: browse workspace paths
- get_workspace_object_status: get metadata for a single object
- read_notebook: export notebook content in various formats
- create_notebook: create or overwrite notebooks from inline content
- create_workspace_directory: create directories (idempotent)
"""

from typing import Any, Dict, Optional

from databricks_tools_core.file import (
    create_notebook as _create_notebook,
    create_workspace_directory as _create_workspace_directory,
    get_workspace_object_status as _get_workspace_object_status,
    list_workspace_directory as _list_workspace_directory,
    read_notebook as _read_notebook,
)

from ..server import mcp


@mcp.tool(timeout=30)
def list_workspace_directory(path: str) -> Dict[str, Any]:
    """
    List files, notebooks, and directories at a workspace path.

    Use this to browse the workspace filesystem and discover notebooks, files,
    and directories. Each object includes its type (NOTEBOOK, FILE, DIRECTORY,
    LIBRARY, REPO) and language for notebooks.

    Args:
        path: Workspace path to list (e.g. "/Users/user@example.com",
            "/Repos/user@example.com/my-repo", "/Shared")

    Returns:
        Dictionary with:
        - path: The listed path
        - objects: List of object dicts with path, object_type, language, object_id, size
        - count: Number of objects returned

    Example:
        >>> list_workspace_directory("/Users/user@example.com")
        {"path": "/Users/user@example.com", "objects": [...], "count": 5}
    """
    return _list_workspace_directory(path=path)


@mcp.tool(timeout=30)
def get_workspace_object_status(path: str) -> Dict[str, Any]:
    """
    Get metadata for a workspace object (notebook, file, or directory).

    Returns type, language, size, and timestamps for a single workspace object.

    Args:
        path: Full workspace path to the object

    Returns:
        Dictionary with:
        - path: Full workspace path
        - object_type: NOTEBOOK, FILE, DIRECTORY, LIBRARY, or REPO
        - language: For notebooks — PYTHON, SQL, SCALA, or R
        - object_id: Unique identifier
        - size: File size in bytes (if applicable)
        - created_at: Creation timestamp
        - modified_at: Last modification timestamp

    Example:
        >>> get_workspace_object_status("/Users/user@example.com/my_notebook")
        {"path": "...", "object_type": "NOTEBOOK", "language": "PYTHON", ...}
    """
    return _get_workspace_object_status(path=path)


@mcp.tool(timeout=30)
def read_notebook(path: str, format: str = "SOURCE") -> Dict[str, Any]:
    """
    Read/export a notebook or workspace file.

    Use this to retrieve notebook source code or export in other formats.
    SOURCE format returns decoded text; binary formats return base64.

    Args:
        path: Workspace path of the notebook or file
        format: Export format (default: SOURCE). Options: SOURCE, HTML,
            JUPYTER, DBC, RAW, R_MARKDOWN, AUTO

    Returns:
        Dictionary with:
        - path: The notebook path
        - content: Notebook content (decoded string for text formats, base64 for binary)
        - format: The export format used
        - is_base64: True if content is base64-encoded (binary formats)

    Example:
        >>> read_notebook("/Users/user@example.com/my_notebook")
        {"path": "...", "content": "print('hello')", "format": "SOURCE", "is_base64": false}
    """
    return _read_notebook(path=path, format=format)


@mcp.tool(timeout=60)
def create_notebook(
    path: str,
    content: str,
    language: str = "PYTHON",
    format: str = "SOURCE",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Create or import a notebook in the workspace.

    Pass plain source code for SOURCE format. For JUPYTER, pass the raw JSON.
    Parent directories must already exist.

    Args:
        path: Workspace path for the notebook
            (e.g. "/Users/user@example.com/my_notebook")
        content: Notebook content as a string
        language: PYTHON (default), SQL, SCALA, or R
        format: SOURCE (default), JUPYTER, DBC, HTML, RAW, R_MARKDOWN, or AUTO
        overwrite: If true, replaces existing notebook (default: false)

    Returns:
        Dictionary with:
        - path: The created notebook path
        - language: Language used
        - format: Import format used
        - overwrite: Whether overwrite was enabled
        - success: True on success

    Example:
        >>> create_notebook("/Users/me/hello", "print('hello world')")
        {"path": "/Users/me/hello", "language": "PYTHON", "success": true, ...}
    """
    return _create_notebook(path=path, content=content, language=language, format=format, overwrite=overwrite)


@mcp.tool(timeout=30)
def create_workspace_directory(path: str) -> Dict[str, Any]:
    """
    Create a directory in the workspace, including parent directories.

    This is idempotent — calling it on an existing directory succeeds silently.

    Args:
        path: Workspace path for the directory
            (e.g. "/Users/user@example.com/my_project")

    Returns:
        Dictionary with:
        - path: The created directory path
        - success: True on success

    Example:
        >>> create_workspace_directory("/Users/me/my_project")
        {"path": "/Users/me/my_project", "success": true}
    """
    return _create_workspace_directory(path=path)
