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


@mcp.tool(timeout=60)
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
    """Manage Databricks jobs: create, get, list, find_by_name, update, delete.

    create: requires name+tasks, serverless default, idempotent (returns existing if same name).
    get/update/delete: require job_id. find_by_name: returns job_id.
    tasks: [{task_key, notebook_task|spark_python_task|..., job_cluster_key or environment_key}].
    job_clusters: Shared cluster definitions tasks can reference. environments: Serverless env configs.
    schedule: {quartz_cron_expression, timezone_id}. git_source: {git_url, git_provider, git_branch}.
    See databricks-jobs skill for task configuration details.
    Returns: create={job_id}, get=full config, list={items}, find_by_name={job_id}, update/delete={status, job_id}."""
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


@mcp.tool(timeout=300)
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
    """Manage job runs: run_now, get, get_output, cancel, list, wait.

    run_now: requires job_id, returns {run_id}. get/get_output/cancel/wait: require run_id.
    list: filter by job_id/active_only/completed_only. wait: blocks until complete (timeout default 3600s).
    Returns: run_now={run_id}, get=run details, get_output=logs+results, cancel={status}, list={items}, wait=full result."""
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
