"""
Unity Catalog MCP Tools

Consolidated MCP tools for Unity Catalog operations.
8 tools covering: objects, grants, storage, connections,
tags, security policies, monitors, and sharing.
"""

import logging
from typing import Any, Dict, List

from databricks_tools_core.identity import get_default_tags
from databricks_tools_core.unity_catalog import (
    # Metric Views
    create_metric_view as _create_metric_view,
    alter_metric_view as _alter_metric_view,
    drop_metric_view as _drop_metric_view,
    describe_metric_view as _describe_metric_view,
    query_metric_view as _query_metric_view,
    grant_metric_view as _grant_metric_view,
)
from databricks_tools_core.unity_catalog import (
    # Catalogs
    list_catalogs as _list_catalogs,
    get_catalog as _get_catalog,
    create_catalog as _create_catalog,
    update_catalog as _update_catalog,
    delete_catalog as _delete_catalog,
    # Schemas
    list_schemas as _list_schemas,
    get_schema as _get_schema,
    create_schema as _create_schema,
    update_schema as _update_schema,
    delete_schema as _delete_schema,
    # Volumes
    list_volumes as _list_volumes,
    get_volume as _get_volume,
    create_volume as _create_volume,
    update_volume as _update_volume,
    delete_volume as _delete_volume,
    # Functions
    list_functions as _list_functions,
    get_function as _get_function,
    delete_function as _delete_function,
    # Grants
    grant_privileges as _grant_privileges,
    revoke_privileges as _revoke_privileges,
    get_grants as _get_grants,
    get_effective_grants as _get_effective_grants,
    # Storage
    list_storage_credentials as _list_storage_credentials,
    get_storage_credential as _get_storage_credential,
    create_storage_credential as _create_storage_credential,
    update_storage_credential as _update_storage_credential,
    delete_storage_credential as _delete_storage_credential,
    validate_storage_credential as _validate_storage_credential,
    list_external_locations as _list_external_locations,
    get_external_location as _get_external_location,
    create_external_location as _create_external_location,
    update_external_location as _update_external_location,
    delete_external_location as _delete_external_location,
    # Connections
    list_connections as _list_connections,
    get_connection as _get_connection,
    create_connection as _create_connection,
    update_connection as _update_connection,
    delete_connection as _delete_connection,
    create_foreign_catalog as _create_foreign_catalog,
    # Tags
    set_tags as _set_tags,
    unset_tags as _unset_tags,
    set_comment as _set_comment,
    query_table_tags as _query_table_tags,
    query_column_tags as _query_column_tags,
    # Security policies
    create_security_function as _create_security_function,
    set_row_filter as _set_row_filter,
    drop_row_filter as _drop_row_filter,
    set_column_mask as _set_column_mask,
    drop_column_mask as _drop_column_mask,
    # Monitors
    create_monitor as _create_monitor,
    get_monitor as _get_monitor,
    run_monitor_refresh as _run_monitor_refresh,
    list_monitor_refreshes as _list_monitor_refreshes,
    delete_monitor as _delete_monitor,
    # Sharing
    list_shares as _list_shares,
    get_share as _get_share,
    create_share as _create_share,
    add_table_to_share as _add_table_to_share,
    remove_table_from_share as _remove_table_from_share,
    delete_share as _delete_share,
    grant_share_to_recipient as _grant_share_to_recipient,
    revoke_share_from_recipient as _revoke_share_from_recipient,
    list_recipients as _list_recipients,
    get_recipient as _get_recipient,
    create_recipient as _create_recipient,
    rotate_recipient_token as _rotate_recipient_token,
    delete_recipient as _delete_recipient,
    list_providers as _list_providers,
    get_provider as _get_provider,
    list_provider_shares as _list_provider_shares,
)

from ..manifest import register_deleter
from ..server import mcp

logger = logging.getLogger(__name__)


def _delete_catalog_resource(resource_id: str) -> None:
    _delete_catalog(catalog_name=resource_id, force=True)


def _delete_schema_resource(resource_id: str) -> None:
    _delete_schema(full_schema_name=resource_id)


def _delete_volume_resource(resource_id: str) -> None:
    _delete_volume(full_volume_name=resource_id)


register_deleter("catalog", _delete_catalog_resource)
register_deleter("schema", _delete_schema_resource)
register_deleter("volume", _delete_volume_resource)


def _auto_tag(object_type: str, full_name: str) -> None:
    """Best-effort: apply default tags to a newly created UC object.

    Tags are set individually so that a tag-policy violation on one key
    does not prevent the remaining tags from being applied.
    """
    for key, value in get_default_tags().items():
        try:
            _set_tags(object_type=object_type, full_name=full_name, tags={key: value})
        except Exception:
            logger.warning("Failed to set tag %s=%s on %s '%s'", key, value, object_type, full_name, exc_info=True)


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Convert SDK objects to serializable dicts."""
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "as_dict"):
        return obj.as_dict()
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)
    return vars(obj)


def _to_dict_list(items: list) -> List[Dict[str, Any]]:
    """Convert a list of SDK objects to serializable dicts."""
    return [_to_dict(item) for item in items]


# =============================================================================
# Tool 1: manage_uc_objects
# =============================================================================


@mcp.tool
def manage_uc_objects(
    object_type: str,
    action: str,
    name: str = None,
    full_name: str = None,
    catalog_name: str = None,
    schema_name: str = None,
    comment: str = None,
    owner: str = None,
    storage_root: str = None,
    volume_type: str = None,
    storage_location: str = None,
    new_name: str = None,
    properties: Dict[str, str] = None,
    isolation_mode: str = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Manage Unity Catalog namespace objects: catalogs, schemas, volumes, functions.

    Actions per object_type:
    - catalog: create, get, list, update, delete
    - schema: create, get, list, update, delete
    - volume: create, get, list, update, delete
    - function: get, list, delete (create functions via manage_uc_security_policies or execute_sql)

    Args:
        object_type: "catalog", "schema", "volume", or "function"
        action: "create", "get", "list", "update", or "delete"
        name: Object name (for create)
        full_name: Full qualified name (for get/update/delete).
                   Format: "catalog" or "catalog.schema" or "catalog.schema.object".
        catalog_name: Parent catalog (for list schemas/volumes/functions, or create schema)
        schema_name: Parent schema (for list volumes/functions, or create volume)
        comment: Description (for create/update)
        owner: Owner (for create/update)
        storage_root: Managed storage location (for catalog/schema create)
        volume_type: "MANAGED" or "EXTERNAL" (for volume create, default: MANAGED)
        storage_location: Cloud storage URL (for external volumes)
        new_name: New name (for update/rename)
        properties: Key-value properties (for catalog create)
        isolation_mode: "OPEN" or "ISOLATED" (for catalog update)
        force: Force deletion (default: False)

    Returns:
        Dict with operation result. For list: {"items": [...]}. For get/create/update: object details.
    """
    otype = object_type.lower()

    if otype == "catalog":
        if action == "create":
            result = _to_dict(
                _create_catalog(
                    name=name,
                    comment=comment,
                    storage_root=storage_root,
                    properties=properties,
                )
            )
            _auto_tag("catalog", name)
            try:
                from ..manifest import track_resource

                track_resource(
                    resource_type="catalog",
                    name=name,
                    resource_id=result.get("name", name),
                )
            except Exception:
                pass
            return result
        elif action == "get":
            return _to_dict(_get_catalog(catalog_name=full_name or name))
        elif action == "list":
            return {"items": _to_dict_list(_list_catalogs())}
        elif action == "update":
            return _to_dict(
                _update_catalog(
                    catalog_name=full_name or name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                    isolation_mode=isolation_mode,
                )
            )
        elif action == "delete":
            _delete_catalog(catalog_name=full_name or name, force=force)
            try:
                from ..manifest import remove_resource

                remove_resource(resource_type="catalog", resource_id=full_name or name)
            except Exception:
                pass
            return {"status": "deleted", "catalog": full_name or name}

    elif otype == "schema":
        if action == "create":
            result = _to_dict(_create_schema(catalog_name=catalog_name, schema_name=name, comment=comment))
            _auto_tag("schema", f"{catalog_name}.{name}")
            try:
                from ..manifest import track_resource

                full_schema = result.get("full_name") or f"{catalog_name}.{name}"
                track_resource(resource_type="schema", name=full_schema, resource_id=full_schema)
            except Exception:
                logger.warning("Failed to track schema in manifest", exc_info=True)
            return result
        elif action == "get":
            return _to_dict(_get_schema(full_schema_name=full_name))
        elif action == "list":
            return {"items": _to_dict_list(_list_schemas(catalog_name=catalog_name))}
        elif action == "update":
            return _to_dict(
                _update_schema(
                    full_schema_name=full_name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                )
            )
        elif action == "delete":
            _delete_schema(full_schema_name=full_name)
            try:
                from ..manifest import remove_resource

                remove_resource(resource_type="schema", resource_id=full_name)
            except Exception:
                pass
            return {"status": "deleted", "schema": full_name}

    elif otype == "volume":
        if action == "create":
            result = _to_dict(
                _create_volume(
                    catalog_name=catalog_name,
                    schema_name=schema_name,
                    name=name,
                    volume_type=volume_type or "MANAGED",
                    comment=comment,
                    storage_location=storage_location,
                )
            )
            _auto_tag("volume", f"{catalog_name}.{schema_name}.{name}")
            try:
                from ..manifest import track_resource

                full_vol = result.get("full_name") or f"{catalog_name}.{schema_name}.{name}"
                track_resource(resource_type="volume", name=full_vol, resource_id=full_vol)
            except Exception:
                pass
            return result
        elif action == "get":
            return _to_dict(_get_volume(full_volume_name=full_name))
        elif action == "list":
            return {"items": _to_dict_list(_list_volumes(catalog_name=catalog_name, schema_name=schema_name))}
        elif action == "update":
            return _to_dict(
                _update_volume(
                    full_volume_name=full_name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                )
            )
        elif action == "delete":
            _delete_volume(full_volume_name=full_name)
            try:
                from ..manifest import remove_resource

                remove_resource(resource_type="volume", resource_id=full_name)
            except Exception:
                pass
            return {"status": "deleted", "volume": full_name}

    elif otype == "function":
        if action == "create":
            return {
                "error": """Functions cannot be created via SDK. Use manage_uc_security_policies tool with 
                action='create_security_function' or execute_sql with a CREATE FUNCTION statement."""
            }
        elif action == "get":
            return _to_dict(_get_function(full_function_name=full_name))
        elif action == "list":
            return {"items": _to_dict_list(_list_functions(catalog_name=catalog_name, schema_name=schema_name))}
        elif action == "delete":
            _delete_function(full_function_name=full_name, force=force)
            return {"status": "deleted", "function": full_name}

    raise ValueError(f"Invalid object_type='{object_type}' or action='{action}'")


# =============================================================================
# Tool 2: manage_uc_grants
# =============================================================================


@mcp.tool
def manage_uc_grants(
    action: str,
    securable_type: str,
    full_name: str,
    principal: str = None,
    privileges: List[str] = None,
) -> Dict[str, Any]:
    """
    Manage permissions on Unity Catalog securables.

    Actions:
    - grant: Grant privileges to a principal.
    - revoke: Revoke privileges from a principal.
    - get: Get current grants on an object.
    - get_effective: Get effective (inherited + direct) grants.

    Args:
        action: "grant", "revoke", "get", or "get_effective"
        securable_type: Object type: "catalog", "schema", "table", "volume", "function",
            "storage_credential", "external_location", "connection", "share", "metastore"
        full_name: Full name of the securable object
        principal: User, group, or service principal (required for grant/revoke)
        privileges: List of privileges (required for grant/revoke).
            Common values: "SELECT", "MODIFY", "CREATE_TABLE", "CREATE_SCHEMA",
            "USE_CATALOG", "USE_SCHEMA", "ALL_PRIVILEGES", "EXECUTE",
            "READ_VOLUME", "WRITE_VOLUME", "CREATE_VOLUME", "CREATE_FUNCTION"

    Returns:
        Dict with grant/revoke result or current permissions
    """
    act = action.lower()

    if act == "grant":
        return _grant_privileges(
            securable_type=securable_type,
            full_name=full_name,
            principal=principal,
            privileges=privileges,
        )
    elif act == "revoke":
        return _revoke_privileges(
            securable_type=securable_type,
            full_name=full_name,
            principal=principal,
            privileges=privileges,
        )
    elif act == "get":
        return _get_grants(securable_type=securable_type, full_name=full_name, principal=principal)
    elif act == "get_effective":
        return _get_effective_grants(securable_type=securable_type, full_name=full_name, principal=principal)

    raise ValueError(f"Invalid action: '{action}'. Valid: grant, revoke, get, get_effective")


# =============================================================================
# Tool 3: manage_uc_storage
# =============================================================================


@mcp.tool
def manage_uc_storage(
    resource_type: str,
    action: str,
    name: str = None,
    aws_iam_role_arn: str = None,
    azure_access_connector_id: str = None,
    url: str = None,
    credential_name: str = None,
    read_only: bool = False,
    comment: str = None,
    owner: str = None,
    new_name: str = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Manage storage credentials and external locations.

    resource_type + action combinations:
    - credential: create, get, list, update, delete, validate
    - external_location: create, get, list, update, delete

    Args:
        resource_type: "credential" or "external_location"
        action: "create", "get", "list", "update", "delete", "validate"
        name: Resource name (for all actions except list)
        aws_iam_role_arn: AWS IAM Role ARN (for credential create/update on AWS)
        azure_access_connector_id: Azure Access Connector ID (for credential create/update on Azure)
        url: Cloud storage URL (for external_location create/update, or credential validate)
        credential_name: Storage credential name (for external_location create/update)
        read_only: Whether resource is read-only (default: False)
        comment: Description
        owner: Owner
        new_name: New name for update/rename
        force: Force deletion (default: False)

    Returns:
        Dict with operation result
    """
    rtype = resource_type.lower().replace(" ", "_").replace("-", "_")

    if rtype == "credential":
        if action == "create":
            return _to_dict(
                _create_storage_credential(
                    name=name,
                    comment=comment,
                    aws_iam_role_arn=aws_iam_role_arn,
                    azure_access_connector_id=azure_access_connector_id,
                    read_only=read_only,
                )
            )
        elif action == "get":
            return _to_dict(_get_storage_credential(name=name))
        elif action == "list":
            return {"items": _to_dict_list(_list_storage_credentials())}
        elif action == "update":
            return _to_dict(
                _update_storage_credential(
                    name=name,
                    new_name=new_name,
                    comment=comment,
                    owner=owner,
                    aws_iam_role_arn=aws_iam_role_arn,
                    azure_access_connector_id=azure_access_connector_id,
                )
            )
        elif action == "delete":
            _delete_storage_credential(name=name, force=force)
            return {"status": "deleted", "credential": name}
        elif action == "validate":
            return _validate_storage_credential(name=name, url=url)

    elif rtype == "external_location":
        if action == "create":
            return _to_dict(
                _create_external_location(
                    name=name,
                    url=url,
                    credential_name=credential_name,
                    comment=comment,
                    read_only=read_only,
                )
            )
        elif action == "get":
            return _to_dict(_get_external_location(name=name))
        elif action == "list":
            return {"items": _to_dict_list(_list_external_locations())}
        elif action == "update":
            return _to_dict(
                _update_external_location(
                    name=name,
                    new_name=new_name,
                    url=url,
                    credential_name=credential_name,
                    comment=comment,
                    owner=owner,
                    read_only=read_only,
                )
            )
        elif action == "delete":
            _delete_external_location(name=name, force=force)
            return {"status": "deleted", "external_location": name}

    raise ValueError(f"Invalid resource_type='{resource_type}' or action='{action}'")


# =============================================================================
# Tool 4: manage_uc_connections
# =============================================================================


@mcp.tool
def manage_uc_connections(
    action: str,
    name: str = None,
    connection_type: str = None,
    options: Dict[str, str] = None,
    comment: str = None,
    owner: str = None,
    new_name: str = None,
    connection_name: str = None,
    catalog_name: str = None,
    catalog_options: Dict[str, str] = None,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    Manage Lakehouse Federation foreign connections.

    Actions:
    - create: Create a foreign connection.
    - get: Get connection details.
    - list: List all connections.
    - update: Update a connection.
    - delete: Delete a connection.
    - create_foreign_catalog: Create a foreign catalog using a connection.

    Args:
        action: "create", "get", "list", "update", "delete", "create_foreign_catalog"
        name: Connection name (for CRUD operations)
        connection_type: "SNOWFLAKE", "POSTGRESQL", "MYSQL", "SQLSERVER", "BIGQUERY" (for create)
        options: Connection options dict with keys like "host", "port", "user", "password", "database"
        comment: Description
        owner: Owner
        new_name: New name for rename
        connection_name: Connection to use (for create_foreign_catalog)
        catalog_name: Name for the foreign catalog (for create_foreign_catalog)
        catalog_options: Options for foreign catalog (e.g., {"database": "mydb"})
        warehouse_id: SQL warehouse ID (for create_foreign_catalog)

    Returns:
        Dict with operation result
    """
    act = action.lower()

    if act == "create":
        return _to_dict(
            _create_connection(
                name=name,
                connection_type=connection_type,
                options=options,
                comment=comment,
            )
        )
    elif act == "get":
        return _to_dict(_get_connection(name=name))
    elif act == "list":
        return {"items": _to_dict_list(_list_connections())}
    elif act == "update":
        return _to_dict(_update_connection(name=name, options=options, new_name=new_name, owner=owner))
    elif act == "delete":
        _delete_connection(name=name)
        return {"status": "deleted", "connection": name}
    elif act == "create_foreign_catalog":
        return _create_foreign_catalog(
            catalog_name=catalog_name,
            connection_name=connection_name,
            catalog_options=catalog_options,
            comment=comment,
            warehouse_id=warehouse_id,
        )

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# Tool 5: manage_uc_tags
# =============================================================================


@mcp.tool
def manage_uc_tags(
    action: str,
    object_type: str = None,
    full_name: str = None,
    column_name: str = None,
    tags: Dict[str, str] = None,
    tag_names: List[str] = None,
    comment_text: str = None,
    catalog_filter: str = None,
    tag_name_filter: str = None,
    tag_value_filter: str = None,
    table_name_filter: str = None,
    limit: int = 100,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    Manage tags and comments on Unity Catalog objects.

    Actions:
    - set_tags: Set tags on an object or column.
    - unset_tags: Remove tags from an object or column.
    - set_comment: Set a comment on an object or column.
    - query_table_tags: Query tags from system.information_schema.table_tags.
    - query_column_tags: Query tags from system.information_schema.column_tags.

    Args:
        action: "set_tags", "unset_tags", "set_comment", "query_table_tags", "query_column_tags"
        object_type: "catalog", "schema", "table", or "column" (for set/unset/comment)
        full_name: Full object name (for set/unset/comment)
        column_name: Column name when object_type is "column"
        tags: Tag key-value pairs for set_tags (e.g., {"pii": "true", "classification": "confidential"})
        tag_names: Tag keys to remove for unset_tags
        comment_text: Comment text for set_comment
        catalog_filter: Filter by catalog name (for query actions)
        tag_name_filter: Filter by tag name (for query actions)
        tag_value_filter: Filter by tag value (for query actions)
        table_name_filter: Filter by table name (for query_column_tags)
        limit: Max rows for query (default: 100)
        warehouse_id: SQL warehouse ID (auto-selected if not provided)

    Returns:
        Dict with operation result or query results
    """
    act = action.lower()

    if act == "set_tags":
        return _set_tags(
            object_type=object_type,
            full_name=full_name,
            tags=tags,
            column_name=column_name,
            warehouse_id=warehouse_id,
        )
    elif act == "unset_tags":
        return _unset_tags(
            object_type=object_type,
            full_name=full_name,
            tag_names=tag_names,
            column_name=column_name,
            warehouse_id=warehouse_id,
        )
    elif act == "set_comment":
        return _set_comment(
            object_type=object_type,
            full_name=full_name,
            comment_text=comment_text,
            column_name=column_name,
            warehouse_id=warehouse_id,
        )
    elif act == "query_table_tags":
        return {
            "data": _query_table_tags(
                catalog_filter=catalog_filter,
                tag_name=tag_name_filter,
                tag_value=tag_value_filter,
                limit=limit,
                warehouse_id=warehouse_id,
            )
        }
    elif act == "query_column_tags":
        return {
            "data": _query_column_tags(
                catalog_filter=catalog_filter,
                table_name=table_name_filter,
                tag_name=tag_name_filter,
                tag_value=tag_value_filter,
                limit=limit,
                warehouse_id=warehouse_id,
            )
        }

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# Tool 6: manage_uc_security_policies
# =============================================================================


@mcp.tool
def manage_uc_security_policies(
    action: str,
    table_name: str = None,
    column_name: str = None,
    filter_function: str = None,
    filter_columns: List[str] = None,
    mask_function: str = None,
    function_name: str = None,
    function_body: str = None,
    parameter_name: str = None,
    parameter_type: str = None,
    return_type: str = None,
    function_comment: str = None,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    Manage row-level security and column masking policies.

    Actions:
    - set_row_filter: Apply a row filter function to a table.
    - drop_row_filter: Remove the row filter from a table.
    - set_column_mask: Apply a column mask function.
    - drop_column_mask: Remove a column mask.
    - create_security_function: Create a SQL function for row filters or column masks.

    Args:
        action: "set_row_filter", "drop_row_filter", "set_column_mask", "drop_column_mask", "create_security_function"
        table_name: Full table name (for row filter/column mask operations)
        column_name: Column name (for column mask operations)
        filter_function: Full function name for row filter
        filter_columns: Columns passed to the filter function
        mask_function: Full function name for column mask
        function_name: Full function name to create (catalog.schema.function)
        function_body: SQL function body (e.g., "RETURN IF(IS_ACCOUNT_GROUP_MEMBER('admins'), val, '***')")
        parameter_name: Function input parameter name
        parameter_type: Function input parameter type (e.g., "STRING")
        return_type: Function return type ("BOOLEAN" for filters, data type for masks)
        function_comment: Function description
        warehouse_id: SQL warehouse ID (auto-selected if not provided)

    Returns:
        Dict with operation result and executed SQL
    """
    act = action.lower()

    if act == "set_row_filter":
        return _set_row_filter(
            table_name=table_name,
            filter_function=filter_function,
            filter_columns=filter_columns,
            warehouse_id=warehouse_id,
        )
    elif act == "drop_row_filter":
        return _drop_row_filter(table_name=table_name, warehouse_id=warehouse_id)
    elif act == "set_column_mask":
        return _set_column_mask(
            table_name=table_name,
            column_name=column_name,
            mask_function=mask_function,
            warehouse_id=warehouse_id,
        )
    elif act == "drop_column_mask":
        return _drop_column_mask(table_name=table_name, column_name=column_name, warehouse_id=warehouse_id)
    elif act == "create_security_function":
        return _create_security_function(
            function_name=function_name,
            parameter_name=parameter_name,
            parameter_type=parameter_type,
            return_type=return_type,
            function_body=function_body,
            comment=function_comment,
            warehouse_id=warehouse_id,
        )

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# Tool 7: manage_uc_monitors
# =============================================================================


@mcp.tool
def manage_uc_monitors(
    action: str,
    table_name: str,
    output_schema_name: str = None,
    schedule_cron: str = None,
    schedule_timezone: str = "UTC",
    assets_dir: str = None,
) -> Dict[str, Any]:
    """
    Manage Lakehouse quality monitors on tables.

    Actions:
    - create: Create a quality monitor on a table.
    - get: Get monitor details.
    - run_refresh: Trigger a monitor refresh.
    - list_refreshes: List refresh history.
    - delete: Delete the monitor.

    Args:
        action: "create", "get", "run_refresh", "list_refreshes", "delete"
        table_name: Full table name being monitored (catalog.schema.table)
        output_schema_name: Schema for output tables (for create, e.g., "catalog.schema")
        schedule_cron: Quartz cron expression (for create, e.g., "0 0 12 * * ?")
        schedule_timezone: Timezone (default: "UTC")
        assets_dir: Workspace path for assets (for create)

    Returns:
        Dict with monitor details or operation result
    """
    act = action.lower()

    if act == "create":
        return _create_monitor(
            table_name=table_name,
            output_schema_name=output_schema_name,
            assets_dir=assets_dir,
            schedule_cron=schedule_cron,
            schedule_timezone=schedule_timezone,
        )
    elif act == "get":
        return _get_monitor(table_name=table_name)
    elif act == "run_refresh":
        return _run_monitor_refresh(table_name=table_name)
    elif act == "list_refreshes":
        return {"refreshes": _list_monitor_refreshes(table_name=table_name)}
    elif act == "delete":
        _delete_monitor(table_name=table_name)
        return {"status": "deleted", "table_name": table_name}

    raise ValueError(f"Invalid action: '{action}'")


# =============================================================================
# Tool 8: manage_uc_sharing
# =============================================================================


@mcp.tool
def manage_uc_sharing(
    resource_type: str,
    action: str,
    name: str = None,
    comment: str = None,
    table_name: str = None,
    shared_as: str = None,
    partition_spec: str = None,
    authentication_type: str = None,
    sharing_id: str = None,
    ip_access_list: List[str] = None,
    share_name: str = None,
    recipient_name: str = None,
    include_shared_data: bool = True,
) -> Dict[str, Any]:
    """
    Manage Delta Sharing: shares, recipients, and providers.

    resource_type + action combinations:
    - share: create, get, list, delete, add_table, remove_table, grant_to_recipient, revoke_from_recipient
    - recipient: create, get, list, delete, rotate_token
    - provider: get, list, list_shares

    Args:
        resource_type: "share", "recipient", or "provider"
        action: Operation to perform (see combinations above)
        name: Resource name (share/recipient/provider name)
        comment: Description (for create)
        table_name: Full table name for add_table/remove_table
        shared_as: Alias for shared table (hides internal naming)
        partition_spec: Partition filter for shared table
        authentication_type: "TOKEN" or "DATABRICKS" (for recipient create)
        sharing_id: Sharing identifier for D2D sharing (for recipient create)
        ip_access_list: Allowed IP addresses (for recipient create)
        share_name: Share name (for grant/revoke operations)
        recipient_name: Recipient name (for grant/revoke operations)
        include_shared_data: Include shared objects in get (default: True)

    Returns:
        Dict with operation result
    """
    rtype = resource_type.lower()
    act = action.lower()

    if rtype == "share":
        if act == "create":
            return _create_share(name=name, comment=comment)
        elif act == "get":
            return _get_share(name=name, include_shared_data=include_shared_data)
        elif act == "list":
            return {"items": _list_shares()}
        elif act == "delete":
            _delete_share(name=name)
            return {"status": "deleted", "share": name}
        elif act == "add_table":
            return _add_table_to_share(
                share_name=name or share_name,
                table_name=table_name,
                shared_as=shared_as,
                partition_spec=partition_spec,
            )
        elif act == "remove_table":
            return _remove_table_from_share(share_name=name or share_name, table_name=table_name)
        elif act == "grant_to_recipient":
            return _grant_share_to_recipient(share_name=name or share_name, recipient_name=recipient_name)
        elif act == "revoke_from_recipient":
            return _revoke_share_from_recipient(share_name=name or share_name, recipient_name=recipient_name)

    elif rtype == "recipient":
        if act == "create":
            return _create_recipient(
                name=name,
                authentication_type=authentication_type or "TOKEN",
                sharing_id=sharing_id,
                comment=comment,
                ip_access_list=ip_access_list,
            )
        elif act == "get":
            return _get_recipient(name=name)
        elif act == "list":
            return {"items": _list_recipients()}
        elif act == "delete":
            _delete_recipient(name=name)
            return {"status": "deleted", "recipient": name}
        elif act == "rotate_token":
            return _rotate_recipient_token(name=name)

    elif rtype == "provider":
        if act == "get":
            return _get_provider(name=name)
        elif act == "list":
            return {"items": _list_providers()}
        elif act == "list_shares":
            return {"items": _list_provider_shares(name=name)}

    raise ValueError(f"Invalid resource_type='{resource_type}' or action='{action}'")


# =============================================================================
# Tool 9: manage_metric_views
# =============================================================================


@mcp.tool
def manage_metric_views(
    action: str,
    full_name: str,
    source: str = None,
    dimensions: List[Dict[str, str]] = None,
    measures: List[Dict[str, str]] = None,
    version: str = "1.1",
    comment: str = None,
    filter_expr: str = None,
    joins: List[Dict[str, Any]] = None,
    materialization: Dict[str, Any] = None,
    or_replace: bool = False,
    query_measures: List[str] = None,
    query_dimensions: List[str] = None,
    where: str = None,
    order_by: str = None,
    limit: int = None,
    principal: str = None,
    privileges: List[str] = None,
    warehouse_id: str = None,
) -> Dict[str, Any]:
    """
    Manage Unity Catalog metric views: create, alter, describe, query, drop, and grant.

    Metric views define reusable, governed business metrics in YAML. They separate
    measure definitions from dimension groupings, allowing flexible querying across
    any dimension at runtime. Requires Databricks Runtime 17.2+ and a SQL warehouse.

    Actions:
    - create: Create a metric view with dimensions and measures.
    - alter: Update a metric view's YAML definition.
    - describe: Get the full definition and metadata of a metric view.
    - query: Query measures grouped by dimensions using MEASURE() syntax.
    - drop: Drop a metric view.
    - grant: Grant privileges (e.g., SELECT) on a metric view.

    Args:
        action: "create", "alter", "describe", "query", "drop", or "grant"
        full_name: Three-level name (catalog.schema.metric_view_name)
        source: Source table/view (for create/alter, e.g., "catalog.schema.orders")
        dimensions: List of dimension dicts for create/alter. Each has:
            - name: Display name (e.g., "Order Month")
            - expr: SQL expression (e.g., "DATE_TRUNC('MONTH', order_date)")
            - comment: (optional) Description
        measures: List of measure dicts for create/alter. Each has:
            - name: Display name (e.g., "Total Revenue")
            - expr: Aggregate expression (e.g., "SUM(total_price)")
            - comment: (optional) Description
        version: YAML spec version (default: "1.1" for DBR 17.2+)
        comment: Description of the metric view (for create/alter)
        filter_expr: SQL boolean filter applied to all queries (for create/alter)
        joins: Star/snowflake schema joins (for create/alter).
            Each dict: name, source, on (or using), joins (nested for snowflake)
        materialization: Materialization config (experimental, for create/alter).
            Keys: schedule, mode ("relaxed"), materialized_views (list)
        or_replace: If True, uses CREATE OR REPLACE (for create, default: False)
        query_measures: Measure names to query (for query action)
        query_dimensions: Dimension names to group by (for query action)
        where: WHERE clause filter (for query action)
        order_by: ORDER BY clause, use "ALL" for ORDER BY ALL (for query action)
        limit: Row limit (for query action)
        principal: User/group to grant to (for grant action)
        privileges: Privileges to grant, default ["SELECT"] (for grant action)
        warehouse_id: SQL warehouse ID (auto-selected if not provided)

    Returns:
        Dict with operation result. For query: list of row dicts.
    """
    act = action.lower()

    if act == "create":
        result = _create_metric_view(
            full_name=full_name,
            source=source,
            dimensions=dimensions,
            measures=measures,
            version=version,
            comment=comment,
            filter_expr=filter_expr,
            joins=joins,
            materialization=materialization,
            or_replace=or_replace,
            warehouse_id=warehouse_id,
        )
        try:
            from ..manifest import track_resource

            track_resource(
                resource_type="metric_view",
                name=full_name,
                resource_id=full_name,
            )
        except Exception:
            pass
        return result
    elif act == "alter":
        return _alter_metric_view(
            full_name=full_name,
            source=source,
            dimensions=dimensions,
            measures=measures,
            version=version,
            comment=comment,
            filter_expr=filter_expr,
            joins=joins,
            materialization=materialization,
            warehouse_id=warehouse_id,
        )
    elif act == "describe":
        return _describe_metric_view(
            full_name=full_name,
            warehouse_id=warehouse_id,
        )
    elif act == "query":
        if not query_measures:
            raise ValueError("query_measures is required for query action")
        return {
            "data": _query_metric_view(
                full_name=full_name,
                measures=query_measures,
                dimensions=query_dimensions,
                where=where,
                order_by=order_by,
                limit=limit,
                warehouse_id=warehouse_id,
            )
        }
    elif act == "drop":
        result = _drop_metric_view(
            full_name=full_name,
            warehouse_id=warehouse_id,
        )
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="metric_view", resource_id=full_name)
        except Exception:
            pass
        return result
    elif act == "grant":
        return _grant_metric_view(
            full_name=full_name,
            principal=principal,
            privileges=privileges,
            warehouse_id=warehouse_id,
        )

    raise ValueError(f"Invalid action: '{action}'. Valid: create, alter, describe, query, drop, grant")
