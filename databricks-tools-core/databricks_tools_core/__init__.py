"""
Databricks Tools Core Library

High-level, AI-assistant-friendly functions for building Databricks projects.
Organized by product line for scalability.
"""

__version__ = "0.1.0"

# Auth utilities
from .auth import get_workspace_client, set_databricks_auth, clear_databricks_auth, get_current_username

__all__ = [
    "get_workspace_client",
    "set_databricks_auth",
    "clear_databricks_auth",
    "get_current_username",
]
