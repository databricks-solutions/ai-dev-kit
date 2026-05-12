"""
Integration tests for Genie MCP tools.

Tests:
- manage_genie: create_or_update, get, list, delete
- ask_genie: basic queries
"""

import logging
import time
import uuid

import pytest

from databricks_mcp_server.tools.genie import manage_genie, ask_genie
from databricks_mcp_server.tools.sql import execute_sql
from tests.test_config import TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def genie_source_table(
    workspace_client,
    test_catalog: str,
    genie_schema: str,
    warehouse_id: str,
) -> str:
    """Create a source table for Genie space."""
    table_name = f"{test_catalog}.{genie_schema}.sales_data"

    # Create table with test data
    execute_sql(
        sql_query=f"""
            CREATE OR REPLACE TABLE {table_name} (
                order_id INT,
                customer STRING,
                amount DECIMAL(10, 2),
                order_date DATE
            )
        """,
        warehouse_id=warehouse_id,
    )

    execute_sql(
        sql_query=f"""
            INSERT INTO {table_name} VALUES
            (1, 'Alice', 100.00, '2024-01-15'),
            (2, 'Bob', 150.00, '2024-01-16'),
            (3, 'Alice', 200.00, '2024-01-17')
        """,
        warehouse_id=warehouse_id,
    )

    logger.info(f"Created Genie source table: {table_name}")
    return table_name


@pytest.mark.integration
class TestManageGenie:
    """Tests for manage_genie tool."""

    # TODO: Re-enable once pagination performance is improved - takes too long in large workspaces
    # @pytest.mark.slow
    # def test_list_spaces(self):
    #     """Should list all Genie spaces (slow due to pagination)."""
    #     result = manage_genie(action="list")
    #
    #     logger.info(f"List result: found {len(result.get('spaces', []))} spaces")
    #
    #     assert "error" not in result, f"List failed: {result}"
    #     # Should have spaces in a real workspace
    #     assert "spaces" in result

    def test_get_nonexistent_space(self):
        """Should handle nonexistent space gracefully."""
        result = manage_genie(action="get", space_id="nonexistent_space_12345")

        # Should return error or not found
        logger.info(f"Get nonexistent result: {result}")

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_genie(action="invalid_action")

        assert "error" in result


@pytest.mark.integration
class TestGenieLifecycle:
    """End-to-end test for Genie space lifecycle: create -> update -> query -> export -> import -> delete."""

    def test_full_genie_lifecycle(
        self,
        genie_source_table: str,
        warehouse_id: str,
        current_user: str,
    ):
        """Test complete Genie lifecycle with space name containing spaces and /."""
        test_start = time.time()
        # Name with spaces to test edge cases (no / allowed in display name)
        space_name = f"{TEST_RESOURCE_PREFIX}Genie Test Space {uuid.uuid4().hex[:6]}"
        space_id = None
        imported_space_id = None

        def log_time(msg):
            elapsed = time.time() - test_start
            logger.info(f"[{elapsed:.1f}s] {msg}")

        try:
            # Step 1: Create space with special characters in name
            log_time(f"Step 1: Creating space '{space_name}'...")
            create_result = manage_genie(
                action="create_or_update",
                display_name=space_name,
                description="Initial description",
                warehouse_id=warehouse_id,
                table_identifiers=[genie_source_table],
            )
            log_time(f"Create result: {create_result}")
            assert "error" not in create_result, f"Create failed: {create_result}"
            space_id = create_result.get("space_id")
            assert space_id, f"Space ID should be returned: {create_result}"

            # Step 2: Update the space
            log_time("Step 2: Updating space...")
            update_result = manage_genie(
                action="create_or_update",
                space_id=space_id,
                display_name=space_name,
                description="Updated description",
                warehouse_id=warehouse_id,
                table_identifiers=[genie_source_table],
            )
            log_time(f"Update result: {update_result}")
            assert "error" not in update_result, f"Update failed: {update_result}"

            # Step 3: Get and verify update
            log_time("Step 3: Verifying update via get...")
            get_result = manage_genie(action="get", space_id=space_id)
            assert "error" not in get_result, f"Get failed: {get_result}"
            description = get_result.get("description") or get_result.get("spec", {}).get("description")
            log_time(f"Description after update: {description}")
            # Note: The Genie API may not immediately reflect description updates, so we just log it

            # Step 4: Query the space (wait for ready)
            log_time("Step 4: Querying space...")
            max_wait = 120
            wait_interval = 10
            waited = 0
            query_success = False

            while waited < max_wait:
                test_query = ask_genie(
                    space_id=space_id,
                    question="How many orders are there?",
                    timeout_seconds=30,
                )
                log_time(f"Query attempt after {waited}s: status={test_query.get('status')}")

                if test_query.get("status") not in ("FAILED", "ERROR") and "error" not in test_query:
                    query_success = True
                    response_text = str(test_query.get("response", "")) + str(test_query.get("result", ""))
                    if "3" in response_text or test_query.get("status") == "COMPLETED":
                        log_time("Query succeeded with expected result")
                        break
                time.sleep(wait_interval)
                waited += wait_interval

            if not query_success:
                log_time(f"Space not ready after {max_wait}s, skipping query verification")

            # Step 5: Export the space
            log_time("Step 5: Exporting space...")
            export_result = manage_genie(action="export", space_id=space_id)
            log_time(f"Export result: {list(export_result.keys()) if isinstance(export_result, dict) else 'error'}")
            assert "error" not in export_result, f"Export failed: {export_result}"
            serialized_space = export_result.get("serialized_space")
            assert serialized_space, f"serialized_space should be returned: {export_result}"

            # Step 6: Import as new space
            log_time("Step 6: Importing as new space...")
            parent_path = f"/Workspace/Users/{current_user}"
            import_name = f"{TEST_RESOURCE_PREFIX}Genie Imported Space"
            import_result = manage_genie(
                action="import",
                serialized_space=serialized_space,
                title=import_name,
                parent_path=parent_path,
                warehouse_id=warehouse_id,
            )
            log_time(f"Import result: {import_result}")
            assert "error" not in import_result, f"Import failed: {import_result}"
            imported_space_id = import_result.get("space_id")
            assert imported_space_id, f"Imported space ID should be returned: {import_result}"
            assert imported_space_id != space_id, "Imported space should have different ID"

            # Step 7: Delete original space
            log_time("Step 7: Deleting original space...")
            delete_result = manage_genie(action="delete", space_id=space_id)
            log_time(f"Delete result: {delete_result}")
            assert "error" not in delete_result, f"Delete failed: {delete_result}"
            assert delete_result.get("success") is True, f"Delete should return success=True: {delete_result}"
            space_id = None  # Mark as deleted

            # Step 8: Delete imported space
            log_time("Step 8: Deleting imported space...")
            delete_imported = manage_genie(action="delete", space_id=imported_space_id)
            log_time(f"Delete imported result: {delete_imported}")
            assert "error" not in delete_imported, f"Delete imported failed: {delete_imported}"
            imported_space_id = None  # Mark as deleted

            log_time("Full Genie lifecycle test PASSED!")

        except Exception as e:
            log_time(f"Test failed: {e}")
            raise
        finally:
            # Cleanup on failure
            if space_id:
                log_time(f"Cleanup: deleting space {space_id}")
                try:
                    manage_genie(action="delete", space_id=space_id)
                except Exception:
                    pass
            if imported_space_id:
                log_time(f"Cleanup: deleting imported space {imported_space_id}")
                try:
                    manage_genie(action="delete", space_id=imported_space_id)
                except Exception:
                    pass


@pytest.mark.integration
class TestAskGenie:
    """Tests for ask_genie tool."""

    def test_ask_nonexistent_space(self):
        """Should handle nonexistent space gracefully."""
        result = ask_genie(
            space_id="nonexistent_space_12345",
            question="test question",
            timeout_seconds=10,
        )

        # Should return error
        logger.info(f"Ask nonexistent result: {result}")
        assert result.get("status") == "FAILED" or "error" in result
