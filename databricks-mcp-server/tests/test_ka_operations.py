"""
Unit tests for Knowledge Assistant operation actions on manage_ka.

Tests the MCP tool wrapper routing logic without hitting Databricks APIs.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from databricks_mcp_server.tools.agent_bricks import manage_ka


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run an async function synchronously for testing."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def _reset_manager():
    """Reset the singleton manager before each test."""
    import databricks_mcp_server.tools.agent_bricks as mod

    mod._manager = None
    yield
    mod._manager = None


def _mock_manager():
    """Create a mock AgentBricksManager."""
    return MagicMock()


# ---------------------------------------------------------------------------
# sync_sources
# ---------------------------------------------------------------------------


class TestSyncSources:
    @patch("databricks_mcp_server.tools.agent_bricks._get_manager")
    def test_sync_sources_calls_manager(self, mock_get_mgr):
        mgr = _mock_manager()
        mock_get_mgr.return_value = mgr

        result = _run(manage_ka(action="sync_sources", tile_id="tile-123"))

        mgr.ka_sync_sources.assert_called_once_with("tile-123")
        assert result["tile_id"] == "tile-123"
        assert result["status"] == "sync_triggered"

    def test_sync_sources_missing_tile_id(self):
        result = _run(manage_ka(action="sync_sources"))
        assert "error" in result
        assert "tile_id" in result["error"]


# ---------------------------------------------------------------------------
# wait_for_ready
# ---------------------------------------------------------------------------


class TestWaitForReady:
    @patch("databricks_mcp_server.tools.agent_bricks._get_manager")
    def test_wait_for_ready_returns_status(self, mock_get_mgr):
        mgr = _mock_manager()
        mgr.ka_wait_until_endpoint_online.return_value = {
            "knowledge_assistant": {
                "status": {"endpoint_status": "ONLINE"},
            }
        }
        mock_get_mgr.return_value = mgr

        result = _run(manage_ka(action="wait_for_ready", tile_id="tile-123"))

        mgr.ka_wait_until_endpoint_online.assert_called_once_with("tile-123", timeout_s=600)
        assert result["status"] == "ONLINE"
        assert result["tile_id"] == "tile-123"
        assert "details" in result

    @patch("databricks_mcp_server.tools.agent_bricks._get_manager")
    def test_wait_for_ready_custom_timeout(self, mock_get_mgr):
        mgr = _mock_manager()
        mgr.ka_wait_until_endpoint_online.return_value = {
            "knowledge_assistant": {
                "status": {"endpoint_status": "PROVISIONING"},
            }
        }
        mock_get_mgr.return_value = mgr

        result = _run(manage_ka(action="wait_for_ready", tile_id="tile-123", timeout_seconds=300))

        mgr.ka_wait_until_endpoint_online.assert_called_once_with("tile-123", timeout_s=300)
        assert result["status"] == "PROVISIONING"

    def test_wait_for_ready_missing_tile_id(self):
        result = _run(manage_ka(action="wait_for_ready"))
        assert "error" in result
        assert "tile_id" in result["error"]


# ---------------------------------------------------------------------------
# list_examples
# ---------------------------------------------------------------------------


class TestListExamples:
    @patch("databricks_mcp_server.tools.agent_bricks._get_manager")
    def test_list_examples_returns_result(self, mock_get_mgr):
        mgr = _mock_manager()
        mgr.ka_list_examples.return_value = {
            "examples": [
                {"example_id": "ex-1", "question": "What is PTO?"},
                {"example_id": "ex-2", "question": "How to file expenses?"},
            ]
        }
        mock_get_mgr.return_value = mgr

        result = _run(manage_ka(action="list_examples", tile_id="tile-123"))

        mgr.ka_list_examples.assert_called_once_with("tile-123")
        assert len(result["examples"]) == 2

    def test_list_examples_missing_tile_id(self):
        result = _run(manage_ka(action="list_examples"))
        assert "error" in result
        assert "tile_id" in result["error"]


# ---------------------------------------------------------------------------
# add_example
# ---------------------------------------------------------------------------


class TestAddExample:
    @patch("databricks_mcp_server.tools.agent_bricks._get_manager")
    def test_add_example_with_guidelines(self, mock_get_mgr):
        mgr = _mock_manager()
        mgr.ka_create_example.return_value = {
            "example_id": "ex-new",
            "question": "What is PTO?",
            "guidelines": ["Mention 15 days default"],
        }
        mock_get_mgr.return_value = mgr

        result = _run(
            manage_ka(
                action="add_example",
                tile_id="tile-123",
                question="What is PTO?",
                guidelines="Mention 15 days default",
            )
        )

        mgr.ka_create_example.assert_called_once_with(
            "tile-123", question="What is PTO?", guidelines=["Mention 15 days default"]
        )
        assert result["example_id"] == "ex-new"

    @patch("databricks_mcp_server.tools.agent_bricks._get_manager")
    def test_add_example_without_guidelines(self, mock_get_mgr):
        mgr = _mock_manager()
        mgr.ka_create_example.return_value = {
            "example_id": "ex-new",
            "question": "What is PTO?",
        }
        mock_get_mgr.return_value = mgr

        result = _run(manage_ka(action="add_example", tile_id="tile-123", question="What is PTO?"))

        mgr.ka_create_example.assert_called_once_with("tile-123", question="What is PTO?", guidelines=None)
        assert result["example_id"] == "ex-new"

    def test_add_example_missing_tile_id(self):
        result = _run(manage_ka(action="add_example", question="What is PTO?"))
        assert "error" in result

    def test_add_example_missing_question(self):
        result = _run(manage_ka(action="add_example", tile_id="tile-123"))
        assert "error" in result
        assert "question" in result["error"]


# ---------------------------------------------------------------------------
# delete_example
# ---------------------------------------------------------------------------


class TestDeleteExample:
    @patch("databricks_mcp_server.tools.agent_bricks._get_manager")
    def test_delete_example_calls_manager(self, mock_get_mgr):
        mgr = _mock_manager()
        mock_get_mgr.return_value = mgr

        result = _run(manage_ka(action="delete_example", tile_id="tile-123", example_id="ex-1"))

        mgr.ka_delete_example.assert_called_once_with("tile-123", "ex-1")
        assert result["status"] == "deleted"
        assert result["tile_id"] == "tile-123"
        assert result["example_id"] == "ex-1"

    def test_delete_example_missing_tile_id(self):
        result = _run(manage_ka(action="delete_example", example_id="ex-1"))
        assert "error" in result

    def test_delete_example_missing_example_id(self):
        result = _run(manage_ka(action="delete_example", tile_id="tile-123"))
        assert "error" in result
        assert "example_id" in result["error"]


# ---------------------------------------------------------------------------
# Invalid action
# ---------------------------------------------------------------------------


class TestInvalidAction:
    def test_invalid_action_returns_error(self):
        result = _run(manage_ka(action="nonexistent"))
        assert "error" in result
        assert "nonexistent" in result["error"]
        assert "sync_sources" in result["error"]
        assert "wait_for_ready" in result["error"]
