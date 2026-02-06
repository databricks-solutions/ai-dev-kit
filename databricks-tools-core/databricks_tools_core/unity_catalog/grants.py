"""
Unity Catalog - Grant Operations

Functions for managing permissions on Unity Catalog securables.
"""
from typing import Any, Dict, List, Optional
from databricks.sdk.service.catalog import (
    Privilege,
    PermissionsChange,
)

from ..auth import get_workspace_client


def _parse_securable_type(securable_type: str) -> str:
    """Parse securable type string to the API-expected string value.

    The GrantsAPI methods expect securable_type as a plain string,
    not a SecurableType enum instance.
    """
    valid_types = {
        "catalog", "schema", "table", "volume", "function",
        "storage_credential", "external_location", "connection",
        "share", "metastore",
    }
    key = securable_type.lower().replace("-", "_").replace(" ", "_")
    if key not in valid_types:
        raise ValueError(
            f"Invalid securable_type: '{securable_type}'. "
            f"Valid types: {sorted(valid_types)}"
        )
    return key


def _parse_privileges(privileges: list[str]) -> list[Privilege]:
    """Parse privilege strings to SDK enum values."""
    result = []
    for p in privileges:
        try:
            result.append(Privilege(p.upper().replace(" ", "_")))
        except ValueError:
            raise ValueError(
                f"Invalid privilege: '{p}'. "
                f"Common privileges: SELECT, MODIFY, CREATE_TABLE, CREATE_SCHEMA, "
                f"USE_CATALOG, USE_SCHEMA, ALL_PRIVILEGES, EXECUTE, "
                f"READ_VOLUME, WRITE_VOLUME, CREATE_VOLUME, CREATE_FUNCTION"
            )
    return result


def grant_privileges(
    securable_type: str,
    full_name: str,
    principal: str,
    privileges: list[str],
) -> dict[str, Any]:
    """
    Grant privileges to a principal on a UC securable.

    Args:
        securable_type: Type of object (catalog, schema, table, volume, function,
            storage_credential, external_location, connection, share)
        full_name: Full name of the securable object
        principal: User, group, or service principal to grant to
        privileges: List of privileges to grant (e.g., ["SELECT", "MODIFY"])

    Returns:
        Dict with grant result including privilege assignments

    Raises:
        ValueError: If securable_type or privileges are invalid
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)
    privs = _parse_privileges(privileges)

    result = w.grants.update(
        securable_type=stype,
        full_name=full_name,
        changes=[
            PermissionsChange(
                principal=principal,
                add=privs,
            )
        ],
    )
    return {
        "status": "granted",
        "securable_type": securable_type,
        "full_name": full_name,
        "principal": principal,
        "privileges": privileges,
        "assignments": [
            {"principal": a.principal, "privileges": [p.value for p in (a.privileges or [])]}
            for a in (result.privilege_assignments or [])
        ],
    }


def revoke_privileges(
    securable_type: str,
    full_name: str,
    principal: str,
    privileges: list[str],
) -> dict[str, Any]:
    """
    Revoke privileges from a principal on a UC securable.

    Args:
        securable_type: Type of object (catalog, schema, table, volume, function,
            storage_credential, external_location, connection, share)
        full_name: Full name of the securable object
        principal: User, group, or service principal to revoke from
        privileges: List of privileges to revoke (e.g., ["SELECT", "MODIFY"])

    Returns:
        Dict with revoke result

    Raises:
        ValueError: If securable_type or privileges are invalid
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)
    privs = _parse_privileges(privileges)

    result = w.grants.update(
        securable_type=stype,
        full_name=full_name,
        changes=[
            PermissionsChange(
                principal=principal,
                remove=privs,
            )
        ],
    )
    return {
        "status": "revoked",
        "securable_type": securable_type,
        "full_name": full_name,
        "principal": principal,
        "privileges": privileges,
        "assignments": [
            {"principal": a.principal, "privileges": [p.value for p in (a.privileges or [])]}
            for a in (result.privilege_assignments or [])
        ],
    }


def get_grants(
    securable_type: str,
    full_name: str,
    principal: str | None = None,
) -> dict[str, Any]:
    """
    Get current permission grants on a UC securable.

    Args:
        securable_type: Type of object
        full_name: Full name of the securable object
        principal: Optional - filter grants for specific principal

    Returns:
        Dict with privilege assignments list

    Raises:
        ValueError: If securable_type is invalid
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)

    result = w.grants.get(
        securable_type=stype,
        full_name=full_name,
        principal=principal,
    )
    return {
        "securable_type": securable_type,
        "full_name": full_name,
        "assignments": [
            {"principal": a.principal, "privileges": [p.value for p in (a.privileges or [])]}
            for a in (result.privilege_assignments or [])
        ],
    }


def get_effective_grants(
    securable_type: str,
    full_name: str,
    principal: str | None = None,
) -> dict[str, Any]:
    """
    Get effective (inherited + direct) permission grants on a UC securable.

    Args:
        securable_type: Type of object
        full_name: Full name of the securable object
        principal: Optional - filter grants for specific principal

    Returns:
        Dict with effective privilege assignments (includes inherited permissions)

    Raises:
        ValueError: If securable_type is invalid
        DatabricksError: If API request fails
    """
    w = get_workspace_client()
    stype = _parse_securable_type(securable_type)

    result = w.grants.get_effective(
        securable_type=stype,
        full_name=full_name,
        principal=principal,
    )
    return {
        "securable_type": securable_type,
        "full_name": full_name,
        "effective_assignments": [
            {
                "principal": a.principal,
                "privileges": [
                    {"privilege": p.privilege.value if p.privilege else None, "inherited_from_name": p.inherited_from_name, "inherited_from_type": p.inherited_from_type.value if p.inherited_from_type else None}
                    for p in (a.privileges or [])
                ],
            }
            for a in (result.privilege_assignments or [])
        ],
    }
