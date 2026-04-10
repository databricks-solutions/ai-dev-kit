"""
Unit tests for AgentGuard session context helpers.

Tests:
- set_active_session, get_active_session, has_active_session, clear_active_session
"""

from databricks_tools_core.agentguard.context import (
    clear_active_session,
    get_active_session,
    has_active_session,
    set_active_session,
)
from databricks_tools_core.agentguard.models import AgentGuardSession


class TestSessionContext:
    """Tests for thread-local active session helpers."""

    def setup_method(self):
        clear_active_session()

    def teardown_method(self):
        clear_active_session()

    def test_no_session_initially(self):
        assert get_active_session() is None
        assert has_active_session() is False

    def test_set_and_get(self):
        session = AgentGuardSession()
        set_active_session(session)
        assert get_active_session() is session
        assert has_active_session() is True

    def test_clear(self):
        session = AgentGuardSession()
        set_active_session(session)
        clear_active_session()
        assert get_active_session() is None
        assert has_active_session() is False

    def test_replace_session(self):
        s1 = AgentGuardSession()
        s2 = AgentGuardSession()
        set_active_session(s1)
        set_active_session(s2)
        assert get_active_session() is s2

    def test_clear_when_empty_is_safe(self):
        clear_active_session()
        clear_active_session()
        assert get_active_session() is None
