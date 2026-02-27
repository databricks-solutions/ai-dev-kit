"""
Unity Catalog - FGAC Policy Operations

Functions for managing Fine-Grained Access Control (FGAC) policies
via the Databricks Python SDK (WorkspaceClient.policies).

FGAC policies bind governed tags to masking UDFs or row filters, scoped to
catalogs, schemas, or tables, and targeted at specific principals.

Human-in-the-loop design:
  Mutations (create/update/delete) require an approval token from
  preview_policy_changes(). The token is an HMAC-signed binding of
  preview parameters to a timestamp — it ensures mutations match what
  was previewed and prevents parameter tampering.

  IMPORTANT: The token does NOT guarantee a human reviewed the preview.
  That responsibility falls on the MCP client (e.g., Claude Code prompts
  the user for confirmation between tool calls). The token only ensures
  that whatever was approved matches what gets executed.

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

_APPROVAL_SECRET = os.urandom(32).hex()
_ADMIN_GROUP = os.environ.get("FGAC_ADMIN_GROUP", "admins")
_TOKEN_TTL_SECONDS = 600  # 10 minutes


def _generate_approval_token(params: dict) -> str:
    """Generate an HMAC-based approval token binding preview params to a timestamp."""
    clean_params = {k: v for k, v in params.items() if v is not None}
    clean_params["timestamp"] = int(time.time())
    payload = json.dumps(clean_params, sort_keys=True)
    signature = hmac.new(_APPROVAL_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    b64_payload = base64.b64encode(payload.encode()).decode()
    return f"{signature}:{b64_payload}"


def _validate_approval_token(approval_token: str, current_params: dict) -> None:
    """Validate an approval token against current parameters.

    Raises ValueError if the token is invalid, expired, or params don't match.
    """
    params = dict(current_params)  # work on a copy to avoid mutating caller's dict

    try:
        signature, b64_payload = approval_token.split(":", 1)
    except (ValueError, AttributeError):
        raise ValueError("Malformed approval token: expected 'signature:payload' format")

    try:
        payload = base64.b64decode(b64_payload).decode()
    except Exception:
        raise ValueError("Malformed approval token: payload is not valid base64")

    expected_sig = hmac.new(_APPROVAL_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("Invalid approval token: signature verification failed")

    try:
        token_data = json.loads(payload)
    except json.JSONDecodeError:
        raise ValueError("Malformed approval token: payload is not valid JSON")

    ts = token_data.pop("timestamp", 0)
    if abs(time.time() - ts) > _TOKEN_TTL_SECONDS:
        raise ValueError("Expired approval token: please run preview again to get a new token")

    # Map preview action to mutation action
    action_map = {"CREATE": "create", "UPDATE": "update", "DELETE": "delete"}
    token_action = token_data.pop("action", None)
    current_action = params.pop("action", None)
    if token_action and current_action:
        if action_map.get(token_action) != current_action:
            raise ValueError(
                f"Approval token action mismatch: token is for '{token_action}'"
                f" but current action is '{current_action}'"
            )

    # Compare remaining params
    clean_current = {k: v for k, v in params.items() if v is not None}
    if token_data != clean_current:
        raise ValueError("Approval token parameter mismatch: params differ from what was previewed")


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
            f"Invalid securable_type: '{securable_type}'. Must be one of: {sorted(_VALID_SECURABLE_TYPES)}"
        )
    return normalized


def _validate_policy_type(policy_type: str) -> str:
    """Validate and normalize policy type."""
    normalized = policy_type.upper().replace("POLICY_TYPE_", "")
    if normalized not in _VALID_POLICY_TYPES:
        raise ValueError(f"Invalid policy_type: '{policy_type}'. Must be one of: {sorted(_VALID_POLICY_TYPES)}")
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
            p
            for p in policies
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

    Uses the Unity Catalog REST API directly because the Python SDK's
    TableInfo does not expose ``effective_masks`` (FGAC-derived masks).
    The ``/api/2.1/unity-catalog/tables/`` endpoint returns both direct
    column masks and effective masks from FGAC policies.

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

            column_masks.append(
                {
                    "column_name": col.get("name"),
                    "column_type": col.get("type_name"),
                    "mask_functions": mask_functions,
                }
            )

    row_filters = []
    row_filters_data = result.get("row_filters", {})
    if row_filters_data:
        for rf in row_filters_data.get("row_filters", []):
            row_filters.append(
                {
                    "function_name": rf.get("function_name"),
                    "input_column_names": rf.get("input_column_names", []),
                }
            )

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
        func_list.append(
            {
                "name": f.name,
                "full_name": f.full_name,
                "return_type": str(f.data_type) if f.data_type else None,
                "comment": getattr(f, "comment", None),
                "is_deterministic": getattr(f, "is_deterministic", None),
            }
        )

    return {
        "success": True,
        "catalog": catalog,
        "schema": schema,
        "function_count": len(func_list),
        "functions": func_list,
    }


# ---------------------------------------------------------------------------
# Analysis & Discovery
# ---------------------------------------------------------------------------


def get_column_tags_api(
    catalog: str,
    schema: str,
    table: str,
) -> Dict[str, Any]:
    """
    Get column-level tags for a table via the Tags API.

    Queries system.information_schema.column_tags to return governed and
    metadata tags applied to columns on the specified table.

    Args:
        catalog: Catalog name
        schema: Schema name
        table: Table name

    Returns:
        Dict with table name and list of column tag entries
    """
    _validate_identifier(catalog)
    _validate_identifier(schema)
    _validate_identifier(table)

    from .tags import query_column_tags

    tags = query_column_tags(catalog_filter=catalog, table_name=table)
    # Filter to the specific schema (query_column_tags filters by catalog and table but not schema)
    tags = [t for t in tags if t.get("schema_name") == schema]

    return {
        "success": True,
        "table": f"{catalog}.{schema}.{table}",
        "tags": tags,
    }


def get_schema_info(
    catalog: str,
    schema: str,
) -> Dict[str, Any]:
    """
    Get schema metadata via the Unity Catalog API.

    Args:
        catalog: Catalog name
        schema: Schema name

    Returns:
        Dict with serialized schema metadata
    """
    _validate_identifier(catalog)
    _validate_identifier(schema)

    from .schemas import get_schema

    schema_obj = get_schema(f"{catalog}.{schema}")
    return {
        "success": True,
        "schema": {
            "name": schema_obj.name,
            "full_name": schema_obj.full_name,
            "catalog_name": schema_obj.catalog_name,
            "owner": schema_obj.owner,
            "comment": schema_obj.comment,
            "created_at": schema_obj.created_at,
            "updated_at": schema_obj.updated_at,
        },
    }


def get_catalog_info(
    catalog: str,
) -> Dict[str, Any]:
    """
    Get catalog metadata via the Unity Catalog API.

    Args:
        catalog: Catalog name

    Returns:
        Dict with serialized catalog metadata
    """
    _validate_identifier(catalog)

    from .catalogs import get_catalog

    catalog_obj = get_catalog(catalog)
    return {
        "success": True,
        "catalog": {
            "name": catalog_obj.name,
            "owner": catalog_obj.owner,
            "comment": catalog_obj.comment,
            "created_at": catalog_obj.created_at,
            "updated_at": catalog_obj.updated_at,
        },
    }


def list_table_policies_in_schema(
    catalog: str,
    schema: str,
) -> Dict[str, Any]:
    """
    List all tables in a schema with their column masks and row filters.

    Enumerates tables in the schema and calls get_table_policies() on each.

    Args:
        catalog: Catalog name
        schema: Schema name

    Returns:
        Dict with table count and per-table policy details
    """
    _validate_identifier(catalog)
    _validate_identifier(schema)

    from .tables import list_tables

    tables = list_tables(catalog_name=catalog, schema_name=schema)
    table_results = []
    for t in tables:
        try:
            policies = get_table_policies(catalog=catalog, schema=schema, table=t.name)
            table_results.append(
                {
                    "table": t.name,
                    "column_masks": policies.get("column_masks", []),
                    "row_filters": policies.get("row_filters", []),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to get policies for table {t.name}: {e}")
            table_results.append(
                {
                    "table": t.name,
                    "column_masks": [],
                    "row_filters": [],
                    "error": str(e),
                }
            )

    return {
        "success": True,
        "catalog": catalog,
        "schema": schema,
        "table_count": len(table_results),
        "tables": table_results,
    }


def analyze_fgac_coverage(
    catalog: str,
    schema: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze FGAC policy coverage for a catalog or schema.

    Examines tagged columns, existing policies, and available masking UDFs
    to identify gaps where tagged columns lack policy coverage. Useful for
    the "analyze this catalog/schema and suggest FGAC policies" workflow.

    Args:
        catalog: Catalog name
        schema: Optional schema name. If omitted, analyzes all schemas in the catalog.

    Returns:
        Dict with coverage summary, gaps, existing policies, and available UDFs
    """
    _validate_identifier(catalog)
    if schema:
        _validate_identifier(schema)

    from .schemas import list_schemas
    from .tables import list_tables
    from .tags import query_column_tags

    # Determine schemas to scan
    if schema:
        schema_names = [schema]
        scope = f"SCHEMA {catalog}.{schema}"
    else:
        schema_objs = list_schemas(catalog)
        schema_names = [s.name for s in schema_objs if s.name != "information_schema"]
        scope = f"CATALOG {catalog}"

    # 1. Enumerate tables across schemas
    all_tables = []
    for s in schema_names:
        try:
            tables = list_tables(catalog_name=catalog, schema_name=s)
            all_tables.extend(tables)
        except Exception as e:
            logger.warning(f"Failed to list tables in {catalog}.{s}: {e}")

    # 2. Query column tags
    tagged_columns = query_column_tags(catalog_filter=catalog)
    if schema:
        tagged_columns = [t for t in tagged_columns if t.get("schema_name") == schema]

    # 3. List existing FGAC policies
    securable_type = "SCHEMA" if schema else "CATALOG"
    securable_fullname = f"{catalog}.{schema}" if schema else catalog
    policies_result = list_fgac_policies(
        securable_type=securable_type,
        securable_fullname=securable_fullname,
        include_inherited=True,
    )
    existing_policies = policies_result.get("policies", [])

    # 4. List masking UDFs across scanned schemas
    all_udfs = []
    for s in schema_names:
        try:
            udfs_result = get_masking_functions(catalog=catalog, schema=s)
            all_udfs.extend(udfs_result.get("functions", []))
        except Exception as e:
            logger.warning(f"Failed to list UDFs in {catalog}.{s}: {e}")

    # 5. Cross-reference: determine which tag/value pairs are covered by policies
    covered_tags = set()
    for p in existing_policies:
        for mc in p.get("match_columns") or []:
            condition = mc.get("condition", "")
            # Parse hasTagValue('key', 'value') or hasTag('key')
            if "hasTagValue" in condition:
                parts = condition.replace("hasTagValue(", "").rstrip(")").replace("'", "").split(", ")
                if len(parts) == 2:
                    covered_tags.add(f"{parts[0]}:{parts[1]}")
            elif "hasTag" in condition:
                tag = condition.replace("hasTag(", "").rstrip(")").replace("'", "")
                covered_tags.add(tag)

    # Build tag -> columns mapping for uncovered tags
    tag_columns: Dict[str, List[Dict[str, str]]] = {}
    for tc in tagged_columns:
        tag_key = f"{tc.get('tag_name')}:{tc.get('tag_value')}" if tc.get("tag_value") else tc.get("tag_name", "")
        if tag_key not in covered_tags:
            tag_columns.setdefault(tag_key, []).append(
                {
                    "table": f"{tc.get('catalog_name')}.{tc.get('schema_name')}.{tc.get('table_name')}",
                    "column": tc.get("column_name", ""),
                }
            )

    # Build unique tag keys for summary
    all_tag_keys = set()
    for tc in tagged_columns:
        tag_key = f"{tc.get('tag_name')}:{tc.get('tag_value')}" if tc.get("tag_value") else tc.get("tag_name", "")
        all_tag_keys.add(tag_key)

    uncovered_tags = all_tag_keys - covered_tags

    # Build gaps
    gaps = []
    for tag_key in sorted(uncovered_tags):
        if ":" in tag_key:
            t_name, t_value = tag_key.split(":", 1)
        else:
            t_name, t_value = tag_key, None

        columns = tag_columns.get(tag_key, [])
        suggestion = "No policy covers this tag. Consider creating a COLUMN_MASK policy."
        gaps.append(
            {
                "tag_name": t_name,
                "tag_value": t_value,
                "columns": columns,
                "suggestion": suggestion,
            }
        )

    return {
        "success": True,
        "scope": scope,
        "summary": {
            "tables_scanned": len(all_tables),
            "tagged_columns": len(tagged_columns),
            "existing_policies": len(existing_policies),
            "available_udfs": len(all_udfs),
            "covered_tags": sorted(covered_tags),
            "uncovered_tags": sorted(uncovered_tags),
        },
        "gaps": gaps,
        "existing_policies": existing_policies,
        "available_udfs": all_udfs,
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
    direct = [p for p in existing if getattr(p, "on_securable_fullname", None) == securable_fullname]

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

        tag_match = f"hasTagValue('{tag_name}', '{tag_value}')" if tag_value else f"hasTag('{tag_name}')"

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
    ptype = _validate_policy_type(policy_type)
    stype = _validate_securable_type(securable_type)
    # Identifier validation is handled by preview_policy_changes() — the token
    # binding ensures these values match what was already validated at preview time.
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
    _check_admin_group()

    from databricks.sdk.service.catalog import (
        ColumnMaskOptions,
        MatchColumn,
        PolicyInfo,
        RowFilterOptions,
    )

    # Build tag match condition
    tag_condition = f"hasTagValue('{tag_name}', '{tag_value}')" if tag_value else f"hasTag('{tag_name}')"
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
    _check_admin_group()

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
    stype = _validate_securable_type(securable_type)
    current_params = {
        "action": "delete",
        "policy_name": policy_name,
        "securable_type": stype,
        "securable_fullname": securable_fullname,
    }
    _validate_approval_token(approval_token, current_params)
    _check_admin_group()

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
