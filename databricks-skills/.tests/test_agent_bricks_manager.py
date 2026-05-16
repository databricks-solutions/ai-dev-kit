"""
Integration tests for databricks-agent-bricks/scripts/mas_manager.py

Tests the Supervisor Agent (MAS) CLI interface functions.
The mas_manager.py is self-contained - requires only databricks-sdk and requests.
"""

import json
import sys
from pathlib import Path

import pytest

# Add the skills directory to the path
SKILLS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILLS_DIR / "databricks-agent-bricks" / "scripts"))

from mas_manager import (
    create_mas,
    get_mas,
    find_mas,
    update_mas,
    delete_mas,
    list_mas,
    add_examples,
    list_examples,
    _build_agent_list,
    MASManager,
    MASNotFound,
)


@pytest.fixture
def sample_agent_config():
    """Sample agent configuration for testing."""
    return {
        "name": "Test Agent",
        "description": "A test agent for unit testing",
        "endpoint_name": "test-endpoint",
    }


@pytest.fixture
def sample_genie_agent():
    """Sample Genie agent configuration."""
    return {
        "name": "Genie Agent",
        "description": "A Genie-based agent",
        "genie_space_id": "test-space-123",
    }


@pytest.fixture
def sample_uc_function_agent():
    """Sample UC Function agent configuration."""
    return {
        "name": "UC Function Agent",
        "description": "A UC function agent",
        "uc_function_name": "catalog.schema.function_name",
    }


class TestBuildAgentList:
    """Tests for _build_agent_list helper function."""

    def test_build_serving_endpoint_agent(self, sample_agent_config):
        """Should build serving endpoint agent config."""
        result = _build_agent_list([sample_agent_config])

        assert len(result) == 1
        agent = result[0]
        assert agent["name"] == "Test Agent"
        assert agent["description"] == "A test agent for unit testing"
        assert agent["agent_type"] == "serving_endpoint"
        assert agent["serving_endpoint"]["name"] == "test-endpoint"

    def test_build_genie_agent(self, sample_genie_agent):
        """Should build Genie agent config."""
        result = _build_agent_list([sample_genie_agent])

        assert len(result) == 1
        agent = result[0]
        assert agent["agent_type"] == "genie"
        assert agent["genie_space"]["id"] == "test-space-123"

    def test_build_uc_function_agent(self, sample_uc_function_agent):
        """Should build UC function agent config."""
        result = _build_agent_list([sample_uc_function_agent])

        assert len(result) == 1
        agent = result[0]
        assert agent["agent_type"] == "unity_catalog_function"
        assert agent["unity_catalog_function"]["uc_path"]["catalog"] == "catalog"
        assert agent["unity_catalog_function"]["uc_path"]["schema"] == "schema"
        assert agent["unity_catalog_function"]["uc_path"]["name"] == "function_name"

    def test_build_mcp_connection_agent(self):
        """Should build external MCP server agent config."""
        agent_config = {
            "name": "MCP Agent",
            "description": "External MCP server",
            "connection_name": "my-mcp-connection",
        }
        result = _build_agent_list([agent_config])

        assert len(result) == 1
        agent = result[0]
        assert agent["agent_type"] == "external_mcp_server"
        assert agent["external_mcp_server"]["connection_name"] == "my-mcp-connection"

    def test_build_multiple_agents(self, sample_agent_config, sample_genie_agent):
        """Should build multiple agent configs."""
        result = _build_agent_list([sample_agent_config, sample_genie_agent])

        assert len(result) == 2
        assert result[0]["agent_type"] == "serving_endpoint"
        assert result[1]["agent_type"] == "genie"


class TestBuildAgentListValidation:
    """Negative tests for _build_agent_list input validation."""

    def test_rejects_uc_function_name_with_two_parts(self):
        with pytest.raises(ValueError, match="catalog.schema.function"):
            _build_agent_list([{"name": "x", "description": "y", "uc_function_name": "catalog.schema"}])

    def test_rejects_uc_function_name_with_four_parts(self):
        with pytest.raises(ValueError, match="catalog.schema.function"):
            _build_agent_list([{"name": "x", "description": "y", "uc_function_name": "a.b.c.d"}])

    def test_rejects_uc_function_name_with_empty_segment(self):
        """`catalog..fn` has three parts but middle is empty — must be rejected."""
        with pytest.raises(ValueError, match="non-empty parts"):
            _build_agent_list([{"name": "x", "description": "y", "uc_function_name": "catalog..fn"}])

    def test_rejects_uc_function_name_with_whitespace_only_segment(self):
        with pytest.raises(ValueError, match="non-empty parts"):
            _build_agent_list([{"name": "x", "description": "y", "uc_function_name": "catalog.  .fn"}])

    def test_rejects_agent_with_no_identifier(self):
        """No genie/ka/uc/connection/endpoint -> must raise, not silently send name=None."""
        with pytest.raises(ValueError, match="must specify one of"):
            _build_agent_list([{"name": "x", "description": "y"}])

    def test_rejects_agent_with_empty_endpoint_name(self):
        with pytest.raises(ValueError, match="must specify one of"):
            _build_agent_list([{"name": "x", "description": "y", "endpoint_name": ""}])


class TestAddExamplesBatch:
    """Unit tests for MASManager.add_examples_batch — no Databricks connection needed."""

    def test_empty_list_returns_empty(self):
        """Empty input must short-circuit (ThreadPoolExecutor rejects max_workers=0)."""
        manager = MASManager.__new__(MASManager)  # skip __init__ (would need WorkspaceClient)
        assert manager.add_examples_batch("tile-id", []) == []


class TestResponseErrorHandling:
    """Unit tests for typed-404 (MASNotFound) and empty-body handling."""

    @pytest.fixture
    def manager_with_fake_workspace(self):
        class _Cfg:
            host = "https://example.cloud.databricks.com"

            def authenticate(self):
                return {"Authorization": "Bearer x"}

        class _W:
            config = _Cfg()

        manager = MASManager.__new__(MASManager)
        manager.w = _W()
        return manager

    def test_404_raises_MASNotFound_not_generic_exception(self, manager_with_fake_workspace, monkeypatch):
        """A 404 response must raise MASNotFound so callers can branch on existence cleanly."""
        from unittest.mock import MagicMock

        import mas_manager as mas_manager_module

        fake_resp = MagicMock()
        fake_resp.status_code = 404
        fake_resp.content = b'{"message":"tile does not exist"}'
        fake_resp.text = '{"message":"tile does not exist"}'
        fake_resp.json.return_value = {"message": "tile does not exist"}
        monkeypatch.setattr(mas_manager_module.requests, "get", lambda *a, **kw: fake_resp)

        with pytest.raises(MASNotFound):
            manager_with_fake_workspace._get("/api/2.0/multi-agent-supervisors/missing")

    def test_get_method_returns_None_on_404(self, manager_with_fake_workspace, monkeypatch):
        """MASManager.get() should swallow MASNotFound and return None."""
        from unittest.mock import MagicMock

        import mas_manager as mas_manager_module

        fake_resp = MagicMock()
        fake_resp.status_code = 404
        fake_resp.content = b'{"message":"x"}'
        fake_resp.text = '{"message":"x"}'
        fake_resp.json.return_value = {"message": "x"}
        monkeypatch.setattr(mas_manager_module.requests, "get", lambda *a, **kw: fake_resp)

        assert manager_with_fake_workspace.get("missing-tile") is None

    def test_get_method_reraises_non_404(self, manager_with_fake_workspace, monkeypatch):
        """Non-404 errors must still propagate from MASManager.get()."""
        from unittest.mock import MagicMock

        import mas_manager as mas_manager_module

        fake_resp = MagicMock()
        fake_resp.status_code = 500
        fake_resp.content = b'{"message":"boom"}'
        fake_resp.text = '{"message":"boom"}'
        fake_resp.json.return_value = {"message": "boom"}
        monkeypatch.setattr(mas_manager_module.requests, "get", lambda *a, **kw: fake_resp)

        with pytest.raises(Exception) as exc_info:
            manager_with_fake_workspace.get("any-tile")
        assert not isinstance(exc_info.value, MASNotFound)

    def test_post_handles_empty_body(self, manager_with_fake_workspace, monkeypatch):
        """_post must tolerate empty success responses (symmetric with _delete)."""
        from unittest.mock import MagicMock

        import mas_manager as mas_manager_module

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.content = b""
        fake_resp.text = ""
        monkeypatch.setattr(mas_manager_module.requests, "post", lambda *a, **kw: fake_resp)

        assert manager_with_fake_workspace._post("/api/test", {"x": 1}) == {}


class TestDeleteResponseHandling:
    """Unit tests for MASManager._delete — tolerate empty / non-JSON DELETE bodies."""

    @pytest.fixture
    def manager_with_fake_workspace(self):
        from unittest.mock import MagicMock

        class _Cfg:
            host = "https://example.cloud.databricks.com"

            def authenticate(self):
                return {"Authorization": "Bearer x"}

        class _W:
            config = _Cfg()

        manager = MASManager.__new__(MASManager)
        manager.w = _W()
        return manager

    def test_empty_body_returns_empty_dict(self, manager_with_fake_workspace, monkeypatch):
        """204 No Content / empty body must not raise JSONDecodeError."""
        from unittest.mock import MagicMock

        import mas_manager as mas_manager_module

        fake_resp = MagicMock()
        fake_resp.status_code = 204
        fake_resp.content = b""
        fake_resp.text = ""
        monkeypatch.setattr(mas_manager_module.requests, "delete", lambda *a, **kw: fake_resp)

        assert manager_with_fake_workspace._delete("/api/test") == {}

    def test_non_json_body_returns_empty_dict(self, manager_with_fake_workspace, monkeypatch):
        """Some endpoints return plain text on success — must not raise."""
        from unittest.mock import MagicMock

        import mas_manager as mas_manager_module

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.content = b"OK"
        fake_resp.text = "OK"
        fake_resp.json.side_effect = ValueError("not JSON")
        monkeypatch.setattr(mas_manager_module.requests, "delete", lambda *a, **kw: fake_resp)

        assert manager_with_fake_workspace._delete("/api/test") == {}


@pytest.mark.integration
class TestMASLifecycle:
    """Integration tests for MAS CRUD operations.

    Note: These tests require a Databricks workspace with Agent Bricks enabled.
    They are marked as integration tests and may be skipped if connection fails.
    """

    @pytest.fixture
    def test_mas_name(self):
        """Unique name for test MAS."""
        import uuid
        return f"test-mas-{uuid.uuid4().hex[:8]}"

    def test_list_mas(self, workspace_client):
        """Should list existing MAS tiles."""
        try:
            result = list_mas()
            assert isinstance(result, list)
        except Exception as e:
            if "Agent Bricks" in str(e) or "not enabled" in str(e).lower():
                pytest.skip("Agent Bricks not enabled in workspace")
            raise

    def test_find_mas_not_found(self, workspace_client):
        """Should return not found for non-existent MAS."""
        try:
            result = find_mas("nonexistent-mas-name-xyz-123")
            assert result["found"] is False
        except Exception as e:
            if "Agent Bricks" in str(e) or "not enabled" in str(e).lower():
                pytest.skip("Agent Bricks not enabled in workspace")
            raise

    def test_get_mas_not_found(self, workspace_client):
        """Should return error for non-existent tile ID."""
        try:
            result = get_mas("00000000-0000-0000-0000-000000000000")
            assert "error" in result or result.get("tile_id") == ""
        except Exception as e:
            if "Agent Bricks" in str(e) or "not enabled" in str(e).lower():
                pytest.skip("Agent Bricks not enabled in workspace")
            raise
