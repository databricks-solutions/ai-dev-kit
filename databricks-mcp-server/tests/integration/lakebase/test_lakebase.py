"""
Integration tests for Lakebase MCP tools.

Tests:
- manage_lakebase_database: create_or_update, get, list, delete
- manage_lakebase_branch: create_or_update, delete
- manage_lakebase_sync: (requires existing provisioned instance)
- generate_lakebase_credential: (read-only)
"""

import logging
import time
import uuid

import pytest

from databricks_mcp_server.tools.lakebase import (
    manage_lakebase_database,
    manage_lakebase_branch,
    manage_lakebase_sync,
    generate_lakebase_credential,
)
from tests.test_config import TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestManageLakebaseDatabase:
    """Tests for manage_lakebase_database tool."""

    @pytest.mark.slow
    def test_list_all_databases(self):
        """Should list all Lakebase databases (slow due to pagination)."""
        result = manage_lakebase_database(action="list")

        logger.info(f"List all result: found {len(result.get('databases', []))} databases")

        assert "error" not in result, f"List failed: {result}"
        assert "databases" in result
        assert isinstance(result["databases"], list)

    def test_get_nonexistent_database(self):
        """Should handle nonexistent database gracefully."""
        result = manage_lakebase_database(
            action="get",
            name="nonexistent_db_xyz_12345",
        )

        logger.info(f"Get nonexistent result: {result}")

        assert "error" in result

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_lakebase_database(action="invalid_action")

        assert "error" in result


@pytest.mark.integration
class TestManageLakebaseBranch:
    """Tests for manage_lakebase_branch tool (autoscale only)."""

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_lakebase_branch(action="invalid_action")

        assert "error" in result

    def test_create_requires_params(self):
        """Should require project_name and branch_id for create."""
        result = manage_lakebase_branch(action="create_or_update")

        assert "error" in result
        assert "project_name" in result["error"] or "branch_id" in result["error"]

    def test_delete_requires_name(self):
        """Should require name for delete."""
        result = manage_lakebase_branch(action="delete")

        assert "error" in result
        assert "name" in result["error"]


@pytest.mark.integration
class TestManageLakebaseSync:
    """Tests for manage_lakebase_sync tool."""

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_lakebase_sync(action="invalid_action")

        assert "error" in result

    def test_create_requires_params(self):
        """Should require instance_name, source_table_name, target_table_name for create."""
        result = manage_lakebase_sync(action="create_or_update")

        assert "error" in result
        assert "instance_name" in result["error"] or "source_table_name" in result["error"]

    def test_delete_requires_table_name(self):
        """Should require table_name for delete."""
        result = manage_lakebase_sync(action="delete")

        assert "error" in result
        assert "table_name" in result["error"]


@pytest.mark.integration
class TestGenerateLakebaseCredential:
    """Tests for generate_lakebase_credential tool."""

    def test_requires_instance_or_endpoint(self):
        """Should require either instance_names or endpoint."""
        result = generate_lakebase_credential()

        logger.info(f"Generate credential without params result: {result}")

        assert "error" in result


@pytest.mark.integration
class TestAutoscaleLifecycle:
    """End-to-end test for autoscale project lifecycle: create -> branch -> delete."""

    def test_full_autoscale_lifecycle(self, cleanup_lakebase_instances):
        """Test complete autoscale lifecycle: create project, add branch, delete branch, delete project."""
        test_start = time.time()
        # Unique name for this test run
        # Note: Lakebase project_id must match pattern ^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$
        # So we use hyphens instead of underscores and lowercase only
        project_name = f"ai-dev-kit-test-lakebase-{uuid.uuid4().hex[:6]}"
        branch_id = "ai-dev-kit-test-branch"
        branch_name = None

        def log_time(msg):
            elapsed = time.time() - test_start
            logger.info(f"[{elapsed:.1f}s] {msg}")

        try:
            # Step 0: Pre-cleanup - delete any existing project with this name (from crashed previous runs)
            log_time(f"Step 0: Pre-cleanup - checking for existing project '{project_name}'...")
            existing = manage_lakebase_database(
                action="get",
                name=project_name,
                type="autoscale",
            )
            if "error" not in existing:
                log_time(f"Found existing project, deleting...")
                manage_lakebase_database(
                    action="delete",
                    name=project_name,
                    type="autoscale",
                )
                # Wait for deletion to propagate
                time.sleep(15)
                log_time("Existing project deleted")

            # Step 1: Create autoscale project
            log_time(f"Step 1: Creating autoscale project '{project_name}'...")
            create_result = manage_lakebase_database(
                action="create_or_update",
                name=project_name,
                type="autoscale",
                display_name=f"Test Autoscale Project",
            )
            log_time(f"Create result: {create_result}")
            assert "error" not in create_result, f"Create project failed: {create_result}"

            cleanup_lakebase_instances(project_name, "autoscale")

            # Step 2: Wait for project to be ready
            log_time("Step 2: Waiting for project to be ready...")
            max_wait = 120
            wait_interval = 10
            waited = 0
            project_ready = False

            while waited < max_wait:
                get_result = manage_lakebase_database(
                    action="get",
                    name=project_name,
                    type="autoscale",
                )
                state = get_result.get("state") or get_result.get("status")
                log_time(f"Project state after {waited}s: {state}")

                if state in ("ACTIVE", "READY", "RUNNING"):
                    project_ready = True
                    break
                elif state in ("FAILED", "ERROR", "DELETED"):
                    pytest.fail(f"Project creation failed: {get_result}")

                time.sleep(wait_interval)
                waited += wait_interval

            if not project_ready:
                log_time(f"Project not fully ready after {max_wait}s, continuing anyway")

            # Step 3: Create a branch
            log_time("Step 3: Creating branch...")
            branch_result = manage_lakebase_branch(
                action="create_or_update",
                project_name=project_name,
                branch_id=branch_id,
                ttl_seconds=3600,
            )
            log_time(f"Create branch result: {branch_result}")
            assert "error" not in branch_result, f"Create branch failed: {branch_result}"
            branch_name = branch_result.get("name", f"{project_name}/branches/{branch_id}")

            # Step 4: Wait for branch and verify it exists
            log_time("Step 4: Verifying branch exists...")
            time.sleep(10)
            get_project = manage_lakebase_database(
                action="get",
                name=project_name,
                type="autoscale",
            )
            branches = get_project.get("branches", [])
            branch_names = [b.get("name", "") for b in branches]
            log_time(f"Branches found: {branch_names}")
            assert any(branch_id in name for name in branch_names), \
                f"Branch should exist: {branch_names}"

            # Step 5: Delete the branch
            log_time("Step 5: Deleting branch...")
            delete_branch_result = manage_lakebase_branch(
                action="delete",
                name=branch_name,
            )
            log_time(f"Delete branch result: {delete_branch_result}")
            assert "error" not in delete_branch_result, f"Delete branch failed: {delete_branch_result}"

            # Step 6: Verify branch is gone
            log_time("Step 6: Verifying branch deleted...")
            time.sleep(10)
            get_after_branch_delete = manage_lakebase_database(
                action="get",
                name=project_name,
                type="autoscale",
            )
            branches_after = get_after_branch_delete.get("branches", [])
            branch_names_after = [b.get("name", "") for b in branches_after]
            log_time(f"Branches after delete: {branch_names_after}")
            assert not any(branch_id in name for name in branch_names_after), \
                f"Branch should be deleted: {branch_names_after}"
            branch_name = None  # Mark as deleted

            # Step 7: Delete the project
            log_time("Step 7: Deleting project...")
            delete_result = manage_lakebase_database(
                action="delete",
                name=project_name,
                type="autoscale",
            )
            log_time(f"Delete project result: {delete_result}")
            assert "error" not in delete_result, f"Delete project failed: {delete_result}"

            # Step 8: Verify project is gone
            log_time("Step 8: Verifying project deleted...")
            time.sleep(10)
            get_after = manage_lakebase_database(
                action="get",
                name=project_name,
                type="autoscale",
            )
            log_time(f"Get after delete: {get_after}")
            assert "error" in get_after or "not found" in str(get_after).lower(), \
                f"Project should be deleted: {get_after}"

            log_time("Full autoscale lifecycle test PASSED!")

        except Exception as e:
            log_time(f"Test failed: {e}")
            raise
        finally:
            # Cleanup on failure
            if branch_name:
                log_time(f"Cleanup: deleting branch {branch_name}")
                try:
                    manage_lakebase_branch(action="delete", name=branch_name)
                except Exception:
                    pass
            # Project cleanup is handled by cleanup_lakebase_instances fixture
