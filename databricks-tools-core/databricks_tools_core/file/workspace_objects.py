"""
Workspace Object Operations

Functions for browsing, reading, and creating workspace objects (notebooks, files, directories).

Note: For upload/delete of local files to workspace, use the `workspace` module.
      For Unity Catalog Volume file operations, use the `unity_catalog` module.
"""

import base64
import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from databricks.sdk.service.workspace import (
    ExportFormat,
    ImportFormat,
    Language,
    ObjectInfo,
    ObjectType,
)

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)

# Formats that can be decoded to UTF-8 text
_TEXT_FORMATS = {"SOURCE", "RAW", "R_MARKDOWN"}

_VALID_EXPORT_FORMATS = {e.name for e in ExportFormat}
_VALID_IMPORT_FORMATS = {e.name for e in ImportFormat}
_VALID_LANGUAGES = {e.name for e in Language}


def _serialize_object_info(obj: ObjectInfo) -> Dict[str, Any]:
    """Convert an ObjectInfo dataclass to a serializable dict."""
    return {
        "path": obj.path,
        "object_type": obj.object_type.name if obj.object_type else None,
        "language": obj.language.name if obj.language else None,
        "object_id": obj.object_id,
        "size": obj.size,
        "created_at": obj.created_at,
        "modified_at": obj.modified_at,
    }


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


def list_workspace_directory(path: str) -> Dict[str, Any]:
    """List files and directories in a workspace path.

    Args:
        path: Workspace path to list (e.g. "/Users/user@example.com").

    Returns:
        Dictionary with:
        - path: The listed path
        - objects: List of object dicts with path, object_type, language, object_id, size
        - count: Number of objects returned
    """
    client = get_workspace_client()

    try:
        items = list(client.workspace.list(path=path))
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Path not found: {path}", "path": path}

    objects = [_serialize_object_info(obj) for obj in items]
    return {"path": path, "objects": objects, "count": len(objects)}


def get_workspace_object_status(path: str) -> Dict[str, Any]:
    """Get metadata for a workspace object (notebook, file, or directory).

    Args:
        path: Workspace path to inspect.

    Returns:
        Dictionary with object metadata: path, object_type, language, object_id,
        size, created_at, modified_at.
    """
    client = get_workspace_client()

    try:
        status = client.workspace.get_status(path=path)
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Path not found: {path}", "path": path}

    return _serialize_object_info(status)


def read_notebook(path: str, format: str = "SOURCE") -> Dict[str, Any]:
    """Read/export a notebook or workspace file.

    Args:
        path: Workspace path of the notebook or file.
        format: Export format — SOURCE, HTML, JUPYTER, DBC, RAW, R_MARKDOWN, or AUTO.
            Defaults to SOURCE (plain text source code).

    Returns:
        Dictionary with:
        - path: The notebook path
        - content: Notebook content (decoded string for text formats, base64 for binary)
        - format: The export format used
        - is_base64: True if content is base64-encoded (binary formats)
    """
    format_upper = format.upper()
    if format_upper not in _VALID_EXPORT_FORMATS:
        return {"error": f"Invalid format '{format}'. Valid: {sorted(_VALID_EXPORT_FORMATS)}", "path": path}

    client = get_workspace_client()

    try:
        response = client.workspace.export(path=path, format=ExportFormat[format_upper])
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Path not found: {path}", "path": path}

    content = response.content
    is_base64 = format_upper not in _TEXT_FORMATS

    if not is_base64 and content:
        content = base64.b64decode(content).decode("utf-8")

    return {"path": path, "content": content, "format": format_upper, "is_base64": is_base64}


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------


def create_notebook(
    path: str,
    content: str,
    language: str = "PYTHON",
    format: str = "SOURCE",
    overwrite: bool = False,
) -> Dict[str, Any]:
    """Create or import a notebook in the workspace.

    Args:
        path: Workspace path for the notebook (e.g. "/Users/user@example.com/my_notebook").
        content: Notebook content as a string. For SOURCE format, pass plain source code.
            For JUPYTER format, pass the raw JSON string.
        language: Notebook language — PYTHON, SQL, SCALA, or R. Defaults to PYTHON.
        format: Import format — SOURCE, JUPYTER, DBC, HTML, RAW, R_MARKDOWN, or AUTO.
            Defaults to SOURCE.
        overwrite: If True, overwrites an existing notebook at the path. Defaults to False.

    Returns:
        Dictionary with:
        - path: The created notebook path
        - language: Language used
        - format: Import format used
        - overwrite: Whether overwrite was enabled
        - success: True on success
    """
    language_upper = language.upper()
    if language_upper not in _VALID_LANGUAGES:
        return {"error": f"Invalid language '{language}'. Valid: {sorted(_VALID_LANGUAGES)}", "path": path}

    format_upper = format.upper()
    if format_upper not in _VALID_IMPORT_FORMATS:
        return {"error": f"Invalid format '{format}'. Valid: {sorted(_VALID_IMPORT_FORMATS)}", "path": path}

    client = get_workspace_client()
    content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

    client.workspace.import_(
        path=path,
        content=content_b64,
        language=Language[language_upper],
        format=ImportFormat[format_upper],
        overwrite=overwrite,
    )

    return {
        "path": path,
        "language": language_upper,
        "format": format_upper,
        "overwrite": overwrite,
        "success": True,
    }


def create_workspace_directory(path: str) -> Dict[str, Any]:
    """Create a directory in the workspace. Creates parent directories as needed.

    Args:
        path: Workspace path for the directory.

    Returns:
        Dictionary with:
        - path: The created directory path
        - success: True on success
    """
    client = get_workspace_client()
    client.workspace.mkdirs(path=path)
    return {"path": path, "success": True}
