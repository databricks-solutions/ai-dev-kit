"""
Integration tests for Lakebase Autoscaling compute (endpoint) operations.

Tests:
- List endpoints on a branch
- Get endpoint details
- Create and delete endpoints
- Update endpoint (resize)
"""

import logging
import time
import uuid

import pytest

from databricks_tools_core.lakebase_autoscale import (
    create_endpoint,
    delete_endpoint,
    get_endpoint,
    list_endpoints,
    update_endpoint,
)

logger = logging.getLogger(__name__)


def _wait_for_endpoint_ready(name: str, timeout: int = 600, poll: int = 15):
    """Poll endpoint until ACTIVE or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ep = get_endpoint(name)
        state = ep.get("state", "")
        logger.info(f"Endpoint '{name}' state: {state}")
        state_upper = state.upper()
        if "ACTIVE" in state_upper or "READY" in state_upper:
            return ep
        if state == "NOT_FOUND":
            raise RuntimeError(f"Endpoint '{name}' not found")
        if "FAILED" in state_upper or "ERROR" in state_upper:
            raise RuntimeError(f"Endpoint '{name}' in terminal state: {state}")
        time.sleep(poll)
    raise TimeoutError(f"Endpoint '{name}' not ACTIVE within {timeout}s")


class TestListEndpoints:
    """Test listing endpoints on a branch."""

    def test_list_endpoints_returns_list(self, lakebase_default_branch):
        """Listing endpoints should return at least the default primary endpoint."""
        endpoints = list_endpoints(lakebase_default_branch)
        assert isinstance(endpoints, list)
        assert len(endpoints) > 0, "Expected at least one endpoint on production"

    def test_default_endpoint_is_read_write(self, lakebase_default_branch):
        """The default endpoint should be read-write."""
        endpoints = list_endpoints(lakebase_default_branch)
        rw_endpoints = [
            ep
            for ep in endpoints
            if "READ_WRITE" in ep.get("endpoint_type", "")
        ]
        assert len(rw_endpoints) > 0, "Expected a read-write endpoint on production"


class TestGetEndpoint:
    """Test getting endpoint details."""

    def test_get_default_endpoint(self, lakebase_default_branch):
        """Getting the default endpoint should return details including host."""
        endpoints = list_endpoints(lakebase_default_branch)
        assert len(endpoints) > 0

        ep = get_endpoint(endpoints[0]["name"])
        assert "name" in ep
        assert ep.get("state") != "NOT_FOUND"

    def test_get_nonexistent_endpoint(self, lakebase_default_branch):
        """Getting a non-existent endpoint should return NOT_FOUND."""
        result = get_endpoint(f"{lakebase_default_branch}/endpoints/nonexistent")
        assert result["state"] == "NOT_FOUND"


class TestEndpointLifecycle:
    """Test endpoint create, update, and delete lifecycle."""

    @pytest.mark.slow
    def test_create_and_delete_read_only_endpoint(
        self,
        lakebase_default_branch,
        cleanup_endpoints,
        unique_name,
    ):
        """Create a read-only endpoint, verify it, then delete it."""
        endpoint_id = f"test-ro-{unique_name}"
        ep_full_name = f"{lakebase_default_branch}/endpoints/{endpoint_id}"
        cleanup_endpoints(ep_full_name)

        # Create read-only endpoint
        result = create_endpoint(
            branch_name=lakebase_default_branch,
            endpoint_id=endpoint_id,
            endpoint_type="ENDPOINT_TYPE_READ_ONLY",
            autoscaling_limit_min_cu=0.5,
            autoscaling_limit_max_cu=2.0,
        )
        assert result["name"] == ep_full_name
        assert result["status"] in ("CREATED", "ALREADY_EXISTS")

        # Wait for active
        _wait_for_endpoint_ready(ep_full_name)

        # Verify
        ep = get_endpoint(ep_full_name)
        assert ep["name"] == ep_full_name
        assert "READ_ONLY" in ep.get("endpoint_type", "")

        # Delete
        del_result = delete_endpoint(ep_full_name)
        assert del_result["status"] == "deleted"


class TestUpdateEndpoint:
    """Test resizing / updating endpoints."""

    @pytest.mark.slow
    def test_resize_default_endpoint(self, lakebase_default_branch):
        """Resize the default endpoint and verify the update."""
        endpoints = list_endpoints(lakebase_default_branch)
        assert len(endpoints) > 0

        ep_name = endpoints[0]["name"]

        # Get current state
        ep = get_endpoint(ep_name)
        current_min = ep.get("min_cu")
        current_max = ep.get("max_cu")
        logger.info(f"Current CU range: {current_min}-{current_max}")

        # Update to a known range
        target_min = 4.0
        target_max = 8.0

        result = update_endpoint(
            name=ep_name,
            autoscaling_limit_min_cu=target_min,
            autoscaling_limit_max_cu=target_max,
        )
        assert result["status"] == "UPDATED"
        assert result.get("min_cu") == target_min
        assert result.get("max_cu") == target_max

        # Restore original if known
        if current_min is not None and current_max is not None:
            update_endpoint(
                name=ep_name,
                autoscaling_limit_min_cu=current_min,
                autoscaling_limit_max_cu=current_max,
            )

    def test_update_no_changes(self, lakebase_default_branch):
        """Updating with no fields should return NO_CHANGES."""
        endpoints = list_endpoints(lakebase_default_branch)
        assert len(endpoints) > 0

        result = update_endpoint(name=endpoints[0]["name"])
        assert result["status"] == "NO_CHANGES"
