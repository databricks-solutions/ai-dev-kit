"""Pipeline tools - Manage Spark Declarative Pipelines (SDP).

Provides 4 workflow-oriented tools following the Lakebase pattern:
- create_or_update_pipeline: idempotent resource management
- get_pipeline: get details by name/ID, or list all
- delete_pipeline: delete by ID
- run_pipeline: start, stop, and wait for pipeline runs
"""

import logging
from typing import List, Dict, Any, Optional

from databricks_tools_core.identity import get_default_tags
from databricks_tools_core.spark_declarative_pipelines.pipelines import (
    create_or_update_pipeline as _create_or_update_pipeline,
    get_pipeline as _get_pipeline,
    delete_pipeline as _delete_pipeline,
    start_update as _start_update,
    get_update as _get_update,
    stop_pipeline as _stop_pipeline,
    get_pipeline_events as _get_pipeline_events,
    find_pipeline_by_name as _find_pipeline_by_name,
    wait_for_pipeline_update as _wait_for_pipeline_update,
)

from ..manifest import register_deleter
from ..server import mcp

logger = logging.getLogger(__name__)


def _delete_pipeline_resource(resource_id: str) -> None:
    _delete_pipeline(pipeline_id=resource_id)


register_deleter("pipeline", _delete_pipeline_resource)


# ============================================================================
# Tool 1: create_or_update_pipeline
# ============================================================================


@mcp.tool
def create_or_update_pipeline(
    name: str,
    root_path: str,
    catalog: str,
    schema: str,
    workspace_file_paths: List[str],
    start_run: bool = False,
    wait_for_completion: bool = False,
    full_refresh: bool = True,
    timeout: int = 1800,
    extra_settings: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Create a new pipeline or update an existing one with the same name.

    This is the main tool for pipeline resource management. It:
    1. Searches for an existing pipeline with the same name (or uses 'id' from extra_settings)
    2. Creates a new pipeline or updates the existing one
    3. Optionally starts a run and waits for completion

    For more granular run control (stop, selective refresh, validate-only),
    use run_pipeline() separately.

    Uses Unity Catalog and serverless compute by default.

    Args:
        name: Pipeline name (used for lookup and creation)
        root_path: Root folder for source code (added to Python sys.path for imports)
        catalog: Unity Catalog name for output tables
        schema: Schema name for output tables
        workspace_file_paths: List of workspace file paths (raw .sql or .py files)
        start_run: If True, start a pipeline run after create/update (default: False)
        wait_for_completion: If True and start_run=True, wait for the run to finish (default: False)
        full_refresh: If True, performs full refresh when starting (default: True)
        timeout: Maximum wait time in seconds when wait_for_completion=True (default: 1800)
        extra_settings: Optional dict with additional pipeline settings. Supports all SDK
            options: clusters, continuous, development, photon, edition, channel, event_log,
            configuration, notifications, tags, serverless, etc.
            If 'id' is provided, the pipeline will be updated instead of created.
            Explicit parameters (name, root_path, catalog, schema) take precedence.

    Returns:
        Dictionary with:
        - pipeline_id: The pipeline ID
        - pipeline_name: The pipeline name
        - created: True if newly created, False if updated
        - success: True if operation succeeded
        - message: Human-readable status message

    Example:
        >>> create_or_update_pipeline(
        ...     name="my_pipeline",
        ...     root_path="/Workspace/project",
        ...     catalog="my_catalog",
        ...     schema="my_schema",
        ...     workspace_file_paths=["/Workspace/project/pipeline.py"]
        ... )
        >>> create_or_update_pipeline(
        ...     name="my_pipeline", ...,
        ...     start_run=True, wait_for_completion=True
        ... )
    """
    # Auto-inject default tags into extra_settings; user tags take precedence
    extra_settings = extra_settings or {}
    extra_settings.setdefault("tags", {})
    extra_settings["tags"] = {**get_default_tags(), **extra_settings["tags"]}

    result = _create_or_update_pipeline(
        name=name,
        root_path=root_path,
        catalog=catalog,
        schema=schema,
        workspace_file_paths=workspace_file_paths,
        start_run=start_run,
        wait_for_completion=wait_for_completion,
        full_refresh=full_refresh,
        timeout=timeout,
        extra_settings=extra_settings,
    )

    # Track resource on successful create/update
    try:
        result_dict = result.to_dict()
        pipeline_id = result_dict.get("pipeline_id")
        if pipeline_id:
            from ..manifest import track_resource

            track_resource(
                resource_type="pipeline",
                name=name,
                resource_id=pipeline_id,
            )
    except Exception:
        pass  # best-effort tracking

    return result.to_dict()


# ============================================================================
# Tool 2: get_pipeline
# ============================================================================


@mcp.tool
def get_pipeline(
    pipeline_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get pipeline details, or list all pipelines.

    Pass pipeline_id or name to get one pipeline's details enriched with
    latest update status and recent events. Omit both to list all pipelines.

    Args:
        pipeline_id: Pipeline ID. Takes precedence over name.
        name: Pipeline name. Used to look up pipeline ID if pipeline_id not provided.

    Returns:
        Single pipeline dict with enriched details (if ID/name provided),
        or {"pipelines": [...]} when listing all.

    Example:
        >>> get_pipeline(pipeline_id="abc-123")
        {"pipeline_id": "abc-123", "name": "my_pipeline", "state": "IDLE", ...}
        >>> get_pipeline(name="my_pipeline")
        {"pipeline_id": "abc-123", "name": "my_pipeline", ...}
        >>> get_pipeline()
        {"pipelines": [{"pipeline_id": "abc-123", "name": "my_pipeline", ...}]}
    """
    # Resolve name to pipeline_id if needed
    if not pipeline_id and name:
        pipeline_id = _find_pipeline_by_name(name=name)
        if not pipeline_id:
            return {"error": f"Pipeline '{name}' not found."}

    if pipeline_id:
        result = _get_pipeline(pipeline_id=pipeline_id)
        pipeline_dict = result.as_dict() if hasattr(result, "as_dict") else vars(result)

        # Enrich with latest update status
        try:
            latest_updates = pipeline_dict.get("latest_updates", [])
            if latest_updates:
                latest = latest_updates[0]
                update_id = latest.get("update_id")
                if update_id:
                    update_result = _get_update(pipeline_id=pipeline_id, update_id=update_id)
                    update_dict = update_result.as_dict() if hasattr(update_result, "as_dict") else vars(update_result)
                    pipeline_dict["latest_update_status"] = update_dict
        except Exception:
            pass

        # Enrich with recent events
        try:
            events = _get_pipeline_events(pipeline_id=pipeline_id, max_results=10)
            pipeline_dict["recent_events"] = [e.as_dict() if hasattr(e, "as_dict") else vars(e) for e in events]
        except Exception:
            pass

        return pipeline_dict

    # List all pipelines
    from databricks_tools_core.auth import get_workspace_client

    w = get_workspace_client()
    pipelines = []
    try:
        for p in w.pipelines.list_pipelines():
            entry = p.as_dict() if hasattr(p, "as_dict") else vars(p)
            pipelines.append(entry)
    except Exception as e:
        return {"error": f"Failed to list pipelines: {e}"}

    return {"pipelines": pipelines}


# ============================================================================
# Tool 3: delete_pipeline
# ============================================================================


@mcp.tool
def delete_pipeline(pipeline_id: str) -> Dict[str, str]:
    """
    Delete a pipeline.

    Args:
        pipeline_id: Pipeline ID

    Returns:
        Dictionary with status message.
    """
    _delete_pipeline(pipeline_id=pipeline_id)
    try:
        from ..manifest import remove_resource

        remove_resource(resource_type="pipeline", resource_id=pipeline_id)
    except Exception:
        pass
    return {"status": "deleted"}


# ============================================================================
# Tool 4: run_pipeline
# ============================================================================


@mcp.tool
def run_pipeline(
    pipeline_id: str,
    full_refresh: bool = False,
    refresh_selection: Optional[List[str]] = None,
    full_refresh_selection: Optional[List[str]] = None,
    validate_only: bool = False,
    wait_for_completion: bool = False,
    timeout: int = 1800,
    stop: bool = False,
) -> Dict[str, Any]:
    """
    Start, stop, or monitor a pipeline run.

    Set stop=True to stop a running pipeline. Otherwise starts an update.
    Optionally waits for the run to complete with timeout.

    Args:
        pipeline_id: Pipeline ID
        full_refresh: If True, performs full refresh of all tables
        refresh_selection: List of table names to refresh
        full_refresh_selection: List of table names for full refresh
        validate_only: If True, validates without updating data (dry run)
        wait_for_completion: If True, wait for run to complete (default: False)
        timeout: Maximum wait time in seconds (default: 1800 = 30 minutes)
        stop: If True, stop the currently running pipeline instead of starting

    Returns:
        Dictionary with:
        - update_id: Update ID (if started)
        - state: Final state (if waited)
        - success: True if completed successfully
        - duration_seconds: Time taken (if waited)
        - errors: List of error details (if failed)
        - status: "stopped" (if stop=True)

    Example:
        >>> run_pipeline(pipeline_id="abc-123", full_refresh=True)
        {"update_id": "xyz-456", "status": "started"}
        >>> run_pipeline(pipeline_id="abc-123", stop=True)
        {"status": "stopped"}
        >>> run_pipeline(pipeline_id="abc-123", wait_for_completion=True, timeout=600)
        {"update_id": "xyz-456", "state": "COMPLETED", "success": True, ...}
    """
    if stop:
        _stop_pipeline(pipeline_id=pipeline_id)
        return {"pipeline_id": pipeline_id, "status": "stopped"}

    update_id = _start_update(
        pipeline_id=pipeline_id,
        refresh_selection=refresh_selection,
        full_refresh=full_refresh,
        full_refresh_selection=full_refresh_selection,
        validate_only=validate_only,
    )

    result: Dict[str, Any] = {
        "pipeline_id": pipeline_id,
        "update_id": update_id,
        "status": "started",
    }

    if not wait_for_completion:
        result["message"] = (
            f"Pipeline update started. Use get_pipeline(pipeline_id='{pipeline_id}') "
            f"to check status, or run_pipeline with wait_for_completion=True to wait."
        )
        return result

    try:
        wait_result = _wait_for_pipeline_update(
            pipeline_id=pipeline_id,
            update_id=update_id,
            timeout=timeout,
        )
        result["state"] = wait_result["state"]
        result["success"] = wait_result["success"]
        result["duration_seconds"] = wait_result["duration_seconds"]
        result["status"] = "completed" if wait_result["success"] else "failed"

        if not wait_result["success"]:
            result["errors"] = wait_result.get("errors", [])
            if result["errors"]:
                first_error = result["errors"][0]
                error_msg = first_error.get("message", "")
                if first_error.get("exceptions"):
                    exc = first_error["exceptions"][0]
                    error_msg = exc.get("message", error_msg)
                result["error_message"] = error_msg
            result["message"] = (
                f"Pipeline run failed with state: {result['state']}. "
                f"Use get_pipeline(pipeline_id='{pipeline_id}') for full details."
            )
        else:
            result["message"] = f"Pipeline completed successfully in {result['duration_seconds']}s."

    except TimeoutError as e:
        result["state"] = "TIMEOUT"
        result["success"] = False
        result["status"] = "timeout"
        result["error_message"] = str(e)
        result["message"] = (
            f"Pipeline run timed out after {timeout}s. The pipeline may still be running. "
            f"Use get_pipeline(pipeline_id='{pipeline_id}') to check status."
        )

    return result
