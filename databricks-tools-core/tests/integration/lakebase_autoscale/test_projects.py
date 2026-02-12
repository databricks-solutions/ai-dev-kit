"""
Integration tests for Lakebase Autoscaling project operations.

Tests:
- List projects
- Get project details
- Update project display name
- Create and delete a standalone project (full lifecycle)
"""

import logging
import uuid

import pytest

from databricks_tools_core.lakebase_autoscale import (
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project,
)

logger = logging.getLogger(__name__)


class TestListProjects:
    """Test listing Lakebase Autoscaling projects."""

    def test_list_projects_returns_list(self, lakebase_project_name):
        """Listing projects should return a non-empty list."""
        projects = list_projects()
        assert isinstance(projects, list)
        assert len(projects) > 0, "Expected at least one project"

    def test_list_projects_contains_test_project(self, lakebase_project_name):
        """The test project should appear in the list."""
        projects = list_projects()
        names = [p["name"] for p in projects]
        assert lakebase_project_name in names, f"Test project '{lakebase_project_name}' not found in: {names}"


class TestGetProject:
    """Test getting Lakebase Autoscaling project details."""

    def test_get_existing_project(self, lakebase_project_name):
        """Getting an existing project should return its details."""
        project = get_project(lakebase_project_name)
        assert project["name"] == lakebase_project_name
        assert "state" in project or "display_name" in project

    def test_get_project_without_prefix(self, lakebase_project_name):
        """Getting a project by ID without 'projects/' prefix should work."""
        project_id = lakebase_project_name.replace("projects/", "")
        project = get_project(project_id)
        assert project["name"] == lakebase_project_name

    def test_get_nonexistent_project(self):
        """Getting a non-existent project should return NOT_FOUND."""
        result = get_project("projects/nonexistent-project-xyz")
        assert result["state"] == "NOT_FOUND"


class TestUpdateProject:
    """Test updating Lakebase Autoscaling project properties."""

    def test_update_display_name(self, lakebase_project_name):
        """Updating display name should succeed."""
        new_name = f"Updated Test {uuid.uuid4().hex[:6]}"
        result = update_project(lakebase_project_name, display_name=new_name)
        assert result["status"] == "UPDATED"
        assert result["display_name"] == new_name

    def test_update_no_changes(self, lakebase_project_name):
        """Updating with no fields should return NO_CHANGES."""
        result = update_project(lakebase_project_name)
        assert result["status"] == "NO_CHANGES"


class TestProjectLifecycle:
    """Test full project create-delete lifecycle."""

    @pytest.mark.slow
    def test_create_and_delete_project(self, cleanup_projects):
        """Create a project, verify it exists, then delete it.

        NOTE: Project creation can take 10-15 minutes due to LRO provisioning.
        The SDK's operation.wait() blocks until the project is fully created.
        """
        project_id = f"lb-test-lifecycle-{uuid.uuid4().hex[:8]}"
        cleanup_projects(f"projects/{project_id}")

        # Create (operation.wait() blocks until provisioning completes)
        logger.info(f"Creating project '{project_id}' -- this may take 10-15 min...")
        result = create_project(
            project_id=project_id,
            display_name=f"Lifecycle Test {project_id}",
            pg_version="17",
        )
        assert result["name"] == f"projects/{project_id}"
        assert result["status"] in ("CREATED", "ALREADY_EXISTS")
        logger.info(f"Project '{project_id}' created: {result}")

        # Verify it's accessible
        proj = get_project(f"projects/{project_id}")
        assert proj["name"] == f"projects/{project_id}"
        assert "display_name" in proj

        # Delete (operation.wait() blocks until deletion completes)
        logger.info(f"Deleting project '{project_id}'...")
        del_result = delete_project(f"projects/{project_id}")
        assert del_result["status"] == "deleted"
        logger.info(f"Project '{project_id}' deleted")
