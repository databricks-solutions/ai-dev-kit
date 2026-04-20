"""
Integration tests for databricks-genie/scripts/conversation.py

Tests the Genie Conversation API CLI interface.
Requires databricks.sdk for Genie Space operations.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the skills directory to the path
SKILLS_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SKILLS_DIR / "databricks-genie"))

from conversation import ask_genie, _print_json


class TestAskGenieFunction:
    """Tests for the ask_genie function structure and error handling."""

    def test_ask_genie_returns_dict(self):
        """Should return a dictionary result."""
        # Test with a mock to verify return structure
        with patch("conversation.WorkspaceClient") as mock_client:
            # Setup mock
            mock_response = MagicMock()
            mock_response.conversation_id = "conv-123"
            mock_response.message_id = "msg-456"

            mock_message = MagicMock()
            mock_message.status = MagicMock()
            mock_message.status.value = "COMPLETED"
            mock_message.attachments = []
            mock_message.query_result = None

            mock_instance = mock_client.return_value
            mock_instance.genie.start_conversation_and_wait.return_value = mock_response
            mock_instance.genie.get_message.return_value = mock_message

            result = ask_genie(
                space_id="test-space",
                question="Test question",
                timeout_seconds=5,
            )

            assert isinstance(result, dict)
            assert "question" in result
            assert "conversation_id" in result
            assert "message_id" in result
            assert "status" in result

    def test_ask_genie_with_conversation_id(self):
        """Should pass conversation_id for follow-up questions."""
        with patch("conversation.WorkspaceClient") as mock_client:
            mock_response = MagicMock()
            mock_response.conversation_id = "conv-123"
            mock_response.message_id = "msg-456"

            mock_message = MagicMock()
            mock_message.status = MagicMock()
            mock_message.status.value = "COMPLETED"
            mock_message.attachments = []
            mock_message.query_result = None

            mock_instance = mock_client.return_value
            mock_instance.genie.start_conversation_and_wait.return_value = mock_response
            mock_instance.genie.get_message.return_value = mock_message

            result = ask_genie(
                space_id="test-space",
                question="Follow-up question",
                conversation_id="existing-conv-id",
                timeout_seconds=5,
            )

            # Verify the conversation_id was passed
            call_args = mock_instance.genie.start_conversation_and_wait.call_args
            assert call_args.kwargs.get("conversation_id") == "existing-conv-id"

    def test_ask_genie_handles_timeout(self):
        """Should return timeout status when query exceeds timeout."""
        with patch("conversation.WorkspaceClient") as mock_client:
            mock_response = MagicMock()
            mock_response.conversation_id = "conv-123"
            mock_response.message_id = "msg-456"

            mock_message = MagicMock()
            mock_message.status = MagicMock()
            mock_message.status.value = "EXECUTING_QUERY"  # Never completes
            mock_message.attachments = []

            mock_instance = mock_client.return_value
            mock_instance.genie.start_conversation_and_wait.return_value = mock_response
            mock_instance.genie.get_message.return_value = mock_message

            # Very short timeout to trigger timeout path
            result = ask_genie(
                space_id="test-space",
                question="Test question",
                timeout_seconds=0.1,  # Will timeout immediately
            )

            assert result["status"] == "TIMEOUT"
            assert "error" in result

    def test_ask_genie_handles_failure(self):
        """Should return failure status when query fails."""
        with patch("conversation.WorkspaceClient") as mock_client:
            mock_response = MagicMock()
            mock_response.conversation_id = "conv-123"
            mock_response.message_id = "msg-456"

            mock_message = MagicMock()
            mock_message.status = MagicMock()
            mock_message.status.value = "FAILED"
            mock_message.attachments = []

            mock_instance = mock_client.return_value
            mock_instance.genie.start_conversation_and_wait.return_value = mock_response
            mock_instance.genie.get_message.return_value = mock_message

            result = ask_genie(
                space_id="test-space",
                question="Test question",
                timeout_seconds=5,
            )

            assert result["status"] == "FAILED"


class TestPrintJson:
    """Tests for the _print_json helper function."""

    def test_print_json_dict(self, capsys):
        """Should print dict as formatted JSON."""
        _print_json({"key": "value", "number": 42})
        captured = capsys.readouterr()
        assert '"key": "value"' in captured.out
        assert '"number": 42' in captured.out

    def test_print_json_list(self, capsys):
        """Should print list as formatted JSON."""
        _print_json([1, 2, 3])
        captured = capsys.readouterr()
        assert "1" in captured.out
        assert "2" in captured.out
        assert "3" in captured.out


@pytest.mark.integration
class TestGenieConversationIntegration:
    """Integration tests for Genie Conversation API.

    Note: These tests require a Databricks workspace with Genie enabled
    and a valid Genie Space ID configured via environment variable.
    """

    @pytest.fixture
    def genie_space_id(self):
        """Get Genie Space ID from environment."""
        space_id = os.environ.get("TEST_GENIE_SPACE_ID")
        if not space_id:
            pytest.skip("TEST_GENIE_SPACE_ID not set - skipping Genie integration tests")
        return space_id

    def test_ask_genie_simple_question(self, workspace_client, genie_space_id):
        """Should be able to ask a simple question to Genie."""
        result = ask_genie(
            space_id=genie_space_id,
            question="How many rows are in the table?",
            timeout_seconds=120,
        )

        # Should return a valid result
        assert result["conversation_id"] is not None
        assert result["status"] in ["COMPLETED", "FAILED", "TIMEOUT"]

    def test_ask_genie_follow_up(self, workspace_client, genie_space_id):
        """Should be able to ask follow-up questions."""
        # First question
        result1 = ask_genie(
            space_id=genie_space_id,
            question="Show me the first 5 rows",
            timeout_seconds=120,
        )

        if result1["status"] != "COMPLETED":
            pytest.skip("First query did not complete - skipping follow-up test")

        # Follow-up question
        result2 = ask_genie(
            space_id=genie_space_id,
            question="Now show me the count",
            conversation_id=result1["conversation_id"],
            timeout_seconds=120,
        )

        # Should use same conversation
        assert result2["conversation_id"] == result1["conversation_id"]
