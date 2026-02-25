"""Lakebase tools - Manage Lakebase databases (Provisioned and Autoscaling).

Provides 8 high-level workflow tools that wrap the granular databricks-tools-core
functions, following the create_or_update pattern from pipelines.
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
    get_branch as _get_branch,
    list_branches as _list_branches,
    update_branch as _update_branch,
    delete_branch as _delete_branch,
    create_endpoint as _create_endpoint,
    list_endpoints as _list_endpoints,
    update_endpoint as _update_endpoint,
    delete_endpoint as _delete_endpoint,
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
# Tool 1: create_or_update_lakebase_database
# ============================================================================


@mcp.tool
def create_or_update_lakebase_database(
    name: str,
    type: str = "provisioned",
    capacity: str = "CU_1",
    stopped: bool = False,
    display_name: Optional[str] = None,
    pg_version: str = "17",
) -> Dict[str, Any]:
    """
    Create or update a Lakebase managed PostgreSQL database.

    Finds an existing database by name and updates it, or creates a new one.
    For autoscale, a new project includes a production branch, default compute,
    and a databricks_postgres database automatically.

    Args:
        name: Database name (1-63 chars, lowercase letters, digits, hyphens)
        type: "provisioned" (fixed capacity) or "autoscale" (auto-scaling compute)
        capacity: Provisioned compute: "CU_1", "CU_2", "CU_4", or "CU_8"
        stopped: If True, create provisioned instance in stopped state
        display_name: Autoscale display name (defaults to name)
        pg_version: Autoscale Postgres version: "16" or "17"

    Returns:
        Dictionary with database details, status, and connection info.
    """
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
        if existing:
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


# ============================================================================
# Tool 2: get_lakebase_database
# ============================================================================


@mcp.tool
def get_lakebase_database(
    name: Optional[str] = None,
    type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get details of a Lakebase database, or list all databases.

    Pass a name to get one database's details (including branches, endpoints
    for autoscale). Omit name to list all databases.

    Args:
        name: Database name. If omitted, lists all databases.
        type: Filter by "provisioned" or "autoscale". If omitted, checks both.

    Returns:
        Single database dict (if name provided) or {"databases": [...]}.
    """
    if name:
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

    # List all databases
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


# ============================================================================
# Tool 3: delete_lakebase_database
# ============================================================================


@mcp.tool
def delete_lakebase_database(
    name: str,
    type: str = "provisioned",
    force: bool = False,
) -> Dict[str, Any]:
    """
    Delete a Lakebase database and its resources.

    For provisioned: deletes the instance (use force=True to cascade to children).
    For autoscale: deletes the project and all branches, computes, and data.

    Args:
        name: Database name to delete
        type: "provisioned" or "autoscale"
        force: If True, force-delete child resources (provisioned only)

    Returns:
        Dictionary with name and deletion status.
    """
    db_type = type.lower()

    if db_type == "provisioned":
        return _delete_instance(name=name, force=force, purge=True)
    elif db_type == "autoscale":
        return _delete_project(name=name)
    else:
        return {"error": f"Invalid type '{type}'. Use 'provisioned' or 'autoscale'."}


# ============================================================================
# Tool 4: create_or_update_lakebase_branch
# ============================================================================


@mcp.tool
def create_or_update_lakebase_branch(
    project_name: str,
    branch_id: str,
    source_branch: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: bool = False,
    is_protected: Optional[bool] = None,
    endpoint_type: str = "ENDPOINT_TYPE_READ_WRITE",
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create or update a Lakebase Autoscale branch with its compute endpoint.

    Branches are isolated database environments using copy-on-write storage.
    If the branch exists, updates its settings. Otherwise creates a new branch
    and a compute endpoint on it.

    Args:
        project_name: Project name (e.g., "my-app" or "projects/my-app")
        branch_id: Branch identifier (1-63 chars, lowercase letters, digits, hyphens)
        source_branch: Source branch to fork from (default: production)
        ttl_seconds: Time-to-live in seconds (max 30 days = 2592000s)
        no_expiry: If True, branch never expires
        is_protected: If True, branch cannot be deleted
        endpoint_type: "ENDPOINT_TYPE_READ_WRITE" or "ENDPOINT_TYPE_READ_ONLY"
        autoscaling_limit_min_cu: Minimum compute units (0.5-32)
        autoscaling_limit_max_cu: Maximum compute units (0.5-112)
        scale_to_zero_seconds: Inactivity timeout before suspending (0 to disable)

    Returns:
        Dictionary with branch details and endpoint connection info.
    """
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


# ============================================================================
# Tool 5: delete_lakebase_branch
# ============================================================================


@mcp.tool
def delete_lakebase_branch(name: str) -> Dict[str, Any]:
    """
    Delete a Lakebase Autoscale branch and its compute endpoints.

    The branch's data, databases, roles, and computes are permanently deleted.
    Cannot delete protected branches or branches with children.

    Args:
        name: Branch resource name
            (e.g., "projects/my-app/branches/development")

    Returns:
        Dictionary with name and deletion status.
    """
    return _delete_branch(name=name)


# ============================================================================
# Tool 6: create_or_update_lakebase_sync
# ============================================================================


@mcp.tool
def create_or_update_lakebase_sync(
    instance_name: str,
    source_table_name: str,
    target_table_name: str,
    catalog_name: Optional[str] = None,
    database_name: str = "databricks_postgres",
    primary_key_columns: Optional[List[str]] = None,
    scheduling_policy: str = "TRIGGERED",
) -> Dict[str, Any]:
    """
    Set up reverse ETL from a Delta table to Lakebase.

    Ensures the UC catalog registration exists, then creates a synced table
    to replicate data from the Lakehouse into PostgreSQL.

    Args:
        instance_name: Lakebase instance name
        source_table_name: Source Delta table (catalog.schema.table)
        target_table_name: Target table in Lakebase (catalog.schema.table)
        catalog_name: UC catalog name for the Lakebase instance.
            If omitted, derives from target_table_name.
        database_name: PostgreSQL database name (default: "databricks_postgres")
        primary_key_columns: Primary key columns (defaults to source table's PK)
        scheduling_policy: "TRIGGERED", "SNAPSHOT", or "CONTINUOUS"

    Returns:
        Dictionary with catalog and synced table details.
    """
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


# ============================================================================
# Tool 7: delete_lakebase_sync
# ============================================================================


@mcp.tool
def delete_lakebase_sync(
    table_name: str,
    catalog_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Remove a Lakebase synced table and optionally its UC catalog registration.

    The source Delta table is not affected.

    Args:
        table_name: Fully qualified synced table name (catalog.schema.table)
        catalog_name: UC catalog to also remove. If omitted, only the
            synced table is deleted.

    Returns:
        Dictionary with deletion status for synced table and catalog.
    """
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


# ============================================================================
# Tool 8: generate_lakebase_credential
# ============================================================================


@mcp.tool
def generate_lakebase_credential(
    instance_names: Optional[List[str]] = None,
    endpoint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate an OAuth token for connecting to a Lakebase database.

    Provide instance_names for provisioned databases, or endpoint for autoscale.
    The token is valid for ~1 hour. Use as the password in PostgreSQL
    connection strings with sslmode=require.

    Args:
        instance_names: Provisioned instance names to generate credentials for
        endpoint: Autoscale endpoint resource name
            (e.g., "projects/my-app/branches/production/endpoints/ep-primary")

    Returns:
        Dictionary with OAuth token and usage instructions.
    """
    if instance_names:
        return _generate_provisioned_credential(instance_names=instance_names)
    elif endpoint:
        return _generate_autoscale_credential(endpoint=endpoint)
    else:
        return {"error": "Provide either instance_names (provisioned) or endpoint (autoscale)."}
