"""Lakebase Autoscaling tools - Manage projects, branches, computes, and credentials."""

from typing import Any, Dict, List, Optional

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
    get_endpoint as _get_endpoint,
    list_endpoints as _list_endpoints,
    update_endpoint as _update_endpoint,
    delete_endpoint as _delete_endpoint,
    generate_credential as _generate_credential,
)

from ..server import mcp


# ============================================================================
# Project Management Tools
# ============================================================================


@mcp.tool
def create_lakebase_autoscale_project(
    project_id: str,
    display_name: Optional[str] = None,
    pg_version: str = "17",
) -> Dict[str, Any]:
    """
    Create a Lakebase Autoscaling (managed PostgreSQL) project.

    Lakebase Autoscaling provides a fully managed PostgreSQL-compatible database
    with autoscaling compute, branching, scale-to-zero, and instant restore.

    A new project includes: a `production` branch, a primary read-write compute
    (8-32 CU), a `databricks_postgres` database, and a Postgres role for your identity.

    Args:
        project_id: Project identifier (1-63 chars, lowercase letters, digits, hyphens)
        display_name: Human-readable display name (defaults to project_id)
        pg_version: Postgres version: "16" or "17" (default: "17")

    Returns:
        Dictionary with:
        - name: Project resource name (projects/{project_id})
        - display_name: Display name
        - pg_version: Postgres version
        - status: Creation status

    Example:
        >>> create_lakebase_autoscale_project("my-app", display_name="My Application")
        {"name": "projects/my-app", "status": "CREATED", ...}
    """
    return _create_project(
        project_id=project_id,
        display_name=display_name,
        pg_version=pg_version,
    )


@mcp.tool
def get_lakebase_autoscale_project(name: str) -> Dict[str, Any]:
    """
    Get Lakebase Autoscaling project details.

    Args:
        name: Project resource name (e.g., "projects/my-app" or "my-app")

    Returns:
        Dictionary with:
        - name: Project resource name
        - display_name: Display name
        - pg_version: Postgres version
        - state: Current state (READY, CREATING, etc.)

    Example:
        >>> get_lakebase_autoscale_project("my-app")
        {"name": "projects/my-app", "display_name": "My App", "state": "READY", ...}
    """
    return _get_project(name=name)


@mcp.tool
def list_lakebase_autoscale_projects() -> List[Dict[str, Any]]:
    """
    List all Lakebase Autoscaling projects in the workspace.

    Returns:
        List of project dictionaries with name, display_name, pg_version, state.

    Example:
        >>> list_lakebase_autoscale_projects()
        [{"name": "projects/my-app", "display_name": "My App", "state": "READY", ...}]
    """
    return _list_projects()


@mcp.tool
def update_lakebase_autoscale_project(
    name: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Update a Lakebase Autoscaling project (e.g., rename it).

    Args:
        name: Project resource name (e.g., "projects/my-app" or "my-app")
        display_name: New display name for the project

    Returns:
        Dictionary with updated project details

    Example:
        >>> update_lakebase_autoscale_project("my-app", display_name="My Updated App")
        {"name": "projects/my-app", "status": "UPDATED", "display_name": "My Updated App"}
    """
    return _update_project(name=name, display_name=display_name)


@mcp.tool
def delete_lakebase_autoscale_project(name: str) -> Dict[str, Any]:
    """
    Delete a Lakebase Autoscaling project and ALL its resources.

    WARNING: This permanently deletes all branches, computes, databases,
    roles, and data in the project. This action cannot be undone.

    Args:
        name: Project resource name (e.g., "projects/my-app" or "my-app")

    Returns:
        Dictionary with name and status ("deleted" or error info)

    Example:
        >>> delete_lakebase_autoscale_project("my-app")
        {"name": "projects/my-app", "status": "deleted"}
    """
    return _delete_project(name=name)


# ============================================================================
# Branch Management Tools
# ============================================================================


@mcp.tool
def create_lakebase_autoscale_branch(
    project_name: str,
    branch_id: str,
    source_branch: Optional[str] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: bool = False,
) -> Dict[str, Any]:
    """
    Create a branch in a Lakebase Autoscaling project.

    Branches are isolated database environments that share storage with
    their parent through copy-on-write. They enable Git-like workflows
    for databases.

    Args:
        project_name: Project resource name (e.g., "projects/my-app")
        branch_id: Branch identifier (1-63 chars, lowercase letters, digits, hyphens)
        source_branch: Source branch to fork from. Defaults to production branch.
        ttl_seconds: Time-to-live in seconds (max 30 days = 2592000s)
        no_expiry: If True, branch never expires (default: False)

    Returns:
        Dictionary with:
        - name: Branch resource name
        - status: Creation status
        - expire_time: Expiration time (if TTL set)

    Example:
        >>> create_lakebase_autoscale_branch("projects/my-app", "development", ttl_seconds=604800)
        {"name": "projects/my-app/branches/development", "status": "CREATED", ...}
    """
    return _create_branch(
        project_name=project_name,
        branch_id=branch_id,
        source_branch=source_branch,
        ttl_seconds=ttl_seconds,
        no_expiry=no_expiry,
    )


@mcp.tool
def get_lakebase_autoscale_branch(name: str) -> Dict[str, Any]:
    """
    Get Lakebase Autoscaling branch details.

    Args:
        name: Branch resource name
            (e.g., "projects/my-app/branches/production")

    Returns:
        Dictionary with:
        - name: Branch resource name
        - state: Current state
        - is_default: Whether this is the default branch
        - is_protected: Whether the branch is protected
        - expire_time: Expiration time (if set)

    Example:
        >>> get_lakebase_autoscale_branch("projects/my-app/branches/production")
        {"name": "...", "state": "READY", "is_default": true, ...}
    """
    return _get_branch(name=name)


@mcp.tool
def list_lakebase_autoscale_branches(project_name: str) -> List[Dict[str, Any]]:
    """
    List all branches in a Lakebase Autoscaling project.

    Args:
        project_name: Project resource name (e.g., "projects/my-app")

    Returns:
        List of branch dictionaries with name, state, is_default, is_protected.

    Example:
        >>> list_lakebase_autoscale_branches("projects/my-app")
        [{"name": "projects/my-app/branches/production", "is_default": true, ...}]
    """
    return _list_branches(project_name=project_name)


@mcp.tool
def update_lakebase_autoscale_branch(
    name: str,
    is_protected: Optional[bool] = None,
    ttl_seconds: Optional[int] = None,
    no_expiry: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Update a Lakebase Autoscaling branch (protect or set expiration).

    Args:
        name: Branch resource name
            (e.g., "projects/my-app/branches/production")
        is_protected: Set branch protection (protected branches cannot be deleted)
        ttl_seconds: New TTL in seconds (max 30 days)
        no_expiry: If True, remove expiration from branch

    Returns:
        Dictionary with updated branch details

    Example:
        >>> update_lakebase_autoscale_branch("projects/my-app/branches/production", is_protected=True)
        {"name": "...", "status": "UPDATED", "is_protected": true}
    """
    return _update_branch(
        name=name,
        is_protected=is_protected,
        ttl_seconds=ttl_seconds,
        no_expiry=no_expiry,
    )


@mcp.tool
def delete_lakebase_autoscale_branch(name: str) -> Dict[str, Any]:
    """
    Delete a Lakebase Autoscaling branch.

    This permanently deletes all databases, roles, computes, and data
    on the branch. Cannot delete branches with child branches (delete
    children first) or protected branches.

    Args:
        name: Branch resource name
            (e.g., "projects/my-app/branches/development")

    Returns:
        Dictionary with name and status ("deleted" or error info)

    Example:
        >>> delete_lakebase_autoscale_branch("projects/my-app/branches/development")
        {"name": "projects/my-app/branches/development", "status": "deleted"}
    """
    return _delete_branch(name=name)


# ============================================================================
# Compute (Endpoint) Management Tools
# ============================================================================


@mcp.tool
def create_lakebase_autoscale_endpoint(
    branch_name: str,
    endpoint_id: str,
    endpoint_type: str = "ENDPOINT_TYPE_READ_WRITE",
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create a compute endpoint on a Lakebase Autoscaling branch.

    Each branch can have one read-write compute and optional read replicas.
    Autoscaling range: 0.5-32 CU (max-min <= 8 CU). Fixed sizes: 36-112 CU.

    Args:
        branch_name: Branch resource name
            (e.g., "projects/my-app/branches/production")
        endpoint_id: Endpoint identifier (1-63 chars)
        endpoint_type: "ENDPOINT_TYPE_READ_WRITE" or "ENDPOINT_TYPE_READ_ONLY"
        autoscaling_limit_min_cu: Minimum compute units (0.5-32)
        autoscaling_limit_max_cu: Maximum compute units (0.5-112)
        scale_to_zero_seconds: Inactivity timeout before suspending (0 to disable)

    Returns:
        Dictionary with name, host, and creation status

    Example:
        >>> create_lakebase_autoscale_endpoint(
        ...     "projects/my-app/branches/production", "my-compute",
        ...     autoscaling_limit_min_cu=2.0, autoscaling_limit_max_cu=8.0
        ... )
        {"name": "...", "host": "...", "status": "CREATED"}
    """
    return _create_endpoint(
        branch_name=branch_name,
        endpoint_id=endpoint_id,
        endpoint_type=endpoint_type,
        autoscaling_limit_min_cu=autoscaling_limit_min_cu,
        autoscaling_limit_max_cu=autoscaling_limit_max_cu,
        scale_to_zero_seconds=scale_to_zero_seconds,
    )


@mcp.tool
def get_lakebase_autoscale_endpoint(name: str) -> Dict[str, Any]:
    """
    Get Lakebase Autoscaling endpoint (compute) details.

    Args:
        name: Endpoint resource name
            (e.g., "projects/my-app/branches/production/endpoints/ep-primary")

    Returns:
        Dictionary with:
        - name: Endpoint resource name
        - state: Current state (ACTIVE, SUSPENDED, etc.)
        - endpoint_type: READ_WRITE or READ_ONLY
        - host: Connection hostname
        - min_cu: Minimum compute units
        - max_cu: Maximum compute units

    Example:
        >>> get_lakebase_autoscale_endpoint("projects/my-app/branches/production/endpoints/ep-primary")
        {"name": "...", "state": "ACTIVE", "host": "...", "min_cu": 2.0, "max_cu": 8.0}
    """
    return _get_endpoint(name=name)


@mcp.tool
def list_lakebase_autoscale_endpoints(branch_name: str) -> List[Dict[str, Any]]:
    """
    List all compute endpoints on a Lakebase Autoscaling branch.

    Args:
        branch_name: Branch resource name
            (e.g., "projects/my-app/branches/production")

    Returns:
        List of endpoint dictionaries with name, state, type, CU settings.

    Example:
        >>> list_lakebase_autoscale_endpoints("projects/my-app/branches/production")
        [{"name": "...", "state": "ACTIVE", "endpoint_type": "READ_WRITE", ...}]
    """
    return _list_endpoints(branch_name=branch_name)


@mcp.tool
def update_lakebase_autoscale_endpoint(
    name: str,
    autoscaling_limit_min_cu: Optional[float] = None,
    autoscaling_limit_max_cu: Optional[float] = None,
    scale_to_zero_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Update a Lakebase Autoscaling endpoint (resize or configure scale-to-zero).

    Autoscaling range constraint: max - min cannot exceed 8 CU.

    Args:
        name: Endpoint resource name
        autoscaling_limit_min_cu: New minimum compute units (0.5-32)
        autoscaling_limit_max_cu: New maximum compute units (0.5-112)
        scale_to_zero_seconds: Inactivity timeout before suspending (0 to disable)

    Returns:
        Dictionary with updated endpoint details

    Example:
        >>> update_lakebase_autoscale_endpoint(
        ...     "projects/my-app/branches/production/endpoints/ep-primary",
        ...     autoscaling_limit_min_cu=4.0, autoscaling_limit_max_cu=8.0
        ... )
        {"name": "...", "status": "UPDATED", "min_cu": 4.0, "max_cu": 8.0}
    """
    return _update_endpoint(
        name=name,
        autoscaling_limit_min_cu=autoscaling_limit_min_cu,
        autoscaling_limit_max_cu=autoscaling_limit_max_cu,
        scale_to_zero_seconds=scale_to_zero_seconds,
    )


@mcp.tool
def delete_lakebase_autoscale_endpoint(name: str) -> Dict[str, Any]:
    """
    Delete a Lakebase Autoscaling endpoint (compute).

    A compute is required to connect to a branch. After deletion,
    the branch's data remains but cannot be queried until a new
    compute is created.

    Args:
        name: Endpoint resource name

    Returns:
        Dictionary with name and status ("deleted" or error info)

    Example:
        >>> delete_lakebase_autoscale_endpoint(
        ...     "projects/my-app/branches/dev/endpoints/my-compute"
        ... )
        {"name": "...", "status": "deleted"}
    """
    return _delete_endpoint(name=name)


# ============================================================================
# Credential Tools
# ============================================================================


@mcp.tool
def generate_lakebase_autoscale_credential(
    endpoint: str,
) -> Dict[str, Any]:
    """
    Generate an OAuth token for connecting to Lakebase Autoscaling databases.

    The token is valid for ~1 hour. Use it as the password in PostgreSQL
    connection strings with sslmode=require.

    Args:
        endpoint: Endpoint resource name to scope the credential to
            (e.g., "projects/my-app/branches/production/endpoints/ep-primary")

    Returns:
        Dictionary with:
        - token: OAuth token (use as password in connection string)
        - expiration_time: Token expiration time
        - message: Usage instructions

    Example:
        >>> generate_lakebase_autoscale_credential(
        ...     endpoint="projects/my-app/branches/production/endpoints/ep-primary"
        ... )
        {"token": "eyJ...", "expiration_time": "...", "message": "Token generated..."}
    """
    return _generate_credential(endpoint=endpoint)
