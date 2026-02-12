"""
Integration tests for Lakebase Autoscaling credential operations.

Tests:
- Generate database credentials (OAuth token) scoped to an endpoint
"""

import logging

import pytest

from databricks_tools_core.lakebase_autoscale import (
    generate_credential,
    list_endpoints,
)

logger = logging.getLogger(__name__)


class TestGenerateCredential:
    """Test credential generation (requires a project with an endpoint)."""

    def test_generate_credential_returns_token(self, lakebase_default_branch):
        """Generating credentials should return a token."""
        endpoints = list_endpoints(lakebase_default_branch)
        assert len(endpoints) > 0, "Expected at least one endpoint on production"

        ep_name = endpoints[0]["name"]
        result = generate_credential(endpoint=ep_name)
        assert "token" in result, "Expected 'token' in credential response"
        assert isinstance(result["token"], str)
        assert len(result["token"]) > 0, "Token should not be empty"

    def test_generate_credential_has_message(self, lakebase_default_branch):
        """Generated credential response should include usage instructions."""
        endpoints = list_endpoints(lakebase_default_branch)
        assert len(endpoints) > 0

        ep_name = endpoints[0]["name"]
        result = generate_credential(endpoint=ep_name)
        assert "message" in result
        assert "sslmode" in result["message"].lower() or "password" in result["message"].lower()

    def test_generate_credential_token_is_nontrivial(self, lakebase_default_branch):
        """The token should be a non-trivial string."""
        endpoints = list_endpoints(lakebase_default_branch)
        assert len(endpoints) > 0

        ep_name = endpoints[0]["name"]
        result = generate_credential(endpoint=ep_name)
        token = result["token"]
        assert len(token) > 20, f"Token seems too short ({len(token)} chars)"
