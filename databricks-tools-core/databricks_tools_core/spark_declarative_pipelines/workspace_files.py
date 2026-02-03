"""
Spark Declarative Pipelines - Workspace File Operations

Functions for managing workspace files and directories for SDP pipelines.
"""

import base64
from typing import List
from databricks.sdk.service.workspace import (
    ObjectInfo,
    Language,
    ImportFormat,
    ExportFormat,
)

from ..auth import get_workspace_client


def list_files(path: str) -> List[ObjectInfo]:
    """
    List files and directories in a workspace path.

    Args:
        path: Workspace path to list

    Returns:
        List of ObjectInfo objects with file/directory metadata:
        - path: Full workspace path
        - object_type: DIRECTORY, NOTEBOOK, FILE, LIBRARY, or REPO
        - language: For notebooks (PYTHON, SQL, SCALA, R)
        - object_id: Unique identifier

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return list(w.workspace.list(path=path))


def get_file_status(path: str) -> ObjectInfo:
    """
    Get file or directory metadata.

    Args:
        path: Workspace path

    Returns:
        ObjectInfo object with metadata:
        - path: Full workspace path
        - object_type: DIRECTORY, NOTEBOOK, FILE, LIBRARY, or REPO
        - language: For notebooks (PYTHON, SQL, SCALA, R)
        - object_id: Unique identifier
        - size: File size in bytes (for files)
        - created_at: Creation timestamp
        - modified_at: Last modification timestamp

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    return w.workspace.get_status(path=path)


def read_file(path: str) -> str:
    """
    Read workspace file contents.

    Args:
        path: Workspace file path

    Returns:
        Decoded file contents as string

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    response = w.workspace.export(path=path, format=ExportFormat.SOURCE)

    # SDK returns ExportResponse with .content field (base64 encoded)
    return base64.b64decode(response.content).decode("utf-8")


def write_file(
    path: str, content: str, language: str = "PYTHON", overwrite: bool = True
) -> None:
    """
    Write or update workspace file.

    Args:
        path: Workspace file path
        content: File content as string
        language: PYTHON, SQL, SCALA, or R
        overwrite: If True, replaces existing file

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()

    # Convert language string to enum
    lang_map = {
        "PYTHON": Language.PYTHON,
        "SQL": Language.SQL,
        "SCALA": Language.SCALA,
        "R": Language.R,
    }
    lang_enum = lang_map.get(language.upper(), Language.PYTHON)

    # Base64 encode content
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    w.workspace.import_(
        path=path,
        content=content_b64,
        language=lang_enum,
        format=ImportFormat.SOURCE,
        overwrite=overwrite,
    )


def create_directory(path: str) -> None:
    """
    Create workspace directory.

    Args:
        path: Workspace directory path

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.workspace.mkdirs(path=path)


def delete_path(path: str, recursive: bool = False) -> None:
    """
    Delete workspace file or directory.

    Args:
        path: Workspace path to delete
        recursive: If True, recursively deletes directories

    Raises:
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    w.workspace.delete(path=path, recursive=recursive)
