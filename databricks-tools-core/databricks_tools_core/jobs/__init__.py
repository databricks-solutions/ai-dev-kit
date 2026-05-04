"""
Jobs Module - Databricks Jobs API

This module provides functions for managing Databricks jobs and job runs.
Uses serverless compute by default for optimal performance and cost.

Core Operations:
- Job CRUD: create_job, update_job, delete_job, get_job, list_jobs, find_job_by_name
- Run Management: run_job_now, get_run, get_run_output, cancel_run, list_runs
- Run Monitoring: wait_for_run (blocks until completion)

Data Models:
- JobRunResult: Detailed run result with status, timing, and error info
- JobStatus, RunLifecycleState, RunResultState: Status enums
- JobError: Exception class for job-related errors

Example Usage:
    >>> from databricks_tools_core.jobs import (
    ...     create_job, run_job_now, wait_for_run
    ... )
    >>>
    >>> # Create a job
    >>> tasks = [{
    ...     "task_key": "main",
    ...     "notebook_task": {
    ...         "notebook_path": "/Workspace/ETL/process",
    ...         "source": "WORKSPACE"
    ...     }
    ... }]
    >>> job = create_job(name="my_etl_job", tasks=tasks)
    >>>
    >>> # Run the job and wait for completion
    >>> run_id = run_job_now(job_id=job["job_id"])
    >>> result = wait_for_run(run_id=run_id)
    >>> if result.success:
    ...     print(f"Job completed in {result.duration_seconds}s")
"""

# Import all public functions and classes
from .models import (
    JobStatus,
    RunLifecycleState,
    RunResultState,
    JobRunResult,
    JobError,
)

from .jobs import (
    list_jobs,
    get_job,
    find_job_by_name,
    create_job,
    update_job,
    delete_job,
)

from .runs import (
    run_job_now,
    repair_run,
    get_run,
    get_run_output,
    cancel_run,
    list_runs,
    wait_for_run,
)

__all__ = [
    # Models and Enums
    "JobStatus",
    "RunLifecycleState",
    "RunResultState",
    "JobRunResult",
    "JobError",
    # Job CRUD Operations
    "list_jobs",
    "get_job",
    "find_job_by_name",
    "create_job",
    "update_job",
    "delete_job",
    # Run Operations
    "run_job_now",
    "repair_run",
    "get_run",
    "get_run_output",
    "cancel_run",
    "list_runs",
    "wait_for_run",
]
