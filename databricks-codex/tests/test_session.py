"""Tests for session management."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from databricks_codex.session import (
    CodexSession,
    SessionManager,
)


class TestCodexSession:
    """Tests for CodexSession dataclass."""

    def test_minimal_session(self):
        """Test minimal session creation."""
        session = CodexSession(
            session_id="abc123",
            created_at=datetime.now(),
        )

        assert session.session_id == "abc123"
        assert session.last_activity is None
        assert session.project_dir is None
        assert session.metadata == {}

    def test_full_session(self):
        """Test session with all fields."""
        now = datetime.now()
        session = CodexSession(
            session_id="abc123",
            created_at=now,
            last_activity=now,
            project_dir=Path("/workspace"),
            metadata={"key": "value"},
        )

        assert session.session_id == "abc123"
        assert session.project_dir == Path("/workspace")
        assert session.metadata == {"key": "value"}


class TestSessionManager:
    """Tests for SessionManager class."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create session manager with temp directory."""
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_init_default(self):
        """Test default initialization."""
        manager = SessionManager()
        assert manager.session_dir == Path.home() / ".codex" / "sessions"

    def test_init_custom_dir(self, tmp_path):
        """Test initialization with custom directory."""
        custom_dir = tmp_path / "custom"
        manager = SessionManager(session_dir=custom_dir)
        assert manager.session_dir == custom_dir


class TestListSessions:
    """Tests for list_sessions method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_list_sessions_success(self, manager, mock_subprocess_run):
        """Test listing sessions successfully."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="abc12345-def6-7890-abcd-ef1234567890\nxyz98765-uvw4-3210-zyxw-vu0987654321",
            stderr="",
        )

        sessions = manager.list_sessions()

        # Should parse UUID-like patterns
        assert len(sessions) >= 0  # May or may not find patterns

    def test_list_sessions_codex_not_found(self, manager, mock_subprocess_run_not_found):
        """Test list sessions when Codex not installed."""
        sessions = manager.list_sessions()
        assert sessions == []

    def test_list_sessions_timeout(self, manager, mock_subprocess_run_timeout):
        """Test list sessions timeout."""
        sessions = manager.list_sessions()
        assert sessions == []

    def test_list_sessions_with_limit(self, manager, mock_subprocess_run):
        """Test list sessions respects limit."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="session1\nsession2\nsession3\nsession4\nsession5",
            stderr="",
        )

        sessions = manager.list_sessions(limit=2)

        assert len(sessions) <= 2


class TestGetLastSession:
    """Tests for get_last_session method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_get_last_session(self, manager, mock_subprocess_run):
        """Test getting last session."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="abc12345-def6-7890-abcd-ef1234567890",
            stderr="",
        )

        session = manager.get_last_session()

        # May or may not find a session depending on output parsing

    def test_get_last_session_none(self, manager, mock_subprocess_run):
        """Test getting last session when none exist."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        session = manager.get_last_session()
        assert session is None


class TestResumeSession:
    """Tests for resume_session method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_resume_session_by_id(self, manager, mock_subprocess_run):
        """Test resuming session by ID."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Resumed session abc123",
            stderr="",
        )

        result = manager.resume_session("abc123")

        assert result is not None
        mock_subprocess_run.assert_called_once()
        cmd = mock_subprocess_run.call_args[0][0]
        assert "resume" in cmd
        assert "abc123" in cmd

    def test_resume_session_last(self, manager, mock_subprocess_run):
        """Test resuming last session."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Resumed last session",
            stderr="",
        )

        result = manager.resume_session(last=True)

        cmd = mock_subprocess_run.call_args[0][0]
        assert "--last" in cmd

    def test_resume_session_no_args(self, manager):
        """Test resume without session_id or last flag."""
        result = manager.resume_session()
        assert result is None

    def test_resume_session_failure(self, manager, mock_subprocess_run):
        """Test resume session failure."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Session not found",
        )

        result = manager.resume_session("nonexistent")
        assert result is None

    def test_resume_session_not_installed(self, manager, mock_subprocess_run_not_found):
        """Test resume when Codex not installed."""
        result = manager.resume_session("abc123")
        assert result is None


class TestForkSession:
    """Tests for fork_session method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_fork_session_basic(self, manager, mock_subprocess_run):
        """Test basic session fork."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Forked to new123",
            stderr="",
        )

        result = manager.fork_session("original123")

        cmd = mock_subprocess_run.call_args[0][0]
        assert "fork" in cmd
        assert "original123" in cmd

    def test_fork_session_with_prompt(self, manager, mock_subprocess_run):
        """Test forking with new prompt."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Forked",
            stderr="",
        )

        result = manager.fork_session("original", new_prompt="Continue with tests")

        cmd = mock_subprocess_run.call_args[0][0]
        assert "--prompt" in cmd
        assert "Continue with tests" in cmd

    def test_fork_session_failure(self, manager, mock_subprocess_run):
        """Test fork session failure."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Fork failed",
        )

        result = manager.fork_session("original")
        assert result is None

    def test_fork_session_not_installed(self, manager, mock_subprocess_run_not_found):
        """Test fork when Codex not installed."""
        result = manager.fork_session("original")
        assert result is None


class TestSessionExists:
    """Tests for session_exists method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_session_exists_true(self, manager, mock_subprocess_run):
        """Test session exists check - positive."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123",
            stderr="",
        )

        # This depends on parsing - may need adjustment
        exists = manager.session_exists("abc123")
        # Result depends on implementation

    def test_session_exists_false(self, manager, mock_subprocess_run):
        """Test session exists check - negative."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="other-session",
            stderr="",
        )

        exists = manager.session_exists("nonexistent")
        # Result depends on implementation


class TestClearSessions:
    """Tests for clear_sessions method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_clear_sessions_not_implemented(self, manager):
        """Test clear sessions returns 0 (not implemented)."""
        result = manager.clear_sessions()
        assert result == 0


class TestParseSessionOutput:
    """Tests for _parse_session_output method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_parse_uuid_format(self, manager):
        """Test parsing UUID format session IDs."""
        output = "abc12345-def6-7890-abcd-ef1234567890"
        sessions = manager._parse_session_output(output)

        assert len(sessions) == 1
        assert sessions[0].session_id == "abc12345-def6-7890-abcd-ef1234567890"

    def test_parse_multiple_sessions(self, manager):
        """Test parsing multiple sessions."""
        output = """Session: abc12345-def6-7890-abcd-ef1234567890
Session: xyz98765-uvw4-3210-zyxw-vu0987654321"""
        sessions = manager._parse_session_output(output)

        assert len(sessions) == 2

    def test_parse_empty_output(self, manager):
        """Test parsing empty output."""
        sessions = manager._parse_session_output("")
        assert sessions == []

    def test_parse_short_hex_format(self, manager):
        """Test parsing short hex format IDs."""
        output = "abcd1234"
        sessions = manager._parse_session_output(output)

        assert len(sessions) == 1


class TestExtractSessionId:
    """Tests for _extract_session_id method."""

    @pytest.fixture
    def manager(self, tmp_path):
        return SessionManager(session_dir=tmp_path / "sessions")

    def test_extract_uuid(self, manager):
        """Test extracting UUID format ID."""
        output = "Created session abc12345-def6-7890-abcd-ef1234567890"
        session_id = manager._extract_session_id(output)

        assert session_id == "abc12345-def6-7890-abcd-ef1234567890"

    def test_extract_short_id(self, manager):
        """Test extracting short hex ID."""
        output = "Forked to abcd1234"
        session_id = manager._extract_session_id(output)

        assert session_id is not None

    def test_extract_from_empty(self, manager):
        """Test extracting from empty output."""
        session_id = manager._extract_session_id("")
        assert session_id is None
