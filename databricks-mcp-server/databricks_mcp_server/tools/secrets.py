"""Secrets management tools - Manage secret scopes and secrets.

Provides 7 tools:
- create_or_update_secret_scope: idempotent scope creation
- list_secret_scopes: list all scopes
- delete_secret_scope: delete a scope and all secrets
- put_secret: create or update a secret (upsert)
- get_secret: get metadata (existence, byte length) without exposing value
- list_secrets: list keys in a scope (metadata only)
- delete_secret: delete a single secret
"""

from typing import Any, Dict, List, Optional

from databricks_tools_core.secrets import (
    create_secret_scope as _create_secret_scope,
    delete_secret as _delete_secret,
    delete_secret_scope as _delete_secret_scope,
    get_secret as _get_secret,
    list_secret_scopes as _list_secret_scopes,
    list_secrets as _list_secrets,
    put_secret as _put_secret,
)

from ..manifest import register_deleter
from ..server import mcp


def _delete_scope_resource(resource_id: str) -> None:
    _delete_secret_scope(scope=resource_id)


register_deleter("secret_scope", _delete_scope_resource)


@mcp.tool(timeout=30)
def create_or_update_secret_scope(
    scope: str,
    initial_manage_principal: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Idempotent create for secret scopes. Returns existing if already present.

    If the scope already exists, returns it with ``created: false``.
    Otherwise creates it and returns with ``created: true``.

    Args:
        scope: Scope name (max 128 chars; alphanumeric, dashes, underscores, periods)
        initial_manage_principal: Set to "users" to grant all workspace users
            MANAGE permission. If omitted, only the caller gets MANAGE.

    Returns:
        Dictionary with:
        - scope: Scope name
        - status: "created" or "already_exists"
        - created: True if newly created, False if already existed
        - message: Confirmation message

    Example:
        >>> create_or_update_secret_scope("my-app-secrets")
        {"scope": "my-app-secrets", "status": "created", "created": true, ...}
    """
    result = _create_secret_scope(scope=scope, initial_manage_principal=initial_manage_principal)

    if result.get("created"):
        try:
            from ..manifest import track_resource

            track_resource(resource_type="secret_scope", name=scope, resource_id=scope)
        except Exception:
            pass

    return result


@mcp.tool(timeout=30)
def list_secret_scopes() -> List[Dict[str, Any]]:
    """
    List all secret scopes in the workspace.

    Returns:
        List of scope dicts, each with:
        - name: Scope name
        - backend_type: "DATABRICKS" or "AZURE_KEYVAULT"

    Example:
        >>> list_secret_scopes()
        [{"name": "my-scope", "backend_type": "DATABRICKS"}, ...]
    """
    return _list_secret_scopes()


@mcp.tool(timeout=30)
def delete_secret_scope(scope: str) -> Dict[str, Any]:
    """
    Delete a secret scope and ALL secrets within it.

    This is irreversible. All secrets in the scope are permanently deleted.

    Args:
        scope: Name of the scope to delete

    Returns:
        Dictionary with:
        - scope: Scope name
        - status: "deleted" or "not_found"
        - message: Confirmation or error message

    Example:
        >>> delete_secret_scope("old-scope")
        {"scope": "old-scope", "status": "deleted", ...}
    """
    result = _delete_secret_scope(scope=scope)

    if result.get("status") == "deleted":
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="secret_scope", resource_id=scope)
        except Exception:
            pass

    return result


@mcp.tool(timeout=30)
def put_secret(
    scope: str,
    key: str,
    string_value: Optional[str] = None,
    bytes_value: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create or update a secret in a scope (upsert).

    Exactly one of string_value or bytes_value must be provided.
    The secret value is NOT echoed back in the response for security.

    Args:
        scope: Name of the secret scope
        key: Secret key (max 128 chars; alphanumeric, dashes, underscores, periods)
        string_value: The secret value as a string
        bytes_value: The secret value as base64-encoded bytes

    Returns:
        Dictionary with:
        - scope: Scope name
        - key: Secret key
        - status: "created"
        - message: Confirmation message

    Example:
        >>> put_secret("my-scope", "api-key", string_value="sk-abc123")
        {"scope": "my-scope", "key": "api-key", "status": "created", ...}
    """
    return _put_secret(scope=scope, key=key, string_value=string_value, bytes_value=bytes_value)


@mcp.tool(timeout=30)
def get_secret(scope: str, key: str) -> Dict[str, Any]:
    """
    Get metadata about a secret (existence and byte length).

    SECURITY: This tool intentionally does NOT return the secret value.
    It returns only whether the secret exists and its byte length, which
    is sufficient for debugging ("is it set?", "is it empty?", "is it
    the right size for an API key?") without exposing sensitive material.

    Args:
        scope: Name of the secret scope
        key: Secret key to check

    Returns:
        Dictionary with:
        - scope: Scope name
        - key: Secret key
        - exists: True if found
        - value_length: Byte length of the secret value

    Example:
        >>> get_secret("my-scope", "api-key")
        {"scope": "my-scope", "key": "api-key", "exists": true, "value_length": 42}
    """
    return _get_secret(scope=scope, key=key, return_value=False)


@mcp.tool(timeout=30)
def list_secrets(scope: str) -> List[Dict[str, Any]]:
    """
    List secret keys in a scope (metadata only, no values).

    Args:
        scope: Name of the secret scope

    Returns:
        List of secret metadata dicts, each with:
        - key: Secret key name
        - last_updated_timestamp: Milliseconds since epoch

    Example:
        >>> list_secrets("my-scope")
        [{"key": "api-key", "last_updated_timestamp": 1700000000000}, ...]
    """
    return _list_secrets(scope=scope)


@mcp.tool(timeout=30)
def delete_secret(scope: str, key: str) -> Dict[str, Any]:
    """
    Delete a secret from a scope.

    Args:
        scope: Name of the secret scope
        key: Secret key to delete

    Returns:
        Dictionary with:
        - scope: Scope name
        - key: Secret key
        - status: "deleted" or "not_found"
        - message: Confirmation or error message

    Example:
        >>> delete_secret("my-scope", "old-key")
        {"scope": "my-scope", "key": "old-key", "status": "deleted", ...}
    """
    return _delete_secret(scope=scope, key=key)
