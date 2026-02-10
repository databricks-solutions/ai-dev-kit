"""Jobs tools - Manage Databricks jobs and job runs."""

from typing import Any, Dict, List

from databricks_tools_core.identity import get_default_tags
from databricks_tools_core.jobs import (
    list_jobs as _list_jobs,
    get_job as _get_job,
    find_job_by_name as _find_job_by_name,
    create_job as _create_job,
    update_job as _update_job,
    delete_job as _delete_job,
    run_job_now as _run_job_now,
    get_run as _get_run,
    get_run_output as _get_run_output,
    cancel_run as _cancel_run,
    list_runs as _list_runs,
    wait_for_run as _wait_for_run,
)

from ..manifest import register_deleter
from ..server import mcp


def _delete_job_resource(resource_id: str) -> None:
    _delete_job(job_id=int(resource_id))


register_deleter("job", _delete_job_resource)


@mcp.tool
def list_jobs(
    name: str = None,
    limit: int = 25,
    expand_tasks: bool = False,
) -> List[Dict[str, Any]]:
    """
    List jobs in the workspace.

    Args:
        name: Optional name filter (partial match, case-insensitive).
        limit: Maximum number of jobs to return (default: 25).
        expand_tasks: If True, include full task definitions in results.

    Returns:
        List of job info dicts with job_id, name, creator, created_time, etc.
    """
    return _list_jobs(name=name, limit=limit, expand_tasks=expand_tasks)


@mcp.tool
def get_job(job_id: int) -> Dict[str, Any]:
    """
    Get detailed job configuration.

    Args:
        job_id: Job ID to retrieve.

    Returns:
        Dictionary with full job configuration including tasks, clusters, schedule, etc.
    """
    return _get_job(job_id=job_id)


@mcp.tool
def find_job_by_name(name: str) -> int | None:
    """
    Find a job by exact name and return its ID.

    Args:
        name: Job name to search for (exact match).

    Returns:
        Job ID if found, None otherwise.
    """
    return _find_job_by_name(name=name)


@mcp.tool
def create_job(
    name: str,
    tasks: List[Dict[str, Any]],
    job_clusters: List[Dict[str, Any]] = None,
    environments: List[Dict[str, Any]] = None,
    tags: Dict[str, str] = None,
    timeout_seconds: int = None,
    max_concurrent_runs: int = 1,
    email_notifications: Dict[str, Any] = None,
    webhook_notifications: Dict[str, Any] = None,
    notification_settings: Dict[str, Any] = None,
    schedule: Dict[str, Any] = None,
    queue: Dict[str, Any] = None,
    run_as: Dict[str, Any] = None,
    git_source: Dict[str, Any] = None,
    parameters: List[Dict[str, Any]] = None,
    health: Dict[str, Any] = None,
    deployment: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Create a new Databricks job with serverless compute by default.

    Args:
        name: Job name.
        tasks: List of task definitions. Each task should have:
            - task_key: Unique identifier
            - description: Optional task description
            - depends_on: Optional list of task dependencies
            - [task_type]: One of spark_python_task, notebook_task, python_wheel_task,
                          spark_jar_task, spark_submit_task, pipeline_task, sql_task, dbt_task, run_job_task
            - [compute]: One of new_cluster, existing_cluster_id, job_cluster_key, compute_key
        job_clusters: Optional list of job cluster definitions (for non-serverless tasks).
        environments: Optional list of environment definitions for serverless tasks with
            custom dependencies. Each dict should have:
            - environment_key: Unique identifier (referenced by tasks via environment_key)
            - spec: Dict with client (base environment version, defaults to "4" if omitted)
                    and dependencies (list of pip packages like "pandas==2.0.0")
            Example: [{
                       "environment_key": "ml_env",
                       "spec": {"client": "4", "dependencies": ["pandas==2.0.0", "scikit-learn"]}
                     }].
        tags: Optional tags dict for organization.
        timeout_seconds: Job-level timeout (0 means no timeout).
        max_concurrent_runs: Maximum number of concurrent runs (default: 1).
        email_notifications: Email notification settings.
        webhook_notifications: Webhook notification settings.
        notification_settings: Notification settings for run lifecycle events.
        schedule: Optional schedule configuration.
        queue: Optional queue settings for job queueing.
        run_as: Optional run-as user/service principal.
        git_source: Optional Git source configuration.
        parameters: Optional job parameters.
        health: Optional health monitoring rules.
        deployment: Optional deployment configuration.

    Returns:
        Dictionary with job_id and other creation metadata.

    Example:
        >>> tasks = [
        ...     {
        ...         "task_key": "data_ingestion",
        ...         "notebook_task": {
        ...             "notebook_path": "/Workspace/ETL/ingest",
        ...             "source": "WORKSPACE"
        ...         }
        ...     }
        ... ]
        >>> job = create_job(name="my_etl_job", tasks=tasks)
        >>> print(job["job_id"])
    """
    # Idempotency guard: check if a job with this name already exists.
    # Prevents duplicate creation when agents retry after MCP timeouts.
    existing_job_id = _find_job_by_name(name=name)
    if existing_job_id is not None:
        return {
            "job_id": existing_job_id,
            "already_exists": True,
            "message": (
                f"Job '{name}' already exists with job_id={existing_job_id}. "
                "Returning existing job instead of creating a duplicate. "
                "Use update_job() to modify it, or delete_job() first to recreate."
            ),
        }

    # Auto-inject default tags; user-provided tags take precedence
    merged_tags = {**get_default_tags(), **(tags or {})}
    result = _create_job(
        name=name,
        tasks=tasks,
        job_clusters=job_clusters,
        environments=environments,
        tags=merged_tags,
        timeout_seconds=timeout_seconds,
        max_concurrent_runs=max_concurrent_runs,
        email_notifications=email_notifications,
        webhook_notifications=webhook_notifications,
        notification_settings=notification_settings,
        schedule=schedule,
        queue=queue,
        run_as=run_as,
        git_source=git_source,
        parameters=parameters,
        health=health,
        deployment=deployment,
    )

    # Track resource on successful create
    try:
        job_id = result.get("job_id") if isinstance(result, dict) else None
        if job_id:
            from ..manifest import track_resource

            track_resource(
                resource_type="job",
                name=name,
                resource_id=str(job_id),
            )
    except Exception:
        pass  # best-effort tracking

    return result


@mcp.tool
def update_job(
    job_id: int,
    name: str = None,
    tasks: List[Dict[str, Any]] = None,
    job_clusters: List[Dict[str, Any]] = None,
    environments: List[Dict[str, Any]] = None,
    tags: Dict[str, str] = None,
    timeout_seconds: int = None,
    max_concurrent_runs: int = None,
    email_notifications: Dict[str, Any] = None,
    webhook_notifications: Dict[str, Any] = None,
    notification_settings: Dict[str, Any] = None,
    schedule: Dict[str, Any] = None,
    queue: Dict[str, Any] = None,
    run_as: Dict[str, Any] = None,
    git_source: Dict[str, Any] = None,
    parameters: List[Dict[str, Any]] = None,
    health: Dict[str, Any] = None,
    deployment: Dict[str, Any] = None,
) -> None:
    """
    Update an existing job's configuration.

    Only provided parameters will be updated. To remove a field, explicitly set it to None
    or an empty value.

    Args:
        job_id: Job ID to update.
        name: New job name.
        tasks: New task definitions.
        job_clusters: New job cluster definitions.
        environments: New environment definitions for serverless tasks with dependencies.
        tags: New tags (replaces existing).
        timeout_seconds: New timeout.
        max_concurrent_runs: New max concurrent runs.
        email_notifications: New email notifications.
        webhook_notifications: New webhook notifications.
        notification_settings: New notification settings.
        schedule: New schedule configuration.
        queue: New queue settings.
        run_as: New run-as configuration.
        git_source: New Git source configuration.
        parameters: New job parameters.
        health: New health monitoring rules.
        deployment: New deployment configuration.
    """
    _update_job(
        job_id=job_id,
        name=name,
        tasks=tasks,
        job_clusters=job_clusters,
        environments=environments,
        tags=tags,
        timeout_seconds=timeout_seconds,
        max_concurrent_runs=max_concurrent_runs,
        email_notifications=email_notifications,
        webhook_notifications=webhook_notifications,
        notification_settings=notification_settings,
        schedule=schedule,
        queue=queue,
        run_as=run_as,
        git_source=git_source,
        parameters=parameters,
        health=health,
        deployment=deployment,
    )


@mcp.tool
def delete_job(job_id: int) -> None:
    """
    Delete a job permanently.

    Args:
        job_id: Job ID to delete.
    """
    _delete_job(job_id=job_id)
    try:
        from ..manifest import remove_resource

        remove_resource(resource_type="job", resource_id=str(job_id))
    except Exception:
        pass


@mcp.tool
def run_job_now(
    job_id: int,
    idempotency_token: str = None,
    jar_params: List[str] = None,
    notebook_params: Dict[str, str] = None,
    python_params: List[str] = None,
    spark_submit_params: List[str] = None,
    python_named_params: Dict[str, str] = None,
    pipeline_params: Dict[str, Any] = None,
    sql_params: Dict[str, str] = None,
    dbt_commands: List[str] = None,
    queue: Dict[str, Any] = None,
) -> int:
    """
    Trigger a job run immediately and return the run ID.

    Args:
        job_id: Job ID to run.
        idempotency_token: Optional token to ensure idempotent job runs.
        jar_params: Parameters for JAR tasks.
        notebook_params: Parameters for notebook tasks.
        python_params: Parameters for Python tasks.
        spark_submit_params: Parameters for spark-submit tasks.
        python_named_params: Named parameters for Python tasks.
        pipeline_params: Parameters for pipeline tasks.
        sql_params: Parameters for SQL tasks.
        dbt_commands: Commands for dbt tasks.
        queue: Queue settings for this run.

    Returns:
        Run ID (integer) for tracking the run.

    Example:
        >>> run_id = run_job_now(job_id=123, notebook_params={"env": "prod"})
        >>> print(f"Started run {run_id}")
    """
    return _run_job_now(
        job_id=job_id,
        idempotency_token=idempotency_token,
        jar_params=jar_params,
        notebook_params=notebook_params,
        python_params=python_params,
        spark_submit_params=spark_submit_params,
        python_named_params=python_named_params,
        pipeline_params=pipeline_params,
        sql_params=sql_params,
        dbt_commands=dbt_commands,
        queue=queue,
    )


@mcp.tool
def get_run(run_id: int) -> Dict[str, Any]:
    """
    Get detailed run status and information.

    Args:
        run_id: Run ID to retrieve.

    Returns:
        Dictionary with run details including state, start_time, end_time, tasks, etc.
    """
    return _get_run(run_id=run_id)


@mcp.tool
def get_run_output(run_id: int) -> Dict[str, Any]:
    """
    Get run output including logs and results.

    Args:
        run_id: Run ID to get output for.

    Returns:
        Dictionary with run output including logs, error messages, and task outputs.
    """
    return _get_run_output(run_id=run_id)


@mcp.tool
def cancel_run(run_id: int) -> None:
    """
    Cancel a running job.

    Args:
        run_id: Run ID to cancel.
    """
    _cancel_run(run_id=run_id)


@mcp.tool
def list_runs(
    job_id: int = None,
    active_only: bool = False,
    completed_only: bool = False,
    limit: int = 25,
    offset: int = 0,
    start_time_from: int = None,
    start_time_to: int = None,
) -> List[Dict[str, Any]]:
    """
    List job runs with optional filters.

    Args:
        job_id: Optional filter by specific job ID.
        active_only: If True, only return active runs (RUNNING, PENDING, etc.).
        completed_only: If True, only return completed runs.
        limit: Maximum number of runs to return (default: 25, max: 1000).
        offset: Offset for pagination.
        start_time_from: Filter by start time (epoch milliseconds).
        start_time_to: Filter by start time (epoch milliseconds).

    Returns:
        List of run info dicts with run_id, state, start_time, job_id, etc.

    Example:
        >>> # Get last 10 runs for a specific job
        >>> runs = list_runs(job_id=123, limit=10)
        >>>
        >>> # Get all active runs
        >>> active_runs = list_runs(active_only=True)
    """
    return _list_runs(
        job_id=job_id,
        active_only=active_only,
        completed_only=completed_only,
        limit=limit,
        offset=offset,
        start_time_from=start_time_from,
        start_time_to=start_time_to,
    )


@mcp.tool
def wait_for_run(
    run_id: int,
    timeout: int = 3600,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """
    Wait for a job run to complete and return detailed results.

    Args:
        run_id: Run ID to wait for.
        timeout: Maximum wait time in seconds (default: 3600 = 1 hour).
        poll_interval: Time between status checks in seconds (default: 10).

    Returns:
        Dictionary with detailed run status including:
        - success: True if run completed successfully
        - lifecycle_state: Final lifecycle state (TERMINATED, SKIPPED, etc.)
        - result_state: Final result state (SUCCESS, FAILED, etc.)
        - duration_seconds: Total time taken
        - error_message: Error message if failed
        - run_page_url: Link to run in Databricks UI

    Example:
        >>> run_id = run_job_now(job_id=123)
        >>> result = wait_for_run(run_id=run_id, timeout=1800)
        >>> if result["success"]:
        ...     print(f"Job completed in {result['duration_seconds']}s")
        ... else:
        ...     print(f"Job failed: {result['error_message']}")
    """
    result = _wait_for_run(run_id=run_id, timeout=timeout, poll_interval=poll_interval)
    return result.to_dict()
