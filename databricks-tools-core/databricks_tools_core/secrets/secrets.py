"""
Secret Scopes and Secrets Operations

Functions for managing Databricks secret scopes and the secrets within them.

SECURITY NOTE:
    Secret values are sensitive. The `get_secret` function defaults to
    `return_value=False`, which returns only metadata (existence, byte length)
    without exposing the actual value. This is the mode used by MCP tools to
    prevent secret values from leaking into LLM conversation context.

    The `return_value=True` option is available for programmatic use only
    (e.g. scripts, direct SDK calls) where the caller controls the output.
    It should NEVER be exposed through MCP tools.

    The `put_secret` function intentionally does NOT echo back the value
    in its response for the same reason.
"""

import base64
import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.errors import NotFound, ResourceAlreadyExists, ResourceDoesNotExist

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scopes
# ---------------------------------------------------------------------------


def create_secret_scope(
    scope: str,
    initial_manage_principal: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new Databricks-backed secret scope.

    Args:
        scope: Scope name (max 128 chars; alphanumeric, dashes, underscores, periods).
        initial_manage_principal: If set to "users", all workspace users get MANAGE
            permission. If omitted, only the caller gets MANAGE.

    Returns:
        Dictionary with:
        - scope: The created scope name
        - status: "created"
        - message: Confirmation message
    """
    client = get_workspace_client()

    try:
        client.secrets.create_scope(
            scope=scope,
            initial_manage_principal=initial_manage_principal,
        )
    except ResourceAlreadyExists:
        raise Exception(f"Secret scope '{scope}' already exists.")

    return {
        "scope": scope,
        "status": "created",
        "message": f"Secret scope '{scope}' created successfully.",
    }


def list_secret_scopes() -> List[Dict[str, Any]]:
    """List all secret scopes in the workspace.

    Returns:
        List of scope dicts, each with:
        - name: Scope name
        - backend_type: "DATABRICKS" or "AZURE_KEYVAULT"
    """
    client = get_workspace_client()

    scopes = list(client.secrets.list_scopes())

    return [
        {
            "name": s.name,
            "backend_type": s.backend_type.value if s.backend_type else None,
        }
        for s in scopes
    ]


def delete_secret_scope(scope: str) -> Dict[str, Any]:
    """Delete a secret scope and all secrets within it.

    This is irreversible. All secrets in the scope are permanently deleted.

    Args:
        scope: Name of the scope to delete.

    Returns:
        Dictionary with:
        - scope: Scope name
        - status: "deleted" or "not_found"
        - message: Confirmation or error message
    """
    client = get_workspace_client()

    try:
        client.secrets.delete_scope(scope=scope)
        return {
            "scope": scope,
            "status": "deleted",
            "message": f"Secret scope '{scope}' and all its secrets deleted.",
        }
    except (ResourceDoesNotExist, NotFound):
        return {
            "scope": scope,
            "status": "not_found",
            "message": f"Secret scope '{scope}' not found. It may have already been deleted.",
        }


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def put_secret(
    scope: str,
    key: str,
    string_value: Optional[str] = None,
    bytes_value: Optional[str] = None,
) -> Dict[str, Any]:
    """Create or update a secret in a scope.

    If a secret with the same key already exists, it is overwritten (upsert).
    Exactly one of string_value or bytes_value must be provided.

    The secret value is NOT included in the response for security.

    Args:
        scope: Name of the secret scope.
        key: Secret key name (max 128 chars; alphanumeric, dashes, underscores, periods).
        string_value: The secret value as a string.
        bytes_value: The secret value as base64-encoded bytes.

    Returns:
        Dictionary with:
        - scope: Scope name
        - key: Secret key
        - status: "created"
        - message: Confirmation message
    """
    if not string_value and not bytes_value:
        raise Exception("Exactly one of string_value or bytes_value must be provided.")
    if string_value and bytes_value:
        raise Exception("Exactly one of string_value or bytes_value must be provided, not both.")

    client = get_workspace_client()

    try:
        client.secrets.put_secret(
            scope=scope,
            key=key,
            string_value=string_value,
            bytes_value=bytes_value,
        )
    except (ResourceDoesNotExist, NotFound):
        raise Exception(f"Secret scope '{scope}' not found. Create it first with create_secret_scope().")

    return {
        "scope": scope,
        "key": key,
        "status": "created",
        "message": f"Secret '{key}' set in scope '{scope}'.",
    }


def get_secret(
    scope: str,
    key: str,
    return_value: bool = False,
) -> Dict[str, Any]:
    """Get a secret's metadata, and optionally its value.

    By default (return_value=False), returns only metadata: whether the secret
    exists, its key, and the byte length of its value. This is safe to use in
    MCP tools because no secret material is exposed to the LLM.

    When return_value=True, the decoded secret value is included in the response.
    This mode is for programmatic use only and MUST NOT be exposed through MCP
    tools, as it would leak secrets into LLM conversation context.

    Args:
        scope: Name of the secret scope.
        key: Secret key to retrieve.
        return_value: If True, include the decoded value. Defaults to False.
            WARNING: Only use True in programmatic contexts, never in MCP tools.

    Returns:
        Dictionary with:
        - scope: Scope name
        - key: Secret key
        - exists: True
        - value_length: Byte length of the secret value
        - value: The decoded secret string (only if return_value=True)
    """
    client = get_workspace_client()

    try:
        response = client.secrets.get_secret(scope=scope, key=key)
    except (ResourceDoesNotExist, NotFound):
        raise Exception(f"Secret '{key}' not found in scope '{scope}'.")

    # The API returns the value as base64-encoded string
    raw_value = response.value or ""
    try:
        decoded = base64.b64decode(raw_value)
        value_length = len(decoded)
    except Exception:
        value_length = len(raw_value)
        decoded = raw_value.encode("utf-8") if isinstance(raw_value, str) else raw_value

    result: Dict[str, Any] = {
        "scope": scope,
        "key": key,
        "exists": True,
        "value_length": value_length,
    }

    if return_value:
        try:
            result["value"] = decoded.decode("utf-8")
        except UnicodeDecodeError:
            result["value"] = raw_value  # Return base64 if not valid UTF-8

    return result


def list_secrets(scope: str) -> List[Dict[str, Any]]:
    """List secret keys in a scope.

    Returns metadata only — secret values are never included.

    Args:
        scope: Name of the secret scope.

    Returns:
        List of secret metadata dicts, each with:
        - key: Secret key name
        - last_updated_timestamp: Milliseconds since epoch
    """
    client = get_workspace_client()

    try:
        secrets = list(client.secrets.list_secrets(scope=scope))
    except (ResourceDoesNotExist, NotFound):
        raise Exception(f"Secret scope '{scope}' not found.")

    return [
        {
            "key": s.key,
            "last_updated_timestamp": s.last_updated_timestamp,
        }
        for s in secrets
    ]


def delete_secret(scope: str, key: str) -> Dict[str, Any]:
    """Delete a secret from a scope.

    Args:
        scope: Name of the secret scope.
        key: Secret key to delete.

    Returns:
        Dictionary with:
        - scope: Scope name
        - key: Secret key
        - status: "deleted" or "not_found"
        - message: Confirmation or error message
    """
    client = get_workspace_client()

    try:
        client.secrets.delete_secret(scope=scope, key=key)
        return {
            "scope": scope,
            "key": key,
            "status": "deleted",
            "message": f"Secret '{key}' deleted from scope '{scope}'.",
        }
    except (ResourceDoesNotExist, NotFound):
        return {
            "scope": scope,
            "key": key,
            "status": "not_found",
            "message": f"Secret '{key}' not found in scope '{scope}'.",
        }
