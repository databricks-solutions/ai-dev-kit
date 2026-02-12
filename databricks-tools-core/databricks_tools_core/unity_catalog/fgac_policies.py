"""
Unity Catalog - FGAC Policy Operations

Functions for managing Fine-Grained Access Control (FGAC) policies
via the Databricks Python SDK (WorkspaceClient.policies).

FGAC policies bind governed tags to masking UDFs or row filters, scoped to
catalogs, schemas, or tables, and targeted at specific principals.

Policy quotas:
  - Catalog: 10 policies max
  - Schema:  10 policies max
  - Table:    5 policies max
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.\-]*$")

_VALID_SECURABLE_TYPES = {"CATALOG", "SCHEMA", "TABLE"}
_VALID_POLICY_TYPES = {"COLUMN_MASK", "ROW_FILTER"}
_POLICY_QUOTAS = {"CATALOG": 10, "SCHEMA": 10, "TABLE": 5}

_APPROVAL_SECRET = os.environ.get("FGAC_APPROVAL_SECRET", "fgac-default-dev-secret")
_ADMIN_GROUP = os.environ.get("FGAC_ADMIN_GROUP", "admins")
_TOKEN_TTL_SECONDS = 600  # 10 minutes
def _generate_approval_token(params: dict) -> str:
    """Generate an HMAC-based approval token binding preview params to a timestamp."""
    clean_params = {k: v for k, v in params.items() if v is not None}
    clean_params["timestamp"] = int(time.time())
    payload = json.dumps(clean_params, sort_keys=True)
    signature = hmac.new(
        _APPROVAL_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    b64_payload = base64.b64encode(payload.encode()).decode()
    return f"{signature}:{b64_payload}"


def _validate_approval_token(approval_token: str, current_params: dict) -> None:
    """Validate an approval token against current parameters.

    Raises ValueError if the token is invalid, expired, or params don't match.
    """
    try:
        signature, b64_payload = approval_token.split(":", 1)
    except (ValueError, AttributeError):
        raise ValueError("Invalid or expired approval token")

    try:
        payload = base64.b64decode(b64_payload).decode()
    except Exception:
        raise ValueError("Invalid or expired approval token")

    expected_sig = hmac.new(
        _APPROVAL_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("Invalid or expired approval token")

    try:
        token_data = json.loads(payload)
    except json.JSONDecodeError:
        raise ValueError("Invalid or expired approval token")

    ts = token_data.pop("timestamp", 0)
    if abs(time.time() - ts) > _TOKEN_TTL_SECONDS:
        raise ValueError("Invalid or expired approval token")

    # Map preview action to mutation action
    action_map = {"CREATE": "create", "UPDATE": "update", "DELETE": "delete"}
    token_action = token_data.pop("action", None)
    current_action = current_params.pop("action", None)
    if token_action and current_action:
        if action_map.get(token_action) != current_action:
            raise ValueError("Invalid or expired approval token")

    # Compare remaining params
    clean_current = {k: v for k, v in current_params.items() if v is not None}
    if token_data != clean_current:
        raise ValueError("Invalid or expired approval token")


def _check_admin_group() -> dict:
    """Verify the current user belongs to the configured admin group.

    Raises PermissionError if user is not a member.
    """
    w = get_workspace_client()
    me = w.current_user.me()
    group_names = [g.display for g in (me.groups or []) if g.display]
    if _ADMIN_GROUP not in group_names:
        raise PermissionError(
            f"User '{me.user_name}' is not a member of admin group '{_ADMIN_GROUP}'. "
            f"FGAC mutating operations require membership in the '{_ADMIN_GROUP}' group."
        )
    return {"is_admin": True, "user": me.user_name, "admin_group": _ADMIN_GROUP}


def _validate_identifier(name: str) -> str:
    """Validate a SQL identifier to prevent injection."""
    if not _IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Invalid SQL identifier: '{name}'")
    return name


def _validate_securable_type(securable_type: str) -> str:
    """Validate and normalize securable type."""
    normalized = securable_type.upper()
    if normalized not in _VALID_SECURABLE_TYPES:
        raise ValueError(
            f"Invalid securable_type: '{securable_type}'. "
            f"Must be one of: {sorted(_VALID_SECURABLE_TYPES)}"
        )
    return normalized


def _validate_policy_type(policy_type: str) -> str:
    """Validate and normalize policy type."""
    normalized = policy_type.upper().replace("POLICY_TYPE_", "")
    if normalized not in _VALID_POLICY_TYPES:
        raise ValueError(
            f"Invalid policy_type: '{policy_type}'. "
            f"Must be one of: {sorted(_VALID_POLICY_TYPES)}"
        )
    return normalized


def _to_policy_type_enum(policy_type: str):
    """Convert a policy type string to the SDK PolicyType enum."""
    from databricks.sdk.service.catalog import PolicyType

    normalized = policy_type.upper().replace("POLICY_TYPE_", "")
    if normalized == "COLUMN_MASK":
        return PolicyType.POLICY_TYPE_COLUMN_MASK
    elif normalized == "ROW_FILTER":
        return PolicyType.POLICY_TYPE_ROW_FILTER
    raise ValueError(f"Invalid policy_type: '{policy_type}'")


def _to_securable_type_enum(securable_type: str):
    """Convert a securable type string to the SDK SecurableType enum."""
    from databricks.sdk.service.catalog import SecurableType

    return SecurableType(securable_type.upper())


def _policy_to_dict(policy: Any) -> Dict[str, Any]:
    """Convert a policy SDK object to a serializable dict."""
    if hasattr(policy, "as_dict"):
        return policy.as_dict()
    return {
        "name": getattr(policy, "name", None),
        "policy_type": getattr(policy, "policy_type", None),
        "to_principals": getattr(policy, "to_principals", []),
        "except_principals": getattr(policy, "except_principals", []),
        "on_securable_type": getattr(policy, "on_securable_type", None),
        "on_securable_fullname": getattr(policy, "on_securable_fullname", None),
        "for_securable_type": getattr(policy, "for_securable_type", None),
        "column_mask": getattr(policy, "column_mask", None),
        "row_filter": getattr(policy, "row_filter", None),
        "match_columns": getattr(policy, "match_columns", []),
        "comment": getattr(policy, "comment", None),
    }


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def list_fgac_policies(
    securable_type: str,
    securable_fullname: str,
    include_inherited: bool = True,
    policy_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List FGAC policies on a catalog, schema, or table.

    Args:
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified name (e.g., "my_catalog.my_schema")
        include_inherited: Include policies inherited from parent securables
        policy_type: Optional filter — "COLUMN_MASK" or "ROW_FILTER"

    Returns:
        Dict with policy_count and policies list
    """
    stype = _validate_securable_type(securable_type)
    _validate_identifier(securable_fullname)

    w = get_workspace_client()
    policies = list(
        w.policies.list_policies(
            on_securable_type=stype,
            on_securable_fullname=securable_fullname,
            include_inherited=include_inherited,
        )
    )

    if policy_type:
        ptype = _validate_policy_type(policy_type)
        # SDK returns POLICY_TYPE_COLUMN_MASK / POLICY_TYPE_ROW_FILTER
        sdk_ptype = f"POLICY_TYPE_{ptype}"
        policies = [
            p for p in policies
            if str(getattr(p, "policy_type", "")) in (ptype, sdk_ptype)
            or (p.as_dict() if hasattr(p, "as_dict") else {}).get("policy_type") in (ptype, sdk_ptype)
        ]

    policy_dicts = [_policy_to_dict(p) for p in policies]
    return {
        "success": True,
        "securable_type": stype,
        "securable_fullname": securable_fullname,
        "policy_count": len(policy_dicts),
        "policies": policy_dicts,
    }


def get_fgac_policy(
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
) -> Dict[str, Any]:
    """
    Get details for a specific FGAC policy by name.

    Args:
        policy_name: Policy name
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified securable name

    Returns:
        Dict with policy details
    """
    stype = _validate_securable_type(securable_type)
    _validate_identifier(securable_fullname)

    w = get_workspace_client()
    policy = w.policies.get_policy(
        on_securable_type=stype,
        on_securable_fullname=securable_fullname,
        name=policy_name,
    )

    return {
        "success": True,
        "policy": _policy_to_dict(policy),
    }


def get_table_policies(
    catalog: str,
    schema: str,
    table: str,
) -> Dict[str, Any]:
    """
    Get column masks and row filters applied to a specific table.

    Uses the Unity Catalog REST API directly to retrieve effective
    column masks and row filters, including those derived from FGAC policies.

    Args:
        catalog: Catalog name
        schema: Schema name
        table: Table name

    Returns:
        Dict with column_masks and row_filters lists
    """
    _validate_identifier(catalog)
    _validate_identifier(schema)
    _validate_identifier(table)
    full_name = f"{catalog}.{schema}.{table}"

    w = get_workspace_client()
    result = w.api_client.do("GET", f"/api/2.1/unity-catalog/tables/{full_name}")

    column_masks = []
    for col in result.get("columns", []):
        masks = col.get("column_masks", {})
        effective_masks = col.get("effective_masks", [])

        if masks.get("column_masks") or effective_masks:
            mask_functions = []
            for m in masks.get("column_masks", []):
                mask_functions.append(m.get("function_name"))
            for m in effective_masks:
                fn = m.get("function_name")
                if fn and fn not in mask_functions:
                    mask_functions.append(fn)

            column_masks.append({
                "column_name": col.get("name"),
                "column_type": col.get("type_name"),
                "mask_functions": mask_functions,
            })

    row_filters = []
    row_filters_data = result.get("row_filters", {})
    if row_filters_data:
        for rf in row_filters_data.get("row_filters", []):
            row_filters.append({
                "function_name": rf.get("function_name"),
                "input_column_names": rf.get("input_column_names", []),
            })

    return {
        "success": True,
        "table": full_name,
        "column_masks": column_masks,
        "row_filters": row_filters,
    }


def get_masking_functions(
    catalog: str,
    schema: str,
) -> Dict[str, Any]:
    """
    List masking UDFs in a schema.

    Retrieves all user-defined functions in the specified schema and returns
    their metadata for use in FGAC policy creation.

    Args:
        catalog: Catalog name
        schema: Schema name

    Returns:
        Dict with list of functions and their metadata
    """
    _validate_identifier(catalog)
    _validate_identifier(schema)

    w = get_workspace_client()
    functions = list(w.functions.list(catalog_name=catalog, schema_name=schema))

    func_list = []
    for f in functions:
        func_list.append({
            "name": f.name,
            "full_name": f.full_name,
            "return_type": str(f.data_type) if f.data_type else None,
            "comment": getattr(f, "comment", None),
            "is_deterministic": getattr(f, "is_deterministic", None),
        })

    return {
        "success": True,
        "catalog": catalog,
        "schema": schema,
        "function_count": len(func_list),
        "functions": func_list,
    }


# ---------------------------------------------------------------------------
# Quota checking
# ---------------------------------------------------------------------------


def check_policy_quota(
    securable_type: str,
    securable_fullname: str,
) -> Dict[str, Any]:
    """
    Check if the policy quota allows creating a new policy.

    Policy quotas: CATALOG=10, SCHEMA=10, TABLE=5.

    Args:
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified securable name

    Returns:
        Dict with current count, max allowed, and whether creation is allowed
    """
    stype = _validate_securable_type(securable_type)
    _validate_identifier(securable_fullname)

    w = get_workspace_client()
    existing = list(
        w.policies.list_policies(
            on_securable_type=stype,
            on_securable_fullname=securable_fullname,
        )
    )

    # Count only direct policies (not inherited)
    direct = [
        p for p in existing
        if getattr(p, "on_securable_fullname", None) == securable_fullname
    ]

    max_policies = _POLICY_QUOTAS.get(stype, 10)
    return {
        "success": True,
        "securable_type": stype,
        "securable_fullname": securable_fullname,
        "current": len(direct),
        "max": max_policies,
        "can_create": len(direct) < max_policies,
    }


# ---------------------------------------------------------------------------
# Preview (human-in-the-loop gate)
# ---------------------------------------------------------------------------


def preview_policy_changes(
    action: str,
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
    policy_type: Optional[str] = None,
    to_principals: Optional[List[str]] = None,
    except_principals: Optional[List[str]] = None,
    function_name: Optional[str] = None,
    tag_name: Optional[str] = None,
    tag_value: Optional[str] = None,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Preview policy changes without executing. Human-in-the-loop gate.

    Generates the equivalent SQL and returns it for review. No changes
    are made until a subsequent create/update/delete call.

    Args:
        action: "CREATE", "UPDATE", or "DELETE"
        policy_name: Policy name
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified securable name
        policy_type: "COLUMN_MASK" or "ROW_FILTER" (required for CREATE)
        to_principals: Principals the policy applies to
        except_principals: Excluded principals
        function_name: Fully qualified UDF name (required for CREATE).
            Can reference any catalog/schema, not just the policy scope.
        tag_name: Tag key to match (required for CREATE)
        tag_value: Tag value to match (optional; omit for hasTag vs hasTagValue)
        comment: Policy description

    Returns:
        Dict with preview details, equivalent SQL, warnings, and approval flag
    """
    action = action.upper()
    if action not in ("CREATE", "UPDATE", "DELETE"):
        raise ValueError(f"Invalid action: '{action}'. Must be CREATE, UPDATE, or DELETE")

    stype = _validate_securable_type(securable_type)
    _validate_identifier(securable_fullname)
    warnings = []

    safe_except = list(except_principals) if except_principals else []

    if action == "CREATE":
        if not policy_type:
            raise ValueError("policy_type is required for CREATE action")
        ptype = _validate_policy_type(policy_type)
        if not function_name:
            raise ValueError("function_name is required for CREATE action")
        if not tag_name:
            raise ValueError("tag_name is required for CREATE action")
        if not to_principals:
            raise ValueError("to_principals is required for CREATE action")

        tag_match = (
            f"hasTagValue('{tag_name}', '{tag_value}')" if tag_value
            else f"hasTag('{tag_name}')"
        )

        principals_sql = ", ".join(f"`{p}`" for p in to_principals)
        except_sql = ", ".join(f"`{p}`" for p in safe_except) if safe_except else ""

        if ptype == "COLUMN_MASK":
            sql_lines = [
                f"CREATE OR REPLACE POLICY {policy_name}",
                f"ON {stype} {securable_fullname}",
            ]
            if comment:
                sql_lines.append(f"COMMENT '{comment}'")
            sql_lines += [
                f"COLUMN MASK {function_name}",
                f"TO {principals_sql}",
            ]
            if except_sql:
                sql_lines.append(f"EXCEPT {except_sql}")
            sql_lines += [
                "FOR TABLES",
                f"MATCH COLUMNS {tag_match} AS masked_col",
                "ON COLUMN masked_col;",
            ]
        else:  # ROW_FILTER
            sql_lines = [
                f"CREATE OR REPLACE POLICY {policy_name}",
                f"ON {stype} {securable_fullname}",
            ]
            if comment:
                sql_lines.append(f"COMMENT '{comment}'")
            sql_lines += [
                f"ROW FILTER {function_name}",
                f"TO {principals_sql}",
            ]
            if except_sql:
                sql_lines.append(f"EXCEPT {except_sql}")
            sql_lines += [
                "FOR TABLES",
                f"MATCH COLUMNS {tag_match} AS filter_col",
                "USING COLUMNS (filter_col);",
            ]

        equivalent_sql = "\n".join(sql_lines)
        preview = {
            "policy_name": policy_name,
            "policy_type": ptype,
            "securable": f"{stype} {securable_fullname}",
            "to_principals": to_principals,
            "except_principals": safe_except,
            "function": function_name,
            "tag_match": tag_match,
            "equivalent_sql": equivalent_sql,
        }

    elif action == "UPDATE":
        changes = {}
        if to_principals is not None:
            changes["to_principals"] = to_principals
        if except_principals is not None:
            changes["except_principals"] = safe_except
        if comment is not None:
            changes["comment"] = comment

        if not changes:
            warnings.append("No changes specified for UPDATE")

        preview = {
            "policy_name": policy_name,
            "securable": f"{stype} {securable_fullname}",
            "changes": changes,
            "equivalent_sql": f"-- UPDATE via SDK: w.policies.update_policy(name='{policy_name}', ...)",
            "note": "update_policy only modifies principals and comment. "
            "To change UDF, tags, or scope, drop and recreate.",
        }

    else:  # DELETE
        equivalent_sql = f"DROP POLICY {policy_name} ON {stype} {securable_fullname};"
        preview = {
            "policy_name": policy_name,
            "securable": f"{stype} {securable_fullname}",
            "equivalent_sql": equivalent_sql,
        }
        warnings.append("This action is irreversible. The policy will be permanently removed.")

    # Generate approval token binding these params
    token_params = {
        "action": action,
        "policy_name": policy_name,
        "securable_type": stype,
        "securable_fullname": securable_fullname,
    }
    if policy_type:
        token_params["policy_type"] = _validate_policy_type(policy_type)
    if to_principals is not None:
        token_params["to_principals"] = to_principals
    if except_principals is not None:
        token_params["except_principals"] = safe_except
    if function_name is not None:
        token_params["function_name"] = function_name
    if tag_name is not None:
        token_params["tag_name"] = tag_name
    if tag_value is not None:
        token_params["tag_value"] = tag_value
    if comment is not None:
        token_params["comment"] = comment

    approval_token = _generate_approval_token(token_params)

    return {
        "success": True,
        "action": action,
        "preview": preview,
        "warnings": warnings,
        "requires_approval": True,
        "approval_token": approval_token,
        "message": "Review the preview above. Reply 'approve' to execute, passing the approval_token.",
    }


# ---------------------------------------------------------------------------
# Management (mutating operations)
# ---------------------------------------------------------------------------


def create_fgac_policy(
    policy_name: str,
    policy_type: str,
    securable_type: str,
    securable_fullname: str,
    function_name: str,
    to_principals: List[str],
    tag_name: str,
    approval_token: str,
    tag_value: Optional[str] = None,
    except_principals: Optional[List[str]] = None,
    comment: str = "",
) -> Dict[str, Any]:
    """
    Create a new FGAC policy (COLUMN_MASK or ROW_FILTER).

    Requires a valid approval_token from preview_policy_changes() and
    the caller must be a member of the configured admin group.

    Args:
        policy_name: Policy name (must be unique within the securable scope)
        policy_type: "COLUMN_MASK" or "ROW_FILTER"
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified securable name
        function_name: Fully qualified UDF name (e.g., "catalog.schema.mask_ssn").
            The UDF can reside in any catalog/schema, not just the policy scope.
            For example, a policy on "prod.finance" can use "governance.masking_udfs.mask_ssn".
        to_principals: Users/groups the policy applies to
        tag_name: Tag key to match columns on
        approval_token: Token from preview_policy_changes()
        tag_value: Tag value to match (optional; omit for hasTag vs hasTagValue)
        except_principals: Excluded principals
        comment: Policy description

    Returns:
        Dict with creation status and policy details
    """
    _check_admin_group()
    ptype = _validate_policy_type(policy_type)
    stype = _validate_securable_type(securable_type)
    current_params = {
        "action": "create",
        "policy_name": policy_name,
        "policy_type": ptype,
        "securable_type": stype,
        "securable_fullname": securable_fullname,
        "function_name": function_name,
        "to_principals": to_principals,
        "tag_name": tag_name,
    }
    if tag_value is not None:
        current_params["tag_value"] = tag_value
    if except_principals is not None:
        current_params["except_principals"] = list(except_principals)
    if comment:
        current_params["comment"] = comment
    _validate_approval_token(approval_token, current_params)

    _validate_identifier(securable_fullname)
    _validate_identifier(function_name)

    from databricks.sdk.service.catalog import (
        ColumnMaskOptions,
        MatchColumn,
        PolicyInfo,
        RowFilterOptions,
    )

    # Build tag match condition
    tag_condition = (
        f"hasTagValue('{tag_name}', '{tag_value}')" if tag_value
        else f"hasTag('{tag_name}')"
    )
    alias = "masked_col" if ptype == "COLUMN_MASK" else "filter_col"
    match_columns = [MatchColumn(alias=alias, condition=tag_condition)]

    # Build PolicyInfo
    policy_info = PolicyInfo(
        name=policy_name,
        policy_type=_to_policy_type_enum(ptype),
        on_securable_type=_to_securable_type_enum(stype),
        on_securable_fullname=securable_fullname,
        for_securable_type=_to_securable_type_enum("TABLE"),
        to_principals=to_principals,
        except_principals=list(except_principals) if except_principals else None,
        comment=comment,
        match_columns=match_columns,
    )

    if ptype == "COLUMN_MASK":
        policy_info.column_mask = ColumnMaskOptions(
            function_name=function_name,
            on_column=alias,
        )
    else:  # ROW_FILTER
        policy_info.row_filter = RowFilterOptions(
            function_name=function_name,
        )

    w = get_workspace_client()
    policy = w.policies.create_policy(policy_info=policy_info)

    return {
        "success": True,
        "policy_name": policy_name,
        "action": "created",
        "details": {
            "policy_type": ptype,
            "on_securable": f"{stype} {securable_fullname}",
            "function": function_name,
            "to_principals": to_principals,
            "except_principals": list(except_principals) if except_principals else [],
            "tag_match": f"{tag_name}={tag_value}" if tag_value else tag_name,
        },
        "policy": _policy_to_dict(policy),
    }


def update_fgac_policy(
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
    approval_token: str,
    to_principals: Optional[List[str]] = None,
    except_principals: Optional[List[str]] = None,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update an existing FGAC policy's principals or comment.

    Requires a valid approval_token from preview_policy_changes() and
    the caller must be a member of the configured admin group.

    Only principals and comment can be modified. To change the UDF, tag
    matching, or scope, drop and recreate the policy.

    Args:
        policy_name: Policy name
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified securable name
        approval_token: Token from preview_policy_changes()
        to_principals: Updated list of principals the policy applies to
        except_principals: Updated excluded principals
        comment: Updated policy description

    Returns:
        Dict with update status and applied changes
    """
    _check_admin_group()
    stype = _validate_securable_type(securable_type)
    current_params = {
        "action": "update",
        "policy_name": policy_name,
        "securable_type": stype,
        "securable_fullname": securable_fullname,
    }
    if to_principals is not None:
        current_params["to_principals"] = to_principals
    if except_principals is not None:
        current_params["except_principals"] = list(except_principals)
    if comment is not None:
        current_params["comment"] = comment
    _validate_approval_token(approval_token, current_params)

    _validate_identifier(securable_fullname)

    from databricks.sdk.service.catalog import PolicyInfo

    w = get_workspace_client()

    # Get existing policy to preserve required fields
    existing = w.policies.get_policy(
        on_securable_type=stype,
        on_securable_fullname=securable_fullname,
        name=policy_name,
    )

    # Build update PolicyInfo with existing required fields
    policy_info = PolicyInfo(
        to_principals=existing.to_principals,
        for_securable_type=existing.for_securable_type,
        policy_type=existing.policy_type,
    )

    changes: Dict[str, Any] = {}
    update_fields = []

    if to_principals is not None:
        policy_info.to_principals = to_principals
        changes["to_principals"] = to_principals
        update_fields.append("to_principals")

    if except_principals is not None:
        policy_info.except_principals = list(except_principals)
        changes["except_principals"] = list(except_principals)
        update_fields.append("except_principals")

    if comment is not None:
        policy_info.comment = comment
        changes["comment"] = comment
        update_fields.append("comment")

    policy = w.policies.update_policy(
        on_securable_type=stype,
        on_securable_fullname=securable_fullname,
        name=policy_name,
        policy_info=policy_info,
        update_mask=",".join(update_fields) if update_fields else None,
    )

    return {
        "success": True,
        "policy_name": policy_name,
        "action": "updated",
        "changes": changes,
        "policy": _policy_to_dict(policy),
    }


def delete_fgac_policy(
    policy_name: str,
    securable_type: str,
    securable_fullname: str,
    approval_token: str,
) -> Dict[str, Any]:
    """
    Delete an FGAC policy.

    Requires a valid approval_token from preview_policy_changes() and
    the caller must be a member of the configured admin group.

    This is irreversible. The policy will be permanently removed.

    Args:
        policy_name: Policy name
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified securable name
        approval_token: Token from preview_policy_changes()

    Returns:
        Dict with deletion status
    """
    _check_admin_group()
    stype = _validate_securable_type(securable_type)
    _validate_identifier(securable_fullname)
    current_params = {
        "action": "delete",
        "policy_name": policy_name,
        "securable_type": stype,
        "securable_fullname": securable_fullname,
    }
    _validate_approval_token(approval_token, current_params)

    w = get_workspace_client()
    w.policies.delete_policy(
        on_securable_type=stype,
        on_securable_fullname=securable_fullname,
        name=policy_name,
    )

    return {
        "success": True,
        "policy_name": policy_name,
        "action": "deleted",
    }
