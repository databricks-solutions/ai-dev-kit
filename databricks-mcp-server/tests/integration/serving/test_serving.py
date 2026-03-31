"""
Integration tests for model serving MCP tool.

Tests:
- manage_serving_endpoint: get, list, query

Note: The manage_serving_endpoint tool only supports read-only operations.
Creating/updating/deleting serving endpoints requires a separate skill
(databricks-model-serving) or direct SDK usage.
"""

import logging

import pytest

from databricks_mcp_server.tools.serving import manage_serving_endpoint
from tests.test_config import TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def existing_serving_endpoint(workspace_client) -> str:
    """Find an existing serving endpoint for tests."""
    try:
        result = manage_serving_endpoint(action="list")
        endpoints = result.get("endpoints", [])
        for ep in endpoints:
            state = ep.get("state") or ep.get("status")
            if state in ("READY", "ONLINE", "NOT_UPDATING"):
                name = ep.get("name")
                logger.info(f"Using existing serving endpoint: {name}")
                return name
    except Exception as e:
        logger.warning(f"Could not list serving endpoints: {e}")

    pytest.skip("No existing serving endpoint available")


@pytest.mark.integration
class TestManageServingEndpoint:
    """Tests for manage_serving_endpoint tool."""

    def test_list_endpoints(self):
        """Should list all serving endpoints."""
        result = manage_serving_endpoint(action="list")

        logger.info(f"List result: {result}")

        assert "error" not in result, f"List failed: {result}"
        assert "endpoints" in result
        assert isinstance(result["endpoints"], list)

    def test_get_endpoint(self, existing_serving_endpoint: str):
        """Should get endpoint details."""
        result = manage_serving_endpoint(action="get", name=existing_serving_endpoint)

        logger.info(f"Get result: {result}")

        # API returns error: None as a field, check truthiness not presence
        assert not result.get("error"), f"Get failed: {result}"
        assert result.get("name") == existing_serving_endpoint

    def test_get_nonexistent_endpoint(self):
        """Should handle nonexistent endpoint gracefully."""
        try:
            result = manage_serving_endpoint(action="get", name="nonexistent_endpoint_xyz_12345")

            logger.info(f"Get nonexistent result: {result}")

            assert result.get("state") == "NOT_FOUND" or result.get("error")
        except Exception as e:
            # Function raises exception for nonexistent endpoint - this is acceptable
            error_msg = str(e).lower()
            assert "not exist" in error_msg or "not found" in error_msg

    def test_query_foundation_model(self):
        """Should query a foundation model endpoint."""
        result = manage_serving_endpoint(
            action="query",
            name="databricks-meta-llama-3-3-70b-instruct",
            messages=[
                {"role": "user", "content": "Say hello in one word."}
            ],
            max_tokens=10,
        )

        logger.info(f"Query result: {result}")

        assert "error" not in result, f"Query failed: {result}"
        # Should have some response
        assert result.get("choices") or result.get("predictions") or result.get("output")

    def test_query_with_invalid_endpoint(self):
        """Should handle invalid endpoint query gracefully."""
        try:
            result = manage_serving_endpoint(
                action="query",
                name="nonexistent_endpoint_xyz_12345",
                messages=[{"role": "user", "content": "test"}],
            )

            logger.info(f"Query invalid endpoint result: {result}")

            # Should return error
            assert result.get("error") or result.get("status") == "error"
        except Exception as e:
            # Function raises exception for invalid endpoint - this is acceptable
            error_msg = str(e).lower()
            assert "not exist" in error_msg or "not found" in error_msg

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_serving_endpoint(action="invalid_action")

        assert "error" in result
