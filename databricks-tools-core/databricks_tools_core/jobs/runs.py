"""
Jobs - Run Operations

Functions for triggering and monitoring job runs.
"""

import time
from typing import Optional, List, Dict, Any

from databricks.sdk.service.jobs import (
    RunLifeCycleState,
    RunResultState,
)

from ..auth import get_workspace_client
from .models import JobRunResult, JobError


# Terminal states - run has finished (success or failure)
TERMINAL_STATES = {
    RunLifeCycleState.TERMINATED,
    RunLifeCycleState.SKIPPED,
    RunLifeCycleState.INTERNAL_ERROR,
}

# Success states - run completed successfully
SUCCESS_STATES = {
    RunResultState.SUCCESS,
}


def run_job_now(
    job_id: int,
    idempotency_token: Optional[str] = None,
    jar_params: Optional[List[str]] = None,
    notebook_params: Optional[Dict[str, str]] = None,
    python_params: Optional[List[str]] = None,
    spark_submit_params: Optional[List[str]] = None,
    python_named_params: Optional[Dict[str, str]] = None,
    pipeline_params: Optional[Dict[str, Any]] = None,
    sql_params: Optional[Dict[str, str]] = None,
    dbt_commands: Optional[List[str]] = None,
    queue: Optional[Dict[str, Any]] = None,
    **extra_params,
) -> int:
    """
    Trigger a job run immediately and return the run ID.

    Args:
        job_id: Job ID to run
        idempotency_token: Optional token to ensure idempotent job runs
        jar_params: Parameters for JAR tasks
        notebook_params: Parameters for notebook tasks
        python_params: Parameters for Python tasks
        spark_submit_params: Parameters for spark-submit tasks
        python_named_params: Named parameters for Python tasks
        pipeline_params: Parameters for pipeline tasks
        sql_params: Parameters for SQL tasks
        dbt_commands: Commands for dbt tasks
        queue: Queue settings for this run
        **extra_params: Additional run parameters

    Returns:
        Run ID (integer) for tracking the run

    Raises:
        JobError: If job run fails to start

    Example:
        >>> run_id = run_job_now(job_id=123, notebook_params={"env": "prod"})
        >>> print(f"Started run {run_id}")
    """
    w = get_workspace_client()

    try:
        # Build kwargs for SDK call
        kwargs: Dict[str, Any] = {"job_id": job_id}

        # Add optional parameters
        if idempotency_token:
            kwargs["idempotency_token"] = idempotency_token
        if jar_params:
            kwargs["jar_params"] = jar_params
        if notebook_params:
            kwargs["notebook_params"] = notebook_params
        if python_params:
            kwargs["python_params"] = python_params
        if spark_submit_params:
            kwargs["spark_submit_params"] = spark_submit_params
        if python_named_params:
            kwargs["python_named_params"] = python_named_params
        if pipeline_params:
            kwargs["pipeline_params"] = pipeline_params
        if sql_params:
            kwargs["sql_params"] = sql_params
        if dbt_commands:
            kwargs["dbt_commands"] = dbt_commands
        if queue:
            kwargs["queue"] = queue

        # Add extra params
        kwargs.update(extra_params)

        # Trigger run - SDK returns Wait[Run] object
        response = w.jobs.run_now(**kwargs)

        # Extract run_id from response
        # The Wait object has a response attribute that contains the Run
        if hasattr(response, "response") and hasattr(response.response, "run_id"):
            return response.response.run_id
        elif hasattr(response, "run_id"):
            return response.run_id
        else:
            # Fallback: try to get it from as_dict()
            response_dict = response.as_dict() if hasattr(response, "as_dict") else {}
            if "run_id" in response_dict:
                return response_dict["run_id"]
            raise JobError(
                f"Failed to extract run_id from response for job {job_id}",
                job_id=job_id,
            )

    except Exception as e:
        raise JobError(f"Failed to start run for job {job_id}: {str(e)}", job_id=job_id)


def get_run(run_id: int) -> Dict[str, Any]:
    """
    Get detailed run status and information.

    Args:
        run_id: Run ID

    Returns:
        Dictionary with run details including state, start_time, end_time, tasks, etc.

    Raises:
        JobError: If run not found or API request fails
    """
    w = get_workspace_client()

    try:
        run = w.jobs.get_run(run_id=run_id)

        # Convert SDK object to dict for JSON serialization
        return run.as_dict()

    except Exception as e:
        raise JobError(f"Failed to get run {run_id}: {str(e)}", run_id=run_id)


def get_run_output(run_id: int) -> Dict[str, Any]:
    """
    Get run output including logs and results.

    Args:
        run_id: Run ID

    Returns:
        Dictionary with run output including logs, error messages, and task outputs

    Raises:
        JobError: If run not found or API request fails
    """
    w = get_workspace_client()

    try:
        output = w.jobs.get_run_output(run_id=run_id)

        # Convert SDK object to dict for JSON serialization
        return output.as_dict()

    except Exception as e:
        raise JobError(
            f"Failed to get output for run {run_id}: {str(e)}", run_id=run_id
        )


def cancel_run(run_id: int) -> None:
    """
    Cancel a running job.

    Args:
        run_id: Run ID to cancel

    Raises:
        JobError: If cancel request fails
    """
    w = get_workspace_client()

    try:
        w.jobs.cancel_run(run_id=run_id)
    except Exception as e:
        raise JobError(f"Failed to cancel run {run_id}: {str(e)}", run_id=run_id)


def list_runs(
    job_id: Optional[int] = None,
    active_only: bool = False,
    completed_only: bool = False,
    limit: int = 25,
    offset: int = 0,
    start_time_from: Optional[int] = None,
    start_time_to: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    List job runs with optional filters.

    Args:
        job_id: Optional filter by specific job ID
        active_only: If True, only return active runs (RUNNING, PENDING, etc.)
        completed_only: If True, only return completed runs
        limit: Maximum number of runs to return (default: 25, max: 1000)
        offset: Offset for pagination
        start_time_from: Filter by start time (epoch milliseconds)
        start_time_to: Filter by start time (epoch milliseconds)

    Returns:
        List of run info dicts with run_id, state, start_time, job_id, etc.

    Example:
        >>> # Get last 10 runs for a specific job
        >>> runs = list_runs(job_id=123, limit=10)
        >>>
        >>> # Get all active runs
        >>> active_runs = list_runs(active_only=True)
    """
    w = get_workspace_client()
    runs = []

    try:
        # SDK list_runs returns an iterator
        for run in w.jobs.list_runs(
            job_id=job_id,
            active_only=active_only,
            completed_only=completed_only,
            limit=limit,
            offset=offset,
            start_time_from=start_time_from,
            start_time_to=start_time_to,
        ):
            run_dict = run.as_dict()
            runs.append(run_dict)

            if len(runs) >= limit:
                break

        return runs

    except Exception as e:
        raise JobError(f"Failed to list runs: {str(e)}", job_id=job_id)


def wait_for_run(
    run_id: int,
    timeout: int = 3600,
    poll_interval: int = 10,
) -> JobRunResult:
    """
    Wait for a job run to complete and return detailed results.

    Args:
        run_id: Run ID to wait for
        timeout: Maximum wait time in seconds (default: 3600 = 1 hour)
        poll_interval: Time between status checks in seconds (default: 10)

    Returns:
        JobRunResult with detailed run status including:
        - success: True if run completed successfully
        - lifecycle_state: Final lifecycle state (TERMINATED, SKIPPED, etc.)
        - result_state: Final result state (SUCCESS, FAILED, etc.)
        - duration_seconds: Total time taken
        - error_message: Error message if failed
        - run_page_url: Link to run in Databricks UI

    Raises:
        TimeoutError: If run doesn't complete within timeout
        JobError: If API request fails

    Example:
        >>> run_id = run_job_now(job_id=123)
        >>> result = wait_for_run(run_id=run_id, timeout=1800)
        >>> if result.success:
        ...     print(f"Job completed in {result.duration_seconds}s")
        ... else:
        ...     print(f"Job failed: {result.error_message}")
    """
    w = get_workspace_client()
    start_time = time.time()

    job_id = None
    job_name = None

    while True:
        elapsed = time.time() - start_time

        if elapsed > timeout:
            raise TimeoutError(
                f"Job run {run_id} did not complete within {timeout} seconds. "
                f"Check run status in Databricks UI or call get_run(run_id={run_id})."
            )

        try:
            run = w.jobs.get_run(run_id=run_id)

            # Extract job info on first iteration
            if job_id is None:
                job_id = run.job_id
                # Get job name if available
                if run.job_id:
                    try:
                        job = w.jobs.get(job_id=run.job_id)
                        job_name = job.settings.name if job.settings else None
                    except Exception:
                        pass  # Ignore errors getting job name

            # Check if run is in terminal state
            lifecycle_state = run.state.life_cycle_state if run.state else None
            result_state = run.state.result_state if run.state else None
            state_message = run.state.state_message if run.state else None

            if lifecycle_state in TERMINAL_STATES:
                # Calculate duration
                duration = round(elapsed, 2)
                if run.start_time and run.end_time:
                    # Use actual run times if available (more accurate)
                    duration = round((run.end_time - run.start_time) / 1000.0, 2)

                # Determine success
                success = result_state in SUCCESS_STATES

                # Build result
                result = JobRunResult(
                    job_id=job_id or 0,
                    run_id=run_id,
                    job_name=job_name,
                    lifecycle_state=lifecycle_state.value if lifecycle_state else None,
                    result_state=result_state.value if result_state else None,
                    success=success,
                    duration_seconds=duration,
                    start_time=run.start_time,
                    end_time=run.end_time,
                    run_page_url=run.run_page_url,
                    state_message=state_message,
                )

                # Build message
                if success:
                    result.message = (
                        f"Job run {run_id} completed successfully in {duration}s. "
                        f"View: {run.run_page_url}"
                    )
                else:
                    # Extract error details
                    error_message = (
                        state_message
                        or f"Run failed with state: {result_state.value if result_state else 'UNKNOWN'}"
                    )
                    result.error_message = error_message

                    # Try to get output for more details
                    try:
                        output = w.jobs.get_run_output(run_id=run_id)
                        if output.error:
                            result.error_message = output.error
                        if output.error_trace:
                            result.errors = [{"trace": output.error_trace}]
                    except Exception:
                        pass  # Ignore errors getting output

                    result.message = (
                        f"Job run {run_id} failed. "
                        f"State: {lifecycle_state.value if lifecycle_state else 'UNKNOWN'}, "
                        f"Result: {result_state.value if result_state else 'UNKNOWN'}. "
                        f"Error: {error_message}. "
                        f"View: {run.run_page_url}"
                    )

                return result

        except Exception as e:
            # If we can't get run status, raise error
            raise JobError(
                f"Failed to get run status for {run_id}: {str(e)}", run_id=run_id
            )

        time.sleep(poll_interval)
