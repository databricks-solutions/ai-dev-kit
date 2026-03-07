"""
Jobs MCP Tools

Consolidated MCP tools for Databricks Jobs operations.
2 tools covering: job CRUD and job run management.
"""

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


# =============================================================================
# Tool 1: manage_jobs
# =============================================================================


@mcp.tool
def manage_jobs(
    action: str,
    job_id: int = None,
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
    limit: int = 25,
    expand_tasks: bool = False,
) -> Dict[str, Any]:
    """
    Manage Databricks jobs: create, get, list, find by name, update, and delete.

    Actions:
    - create: Create a new job (requires name, tasks). Uses serverless compute by default.
        Idempotent: if a job with the same name exists, returns it instead of creating a duplicate.
        Auto-merges default tags; user-provided tags take precedence.
    - get: Get detailed job configuration (requires job_id).
    - list: List jobs with optional name filter.
    - find_by_name: Find a job by exact name and return its ID.
    - update: Update an existing job's configuration (requires job_id).
    - delete: Delete a job permanently (requires job_id).

    Args:
        action: "create", "get", "list", "find_by_name", "update", or "delete"
        job_id: Job ID (for get, update, delete)
        name: Job name (for create, find_by_name, or list filter)
        tasks: List of task definitions (for create/update). Each task should have:
            - task_key: Unique identifier
            - description: Optional task description
            - depends_on: Optional list of task dependencies
            - [task_type]: One of spark_python_task, notebook_task, python_wheel_task,
                          spark_jar_task, spark_submit_task, pipeline_task, sql_task, dbt_task, run_job_task
            - [compute]: One of new_cluster, existing_cluster_id, job_cluster_key, compute_key
        job_clusters: Job cluster definitions (for create/update, non-serverless tasks)
        environments: Environment definitions for serverless tasks with custom dependencies (for create/update).
            Each dict: environment_key, spec (with client and dependencies list)
        tags: Tags dict for organization (for create/update)
        timeout_seconds: Job-level timeout in seconds (for create/update)
        max_concurrent_runs: Maximum concurrent runs (for create/update)
        email_notifications: Email notification settings (for create/update)
        webhook_notifications: Webhook notification settings (for create/update)
        notification_settings: Notification settings for run lifecycle events (for create/update)
        schedule: Schedule configuration (for create/update)
        queue: Queue settings (for create/update)
        run_as: Run-as user/service principal (for create/update)
        git_source: Git source configuration (for create/update)
        parameters: Job parameters (for create/update)
        health: Health monitoring rules (for create/update)
        deployment: Deployment configuration (for create/update)
        limit: Maximum number of jobs to return for list (default: 25)
        expand_tasks: If True, include full task definitions in list results (default: False)

    Returns:
        Dict with operation result:
        - create: {"job_id": int, ...} or {"job_id": int, "already_exists": True, ...}
        - get: Full job configuration dict
        - list: {"items": [...]}
        - find_by_name: {"job_id": int | None}
        - update: {"status": "updated", "job_id": int}
        - delete: {"status": "deleted", "job_id": int}
    """
    act = action.lower()

    if act == "create":
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
                    "Use manage_jobs(action='update') to modify it, or "
                    "manage_jobs(action='delete') first to recreate."
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
            max_concurrent_runs=max_concurrent_runs or 1,
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
            job_id_val = result.get("job_id") if isinstance(result, dict) else None
            if job_id_val:
                from ..manifest import track_resource

                track_resource(
                    resource_type="job",
                    name=name,
                    resource_id=str(job_id_val),
                )
        except Exception:
            pass  # best-effort tracking

        return result

    elif act == "get":
        return _get_job(job_id=job_id)

    elif act == "list":
        return {"items": _list_jobs(name=name, limit=limit, expand_tasks=expand_tasks)}

    elif act == "find_by_name":
        return {"job_id": _find_job_by_name(name=name)}

    elif act == "update":
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
        return {"status": "updated", "job_id": job_id}

    elif act == "delete":
        _delete_job(job_id=job_id)
        try:
            from ..manifest import remove_resource

            remove_resource(resource_type="job", resource_id=str(job_id))
        except Exception:
            pass
        return {"status": "deleted", "job_id": job_id}

    raise ValueError(f"Invalid action: '{action}'. Valid: create, get, list, find_by_name, update, delete")


# =============================================================================
# Tool 2: manage_job_runs
# =============================================================================


@mcp.tool
def manage_job_runs(
    action: str,
    job_id: int = None,
    run_id: int = None,
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
    active_only: bool = False,
    completed_only: bool = False,
    limit: int = 25,
    offset: int = 0,
    start_time_from: int = None,
    start_time_to: int = None,
    timeout: int = 3600,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """
    Manage Databricks job runs: trigger, monitor, and control.

    Actions:
    - run_now: Trigger a job run immediately (requires job_id).
    - get: Get detailed run status and information (requires run_id).
    - get_output: Get run output including logs and results (requires run_id).
    - cancel: Cancel a running job (requires run_id).
    - list: List job runs with optional filters.
    - wait: Wait for a job run to complete and return detailed results (requires run_id).

    Args:
        action: "run_now", "get", "get_output", "cancel", "list", or "wait"
        job_id: Job ID (for run_now, or list filter)
        run_id: Run ID (for get, get_output, cancel, wait)
        idempotency_token: Token to ensure idempotent job runs (for run_now)
        jar_params: Parameters for JAR tasks (for run_now)
        notebook_params: Parameters for notebook tasks (for run_now)
        python_params: Parameters for Python tasks (for run_now)
        spark_submit_params: Parameters for spark-submit tasks (for run_now)
        python_named_params: Named parameters for Python tasks (for run_now)
        pipeline_params: Parameters for pipeline tasks (for run_now)
        sql_params: Parameters for SQL tasks (for run_now)
        dbt_commands: Commands for dbt tasks (for run_now)
        queue: Queue settings for this run (for run_now)
        active_only: If True, only return active runs (for list)
        completed_only: If True, only return completed runs (for list)
        limit: Maximum number of runs to return (for list, default: 25)
        offset: Offset for pagination (for list)
        start_time_from: Filter by start time in epoch milliseconds (for list)
        start_time_to: Filter by start time in epoch milliseconds (for list)
        timeout: Maximum wait time in seconds (for wait, default: 3600)
        poll_interval: Time between status checks in seconds (for wait, default: 10)

    Returns:
        Dict with operation result:
        - run_now: {"run_id": int}
        - get: Run details dict with state, start_time, end_time, tasks, etc.
        - get_output: Run output dict with logs, error messages, and task outputs
        - cancel: {"status": "cancelled", "run_id": int}
        - list: {"items": [...]}
        - wait: Detailed run result dict with success, lifecycle_state, result_state,
                duration_seconds, error_message, run_page_url
    """
    act = action.lower()

    if act == "run_now":
        run_id_result = _run_job_now(
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
        return {"run_id": run_id_result}

    elif act == "get":
        return _get_run(run_id=run_id)

    elif act == "get_output":
        return _get_run_output(run_id=run_id)

    elif act == "cancel":
        _cancel_run(run_id=run_id)
        return {"status": "cancelled", "run_id": run_id}

    elif act == "list":
        return {
            "items": _list_runs(
                job_id=job_id,
                active_only=active_only,
                completed_only=completed_only,
                limit=limit,
                offset=offset,
                start_time_from=start_time_from,
                start_time_to=start_time_to,
            )
        }

    elif act == "wait":
        result = _wait_for_run(run_id=run_id, timeout=timeout, poll_interval=poll_interval)
        return result.to_dict()

    raise ValueError(f"Invalid action: '{action}'. Valid: run_now, get, get_output, cancel, list, wait")
