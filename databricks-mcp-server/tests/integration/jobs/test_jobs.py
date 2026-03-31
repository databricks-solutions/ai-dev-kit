"""
Integration tests for jobs MCP tools.

Tests:
- manage_jobs: create, get, list, update, delete
- manage_job_runs: run_now, get, list, cancel
"""

import logging
import time
import uuid

import pytest

from databricks_mcp_server.tools.jobs import manage_jobs, manage_job_runs
from databricks_mcp_server.tools.file import manage_workspace_files
from tests.test_config import TEST_CATALOG, SCHEMAS, TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)

# Deterministic job names for tests (enables safe cleanup/restart)
JOB_NAME = f"{TEST_RESOURCE_PREFIX}job"
JOB_UPDATE = f"{TEST_RESOURCE_PREFIX}job_update"
JOB_CANCEL = f"{TEST_RESOURCE_PREFIX}job_cancel"

# Simple notebook content that exits successfully
TEST_NOTEBOOK_CONTENT = """# Databricks notebook source
# MAGIC %md
# MAGIC # Test Notebook for MCP Integration Tests

# COMMAND ----------

print("Hello from MCP integration test!")
result = 1 + 1
print(f"1 + 1 = {result}")

# COMMAND ----------

dbutils.notebook.exit("SUCCESS")
"""


@pytest.fixture(scope="module")
def test_notebook_path(workspace_client, current_user: str):
    """Create a test notebook for job execution."""
    import tempfile
    import shutil
    import os

    # The notebook path without extension (Databricks strips .py from notebooks)
    notebook_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/jobs/resources/test_notebook"

    # Create temp directory with properly named notebook file
    temp_dir = tempfile.mkdtemp()
    temp_notebook_file = os.path.join(temp_dir, "test_notebook.py")
    with open(temp_notebook_file, "w") as f:
        f.write(TEST_NOTEBOOK_CONTENT)

    try:
        # Upload notebook directly to the full path (upload_to_workspace places single files
        # at the workspace_path directly, so we specify the full notebook path)
        result = manage_workspace_files(
            action="upload",
            local_path=temp_notebook_file,
            workspace_path=notebook_path,
            overwrite=True,
        )
        logger.info(f"Uploaded test notebook: {result}")

        yield notebook_path

    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

        # Cleanup workspace notebook
        try:
            workspace_client.workspace.delete(notebook_path)
        except Exception as e:
            logger.warning(f"Failed to cleanup notebook: {e}")


@pytest.fixture(scope="module")
def clean_jobs():
    """Pre-test cleanup: delete any existing test jobs using find_by_name (fast)."""
    jobs_to_clean = [JOB_NAME, JOB_UPDATE, JOB_CANCEL]

    for job_name in jobs_to_clean:
        try:
            # Use find_by_name for O(1) lookup instead of listing all jobs
            result = manage_jobs(action="find_by_name", name=job_name)
            job_id = result.get("job_id")
            if job_id:
                manage_jobs(action="delete", job_id=str(job_id))
                logger.info(f"Pre-cleanup: deleted job {job_name}")
        except Exception as e:
            logger.warning(f"Pre-cleanup failed for {job_name}: {e}")

    yield

    # Post-test cleanup
    for job_name in jobs_to_clean:
        try:
            result = manage_jobs(action="find_by_name", name=job_name)
            job_id = result.get("job_id")
            if job_id:
                manage_jobs(action="delete", job_id=str(job_id))
                logger.info(f"Post-cleanup: deleted job {job_name}")
        except Exception:
            pass


@pytest.fixture(scope="module")
def clean_job():
    """Ensure job doesn't exist before tests and cleanup after using find_by_name (fast)."""
    # Try to find and delete existing job with this name
    try:
        result = manage_jobs(action="find_by_name", name=JOB_NAME)
        job_id = result.get("job_id")
        if job_id:
            manage_jobs(action="delete", job_id=str(job_id))
            logger.info(f"Cleaned up existing job: {JOB_NAME}")
    except Exception as e:
        logger.warning(f"Error during pre-cleanup: {e}")

    yield JOB_NAME

    # Cleanup after tests
    try:
        result = manage_jobs(action="find_by_name", name=JOB_NAME)
        job_id = result.get("job_id")
        if job_id:
            manage_jobs(action="delete", job_id=str(job_id))
            logger.info(f"Final cleanup of job: {JOB_NAME}")
    except Exception as e:
        logger.warning(f"Error during post-cleanup: {e}")


@pytest.mark.integration
class TestManageJobs:
    """Tests for manage_jobs tool."""

    def test_list_jobs(self):
        """Should list all jobs."""
        result = manage_jobs(action="list")

        logger.info(f"List result keys: {result.keys() if isinstance(result, dict) else result}")

        assert not result.get("error"), f"List failed: {result}"
        # API may return "jobs" or "items" depending on SDK version
        jobs = result.get("jobs") or result.get("items", [])
        assert isinstance(jobs, list)

    def test_create_job(self, clean_job: str, test_notebook_path: str, cleanup_jobs):
        """Should create a new job and verify its configuration."""
        # Create a simple notebook task job
        result = manage_jobs(
            action="create",
            name=clean_job,
            tasks=[
                {
                    "task_key": "test_task",
                    "notebook_task": {
                        "notebook_path": test_notebook_path,
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "num_workers": 0,
                        "node_type_id": "i3.xlarge",
                    },
                }
            ],
        )

        logger.info(f"Create result: {result}")

        assert "error" not in result, f"Create failed: {result}"
        assert result.get("job_id") is not None

        job_id = result["job_id"]
        cleanup_jobs(str(job_id))

        # Verify job configuration
        get_result = manage_jobs(action="get", job_id=str(job_id))
        assert "error" not in get_result, f"Get job failed: {get_result}"

        # Verify job name matches
        settings = get_result.get("settings", {})
        assert settings.get("name") == clean_job, f"Job name mismatch: {settings.get('name')}"

        # Verify task is configured
        tasks = settings.get("tasks", [])
        assert len(tasks) >= 1, f"Job should have at least 1 task: {tasks}"
        assert tasks[0].get("task_key") == "test_task"

    def test_create_job_with_optional_params(self, test_notebook_path: str, cleanup_jobs):
        """Should create a job with optional params (email_notifications, schedule, queue).

        This tests the fix for passing raw dicts to SDK - they must be converted to SDK objects.
        """
        job_name = f"{TEST_RESOURCE_PREFIX}job_optional_{uuid.uuid4().hex[:6]}"

        # Create job with optional parameters that require SDK type conversion
        result = manage_jobs(
            action="create",
            name=job_name,
            tasks=[
                {
                    "task_key": "test_task",
                    "notebook_task": {
                        "notebook_path": test_notebook_path,
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "num_workers": 0,
                        "node_type_id": "i3.xlarge",
                    },
                }
            ],
            # These optional params require SDK type conversion (JobEmailNotifications, CronSchedule, QueueSettings)
            email_notifications={
                "on_start": [],  # Empty list is valid
                "on_success": [],
                "on_failure": [],
                "no_alert_for_skipped_runs": True,
            },
            schedule={
                "quartz_cron_expression": "0 0 9 * * ?",  # Daily at 9 AM
                "timezone_id": "UTC",
                "pause_status": "PAUSED",  # Start paused so it doesn't actually run
            },
            queue={
                "enabled": True,
            },
        )

        logger.info(f"Create with optional params result: {result}")

        assert "error" not in result, f"Create with optional params failed: {result}"
        assert result.get("job_id") is not None

        job_id = result["job_id"]
        cleanup_jobs(str(job_id))

        # Verify job configuration includes the optional params
        get_result = manage_jobs(action="get", job_id=str(job_id))
        assert "error" not in get_result, f"Get job failed: {get_result}"

        settings = get_result.get("settings", {})

        # Verify email_notifications was persisted
        email_notif = settings.get("email_notifications", {})
        assert email_notif.get("no_alert_for_skipped_runs") is True, \
            f"email_notifications should be persisted: {email_notif}"

        # Verify schedule was persisted
        schedule = settings.get("schedule", {})
        assert schedule.get("quartz_cron_expression") == "0 0 9 * * ?", \
            f"schedule should be persisted: {schedule}"
        assert schedule.get("timezone_id") == "UTC", \
            f"schedule timezone should be UTC: {schedule}"
        assert schedule.get("pause_status") == "PAUSED", \
            f"schedule should be paused: {schedule}"

        # Verify queue was persisted
        queue = settings.get("queue", {})
        assert queue.get("enabled") is True, \
            f"queue should be enabled: {queue}"

        logger.info("Successfully created job with optional params and verified they were persisted")

    def test_get_job(self, clean_job: str, test_notebook_path: str, cleanup_jobs):
        """Should get job details and verify structure."""
        # First create a job
        job_name = f"{TEST_RESOURCE_PREFIX}job_get_{uuid.uuid4().hex[:6]}"
        create_result = manage_jobs(
            action="create",
            name=job_name,
            tasks=[
                {
                    "task_key": "test_task",
                    "notebook_task": {
                        "notebook_path": test_notebook_path,
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "num_workers": 0,
                        "node_type_id": "i3.xlarge",
                    },
                }
            ],
        )

        job_id = create_result.get("job_id")
        assert job_id, f"Job not created: {create_result}"
        cleanup_jobs(str(job_id))

        # Get job details
        result = manage_jobs(action="get", job_id=str(job_id))

        logger.info(f"Get result keys: {result.keys() if isinstance(result, dict) else result}")

        assert "error" not in result, f"Get failed: {result}"

        # Verify expected fields are present
        assert "job_id" in result or "settings" in result, f"Missing expected fields: {result}"

    def test_delete_job(self, test_notebook_path: str, cleanup_jobs):
        """Should delete a job and verify it's gone."""
        # Create a job to delete
        job_name = f"{TEST_RESOURCE_PREFIX}job_delete_{uuid.uuid4().hex[:6]}"
        create_result = manage_jobs(
            action="create",
            name=job_name,
            tasks=[
                {
                    "task_key": "test_task",
                    "notebook_task": {
                        "notebook_path": test_notebook_path,
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "num_workers": 0,
                        "node_type_id": "i3.xlarge",
                    },
                }
            ],
        )

        job_id = create_result.get("job_id")
        assert job_id, f"Job not created: {create_result}"

        # Verify job exists before delete
        get_before = manage_jobs(action="get", job_id=str(job_id))
        assert "error" not in get_before, f"Job should exist before delete: {get_before}"

        # Delete the job
        result = manage_jobs(action="delete", job_id=str(job_id))

        logger.info(f"Delete result: {result}")

        assert result.get("status") == "deleted" or "error" not in result

        # Verify job is gone - the get action raises an exception for deleted jobs
        try:
            get_after = manage_jobs(action="get", job_id=str(job_id))
            # If we get here without exception, check for error in response
            assert "error" in get_after or "not found" in str(get_after).lower(), \
                f"Job should be deleted: {get_after}"
        except Exception as e:
            # Exception is expected - job doesn't exist
            assert "does not exist" in str(e).lower() or "not found" in str(e).lower(), \
                f"Expected 'does not exist' error, got: {e}"
            logger.info(f"Confirmed job was deleted - get raised expected error: {e}")

    def test_invalid_action(self):
        """Should return error for invalid action."""
        try:
            result = manage_jobs(action="invalid_action")
            assert "error" in result
        except ValueError as e:
            # Function raises ValueError for invalid action - this is acceptable
            assert "invalid" in str(e).lower()


@pytest.mark.integration
class TestManageJobRuns:
    """Tests for manage_job_runs tool."""

    def test_list_runs(self):
        """Should list job runs."""
        result = manage_job_runs(action="list")

        logger.info(f"List runs result keys: {result.keys() if isinstance(result, dict) else result}")

        assert not result.get("error"), f"List runs failed: {result}"

    def test_get_run_nonexistent(self):
        """Should handle nonexistent run gracefully."""
        try:
            result = manage_job_runs(action="get", run_id="999999999999")
            # Should return error or not found
            logger.info(f"Get nonexistent run result: {result}")
        except Exception as e:
            # SDK raises exception for nonexistent run - this is acceptable
            logger.info(f"Expected error for nonexistent run: {e}")

    def test_invalid_action(self):
        """Should return error for invalid action."""
        try:
            result = manage_job_runs(action="invalid_action")
            assert "error" in result
        except ValueError as e:
            # Function raises ValueError for invalid action - this is acceptable
            assert "invalid" in str(e).lower()


@pytest.mark.integration
class TestJobExecution:
    """Tests for actual job execution (slow)."""

    def test_run_job_and_verify_completion(self, test_notebook_path: str, cleanup_jobs):
        """Should run a job and verify it completes successfully."""
        # Create a job
        job_name = f"{TEST_RESOURCE_PREFIX}job_run_{uuid.uuid4().hex[:6]}"
        create_result = manage_jobs(
            action="create",
            name=job_name,
            tasks=[
                {
                    "task_key": "test_task",
                    "notebook_task": {
                        "notebook_path": test_notebook_path,
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "num_workers": 0,
                        "node_type_id": "i3.xlarge",
                    },
                }
            ],
        )

        job_id = create_result.get("job_id")
        assert job_id, f"Job not created: {create_result}"
        cleanup_jobs(str(job_id))

        # Run the job
        run_result = manage_job_runs(
            action="run_now",
            job_id=str(job_id),
        )

        logger.info(f"Run result: {run_result}")

        assert "error" not in run_result, f"Run failed: {run_result}"
        run_id = run_result.get("run_id")
        assert run_id, f"Run ID should be returned: {run_result}"

        # Wait for job to complete (with timeout)
        max_wait = 600  # 10 minutes
        wait_interval = 15
        waited = 0
        final_state = None

        while waited < max_wait:
            status_result = manage_job_runs(action="get", run_id=str(run_id))

            logger.info(f"Run status after {waited}s: {status_result}")

            state = status_result.get("state", {})
            life_cycle_state = state.get("life_cycle_state")
            result_state = state.get("result_state")

            if life_cycle_state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
                final_state = result_state
                break

            time.sleep(wait_interval)
            waited += wait_interval

        assert final_state is not None, f"Job did not complete within {max_wait}s"
        assert final_state == "SUCCESS", f"Job should succeed, got: {final_state}"


@pytest.mark.integration
class TestJobUpdate:
    """Tests for job update functionality."""

    def test_update_job(
        self,
        test_notebook_path: str,
        clean_jobs,
        cleanup_jobs,
    ):
        """Should create a job, update its configuration, and verify changes."""
        # Create initial job
        create_result = manage_jobs(
            action="create",
            name=JOB_UPDATE,
            tasks=[
                {
                    "task_key": "initial_task",
                    "notebook_task": {
                        "notebook_path": test_notebook_path,
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "num_workers": 0,
                        "node_type_id": "i3.xlarge",
                    },
                }
            ],
        )

        logger.info(f"Create for update test: {create_result}")

        assert "error" not in create_result, f"Create failed: {create_result}"

        job_id = create_result.get("job_id")
        assert job_id, f"Job ID should be returned: {create_result}"

        cleanup_jobs(str(job_id))

        # Verify initial configuration
        get_before = manage_jobs(action="get", job_id=str(job_id))
        initial_tasks = get_before.get("settings", {}).get("tasks", [])
        assert len(initial_tasks) == 1, f"Should have 1 task initially: {initial_tasks}"
        assert initial_tasks[0].get("task_key") == "initial_task"

        # Update the job with a new task key
        update_result = manage_jobs(
            action="update",
            job_id=str(job_id),
            name=JOB_UPDATE,
            tasks=[
                {
                    "task_key": "updated_task",
                    "notebook_task": {
                        "notebook_path": test_notebook_path,
                    },
                    "new_cluster": {
                        "spark_version": "14.3.x-scala2.12",
                        "num_workers": 0,
                        "node_type_id": "i3.xlarge",
                    },
                }
            ],
        )

        logger.info(f"Update result: {update_result}")

        assert "error" not in update_result, f"Update failed: {update_result}"

        # Verify the update
        get_after = manage_jobs(action="get", job_id=str(job_id))

        logger.info(f"Get after update: {get_after}")

        assert "error" not in get_after, f"Get after update failed: {get_after}"

        # Verify task was added (Jobs API update does partial updates, adding tasks)
        updated_tasks = get_after.get("settings", {}).get("tasks", [])
        task_keys = [t.get("task_key") for t in updated_tasks]
        # Partial update adds the new task to existing tasks
        assert "updated_task" in task_keys, \
            f"updated_task should be in task list: {task_keys}"
        assert len(updated_tasks) >= 1, f"Should have at least 1 task after update: {updated_tasks}"


@pytest.mark.integration
class TestJobCancel:
    """Tests for job cancellation."""

    def test_cancel_run(
        self,
        test_notebook_path: str,
        clean_jobs,
        cleanup_jobs,
    ):
        """Should start a job run and cancel it, verifying the cancellation."""
        # Create a job that takes a while (sleep in notebook)
        long_running_notebook = """# Databricks notebook source
# MAGIC %md
# MAGIC # Long Running Notebook for Cancel Test

# COMMAND ----------

import time
print("Starting long running task...")
time.sleep(300)  # Sleep for 5 minutes - should be cancelled before this completes
print("This should not print if cancelled")

# COMMAND ----------

dbutils.notebook.exit("COMPLETED")
"""
        import tempfile
        import os
        from pathlib import Path

        # Create temp directory with properly named notebook file
        temp_dir = tempfile.mkdtemp()
        temp_notebook_file = os.path.join(temp_dir, "long_notebook.py")
        with open(temp_notebook_file, "w") as f:
            f.write(long_running_notebook)

        try:
            # Upload long-running notebook
            from databricks_mcp_server.tools.file import manage_workspace_files

            # Get user from test_notebook_path
            user = test_notebook_path.split('/Users/')[1].split('/')[0]
            # Use the same resources folder that the fixture already created
            # This ensures the parent directory exists
            notebook_path = f"/Workspace/Users/{user}/ai_dev_kit_test/jobs/resources/long_notebook"

            # Upload the notebook file directly to the full path
            upload_result = manage_workspace_files(
                action="upload",
                local_path=temp_notebook_file,
                workspace_path=notebook_path,
                overwrite=True,
            )
            logger.info(f"Upload result for cancel test notebook: {upload_result}")
            assert upload_result.get("success", False) or upload_result.get("status") == "success", \
                f"Failed to upload cancel test notebook: {upload_result}"

            # Create job
            create_result = manage_jobs(
                action="create",
                name=JOB_CANCEL,
                tasks=[
                    {
                        "task_key": "long_task",
                        "notebook_task": {
                            "notebook_path": notebook_path,
                        },
                        "new_cluster": {
                            "spark_version": "14.3.x-scala2.12",
                            "num_workers": 0,
                            "node_type_id": "i3.xlarge",
                        },
                    }
                ],
            )

            logger.info(f"Create for cancel test: {create_result}")

            assert "error" not in create_result, f"Create failed: {create_result}"

            job_id = create_result.get("job_id")
            assert job_id, f"Job ID should be returned: {create_result}"

            cleanup_jobs(str(job_id))

            # Start the job
            run_result = manage_job_runs(
                action="run_now",
                job_id=str(job_id),
            )

            logger.info(f"Run result: {run_result}")

            assert "error" not in run_result, f"Run failed: {run_result}"

            run_id = run_result.get("run_id")
            assert run_id, f"Run ID should be returned: {run_result}"

            # Wait a bit for the job to start
            time.sleep(10)

            # Verify the job is running
            status_before = manage_job_runs(action="get", run_id=str(run_id))
            life_cycle_state = status_before.get("state", {}).get("life_cycle_state")
            logger.info(f"State before cancel: {life_cycle_state}")

            # Cancel the run
            cancel_result = manage_job_runs(
                action="cancel",
                run_id=str(run_id),
            )

            logger.info(f"Cancel result: {cancel_result}")

            assert "error" not in cancel_result, f"Cancel failed: {cancel_result}"

            # Wait for cancellation to take effect
            max_wait = 60
            waited = 0
            cancelled = False

            while waited < max_wait:
                status_after = manage_job_runs(action="get", run_id=str(run_id))
                state = status_after.get("state", {})
                life_cycle_state = state.get("life_cycle_state")
                result_state = state.get("result_state")

                logger.info(f"State after cancel ({waited}s): lifecycle={life_cycle_state}, result={result_state}")

                if life_cycle_state == "TERMINATED":
                    # Check if it was cancelled
                    if result_state == "CANCELED":
                        cancelled = True
                        break
                    # If terminated but not cancelled, check other states
                    break

                time.sleep(5)
                waited += 5

            assert cancelled, f"Job run should be cancelled, got state: {status_after.get('state')}"

        finally:
            # Cleanup temp directory
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
