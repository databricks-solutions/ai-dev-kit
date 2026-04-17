"""Lakebase tools - Manage Lakebase databases (Provisioned and Autoscaling).

Consolidated into 4 tools:
- manage_lakebase_database: create_or_update, get, list, delete
- manage_lakebase_branch: create_or_update, delete
- manage_lakebase_sync: create_or_update, delete
- generate_lakebase_credential: Generate OAuth tokens
"""

import logging
from typing import Any, Dict, List, Optional

# Provisioned core functions
from databricks_tools_core.lakebase import (
    create_lakebase_instance as _create_instance,
    get_lakebase_instance as _get_instance,
    list_lakebase_instances as _list_instances,
    update_lakebase_instance as _update_instance,
    delete_lakebase_instance as _delete_instance,
    generate_lakebase_credential as _generate_provisioned_credential,
    create_lakebase_catalog as _create_catalog,
    get_lakebase_catalog as _get_catalog,
    delete_lakebase_catalog as _delete_catalog,
    create_synced_table as _create_synced_table,
    get_synced_table as _get_synced_table,
    delete_synced_table as _delete_synced_table,
)

# Autoscale core functions
from databricks_tools_core.lakebase_autoscale import (
    create_project as _create_project,
    get_project as _get_project,
    list_projects as _list_projects,
    update_project as _update_project,
    delete_project as _delete_project,
    create_branch as _create_branch,
    list_branches as _list_branches,
    update_branch as _update_branch,
    delete_branch as _delete_branch,
    create_endpoint as _create_endpoint,
    list_endpoints as _list_endpoints,
    update_endpoint as _update_endpoint,
    generate_credential as _generate_autoscale_credential,
)

from ..server import mcp

logger = logging.getLogger(__name__)


# ============================================================================
# Helpers
# ============================================================================


def _find_instance_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Find a provisioned instance by name, returns None if not found."""
    try:
        return _get_instance(name=name)
    except Exception:
        return None


def _find_project_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Find an autoscale project by name, returns None if not found."""
    try:
        return _get_project(name=name)
    except Exception:
        return None


def _find_branch(project_name: str, branch_id: str) -> Optional[Dict[str, Any]]:
    """Find a branch in a project, returns None if not found."""
    try:
        branches = _list_branches(project_name=project_name)
        for branch in branches:
            branch_name = branch.get("name", "")
            if branch_name.endswith(f"/branches/{branch_id}"):
                return branch
    except Exception:
        pass
    return None


# ============================================================================
# Tool 1: manage_lakebase_database
# ============================================================================


@mcp.tool(timeout=120)
def manage_lakebase_database(
    action: str,
    name: Optional[str] = None,
    type: str = "provisioned",
    # For create_or_update:
    capacity: str = "CU_1",
    stopped: bool = False,
    display_name: Optional[str] = None,
    pg_version: str = "17",
    # For delete:
    force: bool = False,
) -> Dict[str, Any]:
    """Manage Lakebase PostgreSQL databases: create, update, get, list, delete.

    Actions:
    - create_or_update: Idempotent create/update. Requires name.
      type: "provisioned" (fixed capacity CU_1/2/4/8) or "autoscale" (auto-scaling with branches).
      capacity: For provisioned only. pg_version: For autoscale only.
      Returns: {created: bool, type, ...connection info}.
    - get: Get database details. Requires name.
      For autoscale, includes branches and endpoints.
      Returns: {name, type, state, ...}.
    - list: List all databases. Optional type filter.
      Returns: {databases: [{name, type, ...}]}.
    - delete: Delete database. Requires name.
      force=True cascades to children (provisioned). Autoscale deletes all branches/computes/data.
      Returns: {status, ...}.

    See databricks-lakebase-provisioned or databricks-lakebase-autoscale skill for details."""
    act = action.lower()

    if act == "create_or_update":
        if not name:
            return {"error": "create_or_update requires: name"}
        return _create_or_update_database(
            name=name, type=type, capacity=capacity, stopped=stopped,
            display_name=display_name, pg_version=pg_version,
        )

    elif act == "get":
        if not name:
            return {"error": "get requires: name"}
        return _get_database(name=name, type=type)

    elif act == "list":
        return _list_databases(type=type if type != "provisioned" else None)

    elif act == "delete":
        if not name:
            return {"error": "delete requires: name"}
        return _delete_database(name=name, type=type, force=force)

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: create_or_update, get, list, delete"}


# ============================================================================
# Tool 2: manage_lakebase_branch
# ============================================================================


@mcp.tool(timeout=120)
def manage_lakebase_branch(
    action: str,
    # For create_or_update:
    project_name: Optional[str] = None,
    branch_id: Optional[str] = None,
    source_branch: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: bool = False,
    is_protected: Optional[bool] = None,
    endpoint_type: str = "ENDPOINT_TYPE_READ_WRITE",
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
    # For delete:
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage Autoscale branches: create, update, delete.

    Branches are isolated copy-on-write environments with their own compute endpoints.

    Actions:
    - create_or_update: Idempotent create/update. Requires project_name, branch_id.
      source_branch: Branch to fork from (default: production).
      ttl_seconds: Auto-delete after N seconds. is_protected: Prevent accidental deletion.
      autoscaling_limit_min/max_cu: Compute unit limits. scale_to_zero_seconds: Idle time before scaling to zero.
      Returns: {branch details, endpoint connection info, created: bool}.
    - delete: Delete branch and endpoints. Requires name (full branch name).
      Permanently deletes data/databases/roles. Cannot delete protected branches.
      Returns: {status, ...}.

    See databricks-lakebase-autoscale skill for branch workflows."""
    act = action.lower()

    if act == "create_or_update":
        if not project_name or not branch_id:
            return {"error": "create_or_update requires: project_name, branch_id"}
        return _create_or_update_branch(
            project_name=project_name, branch_id=branch_id, source_branch=source_branch,
            ttl_seconds=ttl_seconds, no_expiry=no_expiry, is_protected=is_protected,
            endpoint_type=endpoint_type, autoscaling_limit_min_cu=autoscaling_limit_min_cu,
            autoscaling_limit_max_cu=autoscaling_limit_max_cu, scale_to_zero_seconds=scale_to_zero_seconds,
        )

    elif act == "delete":
        if not name:
            return {"error": "delete requires: name (full branch name)"}
        return _delete_branch(name=name)

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: create_or_update, delete"}


# ============================================================================
# Tool 3: manage_lakebase_sync
# ============================================================================


@mcp.tool(timeout=120)
def manage_lakebase_sync(
    action: str,
    # For create_or_update:
    instance_name: Optional[str] = None,
    source_table_name: Optional[str] = None,
    target_table_name: Optional[str] = None,
    catalog_name: Optional[str] = None,
    database_name: str = "databricks_postgres",
    primary_key_columns: Optional[List[str]] = None,
    scheduling_policy: str = "TRIGGERED",
    # For delete:
    table_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage Lakebase sync (reverse ETL): create, delete.

    Actions:
    - create_or_update: Set up reverse ETL from Delta table to Lakebase.
      Requires instance_name, source_table_name, target_table_name.
      Creates catalog if needed, then synced table.
      source_table_name: Delta table (catalog.schema.table). target_table_name: Postgres destination.
      primary_key_columns: Required for incremental sync.
      scheduling_policy: TRIGGERED/SNAPSHOT/CONTINUOUS.
      Returns: {catalog, synced_table, created}.
    - delete: Remove synced table, optionally UC catalog. Source Delta table unaffected.
      Requires table_name. Optional catalog_name to also delete catalog.
      Returns: {synced_table, catalog (if deleted)}.

    See databricks-lakebase-provisioned skill for sync workflows."""
    act = action.lower()

    if act == "create_or_update":
        if not all([instance_name, source_table_name, target_table_name]):
            return {"error": "create_or_update requires: instance_name, source_table_name, target_table_name"}
        return _create_or_update_sync(
            instance_name=instance_name, source_table_name=source_table_name,
            target_table_name=target_table_name, catalog_name=catalog_name,
            database_name=database_name, primary_key_columns=primary_key_columns,
            scheduling_policy=scheduling_policy,
        )

    elif act == "delete":
        if not table_name:
            return {"error": "delete requires: table_name"}
        return _delete_sync(table_name=table_name, catalog_name=catalog_name)

    else:
        return {"error": f"Invalid action '{action}'. Valid actions: create_or_update, delete"}


# ============================================================================
# Tool 4: generate_lakebase_credential
# ============================================================================


@mcp.tool(timeout=30)
def generate_lakebase_credential(
    instance_names: Optional[List[str]] = None,
    endpoint: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate OAuth token (~1hr) for Lakebase connection. Use as password with sslmode=require.

    Provide instance_names (provisioned) or endpoint (autoscale)."""
    if instance_names:
        return _generate_provisioned_credential(instance_names=instance_names)
    elif endpoint:
        return _generate_autoscale_credential(endpoint=endpoint)
    else:
        return {"error": "Provide either instance_names (provisioned) or endpoint (autoscale)."}


# ============================================================================
# Helper Functions
# ============================================================================


def _create_or_update_database(
    name: str, type: str, capacity: str, stopped: bool,
    display_name: Optional[str], pg_version: str,
) -> Dict[str, Any]:
    """Create or update a Lakebase database."""
    db_type = type.lower()

    if db_type == "provisioned":
        existing = _find_instance_by_name(name)
        if existing:
            result = _update_instance(name=name, capacity=capacity, stopped=stopped)
            return {**result, "created": False, "type": "provisioned"}
        else:
            result = _create_instance(name=name, capacity=capacity, stopped=stopped)
            try:
                from ..manifest import track_resource
                track_resource(resource_type="lakebase_instance", name=name, resource_id=name)
            except Exception:
                pass
            return {**result, "created": True, "type": "provisioned"}

    elif db_type == "autoscale":
        existing = _find_project_by_name(name)
        # Check if project actually exists (not just a NOT_FOUND response)
        project_exists = existing and "error" not in existing and existing.get("state") != "NOT_FOUND"
        if project_exists:
            result = _update_project(name=name, display_name=display_name)
            return {**result, "created": False, "type": "autoscale"}
        else:
            result = _create_project(
                project_id=name,
                display_name=display_name,
                pg_version=pg_version,
            )
            try:
                from ..manifest import track_resource
                track_resource(resource_type="lakebase_project", name=name, resource_id=name)
            except Exception:
                pass
            return {**result, "created": True, "type": "autoscale"}

    else:
        return {"error": f"Invalid type '{type}'. Use 'provisioned' or 'autoscale'."}


def _get_database(name: str, type: Optional[str]) -> Dict[str, Any]:
    """Get a database by name."""
    result = None
    if type is None or type.lower() == "provisioned":
        result = _find_instance_by_name(name)
        if result:
            result["type"] = "provisioned"

    if result is None and (type is None or type.lower() == "autoscale"):
        result = _find_project_by_name(name)
        if result:
            result["type"] = "autoscale"
            try:
                result["branches"] = _list_branches(project_name=name)
            except Exception:
                pass
            try:
                for branch in result.get("branches", []):
                    branch_name = branch.get("name", "")
                    branch["endpoints"] = _list_endpoints(branch_name=branch_name)
            except Exception:
                pass

    if result is None:
        return {"error": f"Database '{name}' not found."}
    return result


def _list_databases(type: Optional[str]) -> Dict[str, Any]:
    """List all databases."""
    databases = []

    if type is None or type.lower() == "provisioned":
        try:
            for inst in _list_instances():
                inst["type"] = "provisioned"
                databases.append(inst)
        except Exception as e:
            logger.warning("Failed to list provisioned instances: %s", e)

    if type is None or type.lower() == "autoscale":
        try:
            for proj in _list_projects():
                proj["type"] = "autoscale"
                databases.append(proj)
        except Exception as e:
            logger.warning("Failed to list autoscale projects: %s", e)

    return {"databases": databases}


def _delete_database(name: str, type: str, force: bool) -> Dict[str, Any]:
    """Delete a database."""
    db_type = type.lower()

    if db_type == "provisioned":
        return _delete_instance(name=name, force=force, purge=True)
    elif db_type == "autoscale":
        return _delete_project(name=name)
    else:
        return {"error": f"Invalid type '{type}'. Use 'provisioned' or 'autoscale'."}


def _create_or_update_branch(
    project_name: str, branch_id: str, source_branch: Optional[str],
    ttl_seconds: Optional[int], no_expiry: bool, is_protected: Optional[bool],
    endpoint_type: str, autoscaling_limit_min_cu: Optional[float],
    autoscaling_limit_max_cu: Optional[float], scale_to_zero_seconds: Optional[int],
) -> Dict[str, Any]:
    """Create or update a branch with compute endpoint."""
    existing = _find_branch(project_name, branch_id)

    if existing:
        branch_name = existing.get("name", f"{project_name}/branches/{branch_id}")
        branch_result = _update_branch(
            name=branch_name,
            is_protected=is_protected,
            ttl_seconds=ttl_seconds,
            no_expiry=no_expiry if no_expiry else None,
        )

        # Update endpoint if scaling params provided
        endpoint_result = None
        if any(v is not None for v in [autoscaling_limit_min_cu, autoscaling_limit_max_cu, scale_to_zero_seconds]):
            try:
                endpoints = _list_endpoints(branch_name=branch_name)
                if endpoints:
                    ep_name = endpoints[0].get("name", "")
                    endpoint_result = _update_endpoint(
                        name=ep_name,
                        autoscaling_limit_min_cu=autoscaling_limit_min_cu,
                        autoscaling_limit_max_cu=autoscaling_limit_max_cu,
                        scale_to_zero_seconds=scale_to_zero_seconds,
                    )
            except Exception as e:
                logger.warning("Failed to update endpoint: %s", e)

        result = {**branch_result, "created": False}
        if endpoint_result:
            result["endpoint"] = endpoint_result
        return result

    else:
        branch_result = _create_branch(
            project_name=project_name,
            branch_id=branch_id,
            source_branch=source_branch,
            ttl_seconds=ttl_seconds,
            no_expiry=no_expiry,
        )

        # Create compute endpoint on the new branch
        branch_name = branch_result.get("name", f"{project_name}/branches/{branch_id}")
        endpoint_result = None
        try:
            endpoint_result = _create_endpoint(
                branch_name=branch_name,
                endpoint_id=f"{branch_id}-ep",
                endpoint_type=endpoint_type,
                autoscaling_limit_min_cu=autoscaling_limit_min_cu,
                autoscaling_limit_max_cu=autoscaling_limit_max_cu,
                scale_to_zero_seconds=scale_to_zero_seconds,
            )
        except Exception as e:
            logger.warning("Failed to create endpoint on branch: %s", e)

        result = {**branch_result, "created": True}
        if endpoint_result:
            result["endpoint"] = endpoint_result
        return result


def _create_or_update_sync(
    instance_name: str, source_table_name: str, target_table_name: str,
    catalog_name: Optional[str], database_name: str,
    primary_key_columns: Optional[List[str]], scheduling_policy: str,
) -> Dict[str, Any]:
    """Create or update a sync configuration."""
    # Derive catalog name from target table if not provided
    if not catalog_name:
        parts = target_table_name.split(".")
        if len(parts) >= 1:
            catalog_name = parts[0]
        else:
            return {"error": "Cannot derive catalog_name from target_table_name. Provide catalog_name explicitly."}

    # Ensure catalog registration exists
    catalog_result = None
    try:
        catalog_result = _get_catalog(name=catalog_name)
    except Exception:
        try:
            catalog_result = _create_catalog(
                name=catalog_name,
                instance_name=instance_name,
                database_name=database_name,
            )
        except Exception as e:
            return {"error": f"Failed to create catalog '{catalog_name}': {e}"}

    # Check if synced table already exists
    try:
        existing = _get_synced_table(table_name=target_table_name)
        return {
            "catalog": catalog_result,
            "synced_table": existing,
            "created": False,
        }
    except Exception:
        pass

    # Create synced table
    sync_result = _create_synced_table(
        instance_name=instance_name,
        source_table_name=source_table_name,
        target_table_name=target_table_name,
        primary_key_columns=primary_key_columns,
        scheduling_policy=scheduling_policy,
    )

    return {
        "catalog": catalog_result,
        "synced_table": sync_result,
        "created": True,
    }


def _delete_sync(table_name: str, catalog_name: Optional[str]) -> Dict[str, Any]:
    """Delete a sync configuration."""
    result = {}

    sync_result = _delete_synced_table(table_name=table_name)
    result["synced_table"] = sync_result

    if catalog_name:
        try:
            catalog_result = _delete_catalog(name=catalog_name)
            result["catalog"] = catalog_result
        except Exception as e:
            result["catalog"] = {"error": str(e)}

    return result
