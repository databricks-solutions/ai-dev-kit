"""
Integration tests for Lakebase Autoscaling branch operations.

Tests:
- List branches on a project
- Get branch details
- Create and delete a branch
- Protect and unprotect a branch
- Reset a branch from its parent
"""

import logging
import time
import uuid

import pytest

from databricks_tools_core.lakebase_autoscale import (
    create_branch,
    delete_branch,
    get_branch,
    list_branches,
    update_branch,
)

logger = logging.getLogger(__name__)


def _wait_for_branch_ready(name: str, timeout: int = 300, poll: int = 10):
    """Poll branch until READY or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        branch = get_branch(name)
        state = branch.get("state", "")
        logger.info(f"Branch '{name}' state: {state}")
        state_upper = state.upper()
        if "READY" in state_upper or "ACTIVE" in state_upper:
            return branch
        if state == "NOT_FOUND":
            raise RuntimeError(f"Branch '{name}' not found")
        if "FAILED" in state_upper or "ERROR" in state_upper:
            raise RuntimeError(f"Branch '{name}' in terminal state: {state}")
        time.sleep(poll)
    raise TimeoutError(f"Branch '{name}' not READY within {timeout}s")


class TestListBranches:
    """Test listing branches."""

    def test_list_branches_returns_list(self, lakebase_project_name):
        """Listing branches should return at least the production branch."""
        branches = list_branches(lakebase_project_name)
        assert isinstance(branches, list)
        assert len(branches) > 0, "Expected at least one branch (production)"

    def test_default_branch_exists(self, lakebase_project_name):
        """A default branch should exist."""
        branches = list_branches(lakebase_project_name)
        default_branches = [b for b in branches if b.get("is_default") is True]
        assert len(default_branches) > 0, f"No default branch found in: {branches}"


class TestGetBranch:
    """Test getting branch details."""

    def test_get_default_branch(self, lakebase_default_branch):
        """Getting the default branch should return its details."""
        branch = get_branch(lakebase_default_branch)
        assert branch["name"] == lakebase_default_branch

    def test_get_nonexistent_branch(self, lakebase_project_name):
        """Getting a non-existent branch should return NOT_FOUND."""
        result = get_branch(f"{lakebase_project_name}/branches/nonexistent")
        assert result["state"] == "NOT_FOUND"


class TestBranchLifecycle:
    """Test branch create, update, and delete lifecycle."""

    @pytest.mark.slow
    def test_create_and_delete_branch(self, lakebase_project_name, cleanup_branches, unique_name):
        """Create a branch from production and then delete it."""
        branch_id = f"test-br-{unique_name}"
        branch_full_name = f"{lakebase_project_name}/branches/{branch_id}"
        cleanup_branches(branch_full_name)

        # Create
        result = create_branch(
            project_name=lakebase_project_name,
            branch_id=branch_id,
            ttl_seconds=7200,  # 2 hours
        )
        assert result["name"] == branch_full_name
        assert result["status"] in ("CREATED", "ALREADY_EXISTS")

        # Wait for ready
        _wait_for_branch_ready(branch_full_name)

        # Verify
        branch = get_branch(branch_full_name)
        assert branch["name"] == branch_full_name

        # Delete
        del_result = delete_branch(branch_full_name)
        assert del_result["status"] == "deleted"

    @pytest.mark.slow
    def test_create_branch_no_expiry(self, lakebase_project_name, cleanup_branches, unique_name):
        """Create a permanent branch (no expiry)."""
        branch_id = f"test-perm-{unique_name}"
        branch_full_name = f"{lakebase_project_name}/branches/{branch_id}"
        cleanup_branches(branch_full_name)

        result = create_branch(
            project_name=lakebase_project_name,
            branch_id=branch_id,
            no_expiry=True,
        )
        assert result["name"] == branch_full_name
        assert result["status"] in ("CREATED", "ALREADY_EXISTS")

        _wait_for_branch_ready(branch_full_name)

        # Branch should not have an expire_time
        branch = get_branch(branch_full_name)
        # expire_time might be absent or None for permanent branches
        assert branch.get("expire_time") is None or "expire_time" not in branch

    @pytest.mark.slow
    def test_protect_and_unprotect_branch(self, lakebase_project_name, cleanup_branches, unique_name):
        """Create a branch, protect it, then unprotect it."""
        branch_id = f"test-prot-{unique_name}"
        branch_full_name = f"{lakebase_project_name}/branches/{branch_id}"
        cleanup_branches(branch_full_name)

        # Create
        create_branch(
            project_name=lakebase_project_name,
            branch_id=branch_id,
            no_expiry=True,
        )
        _wait_for_branch_ready(branch_full_name)

        # Protect
        result = update_branch(branch_full_name, is_protected=True)
        assert result["status"] == "UPDATED"
        assert result["is_protected"] is True

        # Verify protection
        branch = get_branch(branch_full_name)
        assert branch.get("is_protected") is True

        # Unprotect
        result = update_branch(branch_full_name, is_protected=False)
        assert result["status"] == "UPDATED"

    # NOTE: reset_branch is not yet available in the Databricks SDK.
    # Test will be added when the SDK supports it.
