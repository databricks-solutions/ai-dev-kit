"""Compute tools - Execute code on Databricks clusters."""

from typing import Dict, Any, List, Optional

from databricks_tools_core.compute import (
    list_clusters as _list_clusters,
    get_best_cluster as _get_best_cluster,
    start_cluster as _start_cluster,
    get_cluster_status as _get_cluster_status,
    execute_databricks_command as _execute_databricks_command,
    run_python_file_on_databricks as _run_python_file_on_databricks,
    NoRunningClusterError,
)

from ..server import mcp


@mcp.tool
def list_clusters() -> List[Dict[str, Any]]:
    """
    List all clusters in the workspace.

    Returns:
        List of cluster info dicts with cluster_id, cluster_name, state, etc.
    """
    return _list_clusters()


@mcp.tool
def get_best_cluster() -> Dict[str, Any]:
    """
    Get the ID of the best available cluster for code execution.

    Selection logic:
    1. Only considers RUNNING clusters
    2. Prefers clusters with "shared" in the name (case-insensitive)
    3. Then prefers clusters with "demo" in the name
    4. Otherwise returns the first running cluster

    Returns:
        Dictionary with cluster_id (string or None if no running cluster).
    """
    cluster_id = _get_best_cluster()
    return {"cluster_id": cluster_id}


@mcp.tool
def start_cluster(cluster_id: str) -> Dict[str, Any]:
    """
    Start a terminated Databricks cluster.

    IMPORTANT: Always ask the user for confirmation before starting a cluster.
    Starting a cluster consumes cloud resources and typically takes 3-8 minutes.

    After starting, poll with get_cluster_status() until the cluster reaches
    RUNNING state, then proceed with execute_databricks_command().

    Typical workflow when no running cluster is available:
    1. execute_databricks_command() returns an error with startable_clusters
    2. Ask the user: "I found your cluster '<name>'. Would you like me to start it?"
    3. If approved, call start_cluster(cluster_id=...)
    4. Poll get_cluster_status(cluster_id=...) every 30-60s until state is RUNNING
    5. Retry the original command with the now-running cluster_id

    Args:
        cluster_id: ID of the cluster to start.

    Returns:
        Dictionary with:
        - cluster_id: The cluster ID
        - cluster_name: Human-readable cluster name
        - state: Current state after the start request (typically PENDING)
        - previous_state: State before starting (TERMINATED, ERROR)
        - message: Status message with next steps
    """
    return _start_cluster(cluster_id)


@mcp.tool
def get_cluster_status(cluster_id: str) -> Dict[str, Any]:
    """
    Get the current status of a Databricks cluster.

    Use this to poll a cluster after calling start_cluster() to check
    whether it has reached RUNNING state and is ready for code execution.

    Args:
        cluster_id: ID of the cluster to check.

    Returns:
        Dictionary with:
        - cluster_id: The cluster ID
        - cluster_name: Human-readable cluster name
        - state: Current state (PENDING, RUNNING, TERMINATED, etc.)
        - message: Human-readable status message
    """
    return _get_cluster_status(cluster_id)


@mcp.tool
def execute_databricks_command(
    code: str,
    cluster_id: str = None,
    context_id: str = None,
    language: str = "python",
    timeout: int = 120,
    destroy_context_on_completion: bool = False,
) -> Dict[str, Any]:
    """
    Execute code on a Databricks cluster.

    If context_id is provided, reuses the existing context (faster, maintains state).
    If not provided, creates a new context.

    By default, the context is kept alive for reuse. Set destroy_context_on_completion=True
    to destroy it after execution.

    If no cluster_id is provided and no accessible running cluster is found,
    returns an error with startable_clusters and suggestions. When this happens:
    1. Present the best startable cluster to the user and ASK FOR APPROVAL to start it
    2. If approved, call start_cluster() then poll get_cluster_status() until RUNNING
    3. Retry this command with the now-running cluster_id
    For SQL-only workloads, consider using execute_sql() instead (no cluster needed).

    Args:
        code: Code to execute
        cluster_id: ID of the cluster to run on. If not provided, auto-selects
                   a running cluster accessible to the current user.
                   Single-user clusters owned by other users are automatically skipped.
        context_id: Optional existing execution context ID. If provided, reuses it
                   for faster execution and state preservation (variables, imports).
        language: Programming language ("python", "scala", "sql", "r")
        timeout: Maximum wait time in seconds (default: 120)
        destroy_context_on_completion: If True, destroys the context after execution.
                                       Default is False to allow reuse.

    Returns:
        Dictionary with:
        - success: Whether execution succeeded
        - output: The output from execution
        - error: Error message if failed
        - cluster_id: The cluster ID used
        - context_id: The context ID (reuse this for follow-up commands!)
        - context_destroyed: Whether the context was destroyed
        - message: Helpful message about reusing the context

        On cluster-not-found errors, also includes:
        - startable_clusters: terminated clusters that can be started (ask user first!)
        - suggestions: actionable next steps
        - skipped_clusters: running clusters skipped (single-user, different owner)
    """
    # Convert empty strings to None (Claude agent sometimes passes "" instead of null)
    if cluster_id == "":
        cluster_id = None
    if context_id == "":
        context_id = None

    try:
        result = _execute_databricks_command(
            code=code,
            cluster_id=cluster_id,
            context_id=context_id,
            language=language,
            timeout=timeout,
            destroy_context_on_completion=destroy_context_on_completion,
        )
        return result.to_dict()
    except NoRunningClusterError as e:
        return {
            "success": False,
            "output": None,
            "error": str(e),
            "cluster_id": None,
            "context_id": None,
            "context_destroyed": True,
            "message": None,
            "suggestions": e.suggestions,
            "startable_clusters": e.startable_clusters,
            "skipped_clusters": e.skipped_clusters,
            "available_clusters": e.available_clusters,
        }


@mcp.tool
def run_python_file_on_databricks(
    file_path: str,
    cluster_id: str = None,
    context_id: str = None,
    timeout: int = 600,
    destroy_context_on_completion: bool = False,
) -> Dict[str, Any]:
    """
    Read a local Python file and execute it on a Databricks cluster.

    Useful for running data generation scripts or other Python code.

    If context_id is provided, reuses the existing context (faster, maintains state).
    If not provided, creates a new context.

    If no cluster_id is provided and no accessible running cluster is found,
    returns an error with actionable suggestions (startable clusters, alternatives).

    Args:
        file_path: Local path to the Python file
        cluster_id: ID of the cluster to run on. If not provided, auto-selects
                   a running cluster accessible to the current user.
                   Single-user clusters owned by other users are automatically skipped.
        context_id: Optional existing execution context ID. If provided, reuses it
                   for faster execution and state preservation.
        timeout: Maximum wait time in seconds (default: 600)
        destroy_context_on_completion: If True, destroys the context after execution.
                                       Default is False to allow reuse.

    Returns:
        Dictionary with:
        - success: Whether execution succeeded
        - output: The output from execution
        - error: Error message if failed
        - cluster_id: The cluster ID used
        - context_id: The context ID (reuse this for follow-up commands!)
        - context_destroyed: Whether the context was destroyed
        - message: Helpful message about reusing the context
    """
    # Convert empty strings to None (Claude agent sometimes passes "" instead of null)
    if cluster_id == "":
        cluster_id = None
    if context_id == "":
        context_id = None

    try:
        result = _run_python_file_on_databricks(
            file_path=file_path,
            cluster_id=cluster_id,
            context_id=context_id,
            timeout=timeout,
            destroy_context_on_completion=destroy_context_on_completion,
        )
        return result.to_dict()
    except NoRunningClusterError as e:
        return {
            "success": False,
            "output": None,
            "error": str(e),
            "cluster_id": None,
            "context_id": None,
            "context_destroyed": True,
            "message": None,
            "suggestions": e.suggestions,
            "startable_clusters": e.startable_clusters,
            "skipped_clusters": e.skipped_clusters,
            "available_clusters": e.available_clusters,
        }
