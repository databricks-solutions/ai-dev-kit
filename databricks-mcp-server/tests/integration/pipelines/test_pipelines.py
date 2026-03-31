"""
Integration tests for manage_pipeline and manage_pipeline_run MCP tools.

Tests:
- manage_pipeline: create_or_update, get, delete
- manage_pipeline_run: start, get_events, stop
"""

import logging
import time
import uuid
from pathlib import Path

import pytest

from databricks_mcp_server.tools.pipelines import manage_pipeline, manage_pipeline_run
from databricks_mcp_server.tools.file import manage_workspace_files
from tests.test_config import TEST_CATALOG, TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)

# Path to test pipeline SQL files
RESOURCES_DIR = Path(__file__).parent / "resources"


@pytest.mark.integration
class TestPipelineLifecycle:
    """End-to-end test for pipeline lifecycle: upload SQL -> create -> start -> stop -> delete."""

    def test_full_pipeline_lifecycle(
        self,
        workspace_client,
        current_user: str,
        test_catalog: str,
        pipelines_schema: str,
        cleanup_pipelines,
    ):
        """Test complete pipeline lifecycle in a single test."""
        test_start = time.time()
        unique_id = uuid.uuid4().hex[:6]
        pipeline_name = f"{TEST_RESOURCE_PREFIX}pipeline_{unique_id}"
        workspace_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/pipelines/{pipeline_name}"
        pipeline_id = None

        def log_time(msg):
            elapsed = time.time() - test_start
            logger.info(f"[{elapsed:.1f}s] {msg}")

        try:
            # Step 1: Upload SQL files to workspace
            # Use trailing slash to upload folder contents directly (not the folder itself)
            log_time(f"Step 1: Uploading SQL files to {workspace_path}...")
            upload_result = manage_workspace_files(
                action="upload",
                local_path=str(RESOURCES_DIR) + "/",  # Trailing slash = upload contents only
                workspace_path=workspace_path,
                overwrite=True,
            )
            log_time(f"Upload result: {upload_result}")
            assert upload_result.get("success", False) or upload_result.get("status") == "success", \
                f"Failed to upload pipeline files: {upload_result}"

            # Step 2: Create pipeline with create_or_update
            log_time(f"Step 2: Creating pipeline '{pipeline_name}'...")
            bronze_path = f"{workspace_path}/simple_bronze.sql"

            create_result = manage_pipeline(
                action="create_or_update",
                name=pipeline_name,
                root_path=workspace_path,
                catalog=test_catalog,
                schema=pipelines_schema,
                workspace_file_paths=[bronze_path],
                start_run=False,
            )
            log_time(f"Create result: {create_result}")
            assert "error" not in create_result, f"Create failed: {create_result}"
            assert create_result.get("pipeline_id"), "Should return pipeline_id"
            assert create_result.get("created") is True, "Should be a new pipeline"

            pipeline_id = create_result["pipeline_id"]
            cleanup_pipelines(pipeline_id)
            log_time(f"Pipeline created with ID: {pipeline_id}")

            # Step 3: Get pipeline details
            log_time("Step 3: Getting pipeline details...")
            get_result = manage_pipeline(action="get", pipeline_id=pipeline_id)
            log_time(f"Get result: {get_result}")
            assert "error" not in get_result, f"Get failed: {get_result}"
            assert get_result.get("name") == pipeline_name

            # Verify catalog and schema
            spec = get_result.get("spec", {})
            assert spec.get("catalog") == test_catalog, f"Catalog mismatch: {spec.get('catalog')}"

            # Step 4: Update pipeline (add another SQL file)
            log_time("Step 4: Updating pipeline with additional file...")
            silver_path = f"{workspace_path}/simple_silver.sql"
            update_result = manage_pipeline(
                action="create_or_update",
                name=pipeline_name,
                root_path=workspace_path,
                catalog=test_catalog,
                schema=pipelines_schema,
                workspace_file_paths=[bronze_path, silver_path],
                start_run=False,
            )
            log_time(f"Update result: {update_result}")
            assert "error" not in update_result, f"Update failed: {update_result}"
            assert update_result.get("created") is False, "Should update existing pipeline"

            # Step 5: Start a run and wait for completion
            log_time("Step 5: Starting pipeline run (wait for completion)...")
            start_result = manage_pipeline_run(
                action="start",
                pipeline_id=pipeline_id,
                full_refresh=True,
                wait=True,  # Wait for completion to verify it works
                timeout=600,  # 10 minutes timeout for serverless pipelines
            )
            log_time(f"Start result: {start_result}")
            assert "error" not in start_result, f"Start failed: {start_result}"
            update_id = start_result.get("update_id")
            log_time(f"Pipeline run completed with update_id: {update_id}")

            # Verify the run completed successfully
            state = start_result.get("state") or start_result.get("status")
            assert state in ("COMPLETED", "IDLE", "SUCCESS", None) or "error" not in str(start_result).lower(), \
                f"Pipeline run should complete successfully, got state: {state}, result: {start_result}"

            # Step 6: Get events
            log_time("Step 6: Getting pipeline events...")
            events_result = manage_pipeline_run(
                action="get_events",
                pipeline_id=pipeline_id,
                max_results=10,
            )
            log_time(f"Events result: {len(events_result.get('events', []))} events")
            assert "error" not in events_result, f"Get events failed: {events_result}"
            assert "events" in events_result

            # Step 7: Stop the pipeline (cleanup)
            log_time("Step 7: Stopping pipeline...")
            stop_result = manage_pipeline_run(action="stop", pipeline_id=pipeline_id)
            log_time(f"Stop result: {stop_result}")
            assert stop_result.get("status") == "stopped", f"Stop failed: {stop_result}"

            # Step 8: Delete the pipeline
            log_time("Step 8: Deleting pipeline...")
            delete_result = manage_pipeline(action="delete", pipeline_id=pipeline_id)
            log_time(f"Delete result: {delete_result}")
            assert delete_result.get("status") == "deleted", f"Delete failed: {delete_result}"
            pipeline_id = None  # Mark as deleted

            log_time("Full pipeline lifecycle test PASSED!")

        except Exception as e:
            log_time(f"Test failed: {e}")
            raise
        finally:
            # Cleanup on failure
            if pipeline_id:
                log_time(f"Cleanup: deleting pipeline {pipeline_id}")
                try:
                    manage_pipeline_run(action="stop", pipeline_id=pipeline_id)
                except Exception:
                    pass
                try:
                    manage_pipeline(action="delete", pipeline_id=pipeline_id)
                except Exception:
                    pass

            # Cleanup workspace files
            try:
                workspace_client.workspace.delete(workspace_path, recursive=True)
                log_time(f"Cleaned up workspace path: {workspace_path}")
            except Exception as e:
                log_time(f"Failed to cleanup workspace: {e}")


@pytest.mark.integration
class TestPipelineErrors:
    """Fast validation tests for error handling."""

    def test_create_missing_params(self):
        """Should return error for missing required params."""
        result = manage_pipeline(action="create", name="test")
        assert "error" in result
        assert "requires" in result["error"].lower()

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_pipeline(action="invalid_action")
        assert "error" in result
        assert "invalid action" in result["error"].lower()

    def test_run_invalid_action(self):
        """Should return error for invalid run action."""
        result = manage_pipeline_run(action="invalid_action", pipeline_id="fake-id")
        assert "error" in result
