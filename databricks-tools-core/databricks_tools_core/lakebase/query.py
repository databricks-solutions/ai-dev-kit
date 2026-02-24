"""
Lakebase Query Operations

Functions for executing SQL queries against Lakebase PostgreSQL instances.
Supports both Provisioned and Autoscale instance types.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LakebaseQueryError(Exception):
    """Exception raised when Lakebase query execution fails."""
    pass


def execute_lakebase_query(
    sql_query: str,
    instance_name: Optional[str] = None,
    endpoint: Optional[str] = None,
    database: str = "databricks_postgres",
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Execute a SQL query against a Lakebase PostgreSQL instance.
    
    Supports both Provisioned and Autoscale Lakebase instances.
    Provide either instance_name (for provisioned) or endpoint (for autoscale).

    Args:
        sql_query: SQL query to execute
        instance_name: Name of a Provisioned Lakebase instance (e.g., "my-instance")
        endpoint: Autoscale endpoint - either full resource name 
            (e.g., "projects/xxx/branches/yyy/endpoints/zzz") or just the host
            (e.g., "ep-xxx.database.eastus2.azuredatabricks.net")
        database: PostgreSQL database name (default: "databricks_postgres")
        timeout: Query timeout in seconds (default: 60)

    Returns:
        Dictionary with:
        - columns: List of column names
        - data: List of rows (each row is a list of values)
        - row_count: Number of rows returned
        - type: "provisioned" or "autoscale"
        - target: instance_name or endpoint used

    Raises:
        LakebaseQueryError: If query execution fails
    """
    try:
        import psycopg2
    except ImportError:
        raise LakebaseQueryError(
            "psycopg2 is not installed. Install it with: pip install psycopg2-binary"
        )

    if not instance_name and not endpoint:
        raise LakebaseQueryError(
            "Provide either instance_name (for provisioned) or endpoint (for autoscale)"
        )

    # Determine instance type and get connection details
    if instance_name:
        host, token, username, instance_type = _get_provisioned_connection(instance_name)
        target = instance_name
    else:
        host, token, username, instance_type = _get_autoscale_connection(endpoint)
        target = endpoint

    # Connect and execute query
    conn = None
    try:
        conn = psycopg2.connect(
            host=host,
            port=5432,
            dbname=database,
            user=username,
            password=token,
            sslmode="require",
            connect_timeout=timeout,
        )
        conn.set_session(readonly=False, autocommit=True)
        
        with conn.cursor() as cur:
            cur.execute(sql_query)
            
            # Get column names
            columns = []
            if cur.description:
                columns = [desc[0] for desc in cur.description]
            
            # Fetch results (if any)
            data = []
            if cur.description:  # SELECT or RETURNING query
                data = [list(row) for row in cur.fetchall()]
            
            return {
                "columns": columns,
                "data": data,
                "row_count": len(data),
                "type": instance_type,
                "target": target,
                "database": database,
            }

    except psycopg2.Error as e:
        raise LakebaseQueryError(f"PostgreSQL error: {e}")
    except Exception as e:
        raise LakebaseQueryError(f"Query execution failed: {e}")
    finally:
        if conn:
            conn.close()


def _get_provisioned_connection(instance_name: str) -> tuple:
    """Get connection details for a Provisioned Lakebase instance."""
    from .instances import get_lakebase_instance, generate_lakebase_credential
    from ..auth import get_workspace_client

    # Get instance details
    instance = get_lakebase_instance(instance_name)
    if instance.get("state") == "NOT_FOUND":
        raise LakebaseQueryError(f"Provisioned instance '{instance_name}' not found")
    
    host = instance.get("read_write_dns")
    if not host:
        raise LakebaseQueryError(
            f"Instance '{instance_name}' does not have a read_write_dns endpoint. "
            f"State: {instance.get('state')}"
        )

    # Check if instance is available
    state = str(instance.get("state", ""))
    if "STOPPED" in state:
        raise LakebaseQueryError(
            f"Instance '{instance_name}' is stopped. Start it first with "
            f"update_lakebase_instance('{instance_name}', stopped=False)"
        )

    # Generate OAuth credential
    cred = generate_lakebase_credential(instance_names=[instance_name])
    token = cred.get("token")
    if not token:
        raise LakebaseQueryError("Failed to generate OAuth token for provisioned instance")

    # Get username from current user
    client = get_workspace_client()
    try:
        me = client.current_user.me()
        username = me.user_name
    except Exception:
        username = "databricks"

    return host, token, username, "provisioned"


def _get_autoscale_connection(endpoint: str) -> tuple:
    """Get connection details for an Autoscale Lakebase endpoint."""
    from ..lakebase_autoscale import generate_credential, get_endpoint, list_projects, list_branches, list_endpoints
    from ..auth import get_workspace_client

    endpoint_name = None
    host = None

    # Determine if endpoint is a host or resource name
    if endpoint.startswith("projects/"):
        # Full resource name - get endpoint details
        ep_info = get_endpoint(endpoint)
        host = ep_info.get("host")
        endpoint_name = endpoint
        if not host:
            raise LakebaseQueryError(f"Endpoint '{endpoint}' does not have a host")
    elif ".database." in endpoint and ".azuredatabricks.net" in endpoint:
        # It's a host - need to find the full endpoint name by searching
        host = endpoint
        endpoint_name = _find_endpoint_by_host(host)
        if not endpoint_name:
            raise LakebaseQueryError(
                f"Could not find autoscale endpoint with host '{endpoint}'. "
                "Try providing the full resource name instead."
            )
    else:
        raise LakebaseQueryError(
            f"Invalid endpoint format: '{endpoint}'. Provide either a host "
            "(e.g., 'ep-xxx.database.eastus2.azuredatabricks.net') or full resource name "
            "(e.g., 'projects/xxx/branches/yyy/endpoints/zzz')"
        )

    # Generate OAuth credential for autoscale
    cred = generate_credential(endpoint=endpoint_name)
    token = cred.get("token")
    if not token:
        raise LakebaseQueryError("Failed to generate OAuth token for autoscale endpoint")

    # Get username from current user
    client = get_workspace_client()
    try:
        me = client.current_user.me()
        username = me.user_name
    except Exception:
        username = "databricks"

    return host, token, username, "autoscale"


def _find_endpoint_by_host(target_host: str) -> Optional[str]:
    """Find the full endpoint resource name by searching for a matching host."""
    from ..lakebase_autoscale import list_projects, list_branches, list_endpoints

    try:
        projects = list_projects()
        for project in projects:
            project_name = project.get("name", "")
            project_id = project_name.split("/")[-1] if "/" in project_name else project_name
            
            branches = list_branches(project_id)
            for branch in branches:
                branch_name = branch.get("name", "")
                
                endpoints = list_endpoints(branch_name)
                for ep in endpoints:
                    ep_host = ep.get("host", "")
                    if ep_host == target_host:
                        return ep.get("name")
    except Exception as e:
        logger.warning(f"Error searching for endpoint by host: {e}")
    
    return None
