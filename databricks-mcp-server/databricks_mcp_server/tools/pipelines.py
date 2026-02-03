"""Pipeline tools - Manage Spark Declarative Pipelines (SDP)."""

from typing import List, Dict, Any

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

from ..server import mcp


@mcp.tool
def create_pipeline(
    name: str,
    root_path: str,
    catalog: str,
    schema: str,
    workspace_file_paths: List[str],
    extra_settings: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Create a new Spark Declarative Pipeline (Unity Catalog, serverless by default).

    Args:
        name: Pipeline name
        root_path: Root folder for source code (added to Python sys.path for imports)
        catalog: Unity Catalog name
        schema: Schema name for output tables
        workspace_file_paths: List of workspace file paths (raw .sql or .py files)
        extra_settings: Optional dict with additional pipeline settings (clusters,
            continuous, development, photon, edition, channel, event_log, configuration,
            notifications, tags, serverless, etc.). Explicit parameters take precedence.

    Returns:
        Dictionary with pipeline_id of the created pipeline.
    """
    result = _create_pipeline(
        name=name,
        root_path=root_path,
        catalog=catalog,
        schema=schema,
        workspace_file_paths=workspace_file_paths,
        extra_settings=extra_settings,
    )
    return {"pipeline_id": result.pipeline_id}


@mcp.tool
def get_pipeline(pipeline_id: str) -> Dict[str, Any]:
    """
    Get pipeline details and configuration.

    Args:
        pipeline_id: Pipeline ID

    Returns:
        Dictionary with pipeline configuration and state.
    """
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
    """
    Update pipeline configuration.

    Args:
        pipeline_id: Pipeline ID
        name: New pipeline name
        root_path: New root folder for source code
        catalog: New catalog name
        schema: New schema name
        workspace_file_paths: New list of file paths (raw .sql or .py files)
        extra_settings: Optional dict with additional pipeline settings (clusters,
            continuous, development, photon, edition, channel, event_log, configuration,
            notifications, tags, serverless, etc.). Explicit parameters take precedence.

    Returns:
        Dictionary with status message.
    """
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
    """
    Delete a pipeline.

    Args:
        pipeline_id: Pipeline ID

    Returns:
        Dictionary with status message.
    """
    _delete_pipeline(pipeline_id=pipeline_id)
    return {"status": "deleted"}


@mcp.tool
def start_update(
    pipeline_id: str,
    refresh_selection: List[str] = None,
    full_refresh: bool = False,
    full_refresh_selection: List[str] = None,
    validate_only: bool = False,
) -> Dict[str, str]:
    """
    Start a pipeline update or dry-run validation.

    Args:
        pipeline_id: Pipeline ID
        refresh_selection: List of table names to refresh
        full_refresh: If True, performs full refresh of all tables
        full_refresh_selection: List of table names for full refresh
        validate_only: If True, validates without updating data (dry run)

    Returns:
        Dictionary with update_id for polling status.
    """
    update_id = _start_update(
        pipeline_id=pipeline_id,
        refresh_selection=refresh_selection,
        full_refresh=full_refresh,
        full_refresh_selection=full_refresh_selection,
        validate_only=validate_only,
    )
    return {"update_id": update_id}


@mcp.tool
def get_update(pipeline_id: str, update_id: str) -> Dict[str, Any]:
    """
    Get pipeline update status and results.

    Args:
        pipeline_id: Pipeline ID
        update_id: Update ID from start_update

    Returns:
        Dictionary with update status (QUEUED, RUNNING, COMPLETED, FAILED, etc.)
    """
    result = _get_update(pipeline_id=pipeline_id, update_id=update_id)
    return result.as_dict() if hasattr(result, "as_dict") else vars(result)


@mcp.tool
def stop_pipeline(pipeline_id: str) -> Dict[str, str]:
    """
    Stop a running pipeline.

    Args:
        pipeline_id: Pipeline ID

    Returns:
        Dictionary with status message.
    """
    _stop_pipeline(pipeline_id=pipeline_id)
    return {"status": "stopped"}


@mcp.tool
def get_pipeline_events(
    pipeline_id: str,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """
    Get pipeline events, issues, and error messages.

    Use this to debug pipeline failures.

    Args:
        pipeline_id: Pipeline ID
        max_results: Maximum number of events to return (default: 100)

    Returns:
        List of event dictionaries with error details.
    """
    events = _get_pipeline_events(pipeline_id=pipeline_id, max_results=max_results)
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
    """
    Create a new pipeline or update an existing one with the same name.

    This is the main tool for pipeline management. It:
    1. Searches for an existing pipeline with the same name (or uses 'id' from extra_settings)
    2. Creates a new pipeline or updates the existing one
    3. Optionally starts a pipeline run with full refresh
    4. Optionally waits for the run to complete and returns detailed results

    Uses Unity Catalog and serverless compute by default.

    Args:
        name: Pipeline name (used for lookup and creation)
        root_path: Root folder for source code (added to Python sys.path for imports)
        catalog: Unity Catalog name for output tables
        schema: Schema name for output tables
        workspace_file_paths: List of workspace file paths (raw .sql or .py files)
        start_run: If True, start a pipeline update after create/update (default: False)
        wait_for_completion: If True, wait for run to complete (default: False)
        full_refresh: If True, perform full refresh when starting (default: True)
        timeout: Maximum wait time in seconds (default: 1800 = 30 minutes)
        extra_settings: Optional dict with additional pipeline settings. Supports all SDK
            options: clusters, continuous, development, photon, edition, channel, event_log,
            configuration, notifications, tags, serverless, etc.
            If 'id' is provided, the pipeline will be updated instead of created.
            Explicit parameters (name, root_path, catalog, schema) take precedence.

    Returns:
        Dictionary with detailed status:
        - pipeline_id: The pipeline ID
        - pipeline_name: The pipeline name
        - created: True if newly created, False if updated
        - success: True if all operations succeeded
        - state: Final state if run was started (COMPLETED, FAILED, etc.)
        - duration_seconds: Time taken if waited
        - error_message: Error message if failed
        - errors: List of detailed errors if failed
        - message: Human-readable status message

    Example usage:
        # Just create/update the pipeline
        create_or_update_pipeline(name="my_pipeline", ...)

        # Create/update and run immediately
        create_or_update_pipeline(name="my_pipeline", ..., start_run=True)

        # Create/update, run, and wait for completion
        create_or_update_pipeline(
            name="my_pipeline", ...,
            start_run=True,
            wait_for_completion=True
        )

        # Create with custom settings (non-serverless, development mode)
        create_or_update_pipeline(
            name="my_pipeline", ...,
            extra_settings={
                "serverless": False,
                "development": True,
                "clusters": [{"label": "default", "num_workers": 2}]
            }
        )
    """
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
    return result.to_dict()


@mcp.tool
def find_pipeline_by_name(name: str) -> Dict[str, Any]:
    """
    Find a pipeline by name and return its ID.

    Args:
        name: Pipeline name to search for

    Returns:
        Dictionary with:
        - found: True if pipeline exists
        - pipeline_id: Pipeline ID if found, None otherwise
    """
    pipeline_id = _find_pipeline_by_name(name=name)
    return {
        "found": pipeline_id is not None,
        "pipeline_id": pipeline_id,
    }
