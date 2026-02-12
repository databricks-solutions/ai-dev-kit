"""
Integration tests for Vector Search endpoint operations.

Tests:
- create_vs_endpoint
- get_vs_endpoint
- list_vs_endpoints
- delete_vs_endpoint
"""

import logging
import uuid

import pytest

from databricks_tools_core.vector_search import (
    create_vs_endpoint,
    delete_vs_endpoint,
    get_vs_endpoint,
    list_vs_endpoints,
)

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestGetEndpoint:
    """Tests for getting endpoint details."""

    def test_get_endpoint_online(self, vs_endpoint_name: str):
        """Should return details for a running endpoint."""
        result = get_vs_endpoint(vs_endpoint_name)

        logger.info(f"Endpoint details: {result}")

        assert result["name"] == vs_endpoint_name
        assert result["state"] == "ONLINE"
        assert result.get("endpoint_type") == "STANDARD"
        assert result.get("error") is None

    def test_get_endpoint_not_found(self):
        """Should return NOT_FOUND for non-existent endpoint."""
        result = get_vs_endpoint("nonexistent_endpoint_xyz_99999")

        assert result["state"] == "NOT_FOUND"
        assert "error" in result


@pytest.mark.integration
class TestListEndpoints:
    """Tests for listing endpoints."""

    def test_list_endpoints(self, vs_endpoint_name: str):
        """Should list endpoints including the test endpoint."""
        endpoints = list_vs_endpoints()

        logger.info(f"Found {len(endpoints)} endpoints")

        assert isinstance(endpoints, list)
        assert len(endpoints) > 0

        # Find our test endpoint
        names = [ep["name"] for ep in endpoints]
        assert vs_endpoint_name in names, f"Test endpoint '{vs_endpoint_name}' not found in: {names}"


@pytest.mark.integration
class TestCreateEndpoint:
    """Tests for creating endpoints."""

    def test_create_endpoint(self, cleanup_endpoints):
        """Should create a new endpoint and return creation info."""
        name = f"vs_test_create_{uuid.uuid4().hex[:8]}"
        cleanup_endpoints(name)

        result = create_vs_endpoint(name=name, endpoint_type="STANDARD")

        logger.info(f"Create result: {result}")

        assert result["name"] == name
        assert result["endpoint_type"] == "STANDARD"
        assert result["status"] in ("CREATING", "ALREADY_EXISTS")

    def test_create_duplicate_endpoint(self, vs_endpoint_name: str):
        """Should return ALREADY_EXISTS for duplicate endpoint."""
        result = create_vs_endpoint(name=vs_endpoint_name, endpoint_type="STANDARD")

        assert result["status"] == "ALREADY_EXISTS"


@pytest.mark.integration
class TestDeleteEndpoint:
    """Tests for deleting endpoints."""

    def test_delete_endpoint_not_found(self):
        """Should return NOT_FOUND when deleting non-existent endpoint."""
        result = delete_vs_endpoint("nonexistent_endpoint_xyz_99999")

        assert result["status"] == "NOT_FOUND"
        assert "error" in result
