"""
Spark Declarative Pipelines - Pipeline Management

Functions for managing SDP pipeline lifecycle using Databricks Pipelines API.
All pipelines use Unity Catalog and serverless compute by default.
"""
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from databricks.sdk.service.pipelines import (
    CreatePipelineResponse,
    GetPipelineResponse,
    PipelineLibrary,
    FileLibrary,
    PipelineEvent,
    GetUpdateResponse,
    UpdateInfoState,
    PipelineCluster,
    EventLogSpec,
    Notifications,
    RestartWindow,
    PipelineDeployment,
    Filters,
    PipelinesEnvironment,
    IngestionGatewayPipelineDefinition,
    IngestionPipelineDefinition,
    PipelineTrigger,
    RunAs,
)

from ..auth import get_workspace_client


# Fields that are not valid SDK parameters and should be filtered out
_INVALID_SDK_FIELDS = {"pipeline_type"}

# Fields that need conversion from dict to SDK objects
_COMPLEX_FIELD_CONVERTERS = {
    "libraries": lambda items: [PipelineLibrary.from_dict(item) for item in items] if items else None,
    "clusters": lambda items: [PipelineCluster.from_dict(item) for item in items] if items else None,
    "event_log": lambda item: EventLogSpec.from_dict(item) if item else None,
    "notifications": lambda items: [Notifications.from_dict(item) for item in items] if items else None,
    "restart_window": lambda item: RestartWindow.from_dict(item) if item else None,
    "deployment": lambda item: PipelineDeployment.from_dict(item) if item else None,
    "filters": lambda item: Filters.from_dict(item) if item else None,
    "environment": lambda item: PipelinesEnvironment.from_dict(item) if item else None,
    "gateway_definition": lambda item: IngestionGatewayPipelineDefinition.from_dict(item) if item else None,
    "ingestion_definition": lambda item: IngestionPipelineDefinition.from_dict(item) if item else None,
    "trigger": lambda item: PipelineTrigger.from_dict(item) if item else None,
    "run_as": lambda item: RunAs.from_dict(item) if item else None,
}


def _convert_extra_settings(extra_settings: dict[str, Any]) -> dict[str, Any]:
    """
    Convert extra_settings dict to SDK-compatible kwargs.

    - Filters out invalid fields (e.g., pipeline_type)
    - Converts nested dicts to SDK objects (e.g., clusters, event_log)
    - Passes simple types directly

    Args:
        extra_settings: Raw dict from user (e.g., from Databricks UI JSON export)

    Returns:
        Dict with SDK-compatible values
    """
    result = {}

    for key, value in extra_settings.items():
        # Skip invalid fields
        if key in _INVALID_SDK_FIELDS:
            continue

        # Skip None values
        if value is None:
            continue

        # Convert complex fields
        if key in _COMPLEX_FIELD_CONVERTERS:
            converted = _COMPLEX_FIELD_CONVERTERS[key](value)
            if converted is not None:
                result[key] = converted
        else:
            # Pass simple types directly (strings, bools, dicts like configuration/tags)
            result[key] = value

    return result


# Terminal states - pipeline update has finished (success or failure)
TERMINAL_STATES = {
    UpdateInfoState.COMPLETED,
    UpdateInfoState.FAILED,
    UpdateInfoState.CANCELED,
}

# Running states - pipeline update is in progress
RUNNING_STATES = {
    UpdateInfoState.RUNNING,
    UpdateInfoState.INITIALIZING,
    UpdateInfoState.SETTING_UP_TABLES,
    UpdateInfoState.WAITING_FOR_RESOURCES,
    UpdateInfoState.QUEUED,
    UpdateInfoState.RESETTING,
    UpdateInfoState.STOPPING,
    UpdateInfoState.CREATED,
}


def _build_libraries(workspace_file_paths: list[str]) -> list[PipelineLibrary]:
    """Build PipelineLibrary list from file paths."""
    return [
        PipelineLibrary(file=FileLibrary(path=path))
        for path in workspace_file_paths
    ]


def _extract_error_details(events: list[PipelineEvent]) -> list[dict[str, Any]]:
    """Extract error details from pipeline events for LLM consumption."""
    errors = []
    for event in events:
        if event.error:
            error_info = {
                "message": str(event.message) if event.message else None,
                "level": event.level.value if event.level else None,
                "timestamp": event.timestamp if event.timestamp else None,
            }
            # Extract exception details
            if event.error.exceptions:
                exceptions = []
                for exc in event.error.exceptions:
                    exc_detail = {
                        "class_name": exc.class_name if hasattr(exc, 'class_name') else None,
                        "message": exc.message if hasattr(exc, 'message') else str(exc),
                    }
                    exceptions.append(exc_detail)
                error_info["exceptions"] = exceptions
            errors.append(error_info)
    return errors


@dataclass
class PipelineRunResult:
    """
    Result from a pipeline operation with detailed status for LLM consumption.

    This dataclass provides comprehensive information about pipeline operations
    to help LLMs understand what happened and take appropriate action.
    """
    # Pipeline identification
    pipeline_id: str
    pipeline_name: str

    # Operation details
    update_id: str | None = None
    state: str | None = None
    success: bool = False
    created: bool = False  # True if pipeline was created, False if updated

    # Configuration (for context)
    catalog: str | None = None
    schema: str | None = None
    root_path: str | None = None

    # Timing
    duration_seconds: float | None = None

    # Error details (if failed)
    error_message: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)

    # Human-readable status
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "update_id": self.update_id,
            "state": self.state,
            "success": self.success,
            "created": self.created,
            "catalog": self.catalog,
            "schema": self.schema,
            "root_path": self.root_path,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "errors": self.errors,
            "message": self.message,
        }


def find_pipeline_by_name(name: str) -> str | None:
    """
    Find a pipeline by name and return its ID.

    Args:
        name: Pipeline name to search for (exact match)

    Returns:
        Pipeline ID if found, None otherwise
    """
    w = get_workspace_client()

    # List pipelines with name filter and find exact match
    for pipeline in w.pipelines.list_pipelines(filter=f"name LIKE '{name}'"):
        if pipeline.name == name:
            return pipeline.pipeline_id

    return None


def create_pipeline(
    name: str,
    root_path: str,
    catalog: str,
    schema: str,
    workspace_file_paths: list[str],
    extra_settings: dict[str, Any] | None = None,
) -> CreatePipelineResponse:
    """
    Create a new Spark Declarative Pipeline (Unity Catalog, serverless by default).

    Args:
        name: Pipeline name
        root_path: Root folder for source code (added to Python sys.path for imports)
        catalog: Unity Catalog name
        schema: Schema name for output tables
        workspace_file_paths: List of workspace file paths (raw .sql or .py files)
        extra_settings: Optional dict with additional pipeline settings. These are passed
            directly to the Databricks SDK pipelines.create() call. Explicit parameters
            (name, root_path, catalog, schema, workspace_file_paths) take precedence.
            Supports all SDK options: clusters, continuous, development, photon, edition,
            channel, event_log, configuration, notifications, tags, etc.
            Note: If 'id' is provided in extra_settings, use update_pipeline instead.

    Returns:
        CreatePipelineResponse with pipeline_id

    Raises:
        DatabricksError: If pipeline already exists or API request fails
    """
    w = get_workspace_client()
    libraries = _build_libraries(workspace_file_paths)

    # Start with converted extra_settings as base
    kwargs: dict[str, Any] = {}
    if extra_settings:
        kwargs = _convert_extra_settings(extra_settings)

    # Explicit parameters always take precedence
    kwargs["name"] = name
    kwargs["root_path"] = root_path
    kwargs["catalog"] = catalog
    kwargs["schema"] = schema
    kwargs["libraries"] = libraries

    # Set defaults only if not provided in extra_settings
    if "continuous" not in kwargs:
        kwargs["continuous"] = False
    if "serverless" not in kwargs:
        kwargs["serverless"] = True

    # Remove 'id' if present - create should not have an id
    kwargs.pop("id", None)

    return w.pipelines.create(**kwargs)


def get_pipeline(pipeline_id: str) -> GetPipelineResponse:
    """
    Get pipeline details and configuration.

    Args:
        pipeline_id: Pipeline ID

    Returns:
        GetPipelineResponse with full pipeline configuration and state
    """
    w = get_workspace_client()
    return w.pipelines.get(pipeline_id=pipeline_id)


def update_pipeline(
    pipeline_id: str,
    name: str | None = None,
    root_path: str | None = None,
    catalog: str | None = None,
    schema: str | None = None,
    workspace_file_paths: list[str] | None = None,
    extra_settings: dict[str, Any] | None = None,
) -> None:
    """
    Update pipeline configuration.

    Args:
        pipeline_id: Pipeline ID
        name: New pipeline name
        root_path: New root folder for source code
        catalog: New catalog name
        schema: New schema name
        workspace_file_paths: New list of file paths (raw .sql or .py files)
        extra_settings: Optional dict with additional pipeline settings. These are passed
            directly to the Databricks SDK pipelines.update() call. Explicit parameters
            take precedence over values in extra_settings.
            Supports all SDK options: clusters, continuous, development, photon, edition,
            channel, event_log, configuration, notifications, tags, etc.
    """
    w = get_workspace_client()

    # Start with converted extra_settings as base
    kwargs: dict[str, Any] = {}
    if extra_settings:
        kwargs = _convert_extra_settings(extra_settings)

    # pipeline_id is required and always set
    kwargs["pipeline_id"] = pipeline_id

    # Explicit parameters take precedence (only if provided)
    if name:
        kwargs["name"] = name
    if root_path:
        kwargs["root_path"] = root_path
    if catalog:
        kwargs["catalog"] = catalog
    if schema:
        kwargs["schema"] = schema
    if workspace_file_paths:
        kwargs["libraries"] = _build_libraries(workspace_file_paths)

    # Ensure id in kwargs matches pipeline_id (SDK uses both)
    if "id" in kwargs and kwargs["id"] != pipeline_id:
        kwargs["id"] = pipeline_id

    w.pipelines.update(**kwargs)


def delete_pipeline(pipeline_id: str) -> None:
    """
    Delete a pipeline.

    Args:
        pipeline_id: Pipeline ID
    """
    w = get_workspace_client()
    w.pipelines.delete(pipeline_id=pipeline_id)


def start_update(
    pipeline_id: str,
    refresh_selection: list[str] | None = None,
    full_refresh: bool = False,
    full_refresh_selection: list[str] | None = None,
    validate_only: bool = False
) -> str:
    """
    Start a pipeline update or dry-run validation.

    Args:
        pipeline_id: Pipeline ID
        refresh_selection: List of table names to refresh
        full_refresh: If True, performs full refresh of all tables
        full_refresh_selection: List of table names for full refresh
        validate_only: If True, performs dry-run validation without updating data

    Returns:
        Update ID for polling status
    """
    w = get_workspace_client()

    response = w.pipelines.start_update(
        pipeline_id=pipeline_id,
        refresh_selection=refresh_selection,
        full_refresh=full_refresh,
        full_refresh_selection=full_refresh_selection,
        validate_only=validate_only
    )

    return response.update_id


def get_update(pipeline_id: str, update_id: str) -> GetUpdateResponse:
    """
    Get pipeline update status and results.

    Args:
        pipeline_id: Pipeline ID
        update_id: Update ID from start_update

    Returns:
        GetUpdateResponse with update status (QUEUED, RUNNING, COMPLETED, FAILED, etc.)
    """
    w = get_workspace_client()
    return w.pipelines.get_update(
        pipeline_id=pipeline_id,
        update_id=update_id
    )


def stop_pipeline(pipeline_id: str) -> None:
    """
    Stop a running pipeline.

    Args:
        pipeline_id: Pipeline ID
    """
    w = get_workspace_client()
    w.pipelines.stop(pipeline_id=pipeline_id)


def get_pipeline_events(
    pipeline_id: str,
    max_results: int = 100
) -> list[PipelineEvent]:
    """
    Get pipeline events, issues, and error messages.

    Use this to debug pipeline failures.

    Args:
        pipeline_id: Pipeline ID
        max_results: Maximum number of events to return

    Returns:
        List of PipelineEvent objects with error details
    """
    w = get_workspace_client()
    events = w.pipelines.list_pipeline_events(
        pipeline_id=pipeline_id,
        max_results=max_results
    )
    return list(events)


def wait_for_pipeline_update(
    pipeline_id: str,
    update_id: str,
    timeout: int = 1800,
    poll_interval: int = 5
) -> dict[str, Any]:
    """
    Wait for a pipeline update to complete and return detailed results.

    Args:
        pipeline_id: Pipeline ID
        update_id: Update ID from start_update
        timeout: Maximum wait time in seconds (default: 30 minutes)
        poll_interval: Time between status checks in seconds

    Returns:
        Dictionary with detailed update results:
        - state: Final state (COMPLETED, FAILED, CANCELED)
        - success: True if completed successfully
        - duration_seconds: Total time taken
        - errors: List of error details if failed

    Raises:
        TimeoutError: If pipeline doesn't complete within timeout
    """
    w = get_workspace_client()
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            raise TimeoutError(
                f"Pipeline update {update_id} did not complete within {timeout} seconds. "
                f"Check pipeline status in Databricks UI or call get_update(pipeline_id='{pipeline_id}', update_id='{update_id}')."
            )

        response = w.pipelines.get_update(
            pipeline_id=pipeline_id,
            update_id=update_id
        )

        update_info = response.update
        if not update_info:
            time.sleep(poll_interval)
            continue

        state = update_info.state

        if state in TERMINAL_STATES:
            result = {
                "state": state.value if state else None,
                "success": state == UpdateInfoState.COMPLETED,
                "duration_seconds": round(elapsed, 2),
                "update_id": update_id,
                "errors": [],
            }

            # If failed, get detailed error information
            if state == UpdateInfoState.FAILED:
                events = get_pipeline_events(pipeline_id, max_results=50)
                result["errors"] = _extract_error_details(events)

            return result

        time.sleep(poll_interval)


def create_or_update_pipeline(
    name: str,
    root_path: str,
    catalog: str,
    schema: str,
    workspace_file_paths: list[str],
    start_run: bool = False,
    wait_for_completion: bool = False,
    full_refresh: bool = True,
    timeout: int = 1800,
    extra_settings: dict[str, Any] | None = None,
) -> PipelineRunResult:
    """
    Create a new pipeline or update an existing one with the same name.

    This is the main entry point for pipeline management. It:
    1. Searches for an existing pipeline with the same name (or uses 'id' from extra_settings)
    2. Creates a new pipeline or updates the existing one
    3. Optionally starts a pipeline run
    4. Optionally waits for the run to complete

    Uses Unity Catalog and serverless compute by default.

    Args:
        name: Pipeline name (used for lookup and creation)
        root_path: Root folder for source code (added to Python sys.path for imports)
        catalog: Unity Catalog name for output tables
        schema: Schema name for output tables
        workspace_file_paths: List of workspace file paths (raw .sql or .py files)
        start_run: If True, start a pipeline run after create/update
        wait_for_completion: If True, wait for the run to complete (requires start_run=True)
        full_refresh: If True, perform full refresh when starting
        timeout: Maximum wait time in seconds (default: 30 minutes)
        extra_settings: Optional dict with additional pipeline settings. Supports all SDK
            options: clusters, continuous, development, photon, edition, channel, event_log,
            configuration, notifications, tags, serverless, etc.
            If 'id' is provided, the pipeline will be updated instead of created.
            Explicit parameters (name, root_path, catalog, schema) take precedence.

    Returns:
        PipelineRunResult with detailed status including:
        - pipeline_id, pipeline_name, catalog, schema, root_path
        - created: True if newly created, False if updated
        - success: True if all operations succeeded
        - state: Final state if run was started (COMPLETED, FAILED, etc.)
        - duration_seconds: Time taken if waited
        - error_message: Summary error message if failed
        - errors: List of detailed errors if failed
        - message: Human-readable status message
    """
    # Step 1: Check if pipeline exists (by name or by id in extra_settings)
    existing_pipeline_id = None

    # If extra_settings contains an 'id', use it for update
    if extra_settings and extra_settings.get("id"):
        existing_pipeline_id = extra_settings["id"]
    else:
        existing_pipeline_id = find_pipeline_by_name(name)

    created = existing_pipeline_id is None

    # Step 2: Create or update
    try:
        if created:
            response = create_pipeline(
                name=name,
                root_path=root_path,
                catalog=catalog,
                schema=schema,
                workspace_file_paths=workspace_file_paths,
                extra_settings=extra_settings,
            )
            pipeline_id = response.pipeline_id
        else:
            pipeline_id = existing_pipeline_id
            update_pipeline(
                pipeline_id=pipeline_id,
                name=name,
                root_path=root_path,
                catalog=catalog,
                schema=schema,
                workspace_file_paths=workspace_file_paths,
                extra_settings=extra_settings,
            )
    except Exception as e:
        # Return detailed error for LLM consumption
        return PipelineRunResult(
            pipeline_id=existing_pipeline_id or "unknown",
            pipeline_name=name,
            catalog=catalog,
            schema=schema,
            root_path=root_path,
            success=False,
            created=False,
            error_message=str(e),
            message=f"Failed to {'create' if created else 'update'} pipeline: {e}",
        )

    # Build result with context
    result = PipelineRunResult(
        pipeline_id=pipeline_id,
        pipeline_name=name,
        catalog=catalog,
        schema=schema,
        root_path=root_path,
        created=created,
        success=True,
        message=f"Pipeline {'created' if created else 'updated'} successfully. "
                f"Target: {catalog}.{schema}",
    )

    # Step 3: Start run if requested
    if start_run:
        try:
            update_id = start_update(
                pipeline_id=pipeline_id,
                full_refresh=full_refresh,
            )
            result.update_id = update_id
            result.message = (
                f"Pipeline {'created' if created else 'updated'} and run started. "
                f"Update ID: {update_id}"
            )
        except Exception as e:
            result.success = False
            result.error_message = f"Pipeline created but failed to start run: {e}"
            result.message = result.error_message
            return result

        # Step 4: Wait for completion if requested
        if wait_for_completion:
            try:
                wait_result = wait_for_pipeline_update(
                    pipeline_id=pipeline_id,
                    update_id=update_id,
                    timeout=timeout,
                )
                result.state = wait_result["state"]
                result.success = wait_result["success"]
                result.duration_seconds = wait_result["duration_seconds"]

                if result.success:
                    result.message = (
                        f"Pipeline {'created' if created else 'updated'} and "
                        f"completed successfully in {result.duration_seconds}s. "
                        f"Tables written to {catalog}.{schema}"
                    )
                else:
                    result.errors = wait_result.get("errors", [])
                    # Build informative error message for LLM
                    if result.errors:
                        first_error = result.errors[0]
                        error_msg = first_error.get("message", "")
                        if first_error.get("exceptions"):
                            exc = first_error["exceptions"][0]
                            error_msg = exc.get("message", error_msg)
                        result.error_message = error_msg
                    else:
                        result.error_message = f"Pipeline failed with state: {result.state}"

                    result.message = (
                        f"Pipeline {'created' if created else 'updated'} but run failed. "
                        f"State: {result.state}. "
                        f"Error: {result.error_message}. "
                        f"Use get_pipeline_events(pipeline_id='{pipeline_id}') for full details."
                    )

            except TimeoutError as e:
                result.success = False
                result.state = "TIMEOUT"
                result.error_message = str(e)
                result.message = (
                    f"Pipeline run timed out after {timeout}s. "
                    f"The pipeline may still be running. "
                    f"Check status with get_update(pipeline_id='{pipeline_id}', update_id='{update_id}')"
                )

    return result
