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


@mcp.tool(timeout=60)
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
    """Manage UC namespace objects: catalog/schema/volume/function.

    object_type: "catalog", "schema", "volume", or "function".
    action: "create", "get", "list", "update", "delete" (function: no create, use SQL).

    Parameters by object_type:
    - catalog: create(name, comment?, storage_root?, properties?), get/update/delete(full_name or name).
      update supports: new_name, comment, owner, isolation_mode (OPEN/ISOLATED).
    - schema: create(catalog_name, name, comment?), get/update/delete(full_name).
      list(catalog_name). update supports: new_name, comment, owner.
    - volume: create(catalog_name, schema_name, name, volume_type?, comment?, storage_location?).
      volume_type: MANAGED (default) or EXTERNAL. storage_location required for EXTERNAL.
      list(catalog_name, schema_name). get/update/delete(full_name).
    - function: get/delete(full_name), list(catalog_name, schema_name). force=True for delete.

    full_name format: "catalog" or "catalog.schema" or "catalog.schema.object".
    Returns: list={items}, get/create/update=object details, delete={status}."""
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


@mcp.tool(timeout=60)
def manage_uc_grants(
    action: str,
    securable_type: str,
    full_name: str,
    principal: str = None,
    privileges: List[str] = None,
) -> Dict[str, Any]:
    """Manage UC permissions: grant/revoke/get/get_effective.

    action: "grant", "revoke", "get", "get_effective".
    securable_type: catalog/schema/table/volume/function/storage_credential/external_location/connection/share.
    full_name: Full UC name (e.g., "catalog.schema.table").
    principal: User, group, or service principal (e.g., "user@example.com", "group_name").
    privileges: List of privileges to grant/revoke. Common values:
      - catalog: USE_CATALOG, CREATE_SCHEMA, ALL_PRIVILEGES
      - schema: USE_SCHEMA, CREATE_TABLE, CREATE_FUNCTION, ALL_PRIVILEGES
      - table: SELECT, MODIFY, ALL_PRIVILEGES
      - volume: READ_VOLUME, WRITE_VOLUME, ALL_PRIVILEGES
      - function: EXECUTE, ALL_PRIVILEGES
    Returns: get/get_effective={privilege_assignments: [...]}, grant/revoke={status}."""
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


@mcp.tool(timeout=60)
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
    """Manage storage credentials and external locations.

    resource_type: "credential" or "external_location".

    credential actions:
    - create: name + (aws_iam_role_arn OR azure_access_connector_id), comment?, read_only?.
    - get/delete: name. delete supports force=True.
    - update: name, new_name?, comment?, owner?, aws_iam_role_arn?, azure_access_connector_id?.
    - validate: name, url (cloud path to validate access).
    - list: no params.

    external_location actions:
    - create: name, url (cloud path), credential_name, comment?, read_only?.
    - get/delete: name. delete supports force=True.
    - update: name, new_name?, url?, credential_name?, comment?, owner?, read_only?.
    - list: no params.

    Returns: get/create/update=resource details, list={items}, delete={status}, validate={results}."""
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


@mcp.tool(timeout=60)
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
    """Manage Lakehouse Federation foreign connections.

    action: "create", "get", "list", "update", "delete", "create_foreign_catalog".
    connection_type: SNOWFLAKE, POSTGRESQL, MYSQL, SQLSERVER, BIGQUERY, REDSHIFT, SQLDW (Azure Synapse).

    Parameters by action:
    - create: name, connection_type, options (dict with connection details), comment?.
      options format varies by type. Example for POSTGRESQL:
        {"host": "...", "port": "5432", "user": "...", "password": "..."}.
    - get/delete: name.
    - update: name, options?, new_name?, owner?.
    - list: no params.
    - create_foreign_catalog: Creates UC catalog from external connection.
      Requires: catalog_name (new UC catalog name), connection_name (existing connection).
      Optional: catalog_options (dict, e.g., {"database": "mydb"}), comment, warehouse_id.

    Returns: get/create/update=connection details, list={items}, delete={status}."""
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


@mcp.tool(timeout=60)
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
    """Manage UC tags and comments.

    action: "set_tags", "unset_tags", "set_comment", "query_table_tags", "query_column_tags".

    Parameters by action:
    - set_tags: object_type (catalog/schema/table/column), full_name, tags (dict of key-value pairs).
      For columns: also set column_name. warehouse_id? for SQL-based tagging.
    - unset_tags: object_type, full_name, tag_names (list of keys to remove).
      For columns: also set column_name. warehouse_id?.
    - set_comment: object_type, full_name, comment_text. For columns: column_name. warehouse_id?.
    - query_table_tags: Search tables by tags. catalog_filter?, tag_name_filter?, tag_value_filter?, limit? (default 100).
    - query_column_tags: Search columns by tags. catalog_filter?, table_name_filter?, tag_name_filter?, tag_value_filter?, limit?.

    Returns: set/unset={status}, query={data: [...]}."""
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


@mcp.tool(timeout=60)
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
    """Manage row-level security and column masking.

    action: "set_row_filter", "drop_row_filter", "set_column_mask", "drop_column_mask", "create_security_function".

    Parameters by action:
    - set_row_filter: table_name (full name), filter_function (UDF name), filter_columns (list of columns to pass).
      Example: filter_function="main.default.row_filter_fn", filter_columns=["user_id"].
    - drop_row_filter: table_name.
    - set_column_mask: table_name, column_name, mask_function (UDF that returns masked value).
    - drop_column_mask: table_name, column_name.
    - create_security_function: Creates a UDF for row filtering or column masking.
      Requires: function_name (full name), parameter_name, parameter_type, return_type, function_body.
      Example: function_name="main.default.my_filter", parameter_name="user_id", parameter_type="STRING",
               return_type="BOOLEAN", function_body="return user_id = current_user()".

    All actions accept optional warehouse_id for SQL execution.
    Returns: {status, message} or function details for create."""
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


@mcp.tool(timeout=60)
def manage_uc_monitors(
    action: str,
    table_name: str,
    output_schema_name: str = None,
    schedule_cron: str = None,
    schedule_timezone: str = "UTC",
    assets_dir: str = None,
) -> Dict[str, Any]:
    """Manage Lakehouse quality monitors for data quality tracking.

    action: "create", "get", "run_refresh", "list_refreshes", "delete".
    table_name: Full table name (required for all actions).

    Parameters by action:
    - create: table_name, output_schema_name (where metrics tables are stored).
      Optional: assets_dir (for dashboard assets), schedule_cron (e.g., "0 0 * * *"),
      schedule_timezone (default "UTC").
    - get: table_name. Returns monitor config and status.
    - run_refresh: table_name. Triggers a new monitor refresh.
    - list_refreshes: table_name. Returns {refreshes: [...]}.
    - delete: table_name. Removes the monitor.

    Returns: create/get=monitor details, run_refresh={status}, list_refreshes={refreshes}, delete={status}."""
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


@mcp.tool(timeout=60)
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
    """Manage Delta Sharing: shares, recipients, and providers.

    resource_type: "share", "recipient", or "provider".

    SHARE actions (for data providers to share tables):
    - create: name, comment?. Creates an empty share.
    - get: name, include_shared_data? (default True).
    - list: no params. Returns {items: [...]}.
    - delete: name.
    - add_table: name (or share_name), table_name (full UC name), shared_as? (alias), partition_spec?.
    - remove_table: name (or share_name), table_name.
    - grant_to_recipient: name (or share_name), recipient_name.
    - revoke_from_recipient: name (or share_name), recipient_name.

    RECIPIENT actions (for data providers to manage share consumers):
    - create: name, authentication_type? (TOKEN/DATABRICKS), sharing_id?, comment?, ip_access_list?.
    - get: name. list: no params. delete: name.
    - rotate_token: name. Generates new access token for TOKEN-based recipients.

    PROVIDER actions (for data consumers to view available shares):
    - get: name. list: no params.
    - list_shares: name (provider name). Lists shares available from this provider.

    Returns: create/get=details, list={items}, delete={status}."""
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


@mcp.tool(timeout=60)
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
    """Manage UC metric views (reusable business metrics). Requires DBR 17.2+.

    action: "create", "alter", "describe", "query", "drop", "grant".
    full_name: Full metric view name (catalog.schema.metric_view).

    Parameters by action:
    - create: full_name, source (table/view name), dimensions, measures.
      dimensions: List of dicts [{name: "dim_name", expr: "column_or_expr"}, ...].
      measures: List of dicts [{name: "measure_name", expr: "SUM(amount)"}, ...] (aggregate functions).
      Optional: version (default "1.1"), comment, filter_expr, joins, materialization, or_replace.
    - alter: Same params as create except or_replace. Updates existing metric view.
    - describe: full_name. Returns metric view definition and metadata.
    - query: full_name, query_measures (list of measure names to retrieve).
      Optional: query_dimensions (list of dimension names), where, order_by, limit.
    - drop: full_name. Deletes the metric view.
    - grant: full_name, principal, privileges (list, e.g., ["SELECT"]).

    All actions accept optional warehouse_id for SQL execution.
    Returns: create/alter/describe/grant=details, query={data: [...]}, drop={status}."""
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
        _auto_tag("metric_view", full_name)
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
