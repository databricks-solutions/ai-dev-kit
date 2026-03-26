"""
File - Workspace File Operations

Functions for uploading and deleting files and folders in Databricks Workspace.

Note: For Unity Catalog Volume file operations, use the unity_catalog module.
"""

from .workspace import (
    UploadResult,
    FolderUploadResult,
    DeleteResult,
    upload_to_workspace,
    delete_from_workspace,
)

__all__ = [
    # Workspace file operations
    "UploadResult",
    "FolderUploadResult",
    "DeleteResult",
    "upload_to_workspace",
    "delete_from_workspace",
]
