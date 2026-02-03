"""
Integration tests for SDP pipeline management functions.

Tests:
- create_or_update_pipeline (create, update, run, wait)
- delete_pipeline
"""

import logging
import pytest
from pathlib import Path

from databricks_tools_core.spark_declarative_pipelines.pipelines import (
    create_or_update_pipeline,
    delete_pipeline,
    find_pipeline_by_name,
)
from databricks_tools_core.file.workspace import upload_folder


logger = logging.getLogger(__name__)

# Path to test pipeline files
PIPELINES_DIR = Path(__file__).parent / "pipelines"

# Fixed pipeline name for consistent cleanup
TEST_PIPELINE_NAME = "ai_dev_kit_test_sdp_pipeline"

# Dedicated schema for SDP tests (separate from SQL tests)
SDP_TEST_SCHEMA = "test_sdp_schema"


@pytest.fixture(scope="module")
def pipeline_name() -> str:
    """Return the fixed test pipeline name."""
    return TEST_PIPELINE_NAME


@pytest.fixture(scope="module")
def sdp_test_schema(workspace_client, test_catalog: str) -> str:
    """
    Create a dedicated schema for SDP tests.

    Uses a separate schema from other tests to avoid conflicts.
    """
    full_schema_name = f"{test_catalog}.{SDP_TEST_SCHEMA}"

    # Drop schema if exists (with force to cascade)
    try:
        logger.info(f"Dropping existing SDP test schema: {full_schema_name}")
        workspace_client.schemas.delete(full_schema_name, force=True)
    except Exception:
        pass  # Schema doesn't exist, that's fine

    # Create fresh schema
    logger.info(f"Creating SDP test schema: {full_schema_name}")
    workspace_client.schemas.create(
        name=SDP_TEST_SCHEMA,
        catalog_name=test_catalog,
    )

    yield SDP_TEST_SCHEMA

    # Cleanup - drop schema after tests
    try:
        logger.info(f"Cleaning up SDP test schema: {full_schema_name}")
        workspace_client.schemas.delete(full_schema_name, force=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup SDP test schema: {e}")


@pytest.fixture(scope="module")
def workspace_path(workspace_client) -> str:
    """
    Get workspace path for test pipeline files.

    Uses the current user's home folder.
    """
    user = workspace_client.current_user.me()
    return f"/Workspace/Users/{user.user_name}/test_sdp/{TEST_PIPELINE_NAME}"


@pytest.fixture(scope="module")
def clean_pipeline(pipeline_name: str):
    """
    Ensure pipeline doesn't exist before tests start.

    This cleans up any leftover pipeline from a previous failed run.
    """
    # Check if pipeline exists and delete it
    existing_id = find_pipeline_by_name(pipeline_name)
    if existing_id:
        logger.info(f"Cleaning up existing pipeline: {pipeline_name} ({existing_id})")
        try:
            delete_pipeline(existing_id)
            logger.info("Existing pipeline deleted")
        except Exception as e:
            logger.warning(f"Failed to delete existing pipeline: {e}")

    yield pipeline_name

    # Cleanup after all tests - delete pipeline if it still exists
    existing_id = find_pipeline_by_name(pipeline_name)
    if existing_id:
        logger.info(f"Final cleanup of pipeline: {pipeline_name}")
        try:
            delete_pipeline(existing_id)
        except Exception as e:
            logger.warning(f"Failed to cleanup pipeline: {e}")


@pytest.fixture(scope="module")
def uploaded_pipeline_files(workspace_client, workspace_path: str):
    """Upload test pipeline files to workspace."""
    logger.info(f"Uploading pipeline files to {workspace_path}")

    # Upload the pipelines folder to workspace
    result = upload_folder(
        local_folder=str(PIPELINES_DIR),
        workspace_folder=workspace_path,
        overwrite=True,
    )

    assert result.success, (
        f"Failed to upload pipeline files: {result.get_failed_uploads()}"
    )
    logger.info(f"Uploaded {result.successful} files successfully")

    yield workspace_path

    # Cleanup: delete uploaded files after tests
    try:
        logger.info(f"Cleaning up workspace files: {workspace_path}")
        workspace_client.workspace.delete(workspace_path, recursive=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup workspace files: {e}")


@pytest.mark.integration
class TestCreateOrUpdatePipeline:
    """Tests for create_or_update_pipeline function."""

    def test_create_pipeline_with_bronze_only(
        self,
        test_catalog: str,
        sdp_test_schema: str,
        clean_pipeline: str,
        uploaded_pipeline_files: str,
    ):
        """Should create a new pipeline with bronze layer only."""
        pipeline_name = clean_pipeline
        workspace_path = uploaded_pipeline_files
        bronze_path = f"{workspace_path}/nyctaxi_bronze.sql"

        logger.info(f"Creating pipeline: {pipeline_name}")
        logger.info(f"Catalog: {test_catalog}, Schema: {sdp_test_schema}")
        logger.info(f"Bronze path: {bronze_path}")

        result = create_or_update_pipeline(
            name=pipeline_name,
            root_path=workspace_path,
            catalog=test_catalog,
            schema=sdp_test_schema,
            workspace_file_paths=[bronze_path],
            start_run=True,
            wait_for_completion=True,
            full_refresh=True,
            timeout=600,  # 10 minutes
        )

        logger.info(f"Pipeline result: {result.to_dict()}")

        # Verify creation
        assert result.pipeline_id is not None, "Pipeline ID should be set"
        assert result.pipeline_name == pipeline_name
        assert result.created is True, "Pipeline should be newly created"
        assert result.success is True, (
            f"Pipeline run failed: {result.error_message}. Errors: {result.errors}"
        )
        assert result.state == "COMPLETED", f"Expected COMPLETED, got {result.state}"
        assert result.duration_seconds is not None
        assert result.duration_seconds > 0

    def test_update_pipeline_with_silver_layer(
        self,
        test_catalog: str,
        sdp_test_schema: str,
        clean_pipeline: str,
        uploaded_pipeline_files: str,
    ):
        """Should update existing pipeline by adding silver layer."""
        pipeline_name = clean_pipeline
        workspace_path = uploaded_pipeline_files
        bronze_path = f"{workspace_path}/nyctaxi_bronze.sql"
        silver_path = f"{workspace_path}/nyctaxi_silver.sql"

        logger.info(f"Updating pipeline with silver layer: {pipeline_name}")

        # Update pipeline with both bronze and silver
        result = create_or_update_pipeline(
            name=pipeline_name,
            root_path=workspace_path,
            catalog=test_catalog,
            schema=sdp_test_schema,
            workspace_file_paths=[bronze_path, silver_path],
            start_run=True,
            wait_for_completion=True,
            full_refresh=True,
            timeout=600,
        )

        logger.info(f"Pipeline update result: {result.to_dict()}")

        # Verify update (not creation)
        assert result.pipeline_id is not None
        assert result.pipeline_name == pipeline_name
        assert result.created is False, "Pipeline should be updated, not created"
        assert result.success is True, (
            f"Pipeline run failed: {result.error_message}. Errors: {result.errors}"
        )
        assert result.state == "COMPLETED", f"Expected COMPLETED, got {result.state}"

    def test_find_pipeline_by_name(self, clean_pipeline: str):
        """Should find existing pipeline by name."""
        pipeline_name = clean_pipeline
        pipeline_id = find_pipeline_by_name(pipeline_name)

        assert pipeline_id is not None, f"Pipeline '{pipeline_name}' not found"

    def test_delete_pipeline(self, clean_pipeline: str):
        """Should delete the test pipeline."""
        pipeline_name = clean_pipeline

        # First find the pipeline
        pipeline_id = find_pipeline_by_name(pipeline_name)
        assert pipeline_id is not None, "Pipeline should exist before deletion"

        logger.info(f"Deleting pipeline: {pipeline_name} ({pipeline_id})")

        # Delete it
        delete_pipeline(pipeline_id)

        # Verify deletion
        found_id = find_pipeline_by_name(pipeline_name)
        assert found_id is None, "Pipeline should not exist after deletion"

        logger.info("Pipeline deleted successfully")


# Separate test pipeline name for extra_settings tests
TEST_PIPELINE_NAME_EXTRA = "ai_dev_kit_test_sdp_extra_settings"


@pytest.fixture(scope="module")
def clean_pipeline_extra(pipeline_name_extra: str):
    """
    Ensure pipeline for extra_settings tests doesn't exist before tests start.
    """
    # Check if pipeline exists and delete it
    existing_id = find_pipeline_by_name(pipeline_name_extra)
    if existing_id:
        logger.info(
            f"Cleaning up existing pipeline: {pipeline_name_extra} ({existing_id})"
        )
        try:
            delete_pipeline(existing_id)
            logger.info("Existing pipeline deleted")
        except Exception as e:
            logger.warning(f"Failed to delete existing pipeline: {e}")

    yield pipeline_name_extra

    # Cleanup after all tests - delete pipeline if it still exists
    existing_id = find_pipeline_by_name(pipeline_name_extra)
    if existing_id:
        logger.info(f"Final cleanup of pipeline: {pipeline_name_extra}")
        try:
            delete_pipeline(existing_id)
        except Exception as e:
            logger.warning(f"Failed to cleanup pipeline: {e}")


@pytest.fixture(scope="module")
def pipeline_name_extra() -> str:
    """Return the fixed test pipeline name for extra_settings tests."""
    return TEST_PIPELINE_NAME_EXTRA


@pytest.mark.integration
class TestPipelineExtraSettings:
    """Tests for extra_settings parameter in pipeline functions."""

    def test_create_pipeline_with_development_mode(
        self,
        test_catalog: str,
        sdp_test_schema: str,
        clean_pipeline_extra: str,
        uploaded_pipeline_files: str,
    ):
        """Should create a pipeline with development mode enabled via extra_settings."""
        pipeline_name = clean_pipeline_extra
        workspace_path = uploaded_pipeline_files
        bronze_path = f"{workspace_path}/nyctaxi_bronze.sql"

        logger.info(f"Creating pipeline with extra_settings: {pipeline_name}")

        # Create with development=True and custom tags
        extra_settings = {
            "development": True,
            "tags": {"test": "extra_settings", "environment": "test"},
        }

        result = create_or_update_pipeline(
            name=pipeline_name,
            root_path=workspace_path,
            catalog=test_catalog,
            schema=sdp_test_schema,
            workspace_file_paths=[bronze_path],
            start_run=False,  # Don't run, just create
            extra_settings=extra_settings,
        )

        logger.info(f"Pipeline result: {result.to_dict()}")

        # Verify creation
        assert result.pipeline_id is not None, "Pipeline ID should be set"
        assert result.pipeline_name == pipeline_name
        assert result.created is True, "Pipeline should be newly created"
        assert result.success is True, (
            f"Pipeline creation failed: {result.error_message}"
        )

        # Verify the extra settings were applied by fetching the pipeline
        from databricks_tools_core.spark_declarative_pipelines.pipelines import (
            get_pipeline,
        )

        pipeline_details = get_pipeline(result.pipeline_id)

        # Check development mode is set
        assert pipeline_details.spec.development is True, (
            "Development mode should be True"
        )

        # Check tags are set
        assert pipeline_details.spec.tags is not None, "Tags should be set"
        assert pipeline_details.spec.tags.get("test") == "extra_settings"

    def test_update_pipeline_with_extra_settings(
        self,
        test_catalog: str,
        sdp_test_schema: str,
        clean_pipeline_extra: str,
        uploaded_pipeline_files: str,
    ):
        """Should update a pipeline with new extra_settings."""
        pipeline_name = clean_pipeline_extra
        workspace_path = uploaded_pipeline_files
        bronze_path = f"{workspace_path}/nyctaxi_bronze.sql"

        logger.info(f"Updating pipeline with new extra_settings: {pipeline_name}")

        # Update with new tags
        extra_settings = {
            "development": True,
            "tags": {"test": "updated", "version": "2"},
        }

        result = create_or_update_pipeline(
            name=pipeline_name,
            root_path=workspace_path,
            catalog=test_catalog,
            schema=sdp_test_schema,
            workspace_file_paths=[bronze_path],
            start_run=False,
            extra_settings=extra_settings,
        )

        logger.info(f"Pipeline update result: {result.to_dict()}")

        # Verify update (not creation)
        assert result.created is False, "Pipeline should be updated, not created"
        assert result.success is True, f"Pipeline update failed: {result.error_message}"

        # Verify the updated settings
        from databricks_tools_core.spark_declarative_pipelines.pipelines import (
            get_pipeline,
        )

        pipeline_details = get_pipeline(result.pipeline_id)

        assert pipeline_details.spec.tags.get("test") == "updated"
        assert pipeline_details.spec.tags.get("version") == "2"

    def test_create_pipeline_with_configuration(
        self,
        test_catalog: str,
        sdp_test_schema: str,
        clean_pipeline_extra: str,
        uploaded_pipeline_files: str,
    ):
        """Should create a pipeline with custom configuration dict."""
        pipeline_name = clean_pipeline_extra
        workspace_path = uploaded_pipeline_files
        bronze_path = f"{workspace_path}/nyctaxi_bronze.sql"

        # First delete the existing pipeline to test creation
        existing_id = find_pipeline_by_name(pipeline_name)
        if existing_id:
            delete_pipeline(existing_id)

        logger.info(f"Creating pipeline with configuration: {pipeline_name}")

        # Create with custom configuration
        extra_settings = {
            "configuration": {
                "spark.sql.shuffle.partitions": "10",
                "pipelines.numRetries": "3",
            },
        }

        result = create_or_update_pipeline(
            name=pipeline_name,
            root_path=workspace_path,
            catalog=test_catalog,
            schema=sdp_test_schema,
            workspace_file_paths=[bronze_path],
            start_run=False,
            extra_settings=extra_settings,
        )

        logger.info(f"Pipeline result: {result.to_dict()}")

        assert result.created is True, "Pipeline should be newly created"
        assert result.success is True, (
            f"Pipeline creation failed: {result.error_message}"
        )

        # Verify configuration
        from databricks_tools_core.spark_declarative_pipelines.pipelines import (
            get_pipeline,
        )

        pipeline_details = get_pipeline(result.pipeline_id)

        assert pipeline_details.spec.configuration is not None
        assert (
            pipeline_details.spec.configuration.get("spark.sql.shuffle.partitions")
            == "10"
        )

    def test_delete_extra_settings_pipeline(self, clean_pipeline_extra: str):
        """Should delete the extra_settings test pipeline."""
        pipeline_name = clean_pipeline_extra

        # First find the pipeline
        pipeline_id = find_pipeline_by_name(pipeline_name)
        if pipeline_id is None:
            logger.info(f"Pipeline '{pipeline_name}' already deleted, skipping")
            return

        logger.info(f"Deleting pipeline: {pipeline_name} ({pipeline_id})")

        # Delete it
        delete_pipeline(pipeline_id)

        # Verify deletion
        found_id = find_pipeline_by_name(pipeline_name)
        assert found_id is None, "Pipeline should not exist after deletion"

        logger.info("Extra settings pipeline deleted successfully")
