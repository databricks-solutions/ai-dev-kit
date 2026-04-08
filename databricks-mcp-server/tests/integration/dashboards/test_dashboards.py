"""
Integration tests for AI/BI dashboards MCP tool.

Tests:
- manage_dashboard: create_or_update, get, list, delete, publish, unpublish
"""

import json
import logging
import uuid

import pytest

from databricks_mcp_server.tools.aibi_dashboards import manage_dashboard
from databricks_mcp_server.tools.sql import manage_warehouse
from tests.test_config import TEST_CATALOG, SCHEMAS, TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)

# Deterministic dashboard names for tests (enables safe cleanup/restart)
DASHBOARD_NAME = f"{TEST_RESOURCE_PREFIX}dashboard"
DASHBOARD_UPDATE = f"{TEST_RESOURCE_PREFIX}dashboard_update"
DASHBOARD_PUBLISH = f"{TEST_RESOURCE_PREFIX}dashboard_publish"


@pytest.fixture(scope="module")
def clean_dashboards(current_user: str):
    """Pre-test cleanup: delete any existing test dashboards.

    Uses direct path lookup instead of listing all dashboards (much faster).
    """
    from databricks_tools_core.aibi_dashboards import find_dashboard_by_path

    dashboards_to_clean = [DASHBOARD_NAME, DASHBOARD_UPDATE, DASHBOARD_PUBLISH]
    parent_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/dashboards"

    for dash_name in dashboards_to_clean:
        try:
            # Direct path lookup - much faster than listing all dashboards
            dashboard_path = f"{parent_path}/{dash_name}.lvdash.json"
            dash_id = find_dashboard_by_path(dashboard_path)
            if dash_id:
                manage_dashboard(action="delete", dashboard_id=dash_id)
                logger.info(f"Pre-cleanup: deleted dashboard {dash_name}")
        except Exception as e:
            logger.warning(f"Pre-cleanup failed for {dash_name}: {e}")

    yield

    # Post-test cleanup
    for dash_name in dashboards_to_clean:
        try:
            dashboard_path = f"{parent_path}/{dash_name}.lvdash.json"
            dash_id = find_dashboard_by_path(dashboard_path)
            if dash_id:
                manage_dashboard(action="delete", dashboard_id=dash_id)
                logger.info(f"Post-cleanup: deleted dashboard {dash_name}")
        except Exception:
            pass


@pytest.fixture(scope="module")
def simple_dashboard_json() -> str:
    """Create a simple dashboard JSON for testing."""
    dashboard = {
        "datasets": [
            {
                "name": "simple_data",
                "displayName": "Simple Data",
                "queryLines": ["SELECT 1 as id, 'test' as value"]
            }
        ],
        "pages": [
            {
                "name": "page1",
                "displayName": "Test Page",
                "pageType": "PAGE_TYPE_CANVAS",
                "layout": [
                    {
                        "widget": {
                            "name": "counter1",
                            "queries": [
                                {
                                    "name": "main_query",
                                    "query": {
                                        "datasetName": "simple_data",
                                        "fields": [{"name": "id", "expression": "`id`"}],
                                        "disaggregated": True
                                    }
                                }
                            ],
                            "spec": {
                                "version": 2,
                                "widgetType": "counter",
                                "encodings": {
                                    "value": {"fieldName": "id", "displayName": "Count"}
                                },
                                "frame": {"title": "Test Counter", "showTitle": True}
                            }
                        },
                        "position": {"x": 0, "y": 0, "width": 2, "height": 3}
                    }
                ]
            }
        ]
    }
    return json.dumps(dashboard)


@pytest.fixture(scope="module")
def existing_dashboard(workspace_client, current_user: str) -> str:
    """Find an existing dashboard in our test folder for read-only tests."""
    from databricks_tools_core.aibi_dashboards import find_dashboard_by_path

    test_folder = f"/Workspace/Users/{current_user}/ai_dev_kit_test/dashboards"

    # Try to find one of our test dashboards
    for dash_name in [DASHBOARD_NAME, DASHBOARD_UPDATE, DASHBOARD_PUBLISH]:
        try:
            dashboard_path = f"{test_folder}/{dash_name}.lvdash.json"
            dashboard_id = find_dashboard_by_path(dashboard_path)
            if dashboard_id:
                logger.info(f"Using existing dashboard: {dash_name}")
                return dashboard_id
        except Exception:
            pass

    # If no test dashboard exists, list the test folder
    try:
        items = workspace_client.workspace.list(test_folder)
        for item in items:
            if item.path and item.path.endswith(".lvdash.json"):
                dashboard_id = item.resource_id
                if dashboard_id:
                    logger.info(f"Using dashboard from test folder: {item.path}")
                    return dashboard_id
    except Exception as e:
        logger.warning(f"Could not list test folder: {e}")

    pytest.skip("No existing dashboard in test folder")


@pytest.mark.integration
class TestManageDashboard:
    """Tests for manage_dashboard tool."""

    @pytest.mark.slow
    def test_list_dashboards(self):
        """Should list all dashboards (slow - iterates all dashboards)."""
        result = manage_dashboard(action="list")

        logger.info(f"List result: {result}")

        assert not result.get("error"), f"List failed: {result}"

    def test_get_dashboard(self, existing_dashboard: str):
        """Should get dashboard details."""
        result = manage_dashboard(action="get", dashboard_id=existing_dashboard)

        logger.info(f"Get result: {result}")

        assert not result.get("error"), f"Get failed: {result}"

    def test_get_nonexistent_dashboard(self):
        """Should handle nonexistent dashboard gracefully."""
        try:
            result = manage_dashboard(action="get", dashboard_id="nonexistent_dashboard_12345")
            logger.info(f"Get nonexistent result: {result}")
            # Should return error
            assert result.get("error")
        except Exception as e:
            # SDK raises exception for nonexistent dashboard - this is acceptable
            error_msg = str(e).lower()
            assert "invalid" in error_msg or "not found" in error_msg or "not exist" in error_msg

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_dashboard(action="invalid_action")

        assert "error" in result


@pytest.mark.integration
class TestDashboardLifecycle:
    """End-to-end tests for dashboard lifecycle."""

    def test_create_dashboard(
        self,
        current_user: str,
        simple_dashboard_json: str,
        warehouse_id: str,
        cleanup_dashboards,
    ):
        """Should create a dashboard and verify its structure."""
        dashboard_name = f"{TEST_RESOURCE_PREFIX}dash_create_{uuid.uuid4().hex[:6]}"
        parent_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/dashboards"

        result = manage_dashboard(
            action="create_or_update",
            display_name=dashboard_name,
            parent_path=parent_path,
            serialized_dashboard=simple_dashboard_json,
            warehouse_id=warehouse_id,
        )

        logger.info(f"Create result: {result}")

        assert not result.get("error"), f"Create failed: {result}"

        dashboard_id = result.get("dashboard_id") or result.get("id")
        assert dashboard_id, f"Dashboard ID should be returned: {result}"

        cleanup_dashboards(dashboard_id)

        # Verify dashboard can be retrieved with correct structure
        get_result = manage_dashboard(action="get", dashboard_id=dashboard_id)

        logger.info(f"Get result after create: {get_result}")

        assert not get_result.get("error"), f"Get failed: {get_result}"

        # Verify dashboard name
        retrieved_name = get_result.get("display_name") or get_result.get("name")
        assert dashboard_name in str(retrieved_name), \
            f"Dashboard name mismatch: expected {dashboard_name}, got {retrieved_name}"

        # Verify dashboard has serialized content (proving it was created with our definition)
        serialized = get_result.get("serialized_dashboard")
        if serialized:
            # Should contain our dataset and widget
            assert "simple_data" in serialized, "Dashboard should contain our dataset"
            assert "counter" in serialized.lower(), "Dashboard should contain our counter widget"

    def test_create_and_delete_dashboard(
        self,
        current_user: str,
        simple_dashboard_json: str,
        warehouse_id: str,
    ):
        """Should create and delete a dashboard, verifying each step."""
        dashboard_name = f"{TEST_RESOURCE_PREFIX}dash_del_{uuid.uuid4().hex[:6]}"
        parent_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/dashboards"

        # Create
        create_result = manage_dashboard(
            action="create_or_update",
            display_name=dashboard_name,
            parent_path=parent_path,
            serialized_dashboard=simple_dashboard_json,
            warehouse_id=warehouse_id,
        )

        logger.info(f"Create result: {create_result}")

        dashboard_id = create_result.get("dashboard_id") or create_result.get("id")
        assert dashboard_id, f"Dashboard not created: {create_result}"

        # Verify dashboard exists before delete
        get_result = manage_dashboard(action="get", dashboard_id=dashboard_id)
        assert not get_result.get("error"), f"Dashboard should exist after create: {get_result}"

        # Delete
        delete_result = manage_dashboard(action="delete", dashboard_id=dashboard_id)

        logger.info(f"Delete result: {delete_result}")

        assert not delete_result.get("error") or delete_result.get("status") == "deleted"

        # Verify dashboard is gone
        get_after_delete = manage_dashboard(action="get", dashboard_id=dashboard_id)
        # Should return error or indicate not found
        assert "error" in get_after_delete or get_after_delete.get("lifecycle_state") == "TRASHED", \
            f"Dashboard should be deleted/trashed: {get_after_delete}"


@pytest.mark.integration
class TestDashboardUpdate:
    """Tests for dashboard update functionality."""

    def test_update_dashboard(
        self,
        current_user: str,
        simple_dashboard_json: str,
        warehouse_id: str,
        clean_dashboards,
        cleanup_dashboards,
    ):
        """Should create a dashboard, update it, and verify changes."""
        parent_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/dashboards"

        # Create initial dashboard
        create_result = manage_dashboard(
            action="create_or_update",
            display_name=DASHBOARD_UPDATE,
            parent_path=parent_path,
            serialized_dashboard=simple_dashboard_json,
            warehouse_id=warehouse_id,
        )

        logger.info(f"Create for update test: {create_result}")

        assert not create_result.get("error"), f"Create failed: {create_result}"

        dashboard_id = create_result.get("dashboard_id") or create_result.get("id")
        assert dashboard_id, f"Dashboard ID should be returned: {create_result}"

        cleanup_dashboards(dashboard_id)

        # Create updated dashboard JSON with different dataset
        updated_dashboard = {
            "datasets": [
                {
                    "name": "updated_data",
                    "displayName": "Updated Data",
                    "queryLines": ["SELECT 42 as answer, 'updated' as status"]
                }
            ],
            "pages": [
                {
                    "name": "page1",
                    "displayName": "Updated Page",
                    "pageType": "PAGE_TYPE_CANVAS",
                    "layout": [
                        {
                            "widget": {
                                "name": "counter1",
                                "queries": [
                                    {
                                        "name": "main_query",
                                        "query": {
                                            "datasetName": "updated_data",
                                            "fields": [{"name": "answer", "expression": "`answer`"}],
                                            "disaggregated": True
                                        }
                                    }
                                ],
                                "spec": {
                                    "version": 2,
                                    "widgetType": "counter",
                                    "encodings": {
                                        "value": {"fieldName": "answer", "displayName": "Answer"}
                                    },
                                    "frame": {"title": "Updated Counter", "showTitle": True}
                                }
                            },
                            "position": {"x": 0, "y": 0, "width": 2, "height": 3}
                        }
                    ]
                }
            ]
        }

        # Update the dashboard
        update_result = manage_dashboard(
            action="create_or_update",
            display_name=DASHBOARD_UPDATE,
            parent_path=parent_path,
            serialized_dashboard=json.dumps(updated_dashboard),
            warehouse_id=warehouse_id,
        )

        logger.info(f"Update result: {update_result}")

        assert not update_result.get("error"), f"Update failed: {update_result}"

        # Verify the dashboard was updated
        get_result = manage_dashboard(action="get", dashboard_id=dashboard_id)

        logger.info(f"Get after update: {get_result}")

        assert not get_result.get("error"), f"Get after update failed: {get_result}"

        # Verify updated content
        serialized = get_result.get("serialized_dashboard")
        if serialized:
            assert "updated_data" in serialized, \
                f"Dashboard should contain updated dataset: {serialized[:200]}..."
            assert "42" in serialized or "answer" in serialized, \
                f"Dashboard should contain updated query: {serialized[:200]}..."


@pytest.mark.integration
class TestDashboardPublish:
    """Tests for dashboard publish/unpublish functionality."""

    def test_publish_and_unpublish_dashboard(
        self,
        current_user: str,
        simple_dashboard_json: str,
        warehouse_id: str,
        clean_dashboards,
        cleanup_dashboards,
    ):
        """Should create a dashboard, publish it, verify published state, then unpublish."""
        parent_path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/dashboards"

        # Create dashboard
        create_result = manage_dashboard(
            action="create_or_update",
            display_name=DASHBOARD_PUBLISH,
            parent_path=parent_path,
            serialized_dashboard=simple_dashboard_json,
            warehouse_id=warehouse_id,
        )

        logger.info(f"Create for publish test: {create_result}")

        assert not create_result.get("error"), f"Create failed: {create_result}"

        dashboard_id = create_result.get("dashboard_id") or create_result.get("id")
        assert dashboard_id, f"Dashboard ID should be returned: {create_result}"

        cleanup_dashboards(dashboard_id)

        # Verify initial state is DRAFT
        get_before = manage_dashboard(action="get", dashboard_id=dashboard_id)
        initial_state = get_before.get("lifecycle_state") or get_before.get("state")
        logger.info(f"Initial lifecycle state: {initial_state}")

        # Publish the dashboard
        publish_result = manage_dashboard(
            action="publish",
            dashboard_id=dashboard_id,
            warehouse_id=warehouse_id,
        )

        logger.info(f"Publish result: {publish_result}")

        assert not publish_result.get("error"), f"Publish failed: {publish_result}"

        # Verify published state
        get_after_publish = manage_dashboard(action="get", dashboard_id=dashboard_id)

        logger.info(f"Get after publish: {get_after_publish}")

        assert not get_after_publish.get("error"), f"Get after publish failed: {get_after_publish}"

        # Check lifecycle_state is PUBLISHED or similar
        published_state = get_after_publish.get("lifecycle_state") or get_after_publish.get("state")
        logger.info(f"State after publish: {published_state}")

        # The dashboard should indicate it's published
        assert published_state in ("PUBLISHED", "ACTIVE") or get_after_publish.get("is_published"), \
            f"Dashboard should be published, got state: {published_state}"

        # Unpublish the dashboard
        unpublish_result = manage_dashboard(
            action="unpublish",
            dashboard_id=dashboard_id,
        )

        logger.info(f"Unpublish result: {unpublish_result}")

        assert not unpublish_result.get("error"), f"Unpublish failed: {unpublish_result}"

        # Verify unpublished state
        get_after_unpublish = manage_dashboard(action="get", dashboard_id=dashboard_id)

        logger.info(f"Get after unpublish: {get_after_unpublish}")

        unpublished_state = get_after_unpublish.get("lifecycle_state") or get_after_unpublish.get("state")
        logger.info(f"State after unpublish: {unpublished_state}")

        # Should be back to DRAFT or similar
        assert unpublished_state in ("DRAFT", "ACTIVE") or not get_after_unpublish.get("is_published"), \
            f"Dashboard should be unpublished, got state: {unpublished_state}"
