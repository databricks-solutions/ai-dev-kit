"""Compute tools - Execute code on Databricks clusters and serverless compute, and manage compute resources."""

from typing import Dict, Any, List, Optional

from databricks_tools_core.compute import (
    list_clusters as _list_clusters,
    get_best_cluster as _get_best_cluster,
    start_cluster as _start_cluster,
    get_cluster_status as _get_cluster_status,
    execute_databricks_command as _execute_databricks_command,
    run_file_on_databricks as _run_file_on_databricks,
    run_code_on_serverless as _run_code_on_serverless,
    NoRunningClusterError,
    create_cluster as _create_cluster,
    modify_cluster as _modify_cluster,
    terminate_cluster as _terminate_cluster,
    delete_cluster as _delete_cluster,
    list_node_types as _list_node_types,
    list_spark_versions as _list_spark_versions,
    create_sql_warehouse as _create_sql_warehouse,
    modify_sql_warehouse as _modify_sql_warehouse,
    delete_sql_warehouse as _delete_sql_warehouse,
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
def run_file_on_databricks(
    file_path: str,
    cluster_id: str = None,
    context_id: str = None,
    language: str = None,
    timeout: int = 600,
    destroy_context_on_completion: bool = False,
    workspace_path: str = None,
) -> Dict[str, Any]:
    """
    Read a local file and execute it on a Databricks cluster.

    Supports Python (.py), Scala (.scala), SQL (.sql), and R (.r) files.
    Language is auto-detected from the file extension if not specified.

    Two modes:
    - Ephemeral (default): Sends code via Command Execution API. No workspace artifact.
    - Persistent: If workspace_path is provided, also uploads the file as a notebook
      to that workspace path so it's visible and re-runnable in the Databricks UI.
      Use persistent mode for project work (model training, ETL scripts, etc.).

    If context_id is provided, reuses the existing context (faster, maintains state).
    If not provided, creates a new context.

    If no cluster_id is provided and no accessible running cluster is found,
    returns an error with actionable suggestions (startable clusters, alternatives).

    Args:
        file_path: Local path to the file to execute.
        cluster_id: ID of the cluster to run on. If not provided, auto-selects
                   a running cluster accessible to the current user.
        context_id: Optional existing execution context ID for reuse.
        language: Programming language ("python", "scala", "sql", "r").
                 If omitted, auto-detected from file extension.
        timeout: Maximum wait time in seconds (default: 600).
        destroy_context_on_completion: If True, destroys the context after execution.
        workspace_path: Optional workspace path to persist the file as a notebook
            (e.g. "/Workspace/Users/user@company.com/my-project/train").
            If omitted, no workspace artifact is created.

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
    if language == "":
        language = None
    if workspace_path == "":
        workspace_path = None

    try:
        result = _run_file_on_databricks(
            file_path=file_path,
            cluster_id=cluster_id,
            context_id=context_id,
            language=language,
            timeout=timeout,
            destroy_context_on_completion=destroy_context_on_completion,
            workspace_path=workspace_path,
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
def run_code_on_serverless(
    code: str,
    language: str = "python",
    timeout: int = 1800,
    run_name: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute code on serverless compute (no cluster required).

    This is the primary tool for running Python when no interactive cluster is
    available. Uses the Jobs API (runs/submit) with serverless compute — the code
    is uploaded as a notebook, executed, and (by default) cleaned up automatically.

    Two modes:
    - Ephemeral (default): Uploads to a temp path and cleans up after execution.
      Good for testing, exploration, one-off scripts.
    - Persistent: If workspace_path is provided, saves the notebook at that path
      and keeps it after execution. Good for project work the user wants saved
      (model training, ETL, data pipelines).

    Also supports Jupyter notebooks (.ipynb): if the code content is valid .ipynb
    JSON (i.e. contains a "cells" key), it is automatically uploaded using
    Databricks' native Jupyter import. The language parameter is ignored for .ipynb.
    To run a .ipynb file, read its contents and pass the raw JSON string as code.

    Use this tool when:
    - The user needs to run Python and no cluster is running
    - Running one-off Python scripts that don't need an interactive session
    - Running longer-running Python code (up to 30 min default timeout)
    - Running a Jupyter notebook (.ipynb) on Databricks serverless

    Do NOT use this tool for:
    - Interactive, iterative Python with state (use execute_databricks_command)
    - SQL queries that need result rows (use execute_sql — works with serverless
      SQL warehouses)

    SQL is supported (language="sql") but only for DDL/DML (CREATE TABLE, INSERT,
    MERGE). SQL SELECT results are NOT captured — use execute_sql() instead.

    Args:
        code: Code to execute (Python or SQL), or raw .ipynb JSON content (auto-detected).
        language: Programming language ("python" or "sql"). Default: "python". Ignored for .ipynb.
        timeout: Maximum wait time in seconds (default: 1800 = 30 minutes).
        run_name: Optional human-readable name for the run. Auto-generated if omitted.
        workspace_path: Optional workspace path to persist the notebook
            (e.g. "/Workspace/Users/user@company.com/my-project/train").
            If provided, the notebook is saved at this path and kept after execution.
            If omitted, uses a temp path and cleans up after.

    Returns:
        Dictionary with:
        - success: Whether execution succeeded
        - output: The output from execution (notebook result or logs)
        - error: Error message if failed
        - run_id: Databricks Jobs run ID
        - run_url: URL to view the run in Databricks UI
        - duration_seconds: How long the execution took
        - state: Final state (SUCCESS, FAILED, TIMEDOUT, etc.)
        - message: Human-readable summary
        - workspace_path: (persistent mode only) Where the notebook was saved
    """
    result = _run_code_on_serverless(
        code=code,
        language=language,
        timeout=timeout,
        run_name=run_name if run_name else None,
        cleanup=workspace_path is None,
        workspace_path=workspace_path if workspace_path else None,
    )
    return result.to_dict()


# --- Compute Management Tools ---


@mcp.tool
def create_cluster(
    name: str,
    num_workers: int = 1,
    spark_version: str = None,
    node_type_id: str = None,
    autotermination_minutes: int = 120,
    data_security_mode: str = None,
    spark_conf: str = None,
    autoscale_min_workers: int = None,
    autoscale_max_workers: int = None,
) -> Dict[str, Any]:
    """
    Create a new Databricks cluster with sensible defaults.

    Just provide a name and num_workers — the tool auto-picks the latest LTS
    Databricks Runtime, a reasonable node type for the cloud, SINGLE_USER
    security mode, and 120-minute auto-termination.

    Power users can override any parameter for full control.

    Args:
        name: Human-readable cluster name.
        num_workers: Fixed number of workers (ignored if autoscale is set). Default 1.
        spark_version: DBR version key (e.g. "15.4.x-scala2.12"). Auto-picks latest LTS if omitted.
        node_type_id: Worker node type (e.g. "i3.xlarge"). Auto-picked if omitted.
        autotermination_minutes: Minutes of inactivity before auto-termination. Default 120.
        data_security_mode: Security mode ("SINGLE_USER", "USER_ISOLATION", etc.). Default SINGLE_USER.
        spark_conf: JSON string of Spark config overrides (e.g. '{"spark.sql.shuffle.partitions": "8"}').
        autoscale_min_workers: If set with autoscale_max_workers, enables autoscaling.
        autoscale_max_workers: Maximum workers for autoscaling.

    Returns:
        Dictionary with cluster_id, cluster_name, state, spark_version, node_type_id, and message.
    """
    # Convert empty strings to None
    if spark_version == "":
        spark_version = None
    if node_type_id == "":
        node_type_id = None
    if data_security_mode == "":
        data_security_mode = None

    # Parse spark_conf from JSON string
    parsed_spark_conf = None
    if spark_conf and spark_conf.strip():
        import json
        parsed_spark_conf = json.loads(spark_conf)

    kwargs = {}
    if spark_version:
        kwargs["spark_version"] = spark_version
    if node_type_id:
        kwargs["node_type_id"] = node_type_id
    if data_security_mode:
        kwargs["data_security_mode"] = data_security_mode
    if parsed_spark_conf:
        kwargs["spark_conf"] = parsed_spark_conf
    if autoscale_min_workers is not None:
        kwargs["autoscale_min_workers"] = autoscale_min_workers
    if autoscale_max_workers is not None:
        kwargs["autoscale_max_workers"] = autoscale_max_workers

    return _create_cluster(
        name=name,
        num_workers=num_workers,
        autotermination_minutes=autotermination_minutes,
        **kwargs,
    )


@mcp.tool
def modify_cluster(
    cluster_id: str,
    name: str = None,
    num_workers: int = None,
    spark_version: str = None,
    node_type_id: str = None,
    autotermination_minutes: int = None,
    spark_conf: str = None,
    autoscale_min_workers: int = None,
    autoscale_max_workers: int = None,
) -> Dict[str, Any]:
    """
    Modify an existing Databricks cluster configuration.

    Only the specified parameters are changed; others remain as-is.
    If the cluster is running, it will restart to apply changes.

    Args:
        cluster_id: ID of the cluster to modify.
        name: New cluster name (optional).
        num_workers: New fixed worker count (optional).
        spark_version: New DBR version (optional).
        node_type_id: New worker node type (optional).
        autotermination_minutes: New auto-termination timeout (optional).
        spark_conf: JSON string of Spark config overrides (optional).
        autoscale_min_workers: Set to enable/modify autoscaling (optional).
        autoscale_max_workers: Set to enable/modify autoscaling (optional).

    Returns:
        Dictionary with cluster_id, cluster_name, state, and message.
    """
    # Convert empty strings to None
    if name == "":
        name = None
    if spark_version == "":
        spark_version = None
    if node_type_id == "":
        node_type_id = None

    kwargs = {}
    if name:
        kwargs["name"] = name
    if num_workers is not None:
        kwargs["num_workers"] = num_workers
    if spark_version:
        kwargs["spark_version"] = spark_version
    if node_type_id:
        kwargs["node_type_id"] = node_type_id
    if autotermination_minutes is not None:
        kwargs["autotermination_minutes"] = autotermination_minutes
    if autoscale_min_workers is not None:
        kwargs["autoscale_min_workers"] = autoscale_min_workers
    if autoscale_max_workers is not None:
        kwargs["autoscale_max_workers"] = autoscale_max_workers

    # Parse spark_conf from JSON string
    if spark_conf and spark_conf.strip():
        import json
        kwargs["spark_conf"] = json.loads(spark_conf)

    return _modify_cluster(cluster_id=cluster_id, **kwargs)


@mcp.tool
def terminate_cluster(cluster_id: str) -> Dict[str, Any]:
    """
    Stop a running Databricks cluster (reversible).

    The cluster is terminated but NOT deleted. It can be restarted later
    with start_cluster(). This is safe and reversible.

    Args:
        cluster_id: ID of the cluster to terminate.

    Returns:
        Dictionary with cluster_id, cluster_name, state, and message.
    """
    return _terminate_cluster(cluster_id)


@mcp.tool
def delete_cluster(cluster_id: str) -> Dict[str, Any]:
    """
    PERMANENTLY delete a Databricks cluster.

    WARNING: This is a DESTRUCTIVE, IRREVERSIBLE action. The cluster and its
    configuration will be permanently removed. This cannot be undone.

    IMPORTANT: Always confirm with the user before calling this tool.
    Ask: "Are you sure you want to permanently delete cluster '<name>'?
    This cannot be undone."

    Args:
        cluster_id: ID of the cluster to permanently delete.

    Returns:
        Dictionary with cluster_id, cluster_name, state, and warning message.
    """
    return _delete_cluster(cluster_id)


@mcp.tool
def list_node_types() -> List[Dict[str, Any]]:
    """
    List available VM/node types for cluster creation.

    Returns node type IDs, memory, cores, and GPU info. Useful when the user
    wants to choose a specific node type for create_cluster().

    Returns:
        List of node type dicts with node_type_id, memory_mb, num_cores, num_gpus, description.
    """
    return _list_node_types()


@mcp.tool
def list_spark_versions() -> List[Dict[str, Any]]:
    """
    List available Databricks Runtime (Spark) versions.

    Returns version keys and names. Filter for "LTS" in the name to find
    long-term support versions for create_cluster().

    Returns:
        List of dicts with key and name for each version.
    """
    return _list_spark_versions()


@mcp.tool
def create_sql_warehouse(
    name: str,
    size: str = "Small",
    min_num_clusters: int = 1,
    max_num_clusters: int = 1,
    auto_stop_mins: int = 120,
    warehouse_type: str = "PRO",
    enable_serverless: bool = True,
) -> Dict[str, Any]:
    """
    Create a new SQL warehouse with sensible defaults.

    By default creates a serverless Pro warehouse with auto-stop at 120 minutes.

    Args:
        name: Human-readable warehouse name.
        size: T-shirt size ("2X-Small", "X-Small", "Small", "Medium", "Large",
            "X-Large", "2X-Large", "3X-Large", "4X-Large"). Default "Small".
        min_num_clusters: Minimum cluster count. Default 1.
        max_num_clusters: Maximum cluster count for scaling. Default 1.
        auto_stop_mins: Minutes of inactivity before auto-stop. Default 120.
        warehouse_type: "PRO" or "CLASSIC". Default "PRO".
        enable_serverless: Enable serverless compute. Default True.

    Returns:
        Dictionary with warehouse_id, name, size, state, and message.
    """
    # Convert empty strings to None
    if size == "":
        size = "Small"
    if warehouse_type == "":
        warehouse_type = "PRO"

    return _create_sql_warehouse(
        name=name,
        size=size,
        min_num_clusters=min_num_clusters,
        max_num_clusters=max_num_clusters,
        auto_stop_mins=auto_stop_mins,
        warehouse_type=warehouse_type,
        enable_serverless=enable_serverless,
    )


@mcp.tool
def modify_sql_warehouse(
    warehouse_id: str,
    name: str = None,
    size: str = None,
    min_num_clusters: int = None,
    max_num_clusters: int = None,
    auto_stop_mins: int = None,
) -> Dict[str, Any]:
    """
    Modify an existing SQL warehouse configuration.

    Only the specified parameters are changed; others remain as-is.

    Args:
        warehouse_id: ID of the warehouse to modify.
        name: New warehouse name (optional).
        size: New T-shirt size (optional).
        min_num_clusters: New minimum clusters (optional).
        max_num_clusters: New maximum clusters (optional).
        auto_stop_mins: New auto-stop timeout in minutes (optional).

    Returns:
        Dictionary with warehouse_id, name, state, and message.
    """
    # Convert empty strings to None
    if name == "":
        name = None
    if size == "":
        size = None

    kwargs = {}
    if name:
        kwargs["name"] = name
    if size:
        kwargs["size"] = size
    if min_num_clusters is not None:
        kwargs["min_num_clusters"] = min_num_clusters
    if max_num_clusters is not None:
        kwargs["max_num_clusters"] = max_num_clusters
    if auto_stop_mins is not None:
        kwargs["auto_stop_mins"] = auto_stop_mins

    return _modify_sql_warehouse(warehouse_id=warehouse_id, **kwargs)


@mcp.tool
def delete_sql_warehouse(warehouse_id: str) -> Dict[str, Any]:
    """
    PERMANENTLY delete a SQL warehouse.

    WARNING: This is a DESTRUCTIVE, IRREVERSIBLE action. The warehouse and its
    configuration will be permanently removed. This cannot be undone.

    IMPORTANT: Always confirm with the user before calling this tool.
    Ask: "Are you sure you want to permanently delete warehouse '<name>'?
    This cannot be undone."

    Args:
        warehouse_id: ID of the warehouse to permanently delete.

    Returns:
        Dictionary with warehouse_id, name, state, and warning message.
    """
    return _delete_sql_warehouse(warehouse_id)
