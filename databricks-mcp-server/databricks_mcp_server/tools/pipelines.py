"""Pipeline tools - Manage Spark Declarative Pipelines (SDP)."""

from typing import List, Dict, Any

from databricks_tools_core.identity import get_default_tags
from databricks_tools_core.spark_declarative_pipelines.pipelines import (
    create_pipeline as _create_pipeline,
    get_pipeline as _get_pipeline,
    update_pipeline as _update_pipeline,
    delete_pipeline as _delete_pipeline,
    start_update as _start_update,
    get_update as _get_update,
    stop_pipeline as _stop_pipeline,
    get_pipeline_events as _get_pipeline_events,
    create_or_update_pipeline as _create_or_update_pipeline,
    find_pipeline_by_name as _find_pipeline_by_name,
)

from ..manifest import register_deleter
from ..server import mcp


def _delete_pipeline_resource(resource_id: str) -> None:
    _delete_pipeline(pipeline_id=resource_id)


register_deleter("pipeline", _delete_pipeline_resource)


@mcp.tool
def create_pipeline(
    name: str,
    root_path: str,
    catalog: str,
    schema: str,
    workspace_file_paths: List[str],
    extra_settings: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Create a Spark Declarative Pipeline (SDP). Unity Catalog + serverless by default.

    root_path: Workspace folder for pipeline files. workspace_file_paths: Notebook/file paths to include.
    extra_settings: Additional config (clusters, photon, channel, etc).
    See databricks-spark-declarative-pipelines skill for configuration details.
    Returns: {pipeline_id}."""
    # Auto-inject default tags into extra_settings; user tags take precedence
    extra_settings = extra_settings or {}
    extra_settings.setdefault("tags", {})
    extra_settings["tags"] = {**get_default_tags(), **extra_settings["tags"]}

    result = _create_pipeline(
        name=name,
        root_path=root_path,
        catalog=catalog,
        schema=schema,
        workspace_file_paths=workspace_file_paths,
        extra_settings=extra_settings,
    )

    # Track resource on successful create
    try:
        if result.pipeline_id:
            from ..manifest import track_resource

            track_resource(
                resource_type="pipeline",
                name=name,
                resource_id=result.pipeline_id,
            )
    except Exception:
        pass  # best-effort tracking

    return {"pipeline_id": result.pipeline_id}


@mcp.tool
def get_pipeline(pipeline_id: str) -> Dict[str, Any]:
    """Get pipeline details and configuration."""
    result = _get_pipeline(pipeline_id=pipeline_id)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


@mcp.tool
def update_pipeline(
    pipeline_id: str,
    name: str = None,
    root_path: str = None,
    catalog: str = None,
    schema: str = None,
    workspace_file_paths: List[str] = None,
    extra_settings: Dict[str, Any] = None,
) -> Dict[str, str]:
    """Update pipeline configuration. Only specified params change. Returns: {status}."""
    _update_pipeline(
        pipeline_id=pipeline_id,
        name=name,
        root_path=root_path,
        catalog=catalog,
        schema=schema,
        workspace_file_paths=workspace_file_paths,
        extra_settings=extra_settings,
    )
    return {"status": "updated"}


@mcp.tool
def delete_pipeline(pipeline_id: str) -> Dict[str, str]:
    """Delete a pipeline. Returns: {status}."""
    _delete_pipeline(pipeline_id=pipeline_id)
    try:
        from ..manifest import remove_resource

        remove_resource(resource_type="pipeline", resource_id=pipeline_id)
    except Exception:
        pass
    return {"status": "deleted"}


@mcp.tool(timeout=300)
def start_update(
    pipeline_id: str,
    refresh_selection: List[str] = None,
    full_refresh: bool = False,
    full_refresh_selection: List[str] = None,
    validate_only: bool = False,
    wait: bool = True,
    timeout: int = 300,
    full_error_details: bool = False,
) -> Dict[str, Any]:
    """Start pipeline update. Waits for completion by default.

    Returns: {update_id, state, success, error_summary}."""
    return _start_update(
        pipeline_id=pipeline_id,
        refresh_selection=refresh_selection,
        full_refresh=full_refresh,
        full_refresh_selection=full_refresh_selection,
        validate_only=validate_only,
        wait=wait,
        timeout=timeout,
        full_error_details=full_error_details,
    )


@mcp.tool
def get_update(
    pipeline_id: str,
    update_id: str,
    include_config: bool = False,
    full_error_details: bool = False,
) -> Dict[str, Any]:
    """Get pipeline update status. Auto-fetches errors if failed.

    Returns: {update_id, state, success, error_summary}."""
    return _get_update(
        pipeline_id=pipeline_id,
        update_id=update_id,
        include_config=include_config,
        full_error_details=full_error_details,
    )


@mcp.tool
def stop_pipeline(pipeline_id: str) -> Dict[str, str]:
    """Stop a running pipeline. Returns: {status}."""
    _stop_pipeline(pipeline_id=pipeline_id)
    return {"status": "stopped"}


@mcp.tool
def get_pipeline_events(
    pipeline_id: str,
    max_results: int = 5,
    event_log_level: str = "WARN",
    update_id: str = None,
) -> List[Dict[str, Any]]:
    """Get pipeline events for debugging. event_log_level: ERROR, WARN (default), INFO."""
    # Convert log level to filter expression
    level_filters = {
        "ERROR": "level='ERROR'",
        "WARN": "level in ('ERROR', 'WARN')",
        "INFO": "",  # No filter = all events
    }
    filter_expr = level_filters.get(event_log_level.upper(), level_filters["WARN"])

    events = _get_pipeline_events(
        pipeline_id=pipeline_id, max_results=max_results, filter=filter_expr, update_id=update_id
    )
    return [e.as_dict() if hasattr(e, "as_dict") else vars(e) for e in events]


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
    """Create or update pipeline by name, optionally run. Unity Catalog + serverless.

    root_path: Workspace folder for pipeline files. workspace_file_paths: Notebook/file paths to include.
    extra_settings: Additional config (clusters, photon, etc). full_refresh: Reprocess all data.
    See databricks-spark-declarative-pipelines skill for configuration details.
    Returns: {pipeline_id, created, success, state, error_summary}."""
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


@mcp.tool
def find_pipeline_by_name(name: str) -> Dict[str, Any]:
    """Find pipeline by name. Returns: {found: bool, pipeline_id}."""
    pipeline_id = _find_pipeline_by_name(name=name)
    return {
        "found": pipeline_id is not None,
        "pipeline_id": pipeline_id,
    }
