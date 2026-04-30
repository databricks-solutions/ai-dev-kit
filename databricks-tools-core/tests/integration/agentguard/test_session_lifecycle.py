"""
Integration tests for AgentGuard session lifecycle.

Tests:
- start_session, stop_session, get_session_status
- actions and scope templates
"""

import pytest

from databricks_tools_core.agentguard.context import (
    clear_active_session,
    get_active_session,
    has_active_session,
)
from databricks_tools_core.agentguard.models import (
    Action,
    AgentGuardMode,
    SessionStatus,
)
from databricks_tools_core.agentguard.session import (
    get_session_status,
    start_session,
    stop_session,
)


@pytest.mark.integration
class TestSessionStartStop:
    """Tests for starting and stopping sessions."""

    def test_start_creates_active_session(self):
        """Should create an active monitor session with metadata."""
        session = start_session(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="lifecycle-test",
            agent_id="test-agent",
            user_id="test-user",
        )

        assert session.status == SessionStatus.ACTIVE
        assert session.mode == AgentGuardMode.MONITOR_ONLY
        assert session.description == "lifecycle-test"
        assert session.task_id.startswith("task_")
        assert has_active_session()

    def test_stop_completes_session(self):
        """Should complete the session and clear the active handle."""
        start_session(mode=AgentGuardMode.MONITOR_ONLY, description="stop-test")

        session = stop_session()

        assert session is not None
        assert session.status == SessionStatus.COMPLETED
        assert session.completed_at is not None
        assert not has_active_session()

    def test_stop_returns_none_when_no_session(self):
        """Should return None when no session is active."""
        result = stop_session()
        assert result is None

    def test_double_start_raises(self):
        """Should reject starting a second session while one is active."""
        start_session(mode=AgentGuardMode.MONITOR_ONLY, description="first")

        with pytest.raises(ValueError, match="already active"):
            start_session(mode=AgentGuardMode.MONITOR_ONLY, description="second")

    def test_enforce_mode_session(self):
        """Should start in enforce mode."""
        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="enforce-test",
        )

        assert session.mode == AgentGuardMode.ENFORCE

    def test_session_status_string(self):
        """Should expose a human-readable status string."""
        session = start_session(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="status-test",
        )

        status = get_session_status()

        assert status is not None
        assert "monitor-only" in status
        assert session.task_id in status


@pytest.mark.integration
class TestSessionWithActions:
    """Tests for recording actions on a session."""

    def test_actions_recorded_in_session(self, monitor_session):
        """Should append actions to the active session."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT 1"},
            task_id=monitor_session.task_id,
            agent_id="test-agent",
            sequence=monitor_session.next_sequence(),
        )
        action.final_decision = "executed"
        monitor_session.record_action(action)

        assert monitor_session.action_count == 1
        assert monitor_session.actions[0].tool_name == "execute_sql"

    def test_session_summary_after_actions(self, monitor_session):
        """Should reflect action count in summary()."""
        for i in range(3):
            action = Action.from_tool_call(
                tool_name="execute_sql",
                tool_params={"query": f"SELECT {i}"},
                task_id=monitor_session.task_id,
                agent_id="test-agent",
                sequence=monitor_session.next_sequence(),
            )
            action.final_decision = "executed"
            monitor_session.record_action(action)

        summary = monitor_session.summary()
        assert "Actions: 3" in summary

    def test_write_count_tracks_mutations(self, monitor_session):
        """Should count writes separately from reads."""
        read_action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM test"},
            task_id=monitor_session.task_id,
            agent_id="test-agent",
            sequence=monitor_session.next_sequence(),
        )
        monitor_session.record_action(read_action)

        write_action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO test VALUES (1)"},
            task_id=monitor_session.task_id,
            agent_id="test-agent",
            sequence=monitor_session.next_sequence(),
        )
        monitor_session.record_action(write_action)

        assert monitor_session.write_count == 1
        assert monitor_session.action_count == 2

    def test_session_persists_across_calls(self):
        """Should reuse the same session object from context helpers."""
        start_session(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="persist-test",
        )

        session = get_active_session()
        assert session is not None
        assert session.description == "persist-test"

        session2 = get_active_session()
        assert session2 is session


@pytest.mark.integration
class TestSessionWithScopeTemplate:
    """Tests for scope templates on session start."""

    def test_start_with_scope_template(self):
        """Should attach scope when a template loads successfully."""
        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="scope-template-test",
            scope_template="etl_pipeline_fix",
            scope_variables={
                "catalog": "main",
                "target_table": "customer_orders",
            },
        )

        assert session.scope is not None
        assert session.scope_template == "etl_pipeline_fix"

    def test_invalid_scope_template_warns_but_continues(self):
        """Should start with scope=None when the template name is unknown."""
        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="bad-template-test",
            scope_template="nonexistent_template_xyz",
        )

        assert session.scope is None
        assert session.status == SessionStatus.ACTIVE
