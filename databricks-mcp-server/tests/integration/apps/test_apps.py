"""
Integration tests for Databricks Apps MCP tool.

Tests:
- manage_app: create_or_update, get, list, delete
"""

import logging
import time
import uuid
from pathlib import Path

import pytest

from databricks_mcp_server.tools.apps import manage_app
from databricks_mcp_server.tools.file import manage_workspace_files
from tests.test_config import TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)

# Path to test app resources
RESOURCES_DIR = Path(__file__).parent / "resources"


@pytest.mark.integration
class TestManageApp:
    """Tests for manage_app tool - fast validation tests."""

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_app(action="invalid_action")

        assert "error" in result

    def test_get_nonexistent_app(self):
        """Should handle nonexistent app gracefully."""
        try:
            result = manage_app(action="get", name="nonexistent_app_xyz_12345")

            logger.info(f"Get nonexistent result: {result}")

            # Should return error or not found
            assert result.get("error") or result.get("status") == "NOT_FOUND"
        except Exception as e:
            # SDK raises exception for nonexistent app - this is acceptable
            error_msg = str(e).lower()
            assert "not exist" in error_msg or "not found" in error_msg or "deleted" in error_msg

    def test_create_or_update_requires_name(self):
        """Should require name for create_or_update."""
        result = manage_app(action="create_or_update")

        assert "error" in result
        assert "name" in result["error"]

    def test_delete_requires_name(self):
        """Should require name for delete."""
        result = manage_app(action="delete")

        assert "error" in result
        assert "name" in result["error"]

    @pytest.mark.slow
    def test_list_apps(self):
        """Should list all apps (slow due to pagination)."""
        result = manage_app(action="list")

        logger.info(f"List result: {result}")

        assert "error" not in result, f"List failed: {result}"


@pytest.mark.integration
class TestAppLifecycle:
    """End-to-end test for app lifecycle: upload source -> create -> deploy -> get -> delete."""

    def test_full_app_lifecycle(
        self,
        workspace_client,
        current_user: str,
        cleanup_apps,
    ):
        """Test complete app lifecycle: upload source, create, wait for deployment, get, delete, verify."""
        test_start = time.time()
        unique_id = uuid.uuid4().hex[:6]

        # App names can only contain lowercase letters, numbers, and dashes
        # Convert TEST_RESOURCE_PREFIX underscores to dashes for valid app name
        app_name = f"ai-dev-kit-test-app-{unique_id}"

        workspace_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/apps/{app_name}"

        def log_time(msg):
            elapsed = time.time() - test_start
            logger.info(f"[{elapsed:.1f}s] {msg}")

        try:
            # ==================== SETUP: Upload app source code ====================
            log_time(f"Step 1: Uploading app source to {workspace_path}...")

            upload_result = manage_workspace_files(
                action="upload",
                local_path=str(RESOURCES_DIR) + "/",  # Trailing slash = upload contents only
                workspace_path=workspace_path,
                overwrite=True,
            )

            assert upload_result.get("success", False) or upload_result.get("status") == "success", \
                f"Failed to upload app resources: {upload_result}"
            log_time(f"Upload result: {upload_result}")

            # ==================== APP LIFECYCLE ====================
            # Step 2: Create and deploy app
            log_time(f"Step 2: Creating app '{app_name}'...")

            create_result = manage_app(
                action="create_or_update",
                name=app_name,
                source_code_path=workspace_path,
                description="Test app for MCP integration tests with special chars",
            )

            log_time(f"Create result: {create_result}")

            # Skip test if quota exceeded (workspace limitation, not a test failure)
            if "error" in create_result:
                error_msg = str(create_result.get("error", "")).lower()
                if "quota" in error_msg or "limit" in error_msg or "exceeded" in error_msg:
                    pytest.skip(f"Skipping test due to quota/limit: {create_result['error']}")

            assert "error" not in create_result, f"Create failed: {create_result}"
            assert create_result.get("name") == app_name

            cleanup_apps(app_name)

            # Step 3: Wait for deployment
            log_time("Step 3: Waiting for app deployment...")
            max_wait = 600  # 10 minutes
            wait_interval = 15
            waited = 0
            deployed = False

            while waited < max_wait:
                get_result = manage_app(action="get", name=app_name)
                compute_status = get_result.get("status") or get_result.get("state")

                # Check deployment state (this is where deployment failures are reported)
                active_deployment = get_result.get("active_deployment", {})
                deployment_state = active_deployment.get("state") or active_deployment.get("status")

                log_time(f"App after {waited}s: compute={compute_status}, deployment={deployment_state}")

                # Check for deployment failure first (most important)
                if deployment_state and "FAILED" in str(deployment_state).upper():
                    deployment_msg = active_deployment.get("status", {}).get("message", "")
                    log_time(f"App deployment FAILED: {deployment_msg}")
                    pytest.fail(f"App deployment failed: {deployment_state} - {deployment_msg}")

                # Check for successful deployment
                if deployment_state and "SUCCEEDED" in str(deployment_state).upper():
                    deployed = True
                    log_time("App deployment succeeded!")
                    break
                elif compute_status in ("RUNNING", "READY", "DEPLOYED"):
                    deployed = True
                    break

                time.sleep(wait_interval)
                waited += wait_interval

            if not deployed:
                log_time(f"App not fully deployed after {max_wait}s, continuing with tests")

            # Step 4: Verify app via get
            log_time("Step 4: Verifying app via get...")
            get_result = manage_app(action="get", name=app_name)
            log_time(f"Get result: {get_result}")
            assert "error" not in get_result, f"Get app failed: {get_result}"
            assert get_result.get("name") == app_name

            # App should have a URL (may be None if not fully deployed)
            url = get_result.get("url")
            log_time(f"App URL: {url}")

            # Step 5: Delete app
            log_time("Step 5: Deleting app...")
            delete_result = manage_app(action="delete", name=app_name)
            log_time(f"Delete result: {delete_result}")
            assert "error" not in delete_result, f"Delete failed: {delete_result}"

            # Step 6: Verify app is deleted or deleting
            log_time("Step 6: Verifying app deleted...")
            time.sleep(10)
            get_after = manage_app(action="get", name=app_name)
            log_time(f"Get after delete: {get_after}")

            # Should return error, indicate not found, or be in DELETING state
            status_str = str(get_after).lower()
            assert (
                "error" in get_after
                or "not found" in status_str
                or "deleting" in status_str
            ), f"App should be deleted or deleting: {get_after}"

            log_time("Full app lifecycle test PASSED!")

        except Exception as e:
            log_time(f"Test failed: {e}")
            raise
        finally:
            # Cleanup workspace files
            try:
                workspace_client.workspace.delete(workspace_path, recursive=True)
                log_time(f"Cleaned up workspace path: {workspace_path}")
            except Exception as e:
                log_time(f"Failed to cleanup workspace path: {e}")
