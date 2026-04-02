"""
Secrets Management

Functions for managing Databricks secret scopes, secrets, and scope ACLs.
"""

from .secrets import (
    create_secret_scope,
    delete_secret,
    delete_secret_scope,
    get_secret,
    list_secret_scopes,
    list_secrets,
    put_secret,
)

__all__ = [
    "create_secret_scope",
    "delete_secret",
    "delete_secret_scope",
    "get_secret",
    "list_secret_scopes",
    "list_secrets",
    "put_secret",
]
