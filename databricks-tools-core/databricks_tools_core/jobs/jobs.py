"""
Jobs - Core Job CRUD Operations

Functions for managing Databricks jobs using the Jobs API.
Uses serverless compute by default for optimal performance and cost.
"""

from typing import Optional, List, Dict, Any

from databricks.sdk.service.jobs import JobSettings

from ..auth import get_workspace_client
from .models import JobError


def list_jobs(
    name: Optional[str] = None,
    limit: int = 25,
    expand_tasks: bool = False,
) -> List[Dict[str, Any]]:
    """
    List jobs in the workspace.

    Args:
        name: Optional name filter (partial match, case-insensitive)
        limit: Maximum number of jobs to return (default: 25)
        expand_tasks: If True, include full task definitions in results

    Returns:
        List of job info dicts with job_id, name, creator, created_time, etc.
    """
    w = get_workspace_client()
    jobs = []

    # SDK list() returns an iterator - we need to consume it
    for job in w.jobs.list(name=name, expand_tasks=expand_tasks, limit=limit):
        job_dict = {
            "job_id": job.job_id,
            "name": job.settings.name if job.settings else None,
            "creator_user_name": job.creator_user_name,
            "created_time": job.created_time,
        }

        # Add additional info if available
        if job.settings:
            job_dict["tags"] = job.settings.tags if hasattr(job.settings, "tags") else None
            job_dict["timeout_seconds"] = (
                job.settings.timeout_seconds if hasattr(job.settings, "timeout_seconds") else None
            )
            job_dict["max_concurrent_runs"] = (
                job.settings.max_concurrent_runs if hasattr(job.settings, "max_concurrent_runs") else None
            )

            # Include tasks if expanded
            if expand_tasks and job.settings.tasks:
                job_dict["tasks"] = [task.as_dict() for task in job.settings.tasks]

        jobs.append(job_dict)

        if len(jobs) >= limit:
            break

    return jobs


def get_job(job_id: int) -> Dict[str, Any]:
    """
    Get detailed job configuration.

    Args:
        job_id: Job ID

    Returns:
        Dictionary with full job configuration including tasks, clusters, schedule, etc.

    Raises:
        JobError: If job not found or API request fails
    """
    w = get_workspace_client()

    try:
        job = w.jobs.get(job_id=job_id)

        # Convert SDK object to dict for JSON serialization
        return job.as_dict()

    except Exception as e:
        raise JobError(f"Failed to get job {job_id}: {str(e)}", job_id=job_id)


def find_job_by_name(name: str) -> Optional[int]:
    """
    Find a job by exact name and return its ID.

    Args:
        name: Job name to search for (exact match)

    Returns:
        Job ID if found, None otherwise
    """
    w = get_workspace_client()

    # List jobs with name filter and find exact match
    for job in w.jobs.list(name=name, limit=100):
        if job.settings and job.settings.name == name:
            return job.job_id

    return None


def create_job(
    name: str,
    tasks: List[Dict[str, Any]],
    job_clusters: Optional[List[Dict[str, Any]]] = None,
    environments: Optional[List[Dict[str, Any]]] = None,
    tags: Optional[Dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_concurrent_runs: int = 1,
    email_notifications: Optional[Dict[str, Any]] = None,
    webhook_notifications: Optional[Dict[str, Any]] = None,
    notification_settings: Optional[Dict[str, Any]] = None,
    schedule: Optional[Dict[str, Any]] = None,
    queue: Optional[Dict[str, Any]] = None,
    run_as: Optional[Dict[str, Any]] = None,
    git_source: Optional[Dict[str, Any]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    health: Optional[Dict[str, Any]] = None,
    deployment: Optional[Dict[str, Any]] = None,
    **extra_settings,
) -> Dict[str, Any]:
    """
    Create a new Databricks job with serverless compute by default.

    Args:
        name: Job name
        tasks: List of task definitions (dicts). Each task should have:
            - task_key: Unique identifier
            - description: Optional task description
            - depends_on: Optional list of task dependencies
            - [task_type]: One of spark_python_task, notebook_task, python_wheel_task,
                          spark_jar_task, spark_submit_task, pipeline_task, sql_task, dbt_task, run_job_task
            - [compute]: One of new_cluster, existing_cluster_id, job_cluster_key, compute_key
        job_clusters: Optional list of job cluster definitions (for non-serverless tasks)
        environments: Optional list of environment definitions for serverless tasks.
            Each dict should have:
            - environment_key: Unique identifier referenced by tasks via environment_key
            - spec: Dict with dependencies (list of pip packages) and optionally client ("4")
        tags: Optional tags dict for organization
        timeout_seconds: Job-level timeout (0 means no timeout)
        max_concurrent_runs: Maximum number of concurrent runs (default: 1)
        email_notifications: Email notification settings
        webhook_notifications: Webhook notification settings
        notification_settings: Notification settings for run lifecycle events
        schedule: Optional schedule configuration
        queue: Optional queue settings for job queueing
        run_as: Optional run-as user/service principal
        git_source: Optional Git source configuration
        parameters: Optional job parameters
        health: Optional health monitoring rules
        deployment: Optional deployment configuration
        **extra_settings: Additional job settings passed directly to SDK

    Returns:
        Dictionary with job_id and other creation metadata

    Raises:
        JobError: If job creation fails

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
    w = get_workspace_client()

    try:
        # Build settings dict - JobSettings.from_dict() handles all nested conversions
        settings_dict: Dict[str, Any] = {
            "name": name,
            "max_concurrent_runs": max_concurrent_runs,
        }

        # Add tasks
        if tasks:
            settings_dict["tasks"] = tasks

        # Add job_clusters if provided
        if job_clusters:
            settings_dict["job_clusters"] = job_clusters

        # Add environments if provided (for serverless tasks with dependencies)
        # Auto-inject "client": "4" into spec if missing to avoid API error:
        # "Either base environment or version must be provided for environment"
        if environments:
            for env in environments:
                if "spec" in env and "client" not in env["spec"]:
                    env["spec"]["client"] = "4"
            settings_dict["environments"] = environments

        # Add optional parameters
        if tags:
            settings_dict["tags"] = tags
        if timeout_seconds is not None:
            settings_dict["timeout_seconds"] = timeout_seconds
        if email_notifications:
            settings_dict["email_notifications"] = email_notifications
        if webhook_notifications:
            settings_dict["webhook_notifications"] = webhook_notifications
        if notification_settings:
            settings_dict["notification_settings"] = notification_settings
        if schedule:
            settings_dict["schedule"] = schedule
        if queue:
            settings_dict["queue"] = queue
        if run_as:
            settings_dict["run_as"] = run_as
        if git_source:
            settings_dict["git_source"] = git_source
        if parameters:
            settings_dict["parameters"] = parameters
        if health:
            settings_dict["health"] = health
        if deployment:
            settings_dict["deployment"] = deployment

        # Add any extra settings
        settings_dict.update(extra_settings)

        # Convert entire dict to JobSettings - handles all nested type conversions
        settings = JobSettings.from_dict(settings_dict)

        # Create job using the converted SDK objects
        response = w.jobs.create(
            name=settings.name,
            tasks=settings.tasks,
            job_clusters=settings.job_clusters,
            environments=settings.environments,
            tags=settings.tags,
            timeout_seconds=settings.timeout_seconds,
            max_concurrent_runs=settings.max_concurrent_runs,
            email_notifications=settings.email_notifications,
            webhook_notifications=settings.webhook_notifications,
            notification_settings=settings.notification_settings,
            schedule=settings.schedule,
            queue=settings.queue,
            run_as=settings.run_as,
            git_source=settings.git_source,
            parameters=settings.parameters,
            health=settings.health,
            deployment=settings.deployment,
        )

        # Convert response to dict
        return response.as_dict()

    except Exception as e:
        raise JobError(f"Failed to create job '{name}': {str(e)}")


def update_job(
    job_id: int,
    name: Optional[str] = None,
    tasks: Optional[List[Dict[str, Any]]] = None,
    job_clusters: Optional[List[Dict[str, Any]]] = None,
    environments: Optional[List[Dict[str, Any]]] = None,
    tags: Optional[Dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_concurrent_runs: Optional[int] = None,
    email_notifications: Optional[Dict[str, Any]] = None,
    webhook_notifications: Optional[Dict[str, Any]] = None,
    notification_settings: Optional[Dict[str, Any]] = None,
    schedule: Optional[Dict[str, Any]] = None,
    queue: Optional[Dict[str, Any]] = None,
    run_as: Optional[Dict[str, Any]] = None,
    git_source: Optional[Dict[str, Any]] = None,
    parameters: Optional[List[Dict[str, Any]]] = None,
    health: Optional[Dict[str, Any]] = None,
    deployment: Optional[Dict[str, Any]] = None,
    **extra_settings,
) -> None:
    """
    Update an existing job's configuration.

    Only provided parameters will be updated. To remove a field, explicitly set it to None
    or an empty value.

    Args:
        job_id: Job ID to update
        name: New job name
        tasks: New task definitions
        job_clusters: New job cluster definitions
        environments: New environment definitions for serverless tasks with dependencies
        tags: New tags (replaces existing)
        timeout_seconds: New timeout
        max_concurrent_runs: New max concurrent runs
        email_notifications: New email notifications
        webhook_notifications: New webhook notifications
        notification_settings: New notification settings
        schedule: New schedule configuration
        queue: New queue settings
        run_as: New run-as configuration
        git_source: New Git source configuration
        parameters: New job parameters
        health: New health monitoring rules
        deployment: New deployment configuration
        **extra_settings: Additional job settings

    Raises:
        JobError: If job update fails
    """
    w = get_workspace_client()

    try:
        # Build kwargs for SDK call - must include full new_settings
        # Get current job config first
        current_job = w.jobs.get(job_id=job_id)

        # Start with current settings as dict
        new_settings_dict = current_job.settings.as_dict() if current_job.settings else {}

        # Update with provided parameters
        if name is not None:
            new_settings_dict["name"] = name
        if tasks is not None:
            new_settings_dict["tasks"] = tasks
        if job_clusters is not None:
            new_settings_dict["job_clusters"] = job_clusters
        if environments is not None:
            new_settings_dict["environments"] = environments
        if tags is not None:
            new_settings_dict["tags"] = tags
        if timeout_seconds is not None:
            new_settings_dict["timeout_seconds"] = timeout_seconds
        if max_concurrent_runs is not None:
            new_settings_dict["max_concurrent_runs"] = max_concurrent_runs
        if email_notifications is not None:
            new_settings_dict["email_notifications"] = email_notifications
        if webhook_notifications is not None:
            new_settings_dict["webhook_notifications"] = webhook_notifications
        if notification_settings is not None:
            new_settings_dict["notification_settings"] = notification_settings
        if schedule is not None:
            new_settings_dict["schedule"] = schedule
        if queue is not None:
            new_settings_dict["queue"] = queue
        if run_as is not None:
            new_settings_dict["run_as"] = run_as
        if git_source is not None:
            new_settings_dict["git_source"] = git_source
        if parameters is not None:
            new_settings_dict["parameters"] = parameters
        if health is not None:
            new_settings_dict["health"] = health
        if deployment is not None:
            new_settings_dict["deployment"] = deployment

        # Apply extra settings
        new_settings_dict.update(extra_settings)

        # Convert to JobSettings object
        new_settings = JobSettings.from_dict(new_settings_dict)

        # Update job
        w.jobs.update(job_id=job_id, new_settings=new_settings)

    except Exception as e:
        raise JobError(f"Failed to update job {job_id}: {str(e)}", job_id=job_id)


def delete_job(job_id: int) -> None:
    """
    Delete a job.

    Args:
        job_id: Job ID to delete

    Raises:
        JobError: If job deletion fails
    """
    w = get_workspace_client()

    try:
        w.jobs.delete(job_id=job_id)
    except Exception as e:
        raise JobError(f"Failed to delete job {job_id}: {str(e)}", job_id=job_id)
