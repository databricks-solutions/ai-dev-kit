"""
Integration tests for Agent Bricks MCP tools.

Tests:
- manage_ka: create_or_update, get, find_by_name, delete
- manage_mas: create_or_update, get, find_by_name, delete
"""

import logging
import time
import uuid
from pathlib import Path

import pytest
from databricks.sdk.service.catalog import VolumeType

from databricks_mcp_server.tools.agent_bricks import manage_ka, manage_mas
from databricks_mcp_server.tools.volume_files import manage_volume_files
from tests.test_config import TEST_RESOURCE_PREFIX, TEST_CATALOG

logger = logging.getLogger(__name__)

# Path to test resources (static PDFs)
RESOURCES_DIR = Path(__file__).parent / "resources"


@pytest.mark.integration
class TestManageKA:
    """Tests for manage_ka tool - fast validation tests."""

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_ka(action="invalid_action")

        assert "error" in result

    def test_find_by_name_nonexistent(self):
        """Should return not found for nonexistent KA."""
        result = manage_ka(
            action="find_by_name",
            name="nonexistent_ka_xyz_12345"
        )

        logger.info(f"Find nonexistent KA result: {result}")

        # Should not crash, and return found=False
        assert result is not None
        assert result.get("found") is False

    def test_find_by_name_missing_param(self):
        """Should return error when name not provided."""
        result = manage_ka(action="find_by_name")

        assert "error" in result
        assert "name" in result["error"]

    def test_get_missing_tile_id(self):
        """Should return error when tile_id not provided for get."""
        result = manage_ka(action="get")

        assert "error" in result
        assert "tile_id" in result["error"]

    def test_get_nonexistent_ka(self):
        """Should handle nonexistent KA gracefully."""
        result = manage_ka(
            action="get",
            tile_id="nonexistent_tile_id_xyz_12345"
        )

        logger.info(f"Get nonexistent KA result: {result}")

        assert "error" in result

    def test_delete_missing_tile_id(self):
        """Should return error when tile_id not provided for delete."""
        result = manage_ka(action="delete")

        assert "error" in result
        assert "tile_id" in result["error"]

    def test_create_or_update_requires_params(self):
        """Should require name and volume_path for create_or_update."""
        result = manage_ka(action="create_or_update")

        assert "error" in result
        assert "name" in result["error"] or "volume_path" in result["error"]


@pytest.mark.integration
class TestManageMAS:
    """Tests for manage_mas tool - fast validation tests."""

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_mas(action="invalid_action")

        assert "error" in result

    def test_find_by_name_nonexistent(self):
        """Should return not found for nonexistent MAS."""
        result = manage_mas(
            action="find_by_name",
            name="nonexistent_mas_xyz_12345"
        )

        logger.info(f"Find nonexistent MAS result: {result}")

        # Should not crash, and return found=False
        assert result is not None
        assert result.get("found") is False

    def test_find_by_name_missing_param(self):
        """Should return error when name not provided."""
        result = manage_mas(action="find_by_name")

        assert "error" in result
        assert "name" in result["error"]

    def test_get_missing_tile_id(self):
        """Should return error when tile_id not provided for get."""
        result = manage_mas(action="get")

        assert "error" in result
        assert "tile_id" in result["error"]

    def test_get_nonexistent_mas(self):
        """Should handle nonexistent MAS gracefully."""
        result = manage_mas(
            action="get",
            tile_id="nonexistent_tile_id_xyz_12345"
        )

        logger.info(f"Get nonexistent MAS result: {result}")

        assert "error" in result

    def test_delete_missing_tile_id(self):
        """Should return error when tile_id not provided for delete."""
        result = manage_mas(action="delete")

        assert "error" in result
        assert "tile_id" in result["error"]

    def test_create_or_update_requires_params(self):
        """Should require name and agents for create_or_update."""
        result = manage_mas(action="create_or_update")

        assert "error" in result
        assert "name" in result["error"] or "agents" in result["error"]

    def test_create_or_update_agents_validation(self):
        """Should validate agent configuration."""
        result = manage_mas(
            action="create_or_update",
            name="test_mas",
            agents=[
                {"name": "agent1"}  # Missing description and agent type
            ]
        )

        assert "error" in result
        assert "description" in result["error"]

    def test_create_or_update_agent_type_validation(self):
        """Should require exactly one agent type."""
        result = manage_mas(
            action="create_or_update",
            name="test_mas",
            agents=[
                {
                    "name": "agent1",
                    "description": "Test agent",
                    # Missing agent type (endpoint_name, genie_space_id, etc.)
                }
            ]
        )

        assert "error" in result
        assert "endpoint_name" in result["error"] or "one of" in result["error"].lower()

    def test_create_or_update_multiple_agent_types_validation(self):
        """Should reject multiple agent types on same agent."""
        result = manage_mas(
            action="create_or_update",
            name="test_mas",
            agents=[
                {
                    "name": "agent1",
                    "description": "Test agent",
                    "endpoint_name": "some-endpoint",
                    "genie_space_id": "some-space-id",  # Multiple types!
                }
            ]
        )

        assert "error" in result
        assert "multiple" in result["error"].lower()


@pytest.mark.integration
class TestAgentBricksLifecycle:
    """End-to-end test for KA + MAS lifecycle: upload PDFs -> create KA -> create MAS -> verify -> delete."""

    def test_full_ka_mas_lifecycle(
        self,
        workspace_client,
        test_catalog: str,
        agent_bricks_schema: str,
        cleanup_ka,
        cleanup_mas,
    ):
        """Test complete lifecycle: upload PDFs, create KA, create MAS using KA, test all actions, delete both."""
        test_start = time.time()
        unique_id = uuid.uuid4().hex[:6]

        # Names with underscores (API normalizes spaces and / to underscores)
        ka_name = f"{TEST_RESOURCE_PREFIX}KA_Test_{unique_id}"
        mas_name = f"{TEST_RESOURCE_PREFIX}MAS_Test_{unique_id}"

        volume_name = f"{TEST_RESOURCE_PREFIX}ka_docs_{unique_id}"
        full_volume_path = f"/Volumes/{test_catalog}/{agent_bricks_schema}/{volume_name}"

        ka_tile_id = None
        mas_tile_id = None

        def log_time(msg):
            elapsed = time.time() - test_start
            logger.info(f"[{elapsed:.1f}s] {msg}")

        try:
            # ==================== SETUP: Create volume and upload PDFs ====================
            log_time("Step 1: Creating volume and uploading PDFs...")

            # Create volume
            try:
                workspace_client.volumes.create(
                    catalog_name=test_catalog,
                    schema_name=agent_bricks_schema,
                    name=volume_name,
                    volume_type=VolumeType.MANAGED,
                )
                log_time(f"Created volume: {full_volume_path}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    log_time(f"Volume already exists: {full_volume_path}")
                else:
                    raise

            # Upload PDFs from resources folder
            for pdf_file in RESOURCES_DIR.glob("*.pdf"):
                upload_result = manage_volume_files(
                    action="upload",
                    volume_path=f"{full_volume_path}/docs/{pdf_file.name}",
                    local_path=str(pdf_file),
                )
                log_time(f"Uploaded {pdf_file.name}: {upload_result.get('success', upload_result)}")

            # ==================== KA LIFECYCLE ====================
            log_time(f"Step 2: Creating KA '{ka_name}'...")

            # KA create_or_update
            create_ka_result = manage_ka(
                action="create_or_update",
                name=ka_name,
                volume_path=full_volume_path,
                description="Test KA for integration tests with special chars in name",
                instructions="Answer questions about the test documents.",
                add_examples_from_volume=False,
            )
            log_time(f"Create KA result: {create_ka_result}")
            assert "error" not in create_ka_result, f"Create KA failed: {create_ka_result}"
            assert create_ka_result.get("tile_id"), "Should return tile_id"

            ka_tile_id = create_ka_result["tile_id"]
            cleanup_ka(ka_tile_id)
            log_time(f"KA created with tile_id: {ka_tile_id}")

            # Wait for endpoint to start provisioning
            time.sleep(10)

            # KA get (tile_id)
            log_time("Step 3: Testing KA get...")
            get_ka_result = manage_ka(action="get", tile_id=ka_tile_id)
            log_time(f"Get KA result: {get_ka_result}")
            assert "error" not in get_ka_result, f"Get KA failed: {get_ka_result}"
            assert get_ka_result.get("tile_id") == ka_tile_id
            assert get_ka_result.get("name") == ka_name

            # KA find_by_name (name)
            log_time("Step 4: Testing KA find_by_name...")
            find_ka_result = manage_ka(action="find_by_name", name=ka_name)
            log_time(f"Find KA result: {find_ka_result}")
            assert find_ka_result.get("found") is True, f"KA should be found: {find_ka_result}"
            assert find_ka_result.get("tile_id") == ka_tile_id

            # Get KA endpoint name for MAS
            ka_endpoint_name = get_ka_result.get("endpoint_name")
            log_time(f"KA endpoint name: {ka_endpoint_name}")

            # Wait for KA endpoint to be online (needed for MAS)
            log_time("Step 5: Waiting for KA endpoint to be online...")
            max_wait = 600  # 10 minutes - KA provisioning can take a while
            wait_interval = 15
            waited = 0
            ka_ready = False

            while waited < max_wait:
                check_result = manage_ka(action="get", tile_id=ka_tile_id)
                endpoint_status = check_result.get("endpoint_status", "UNKNOWN")
                log_time(f"KA endpoint status after {waited}s: {endpoint_status}")

                if endpoint_status == "ONLINE":
                    ka_ready = True
                    ka_endpoint_name = check_result.get("endpoint_name")
                    break
                elif endpoint_status in ("FAILED", "ERROR"):
                    log_time(f"KA endpoint failed: {check_result}")
                    break

                time.sleep(wait_interval)
                waited += wait_interval

            if not ka_ready:
                log_time(f"KA endpoint not online after {max_wait}s, skipping MAS creation")
                pytest.skip("KA endpoint not ready, cannot test MAS")

            # KA create_or_update (UPDATE existing - tests name lookup and API 2.1 update)
            # Must wait for ONLINE status before update is allowed
            log_time("Step 5b: Testing KA create_or_update on EXISTING KA...")
            update_ka_result = manage_ka(
                action="create_or_update",
                name=ka_name,  # Same name - should find existing and update
                volume_path=full_volume_path,
                description="UPDATED description for integration test",
                instructions="UPDATED instructions for the test.",
                add_examples_from_volume=False,
            )
            log_time(f"Update KA result: {update_ka_result}")
            assert "error" not in update_ka_result, f"Update KA failed: {update_ka_result}"
            assert update_ka_result.get("tile_id") == ka_tile_id, "Should return same tile_id"
            assert update_ka_result.get("operation") == "updated", "Should report 'updated' operation"

            # Verify the update was applied
            verify_result = manage_ka(action="get", tile_id=ka_tile_id)
            assert "UPDATED description" in verify_result.get("description", ""), "Description should be updated"
            assert "UPDATED instructions" in verify_result.get("instructions", ""), "Instructions should be updated"
            log_time("KA update verified successfully")

            # ==================== MAS LIFECYCLE ====================
            log_time(f"Step 6: Creating MAS '{mas_name}' using KA endpoint...")

            # MAS create_or_update (name + agents)
            create_mas_result = manage_mas(
                action="create_or_update",
                name=mas_name,
                description="Test MAS for integration tests with KA agent",
                instructions="Route questions to the Knowledge Assistant.",
                agents=[
                    {
                        "name": "knowledge_agent",
                        "description": "Answers questions using the Knowledge Assistant",
                        "endpoint_name": ka_endpoint_name,
                    }
                ],
            )
            log_time(f"Create MAS result: {create_mas_result}")
            assert "error" not in create_mas_result, f"Create MAS failed: {create_mas_result}"
            assert create_mas_result.get("tile_id"), "Should return tile_id"
            assert create_mas_result.get("agents_count") == 1

            mas_tile_id = create_mas_result["tile_id"]
            cleanup_mas(mas_tile_id)
            log_time(f"MAS created with tile_id: {mas_tile_id}")

            # Wait for MAS to be created
            time.sleep(10)

            # MAS get (tile_id)
            log_time("Step 7: Testing MAS get...")
            get_mas_result = manage_mas(action="get", tile_id=mas_tile_id)
            log_time(f"Get MAS result: {get_mas_result}")
            assert "error" not in get_mas_result, f"Get MAS failed: {get_mas_result}"
            assert get_mas_result.get("tile_id") == mas_tile_id
            assert get_mas_result.get("name") == mas_name
            assert len(get_mas_result.get("agents", [])) == 1

            # MAS find_by_name (name)
            log_time("Step 8: Testing MAS find_by_name...")
            find_mas_result = manage_mas(action="find_by_name", name=mas_name)
            log_time(f"Find MAS result: {find_mas_result}")
            assert find_mas_result.get("found") is True, f"MAS should be found: {find_mas_result}"
            assert find_mas_result.get("tile_id") == mas_tile_id
            assert find_mas_result.get("agents_count") == 1

            # ==================== CLEANUP: Delete MAS then KA ====================
            # MAS delete (tile_id)
            log_time("Step 9: Deleting MAS...")
            delete_mas_result = manage_mas(action="delete", tile_id=mas_tile_id)
            log_time(f"Delete MAS result: {delete_mas_result}")
            assert delete_mas_result.get("success") is True, f"Delete MAS failed: {delete_mas_result}"

            # Wait for deletion
            time.sleep(10)

            # Verify MAS is gone
            log_time("Step 10: Verifying MAS deleted...")
            find_mas_after = manage_mas(action="find_by_name", name=mas_name)
            log_time(f"Find MAS after delete: {find_mas_after}")
            assert find_mas_after.get("found") is False, f"MAS should be deleted: {find_mas_after}"
            mas_tile_id = None  # Mark as deleted

            # KA delete (tile_id)
            log_time("Step 11: Deleting KA...")
            delete_ka_result = manage_ka(action="delete", tile_id=ka_tile_id)
            log_time(f"Delete KA result: {delete_ka_result}")
            assert delete_ka_result.get("success") is True, f"Delete KA failed: {delete_ka_result}"

            # Wait for deletion
            time.sleep(10)

            # Verify KA is gone
            log_time("Step 12: Verifying KA deleted...")
            find_ka_after = manage_ka(action="find_by_name", name=ka_name)
            log_time(f"Find KA after delete: {find_ka_after}")
            assert find_ka_after.get("found") is False, f"KA should be deleted: {find_ka_after}"
            ka_tile_id = None  # Mark as deleted

            log_time("Full KA + MAS lifecycle test PASSED!")

        except Exception as e:
            log_time(f"Test failed: {e}")
            raise
        finally:
            # Cleanup on failure
            if mas_tile_id:
                log_time(f"Cleanup: deleting MAS {mas_tile_id}")
                try:
                    manage_mas(action="delete", tile_id=mas_tile_id)
                except Exception:
                    pass

            if ka_tile_id:
                log_time(f"Cleanup: deleting KA {ka_tile_id}")
                try:
                    manage_ka(action="delete", tile_id=ka_tile_id)
                except Exception:
                    pass

            # Cleanup volume
            try:
                workspace_client.volumes.delete(f"{test_catalog}.{agent_bricks_schema}.{volume_name}")
                log_time(f"Cleaned up volume: {full_volume_path}")
            except Exception as e:
                log_time(f"Failed to cleanup volume: {e}")
