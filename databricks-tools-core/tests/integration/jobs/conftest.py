"""
Pytest fixtures for jobs integration tests.

Provides fixtures for job creation, cleanup, and test data.
Uses serverless compute for all job executions.
"""

import base64
import logging
import pytest
import uuid

from databricks.sdk.service.workspace import ImportFormat, Language

from databricks_tools_core.auth import get_workspace_client
from databricks_tools_core.jobs import delete_job

logger = logging.getLogger(__name__)

# Fixed test job name prefix for easy identification and cleanup
TEST_JOB_PREFIX = "ai_dev_kit_test_job"


@pytest.fixture(scope="module")
def test_job_name() -> str:
    """
    Generate a unique test job name for this test session.

    Uses UUID suffix to avoid conflicts if multiple test runs
    happen simultaneously.
    """
    unique_suffix = str(uuid.uuid4())[:8]
    return f"{TEST_JOB_PREFIX}_{unique_suffix}"


@pytest.fixture(scope="module")
def test_notebook_path() -> str:
    """
    Create a simple test notebook in the workspace.

    Returns the workspace path to the notebook.
    """
    w = get_workspace_client()
    user = w.current_user.me()
    notebook_path = f"/Users/{user.user_name}/test_jobs/test_notebook"

    # Create notebook with simple Python code
    # Keep it short to minimize serverless execution time
    notebook_content = """# Databricks notebook source
# Test notebook for jobs integration tests
print("Test job executed successfully")
dbutils.notebook.exit("success")
"""

    logger.info(f"Creating test notebook: {notebook_path}")

    try:
        # Create parent folder first
        parent_folder = "/".join(notebook_path.split("/")[:-1])
        w.workspace.mkdirs(parent_folder)
        logger.info(f"Created parent folder: {parent_folder}")

        # Import notebook (creates it if doesn't exist)
        # Content must be base64 encoded
        content_b64 = base64.b64encode(notebook_content.encode("utf-8")).decode("utf-8")
        w.workspace.import_(
            path=notebook_path,
            format=ImportFormat.SOURCE,
            language=Language.PYTHON,
            content=content_b64,
            overwrite=True,
        )
        logger.info(f"Test notebook created: {notebook_path}")
    except Exception as e:
        logger.error(f"Failed to create test notebook: {e}")
        raise

    yield notebook_path

    # Cleanup: Delete notebook and folder after tests
    try:
        logger.info(f"Cleaning up test notebook: {notebook_path}")
        w.workspace.delete(notebook_path)
        # Also try to delete the parent folder
        parent_folder = "/".join(notebook_path.split("/")[:-1])
        w.workspace.delete(parent_folder, recursive=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup test notebook: {e}")


@pytest.fixture(scope="function")
def cleanup_job():
    """
    Fixture to track and cleanup test jobs created during tests.

    Usage:
        def test_create_job(cleanup_job):
            job = create_job(...)
            cleanup_job(job["job_id"])  # Register for cleanup
    """
    job_ids_to_cleanup = []

    def register_job(job_id: int):
        """Register a job ID for cleanup after the test."""
        if job_id and job_id not in job_ids_to_cleanup:
            job_ids_to_cleanup.append(job_id)
            logger.info(f"Registered job {job_id} for cleanup")

    yield register_job

    # Cleanup all registered jobs
    for job_id in job_ids_to_cleanup:
        try:
            logger.info(f"Cleaning up job: {job_id}")
            delete_job(job_id=job_id)
            logger.info(f"Job {job_id} deleted successfully")
        except Exception as e:
            logger.warning(f"Failed to cleanup job {job_id}: {e}")
