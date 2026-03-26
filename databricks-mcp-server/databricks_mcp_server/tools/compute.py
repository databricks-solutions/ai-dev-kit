"""Compute tools - Execute code and manage compute resources on Databricks.

Consolidated into 4 tools (down from 19) to reduce LLM parsing overhead:
- execute_code: Run code on serverless or cluster compute
- manage_cluster: Create, modify, start, terminate, or delete clusters
- manage_sql_warehouse: Create, modify, or delete SQL warehouses
- list_compute: List/inspect clusters, node types, and spark versions
"""

import json
from typing import Dict, Any, List, Optional

from databricks_tools_core.compute import (
    # Execution
    list_clusters as _list_clusters,
    get_best_cluster as _get_best_cluster,
    start_cluster as _start_cluster,
    get_cluster_status as _get_cluster_status,
    execute_databricks_command as _execute_databricks_command,
    run_file_on_databricks as _run_file_on_databricks,
    run_code_on_serverless as _run_code_on_serverless,
    NoRunningClusterError,
    # Cluster management
    create_cluster as _create_cluster,
    modify_cluster as _modify_cluster,
    terminate_cluster as _terminate_cluster,
    delete_cluster as _delete_cluster,
    list_node_types as _list_node_types,
    list_spark_versions as _list_spark_versions,
    # SQL warehouse management
    create_sql_warehouse as _create_sql_warehouse,
    modify_sql_warehouse as _modify_sql_warehouse,
    delete_sql_warehouse as _delete_sql_warehouse,
)

from ..server import mcp


def _none_if_empty(value):
    """Convert empty strings to None (Claude agent sometimes passes '' instead of null)."""
    return None if value == "" else value


# ---------------------------------------------------------------------------
# Tool 1: execute_code
# ---------------------------------------------------------------------------


@mcp.tool
def execute_code(
    code: str = None,
    file_path: str = None,
    compute_type: str = "auto",
    cluster_id: str = None,
    context_id: str = None,
    language: str = "python",
    timeout: int = None,
    destroy_context_on_completion: bool = False,
    workspace_path: str = None,
    run_name: str = None,
) -> Dict[str, Any]:
    """
    Execute code on Databricks — serverless or cluster compute.

    This is the single entry point for all code execution on Databricks.

    Modes (determined by compute_type):
    - "serverless": Run on serverless compute via Jobs API (no cluster needed).
      Best for one-off Python/SQL, batch scripts, model training. Up to 30 min timeout.
    - "cluster": Run on a classic cluster. Best for interactive iteration with
      state preservation (variables, imports persist across calls via context_id).
    - "auto" (default): Uses serverless if no cluster_id/context_id is provided
      and language is python/sql. Falls back to cluster if cluster_id or
      context_id is provided, or if language is scala/r.

    File execution: Set file_path to a local file (.py, .scala, .sql, .r) instead
    of code. Language is auto-detected from extension. Requires cluster compute
    (or serverless for .py/.sql).

    Persistence: Set workspace_path to save the code as a notebook in the
    Databricks workspace (visible in UI, re-runnable, versionable). If omitted,
    execution is ephemeral.

    Jupyter notebooks (.ipynb): Pass raw .ipynb JSON as code with compute_type="serverless".
    Auto-detected and uploaded natively.

    Args:
        code: Code to execute. Required unless file_path is provided.
        file_path: Local file path to execute instead of code. Language auto-detected
            from extension (.py, .scala, .sql, .r).
        compute_type: "serverless", "cluster", or "auto" (default).
        cluster_id: Cluster ID for cluster compute. Auto-selects if omitted.
        context_id: Reuse an existing execution context (cluster compute only).
            Enables state preservation across calls.
        language: "python" (default), "scala", "sql", or "r".
            Ignored when file_path is set (auto-detected) or for .ipynb content.
        timeout: Max wait in seconds. Defaults: serverless=1800, cluster=120, file=600.
        destroy_context_on_completion: Destroy cluster execution context after run.
            Default False (keeps context for reuse).
        workspace_path: Save code as a notebook at this workspace path
            (e.g. "/Workspace/Users/user@company.com/project/train").
            If omitted, execution is ephemeral.
        run_name: Human-readable name for the run (serverless only).

    Returns:
        Dictionary with success, output, error, and compute-specific metadata
        (cluster_id, context_id for cluster; run_id, run_url for serverless).
    """
    # Normalize empty strings to None
    code = _none_if_empty(code)
    file_path = _none_if_empty(file_path)
    cluster_id = _none_if_empty(cluster_id)
    context_id = _none_if_empty(context_id)
    language = _none_if_empty(language) or "python"
    workspace_path = _none_if_empty(workspace_path)
    run_name = _none_if_empty(run_name)

    if not code and not file_path:
        return {"success": False, "error": "Either 'code' or 'file_path' must be provided."}

    # Resolve "auto" compute type
    if compute_type == "auto":
        if cluster_id or context_id:
            compute_type = "cluster"
        elif file_path and language and language.lower() in ("scala", "r"):
            compute_type = "cluster"
        elif language and language.lower() in ("scala", "r"):
            compute_type = "cluster"
        else:
            compute_type = "serverless"

    # --- File-based execution ---
    if file_path:
        if compute_type == "serverless":
            # Read file and run on serverless
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
            except FileNotFoundError:
                return {"success": False, "error": f"File not found: {file_path}"}
            except Exception as e:
                return {"success": False, "error": f"Failed to read file: {e}"}
            # Fall through to serverless execution below
        else:
            # Run file on cluster
            default_timeout = timeout if timeout is not None else 600
            try:
                result = _run_file_on_databricks(
                    file_path=file_path,
                    cluster_id=cluster_id,
                    context_id=context_id,
                    language=language if language != "python" else None,  # let it auto-detect
                    timeout=default_timeout,
                    destroy_context_on_completion=destroy_context_on_completion,
                    workspace_path=workspace_path,
                )
                return result.to_dict()
            except NoRunningClusterError as e:
                return _no_cluster_error_response(e)

    # --- Serverless execution ---
    if compute_type == "serverless":
        default_timeout = timeout if timeout is not None else 1800
        result = _run_code_on_serverless(
            code=code,
            language=language,
            timeout=default_timeout,
            run_name=run_name,
            cleanup=workspace_path is None,
            workspace_path=workspace_path,
        )
        return result.to_dict()

    # --- Cluster execution ---
    default_timeout = timeout if timeout is not None else 120
    try:
        result = _execute_databricks_command(
            code=code,
            cluster_id=cluster_id,
            context_id=context_id,
            language=language,
            timeout=default_timeout,
            destroy_context_on_completion=destroy_context_on_completion,
        )
        return result.to_dict()
    except NoRunningClusterError as e:
        return _no_cluster_error_response(e)


def _no_cluster_error_response(e: NoRunningClusterError) -> Dict[str, Any]:
    """Build a structured error response when no running cluster is available."""
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


# ---------------------------------------------------------------------------
# Tool 2: manage_cluster
# ---------------------------------------------------------------------------


@mcp.tool
def manage_cluster(
    action: str,
    cluster_id: str = None,
    name: str = None,
    num_workers: int = None,
    spark_version: str = None,
    node_type_id: str = None,
    autotermination_minutes: int = None,
    data_security_mode: str = None,
    spark_conf: str = None,
    autoscale_min_workers: int = None,
    autoscale_max_workers: int = None,
) -> Dict[str, Any]:
    """
    Create, modify, start, terminate, or delete a Databricks cluster.

    Actions:
    - "create": Create a new cluster. Requires name. Auto-picks latest LTS DBR,
      reasonable node type, SINGLE_USER mode, and 120-min auto-termination.
    - "modify": Update an existing cluster. Requires cluster_id. Only specified
      parameters change; others stay as-is. Running clusters restart to apply.
    - "start": Start a terminated cluster. Requires cluster_id.
      IMPORTANT: Always ask the user before starting (consumes cloud resources, 3-8 min).
    - "terminate": Stop a running cluster (reversible). Requires cluster_id.
    - "delete": PERMANENTLY delete a cluster (irreversible). Requires cluster_id.
      IMPORTANT: Always confirm with user before deleting.

    Args:
        action: One of "create", "modify", "start", "terminate", "delete".
        cluster_id: Required for modify, start, terminate, delete.
        name: Cluster name. Required for create, optional for modify.
        num_workers: Fixed worker count (ignored if autoscale is set). Default 1 for create.
        spark_version: DBR version key (e.g. "15.4.x-scala2.12"). Auto-picks if omitted.
        node_type_id: Worker node type (e.g. "i3.xlarge"). Auto-picked if omitted.
        autotermination_minutes: Minutes of inactivity before auto-stop. Default 120.
        data_security_mode: "SINGLE_USER", "USER_ISOLATION", etc. Default SINGLE_USER.
        spark_conf: JSON string of Spark config overrides.
        autoscale_min_workers: Min workers for autoscaling (set with max to enable).
        autoscale_max_workers: Max workers for autoscaling.

    Returns:
        Dictionary with cluster_id, cluster_name, state, and message.
    """
    action = action.lower().strip()

    # Normalize empty strings
    cluster_id = _none_if_empty(cluster_id)
    name = _none_if_empty(name)
    spark_version = _none_if_empty(spark_version)
    node_type_id = _none_if_empty(node_type_id)
    data_security_mode = _none_if_empty(data_security_mode)

    if action == "create":
        if not name:
            return {"success": False, "error": "name is required for create action."}

        # Parse spark_conf JSON
        parsed_spark_conf = None
        if spark_conf and spark_conf.strip():
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
            num_workers=num_workers if num_workers is not None else 1,
            autotermination_minutes=autotermination_minutes if autotermination_minutes is not None else 120,
            **kwargs,
        )

    elif action == "modify":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for modify action."}

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
        if spark_conf and spark_conf.strip():
            kwargs["spark_conf"] = json.loads(spark_conf)

        return _modify_cluster(cluster_id=cluster_id, **kwargs)

    elif action == "start":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for start action."}
        return _start_cluster(cluster_id)

    elif action == "terminate":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for terminate action."}
        return _terminate_cluster(cluster_id)

    elif action == "delete":
        if not cluster_id:
            return {"success": False, "error": "cluster_id is required for delete action."}
        return _delete_cluster(cluster_id)

    else:
        return {
            "success": False,
            "error": f"Unknown action: {action!r}. Must be one of: create, modify, start, terminate, delete.",
        }


# ---------------------------------------------------------------------------
# Tool 3: manage_sql_warehouse
# ---------------------------------------------------------------------------


@mcp.tool
def manage_sql_warehouse(
    action: str,
    warehouse_id: str = None,
    name: str = None,
    size: str = None,
    min_num_clusters: int = None,
    max_num_clusters: int = None,
    auto_stop_mins: int = None,
    warehouse_type: str = None,
    enable_serverless: bool = None,
) -> Dict[str, Any]:
    """
    Create, modify, or delete a Databricks SQL warehouse.

    Actions:
    - "create": Create a new warehouse. Requires name. Defaults to serverless
      Pro, Small size, 120-min auto-stop.
    - "modify": Update an existing warehouse. Requires warehouse_id. Only
      specified parameters change.
    - "delete": PERMANENTLY delete a warehouse (irreversible). Requires warehouse_id.
      IMPORTANT: Always confirm with user before deleting.

    For listing warehouses, use the list_warehouses tool (in SQL tools).

    Args:
        action: One of "create", "modify", "delete".
        warehouse_id: Required for modify and delete.
        name: Warehouse name. Required for create.
        size: T-shirt size ("2X-Small" through "4X-Large"). Default "Small".
        min_num_clusters: Minimum cluster count. Default 1.
        max_num_clusters: Maximum cluster count for scaling. Default 1.
        auto_stop_mins: Minutes of inactivity before auto-stop. Default 120.
        warehouse_type: "PRO" or "CLASSIC". Default "PRO".
        enable_serverless: Enable serverless compute. Default True.

    Returns:
        Dictionary with warehouse_id, name, state, and message.
    """
    action = action.lower().strip()

    warehouse_id = _none_if_empty(warehouse_id)
    name = _none_if_empty(name)
    size = _none_if_empty(size)
    warehouse_type = _none_if_empty(warehouse_type)

    if action == "create":
        if not name:
            return {"success": False, "error": "name is required for create action."}

        return _create_sql_warehouse(
            name=name,
            size=size or "Small",
            min_num_clusters=min_num_clusters if min_num_clusters is not None else 1,
            max_num_clusters=max_num_clusters if max_num_clusters is not None else 1,
            auto_stop_mins=auto_stop_mins if auto_stop_mins is not None else 120,
            warehouse_type=warehouse_type or "PRO",
            enable_serverless=enable_serverless if enable_serverless is not None else True,
        )

    elif action == "modify":
        if not warehouse_id:
            return {"success": False, "error": "warehouse_id is required for modify action."}

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

    elif action == "delete":
        if not warehouse_id:
            return {"success": False, "error": "warehouse_id is required for delete action."}
        return _delete_sql_warehouse(warehouse_id)

    else:
        return {
            "success": False,
            "error": f"Unknown action: {action!r}. Must be one of: create, modify, delete.",
        }


# ---------------------------------------------------------------------------
# Tool 4: list_compute
# ---------------------------------------------------------------------------


@mcp.tool
def list_compute(
    resource: str = "clusters",
    cluster_id: str = None,
    auto_select: bool = False,
) -> Dict[str, Any]:
    """
    List and inspect compute resources: clusters, node types, or spark versions.

    Args:
        resource: What to list. One of:
            - "clusters" (default): List all user-created clusters with state info.
            - "node_types": List available VM types for cluster creation.
            - "spark_versions": List available Databricks Runtime versions.
        cluster_id: (clusters only) If provided, returns detailed status for this
            specific cluster. Use after starting a cluster to poll until RUNNING.
        auto_select: (clusters only) If True, returns the best running cluster
            (prefers "shared" > "demo" in name). Useful for auto-picking a cluster.

    Returns:
        Dictionary with the requested resource data.
    """
    resource = resource.lower().strip()
    cluster_id = _none_if_empty(cluster_id)

    if resource == "clusters":
        if cluster_id:
            return _get_cluster_status(cluster_id)
        if auto_select:
            best = _get_best_cluster()
            return {"cluster_id": best}
        return {"clusters": _list_clusters()}

    elif resource == "node_types":
        return {"node_types": _list_node_types()}

    elif resource == "spark_versions":
        return {"spark_versions": _list_spark_versions()}

    else:
        return {
            "success": False,
            "error": f"Unknown resource: {resource!r}. Must be one of: clusters, node_types, spark_versions.",
        }
