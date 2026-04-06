"""Secrets management tools - Manage secret scopes and secrets.

Provides 1 consolidated tool:
- manage_secrets: action-based tool for all scope and secret operations
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

from ..manifest import register_deleter, remove_resource, track_resource
from ..server import mcp

_VALID_SECRETS_ACTIONS = (
    "create_scope",
    "list_scopes",
    "delete_scope",
    "put",
    "get",
    "list",
    "delete",
)


def _delete_scope_resource(resource_id: str) -> None:
    _delete_secret_scope(scope=resource_id)


register_deleter("secret_scope", _delete_scope_resource)


# ============================================================================
# Internal action handlers
# ============================================================================


def _action_create_scope(
    scope: Optional[str],
    initial_manage_principal: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a secret scope (idempotent)."""
    if not scope:
        return {"error": "Missing required parameter 'scope' for create_scope action"}

    result = _create_secret_scope(scope=scope, initial_manage_principal=initial_manage_principal)

    if result.get("created"):
        try:
            track_resource(resource_type="secret_scope", name=scope, resource_id=scope)
        except Exception:
            pass

    return result


def _action_list_scopes() -> List[Dict[str, Any]]:
    """List all secret scopes."""
    return _list_secret_scopes()


def _action_delete_scope(scope: Optional[str]) -> Dict[str, Any]:
    """Delete a secret scope and all its secrets."""
    if not scope:
        return {"error": "Missing required parameter 'scope' for delete_scope action"}

    result = _delete_secret_scope(scope=scope)

    if result.get("status") == "deleted":
        try:
            remove_resource(resource_type="secret_scope", resource_id=scope)
        except Exception:
            pass

    return result


def _action_put(
    scope: Optional[str],
    key: Optional[str],
    value: Optional[str],
    string_value: Optional[str],
    bytes_value: Optional[str],
) -> Dict[str, Any]:
    """Create or update a secret (upsert)."""
    if not scope:
        return {"error": "Missing required parameter 'scope' for put action"}
    if not key:
        return {"error": "Missing required parameter 'key' for put action"}

    # Allow 'value' as alias for 'string_value'
    effective_string_value = string_value or value

    if not effective_string_value and not bytes_value:
        return {"error": "Must provide one of: value, string_value, or bytes_value for put action"}

    return _put_secret(scope=scope, key=key, string_value=effective_string_value, bytes_value=bytes_value)


def _action_get(scope: Optional[str], key: Optional[str]) -> Dict[str, Any]:
    """Get secret metadata (existence and byte length)."""
    if not scope:
        return {"error": "Missing required parameter 'scope' for get action"}
    if not key:
        return {"error": "Missing required parameter 'key' for get action"}

    return _get_secret(scope=scope, key=key, return_value=False)


def _action_list(scope: Optional[str]) -> List[Dict[str, Any]]:
    """List secret keys in a scope."""
    if not scope:
        return {"error": "Missing required parameter 'scope' for list action"}

    return _list_secrets(scope=scope)


def _action_delete(scope: Optional[str], key: Optional[str]) -> Dict[str, Any]:
    """Delete a single secret from a scope."""
    if not scope:
        return {"error": "Missing required parameter 'scope' for delete action"}
    if not key:
        return {"error": "Missing required parameter 'key' for delete action"}

    return _delete_secret(scope=scope, key=key)


# ============================================================================
# Consolidated implementation (testable without MCP)
# ============================================================================


def _manage_secrets_impl(
    action: str,
    scope: Optional[str] = None,
    key: Optional[str] = None,
    value: Optional[str] = None,
    string_value: Optional[str] = None,
    bytes_value: Optional[str] = None,
) -> Dict[str, Any]:
    """Route to the correct action handler."""
    action = action.lower()

    if action == "create_scope":
        return _action_create_scope(scope=scope)
    elif action == "list_scopes":
        return _action_list_scopes()
    elif action == "delete_scope":
        return _action_delete_scope(scope=scope)
    elif action == "put":
        return _action_put(scope=scope, key=key, value=value, string_value=string_value, bytes_value=bytes_value)
    elif action == "get":
        return _action_get(scope=scope, key=key)
    elif action == "list":
        return _action_list(scope=scope)
    elif action == "delete":
        return _action_delete(scope=scope, key=key)
    else:
        valid = ", ".join(_VALID_SECRETS_ACTIONS)
        return {"error": f"Invalid action '{action}'. Must be one of: {valid}"}


# ============================================================================
# Consolidated MCP Tool
# ============================================================================


@mcp.tool(timeout=30)
def manage_secrets(
    action: str,
    scope: Optional[str] = None,
    key: Optional[str] = None,
    value: Optional[str] = None,
    string_value: Optional[str] = None,
    bytes_value: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage Databricks secret scopes and secrets.

    Actions: create_scope, list_scopes, delete_scope, put, get, list, delete.
    See databricks-secrets skill for details.

    Args:
        action: One of the actions listed above.
        scope: Secret scope name (required for all except list_scopes).
        key: Secret key name (required for put, get, delete).
        value: Secret value as string (for put).
        string_value: Secret string value (for put, alternative to value).
        bytes_value: Base64-encoded bytes value (for put).

    Returns:
        Dictionary with operation result.

    Example:
        >>> manage_secrets(action="create_scope", scope="my-scope")
        >>> manage_secrets(action="put", scope="my-scope", key="api-key", value="secret123")
        >>> manage_secrets(action="list", scope="my-scope")
    """
    return _manage_secrets_impl(
        action=action, scope=scope, key=key, value=value, string_value=string_value, bytes_value=bytes_value
    )
