"""
Integration tests for job run operations.

Tests the databricks_tools_core.jobs functions:
- run_job_now
- get_run
- cancel_run
- list_runs
- wait_for_run

All tests use serverless compute for job execution.
"""

import logging
import pytest
import time

from databricks_tools_core.jobs import (
    create_job,
    run_job_now,
    get_run,
    cancel_run,
    list_runs,
    wait_for_run,
    JobError,
    RunLifecycleState,
    RunResultState,
)

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestRunJobNow:
    """Tests for triggering job runs."""

    def test_run_job_now(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should trigger a job run successfully."""
        # Create a test job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(name="test_run_job_now", tasks=tasks)
        cleanup_job(job["job_id"])

        logger.info(f"Triggering run for job: {job['job_id']}")

        # Run the job using our core function
        run_id = run_job_now(job_id=job["job_id"])

        logger.info(f"Run triggered: {run_id}")

        # Verify run was created
        assert run_id is not None, "Run ID should be returned"
        assert isinstance(run_id, int), "Run ID should be an integer"

        # Get run details to verify state
        run_details = get_run(run_id=run_id)
        logger.info(f"Run state: {run_details.get('state', {})}")

        assert run_details["run_id"] == run_id, "Run ID should match"

    def test_run_job_with_parameters(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should run job with notebook parameters."""
        # Create a test job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(name="test_run_with_params", tasks=tasks)
        cleanup_job(job["job_id"])

        logger.info(f"Running job with parameters: {job['job_id']}")

        # Run with parameters using our core function
        params = {"param1": "value1", "param2": "value2"}
        run_id = run_job_now(job_id=job["job_id"], notebook_params=params)

        logger.info(f"Run triggered with params: {run_id}")

        assert run_id is not None, "Run ID should be returned"


@pytest.mark.integration
class TestGetRun:
    """Tests for getting run details."""

    def test_get_run(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should get run status and details."""
        # Create and run a job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(name="test_get_run", tasks=tasks)
        cleanup_job(job["job_id"])
        run_id = run_job_now(job_id=job["job_id"])

        logger.info(f"Getting run details for: {run_id}")

        # Get run details using our core function
        run_details = get_run(run_id=run_id)

        logger.info(f"Run details: {run_details.get('state', {})}")

        # Verify details
        assert run_details["run_id"] == run_id, "Run ID should match"
        assert run_details["job_id"] == job["job_id"], "Job ID should match"
        assert "state" in run_details, "Should have state"

    def test_get_run_not_found(self):
        """Should raise JobError when run doesn't exist."""
        non_existent_run_id = 999999999

        logger.info(f"Attempting to get non-existent run: {non_existent_run_id}")

        with pytest.raises(JobError) as exc_info:
            get_run(run_id=non_existent_run_id)

        logger.info(f"Expected JobError: {exc_info.value}")
        assert exc_info.value.run_id == non_existent_run_id


@pytest.mark.integration
class TestCancelRun:
    """Tests for canceling job runs."""

    def test_cancel_run(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should cancel a running job."""
        # Create and run a job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(name="test_cancel_run", tasks=tasks)
        cleanup_job(job["job_id"])
        run_id = run_job_now(job_id=job["job_id"])

        logger.info(f"Canceling run: {run_id}")

        # Wait a moment to ensure run has started
        time.sleep(3)

        # Cancel the run using our core function
        cancel_run(run_id=run_id)

        logger.info(f"Run {run_id} cancel requested")

        # Poll for cancellation to take effect (serverless may take longer)
        max_wait = 30
        poll_interval = 3
        elapsed = 0
        lifecycle_state = None

        while elapsed < max_wait:
            time.sleep(poll_interval)
            elapsed += poll_interval

            run_details = get_run(run_id=run_id)
            state = run_details.get("state", {})
            lifecycle_state = state.get("life_cycle_state")
            logger.info(f"Run state after {elapsed}s: {lifecycle_state}")

            if lifecycle_state in ["TERMINATING", "TERMINATED"]:
                break

        # Run should be terminating or terminated
        assert lifecycle_state in [
            "TERMINATING",
            "TERMINATED",
        ], f"Run should be terminating or terminated, got {lifecycle_state}"


@pytest.mark.integration
class TestListRuns:
    """Tests for listing job runs."""

    def test_list_runs_for_job(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should list runs for a specific job."""
        # Create a job and trigger multiple runs (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(
            name="test_list_runs",
            tasks=tasks,
            max_concurrent_runs=5,  # Allow concurrent runs for this test
        )
        cleanup_job(job["job_id"])

        logger.info(f"Triggering 3 runs for job: {job['job_id']}")

        # Trigger 3 runs using our core function
        run_ids = []
        for i in range(3):
            run_id = run_job_now(job_id=job["job_id"])
            run_ids.append(run_id)
            logger.info(f"Run {i + 1} triggered: {run_id}")
            time.sleep(1)  # Small delay between runs

        # List runs for this job using our core function
        logger.info(f"Listing runs for job: {job['job_id']}")
        runs = list_runs(job_id=job["job_id"], limit=10)

        logger.info(f"Found {len(runs)} runs for job {job['job_id']}")

        # Verify we got the runs
        assert len(runs) >= 3, f"Should have at least 3 runs, got {len(runs)}"

        # Verify our run IDs are in the list
        found_run_ids = {run["run_id"] for run in runs}
        for run_id in run_ids:
            assert run_id in found_run_ids, f"Run {run_id} should be in the list"

    def test_list_runs_with_limit(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should respect limit parameter when listing runs."""
        # Create a job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(
            name="test_list_runs_limit",
            tasks=tasks,
            max_concurrent_runs=5,
        )
        cleanup_job(job["job_id"])

        # Trigger 5 runs
        for _ in range(5):
            run_job_now(job_id=job["job_id"])
            time.sleep(1)

        # List with limit=3 using our core function
        runs = list_runs(job_id=job["job_id"], limit=3)

        logger.info(f"Listed runs with limit=3: found {len(runs)}")

        assert len(runs) <= 3, f"Should have at most 3 runs, got {len(runs)}"


@pytest.mark.integration
class TestWaitForRun:
    """Tests for waiting for run completion."""

    def test_wait_for_run_success(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should wait for run to complete successfully."""
        # Create and run a job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(name="test_wait_for_run", tasks=tasks)
        cleanup_job(job["job_id"])
        run_id = run_job_now(job_id=job["job_id"])

        logger.info(f"Waiting for run {run_id} to complete")

        # Wait for run using our core function (timeout after 5 minutes)
        result = wait_for_run(run_id=run_id, timeout=300, poll_interval=10)

        logger.info(f"Run completed: lifecycle={result.lifecycle_state}, result={result.result_state}")

        # Verify completion using our JobRunResult model
        # lifecycle_state is stored as string in JobRunResult
        assert result.lifecycle_state == RunLifecycleState.TERMINATED.value
        assert result.result_state in [
            RunResultState.SUCCESS.value,
            RunResultState.FAILED.value,
            RunResultState.CANCELED.value,
        ], "Run should have a result state"

    def test_wait_for_run_with_cancellation(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should wait for canceled run to complete."""
        # Create and run a job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(name="test_wait_canceled", tasks=tasks)
        cleanup_job(job["job_id"])
        run_id = run_job_now(job_id=job["job_id"])

        logger.info(f"Starting run {run_id} and canceling it")

        # Wait a moment, then cancel
        time.sleep(2)
        cancel_run(run_id=run_id)

        logger.info("Waiting for canceled run to complete")

        # Wait for run using our core function
        result = wait_for_run(run_id=run_id, timeout=300, poll_interval=10)

        logger.info(f"Canceled run completed: lifecycle={result.lifecycle_state}, result={result.result_state}")

        # Verify completion (states stored as strings in JobRunResult)
        assert result.lifecycle_state == RunLifecycleState.TERMINATED.value
        assert result.result_state == RunResultState.CANCELED.value

    def test_wait_for_run_result_object(
        self,
        test_notebook_path: str,
        cleanup_job,
    ):
        """Should return JobRunResult with all expected fields."""
        # Create and run a job (serverless)
        tasks = [
            {
                "task_key": "test_task",
                "notebook_task": {
                    "notebook_path": test_notebook_path,
                    "source": "WORKSPACE",
                },
            }
        ]
        job = create_job(name="test_wait_result", tasks=tasks)
        cleanup_job(job["job_id"])
        run_id = run_job_now(job_id=job["job_id"])

        logger.info(f"Waiting for run {run_id}")

        # Wait for run using our core function
        result = wait_for_run(run_id=run_id, timeout=300, poll_interval=10)

        # Verify JobRunResult fields
        assert result.run_id == run_id, "run_id should match"
        assert result.job_id == job["job_id"], "job_id should match"
        assert result.lifecycle_state is not None, "Should have lifecycle_state"
        assert result.run_page_url is not None, "Should have run_page_url"

        # Test to_dict() method
        result_dict = result.to_dict()
        assert "run_id" in result_dict
        assert "success" in result_dict
        assert "lifecycle_state" in result_dict

        logger.info(f"JobRunResult.to_dict(): {result_dict}")
