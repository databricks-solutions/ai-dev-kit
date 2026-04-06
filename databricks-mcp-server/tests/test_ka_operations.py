"""
Unit tests for Knowledge Assistant operation actions on manage_ka.

Tests the _manage_ka_impl function directly (no async, no MCP wrapper).
"""

from unittest.mock import MagicMock, patch

import pytest

from databricks_mcp_server.tools.agent_bricks import _manage_ka_impl as manage_ka

# Patch target for the manager singleton
_GET_MANAGER = "databricks_mcp_server.tools.agent_bricks._get_manager"


@pytest.fixture(autouse=True)
def _reset_manager():
    """Reset the singleton manager before each test."""
    import databricks_mcp_server.tools.agent_bricks as mod

    mod._manager = None
    yield
    mod._manager = None


@pytest.fixture
def mock_manager():
    """Return a fresh MagicMock that stands in for AgentBricksManager."""
    return MagicMock()


# ---------------------------------------------------------------------------
# sync_sources
# ---------------------------------------------------------------------------


class TestSyncSources:
    def test_sync_sources_calls_manager(self, mock_manager):
        with patch(_GET_MANAGER, return_value=mock_manager):
            result = manage_ka(action="sync_sources", tile_id="tile-123")

        mock_manager.ka_sync_sources.assert_called_once_with("tile-123")
        assert result["tile_id"] == "tile-123"
        assert result["status"] == "sync_triggered"

    def test_sync_sources_missing_tile_id(self):
        result = manage_ka(action="sync_sources")
        assert "error" in result
        assert "tile_id" in result["error"]


# ---------------------------------------------------------------------------
# wait_for_ready
# ---------------------------------------------------------------------------


class TestWaitForReady:
    def test_wait_for_ready_returns_status(self, mock_manager):
        mock_manager.ka_wait_until_endpoint_online.return_value = {
            "knowledge_assistant": {
                "status": {"endpoint_status": "ONLINE"},
            }
        }
        with patch(_GET_MANAGER, return_value=mock_manager):
            result = manage_ka(action="wait_for_ready", tile_id="tile-123")

        mock_manager.ka_wait_until_endpoint_online.assert_called_once_with("tile-123", timeout_s=600)
        assert result["status"] == "ONLINE"
        assert result["tile_id"] == "tile-123"
        assert "details" in result

    def test_wait_for_ready_custom_timeout(self, mock_manager):
        mock_manager.ka_wait_until_endpoint_online.return_value = {
            "knowledge_assistant": {
                "status": {"endpoint_status": "PROVISIONING"},
            }
        }
        with patch(_GET_MANAGER, return_value=mock_manager):
            result = manage_ka(action="wait_for_ready", tile_id="tile-123", timeout_seconds=300)

        mock_manager.ka_wait_until_endpoint_online.assert_called_once_with("tile-123", timeout_s=300)
        assert result["status"] == "PROVISIONING"

    def test_wait_for_ready_missing_tile_id(self):
        result = manage_ka(action="wait_for_ready")
        assert "error" in result
        assert "tile_id" in result["error"]


# ---------------------------------------------------------------------------
# list_examples
# ---------------------------------------------------------------------------


class TestListExamples:
    def test_list_examples_returns_result(self, mock_manager):
        mock_manager.ka_list_examples.return_value = {
            "examples": [
                {"example_id": "ex-1", "question": "What is PTO?"},
                {"example_id": "ex-2", "question": "How to file expenses?"},
            ]
        }
        with patch(_GET_MANAGER, return_value=mock_manager):
            result = manage_ka(action="list_examples", tile_id="tile-123")

        mock_manager.ka_list_examples.assert_called_once_with("tile-123")
        assert len(result["examples"]) == 2

    def test_list_examples_missing_tile_id(self):
        result = manage_ka(action="list_examples")
        assert "error" in result
        assert "tile_id" in result["error"]


# ---------------------------------------------------------------------------
# add_example
# ---------------------------------------------------------------------------


class TestAddExample:
    def test_add_example_with_guidelines(self, mock_manager):
        mock_manager.ka_create_example.return_value = {
            "example_id": "ex-new",
            "question": "What is PTO?",
            "guidelines": ["Mention 15 days default"],
        }
        with patch(_GET_MANAGER, return_value=mock_manager):
            result = manage_ka(
                action="add_example",
                tile_id="tile-123",
                question="What is PTO?",
                guidelines="Mention 15 days default",
            )

        mock_manager.ka_create_example.assert_called_once_with(
            "tile-123", question="What is PTO?", guidelines=["Mention 15 days default"]
        )
        assert result["example_id"] == "ex-new"

    def test_add_example_without_guidelines(self, mock_manager):
        mock_manager.ka_create_example.return_value = {
            "example_id": "ex-new",
            "question": "What is PTO?",
        }
        with patch(_GET_MANAGER, return_value=mock_manager):
            result = manage_ka(action="add_example", tile_id="tile-123", question="What is PTO?")

        mock_manager.ka_create_example.assert_called_once_with("tile-123", question="What is PTO?", guidelines=None)
        assert result["example_id"] == "ex-new"

    def test_add_example_missing_tile_id(self):
        result = manage_ka(action="add_example", question="What is PTO?")
        assert "error" in result

    def test_add_example_missing_question(self):
        result = manage_ka(action="add_example", tile_id="tile-123")
        assert "error" in result
        assert "question" in result["error"]


# ---------------------------------------------------------------------------
# delete_example
# ---------------------------------------------------------------------------


class TestDeleteExample:
    def test_delete_example_calls_manager(self, mock_manager):
        with patch(_GET_MANAGER, return_value=mock_manager):
            result = manage_ka(action="delete_example", tile_id="tile-123", example_id="ex-1")

        mock_manager.ka_delete_example.assert_called_once_with("tile-123", "ex-1")
        assert result["status"] == "deleted"
        assert result["tile_id"] == "tile-123"
        assert result["example_id"] == "ex-1"

    def test_delete_example_missing_tile_id(self):
        result = manage_ka(action="delete_example", example_id="ex-1")
        assert "error" in result

    def test_delete_example_missing_example_id(self):
        result = manage_ka(action="delete_example", tile_id="tile-123")
        assert "error" in result
        assert "example_id" in result["error"]


# ---------------------------------------------------------------------------
# Invalid action
# ---------------------------------------------------------------------------


class TestInvalidAction:
    def test_invalid_action_returns_error(self):
        result = manage_ka(action="nonexistent")
        assert "error" in result
        assert "nonexistent" in result["error"]
        assert "sync_sources" in result["error"]
        assert "wait_for_ready" in result["error"]
