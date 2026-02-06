"""Compute tools - Execute code on Databricks clusters."""

from typing import Dict, Any, List, Optional

from databricks_tools_core.compute import (
    list_clusters as _list_clusters,
    get_best_cluster as _get_best_cluster,
    execute_databricks_command as _execute_databricks_command,
    run_python_file_on_databricks as _run_python_file_on_databricks,
    NoRunningClusterError,
)

from ..server import mcp


@mcp.tool
def list_clusters() -> list[dict[str, Any]]:
    """
    List all clusters in the workspace.

    Returns:
        List of cluster info dicts with cluster_id, cluster_name, state, etc.
    """
    return _list_clusters()


@mcp.tool
def get_best_cluster() -> dict[str, Any]:
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
def execute_databricks_command(
    code: str,
    cluster_id: str = None,
    context_id: str = None,
    language: str = "python",
    timeout: int = 120,
    destroy_context_on_completion: bool = False,
) -> dict[str, Any]:
    """
    Execute code on a Databricks cluster.

    If context_id is provided, reuses the existing context (faster, maintains state).
    If not provided, creates a new context.

    By default, the context is kept alive for reuse. Set destroy_context_on_completion=True
    to destroy it after execution.

    Args:
        code: Code to execute
        cluster_id: ID of the cluster to run on. If not provided, auto-selects
                   a running cluster (prefers clusters with "shared" or "demo" in name).
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
            "available_clusters": e.available_clusters,
        }


@mcp.tool
def run_python_file_on_databricks(
    file_path: str,
    cluster_id: str = None,
    context_id: str = None,
    timeout: int = 600,
    destroy_context_on_completion: bool = False,
) -> dict[str, Any]:
    """
    Read a local Python file and execute it on a Databricks cluster.

    Useful for running data generation scripts or other Python code.

    If context_id is provided, reuses the existing context (faster, maintains state).
    If not provided, creates a new context.

    Args:
        file_path: Local path to the Python file
        cluster_id: ID of the cluster to run on. If not provided, auto-selects
                   a running cluster (prefers clusters with "shared" or "demo" in name).
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
            "available_clusters": e.available_clusters,
        }
