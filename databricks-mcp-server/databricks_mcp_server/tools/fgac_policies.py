"""
Unity Catalog FGAC Policy MCP Tool

Consolidated MCP tool for managing Fine-Grained Access Control (FGAC) policies.
Dispatches to core functions in databricks-tools-core based on the action parameter.
"""

from typing import Any, Dict, List, Optional

from databricks_tools_core.unity_catalog import (
    list_fgac_policies as _list_fgac_policies,
    get_fgac_policy as _get_fgac_policy,
    get_table_policies as _get_table_policies,
    get_masking_functions as _get_masking_functions,
    get_column_tags_api as _get_column_tags_api,
    get_schema_info as _get_schema_info,
    get_catalog_info as _get_catalog_info,
    list_table_policies_in_schema as _list_table_policies_in_schema,
    analyze_fgac_coverage as _analyze_fgac_coverage,
    check_policy_quota as _check_policy_quota,
    preview_policy_changes as _preview_policy_changes,
    create_fgac_policy as _create_fgac_policy,
    update_fgac_policy as _update_fgac_policy,
    delete_fgac_policy as _delete_fgac_policy,
)

from ..server import mcp


@mcp.tool
def manage_uc_fgac_policies(
    action: str,
    securable_type: Optional[str] = None,
    securable_fullname: Optional[str] = None,
    policy_name: Optional[str] = None,
    policy_type: Optional[str] = None,
    to_principals: Optional[List[str]] = None,
    except_principals: Optional[List[str]] = None,
    function_name: Optional[str] = None,
    tag_name: Optional[str] = None,
    tag_value: Optional[str] = None,
    comment: Optional[str] = None,
    include_inherited: bool = True,
    catalog: Optional[str] = None,
    schema: Optional[str] = None,
    table: Optional[str] = None,
    udf_catalog: Optional[str] = None,
    udf_schema: Optional[str] = None,
    preview_action: Optional[str] = None,
    approval_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Manage FGAC (Fine-Grained Access Control) policies on Unity Catalog securables.

    FGAC policies bind governed tags to masking UDFs or row filters, scoped to
    catalogs, schemas, or tables, and targeted at specific principals.

    Actions:
    - list: List policies on a securable. Params: securable_type, securable_fullname, include_inherited, policy_type
    - get: Get a specific policy. Params: policy_name, securable_type, securable_fullname
    - get_table_policies: Get column masks and row filters on a table. Params: catalog, schema, table
    - get_masking_functions: List masking UDFs in a schema. Params: catalog, schema
        (or udf_catalog, udf_schema for UDFs in a different catalog/schema)
    - get_column_tags: Get column-level tags for a table. Params: catalog, schema, table
    - get_schema_info: Get schema metadata. Params: catalog, schema
    - get_catalog_info: Get catalog metadata. Params: catalog
    - list_table_policies_in_schema: List all tables in a schema with their policies. Params: catalog, schema
    - analyze_coverage: Analyze FGAC policy coverage gaps. Params: catalog, schema (optional)
    - check_quota: Check policy quota on a securable. Params: securable_type, securable_fullname
    - preview: Preview policy changes without executing. Params: preview_action
        ("CREATE"/"UPDATE"/"DELETE"), policy_name, securable_type, securable_fullname,
        plus policy_type/function_name/tag_name/to_principals for CREATE
    - create: Create an FGAC policy. Params: policy_name,
        policy_type ("COLUMN_MASK"/"ROW_FILTER"), securable_type, securable_fullname,
        function_name, to_principals, tag_name, tag_value, except_principals, comment,
        approval_token (required, from preview)
    - update: Update policy principals or comment. Params: policy_name, securable_type, securable_fullname,
        to_principals, except_principals, comment, approval_token (required, from preview)
    - delete: Delete an FGAC policy. Params: policy_name, securable_type, securable_fullname,
        approval_token (required, from preview)

    Args:
        action: Operation to perform (see actions above)
        securable_type: "CATALOG", "SCHEMA", or "TABLE"
        securable_fullname: Fully qualified securable name (e.g., "my_catalog.my_schema")
        policy_name: Policy name
        policy_type: "COLUMN_MASK" or "ROW_FILTER" (for create/list/preview)
        to_principals: Users/groups the policy applies to
        except_principals: Excluded principals
        function_name: Fully qualified UDF name (e.g., "catalog.schema.mask_ssn")
        tag_name: Tag key to match columns on
        tag_value: Tag value to match (optional; omit for hasTag vs hasTagValue)
        comment: Policy description
        include_inherited: Include inherited policies in list (default: True)
        catalog: Catalog name (for get_table_policies, get_masking_functions)
        schema: Schema name (for get_table_policies, get_masking_functions)
        table: Table name (for get_table_policies)
        udf_catalog: Catalog where masking UDFs reside (for get_masking_functions; defaults to catalog)
        udf_schema: Schema where masking UDFs reside (for get_masking_functions; defaults to schema)
        preview_action: Sub-action for preview: "CREATE", "UPDATE", or "DELETE"
        approval_token: Approval token from preview action (required for create/update/delete)

    Returns:
        Dict with operation result
    """
    act = action.lower()

    if act == "list":
        return _list_fgac_policies(
            securable_type=securable_type,
            securable_fullname=securable_fullname,
            include_inherited=include_inherited,
            policy_type=policy_type,
        )
    elif act == "get":
        return _get_fgac_policy(
            policy_name=policy_name,
            securable_type=securable_type,
            securable_fullname=securable_fullname,
        )
    elif act == "get_table_policies":
        return _get_table_policies(
            catalog=catalog,
            schema=schema,
            table=table,
        )
    elif act == "get_masking_functions":
        return _get_masking_functions(
            catalog=udf_catalog or catalog,
            schema=udf_schema or schema,
        )
    elif act == "get_column_tags":
        return _get_column_tags_api(
            catalog=catalog,
            schema=schema,
            table=table,
        )
    elif act == "get_schema_info":
        return _get_schema_info(
            catalog=catalog,
            schema=schema,
        )
    elif act == "get_catalog_info":
        return _get_catalog_info(
            catalog=catalog,
        )
    elif act == "list_table_policies_in_schema":
        return _list_table_policies_in_schema(
            catalog=catalog,
            schema=schema,
        )
    elif act == "analyze_coverage":
        return _analyze_fgac_coverage(
            catalog=catalog,
            schema=schema,
        )
    elif act == "check_quota":
        return _check_policy_quota(
            securable_type=securable_type,
            securable_fullname=securable_fullname,
        )
    elif act == "preview":
        if not preview_action:
            raise ValueError("preview_action is required for preview action. Must be 'CREATE', 'UPDATE', or 'DELETE'.")
        return _preview_policy_changes(
            action=preview_action,
            policy_name=policy_name,
            securable_type=securable_type,
            securable_fullname=securable_fullname,
            policy_type=policy_type,
            to_principals=to_principals,
            except_principals=except_principals,
            function_name=function_name,
            tag_name=tag_name,
            tag_value=tag_value,
            comment=comment,
        )
    elif act == "create":
        return _create_fgac_policy(
            policy_name=policy_name,
            policy_type=policy_type,
            securable_type=securable_type,
            securable_fullname=securable_fullname,
            function_name=function_name,
            to_principals=to_principals,
            tag_name=tag_name,
            approval_token=approval_token,
            tag_value=tag_value,
            except_principals=except_principals,
            comment=comment or "",
        )
    elif act == "update":
        return _update_fgac_policy(
            policy_name=policy_name,
            securable_type=securable_type,
            securable_fullname=securable_fullname,
            approval_token=approval_token,
            to_principals=to_principals,
            except_principals=except_principals,
            comment=comment,
        )
    elif act == "delete":
        return _delete_fgac_policy(
            policy_name=policy_name,
            securable_type=securable_type,
            securable_fullname=securable_fullname,
            approval_token=approval_token,
        )

    raise ValueError(
        f"Invalid action: '{action}'. Valid actions: list, get, get_table_policies, "
        f"get_masking_functions, get_column_tags, get_schema_info, get_catalog_info, "
        f"list_table_policies_in_schema, analyze_coverage, check_quota, preview, create, update, delete"
    )
