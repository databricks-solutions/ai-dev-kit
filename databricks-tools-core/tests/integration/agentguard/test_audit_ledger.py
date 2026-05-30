"""
Integration tests for AgentGuard audit ledger (Delta + JSONL).

Tests:
- flush_session_to_delta, JSONL append, failure fallback

Requires live workspace, warehouse, and catalog/schema permissions.
"""

import json

import pytest

from databricks_tools_core.agentguard.ledger import (
    append_action,
    flush_session_to_delta,
    init_session_file,
)
from databricks_tools_core.agentguard.models import (
    Action,
    AgentGuardMode,
    AgentGuardSession,
    CheckpointDecision,
    CheckpointResult,
)


def _build_test_session(num_actions: int = 3) -> AgentGuardSession:
    """Builds a completed session with actions mirrored to JSONL."""
    session = AgentGuardSession(
        mode=AgentGuardMode.MONITOR_ONLY,
        description="ledger-integration-test",
        agent_id="test-agent",
        user_id="test-user",
    )

    init_session_file(session.task_id)

    for i in range(num_actions):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"sql_query": f"SELECT {i} AS val"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        action.checkpoint_result = CheckpointResult(
            decision=CheckpointDecision.AUTO_APPROVE,
            risk_score=float(i * 10),
            risk_breakdown={"action_type": float(i * 5), "environment": 10.0},
        )
        action.final_decision = "executed"
        action.execution_success = True
        session.record_action(action)
        append_action(session.task_id, action, session)

    session.complete()
    return session


@pytest.fixture(autouse=True)
def _use_tmp_sessions_dir(tmp_path, monkeypatch):
    """Points JSONL output at tmp_path for isolation."""
    monkeypatch.setattr(
        "databricks_tools_core.agentguard.ledger._SESSIONS_DIR",
        tmp_path,
    )


@pytest.mark.integration
class TestAuditLedgerDeltaWrite:
    """Tests for writing audit rows to Delta."""

    def test_flush_creates_table_and_writes(self, warehouse_id, ledger_schema):
        """Should create or reuse the table and insert rows."""
        session = _build_test_session(num_actions=3)

        result = flush_session_to_delta(
            session,
            catalog=ledger_schema["catalog"],
            schema=ledger_schema["schema"],
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "success"
        assert result["rows"] == 3
        assert result["method"] == "delta"
        assert ledger_schema["catalog"] in result["destination"]

    def test_written_data_is_queryable(self, warehouse_id, ledger_schema):
        """Should read back rows with expected columns."""
        from databricks_tools_core.sql.sql import execute_sql

        session = _build_test_session(num_actions=2)
        task_id = session.task_id

        flush_session_to_delta(
            session,
            catalog=ledger_schema["catalog"],
            schema=ledger_schema["schema"],
            warehouse_id=warehouse_id,
        )

        rows = execute_sql(
            f"SELECT * FROM {ledger_schema['full_schema']}.action_log "
            f"WHERE task_id = '{task_id}' ORDER BY action_sequence",
            warehouse_id=warehouse_id,
        )

        assert len(rows) == 2
        assert rows[0]["tool_name"] == "execute_sql"
        assert rows[0]["task_id"] == task_id
        assert rows[0]["agent_id"] == "test-agent"
        assert rows[0]["final_decision"] == "executed"

    def test_risk_scores_persisted(self, warehouse_id, ledger_schema):
        """Should persist cp3_risk_score and breakdown."""
        from databricks_tools_core.sql.sql import execute_sql

        session = _build_test_session(num_actions=1)
        task_id = session.task_id

        flush_session_to_delta(
            session,
            catalog=ledger_schema["catalog"],
            schema=ledger_schema["schema"],
            warehouse_id=warehouse_id,
        )

        rows = execute_sql(
            f"SELECT cp3_risk_score, cp3_risk_breakdown FROM "
            f"{ledger_schema['full_schema']}.action_log "
            f"WHERE task_id = '{task_id}'",
            warehouse_id=warehouse_id,
        )

        assert len(rows) == 1
        risk_score = float(rows[0]["cp3_risk_score"])
        assert risk_score == 0.0

    def test_empty_session_skipped(self, warehouse_id, ledger_schema):
        """Should skip flush when there are no actions."""
        session = AgentGuardSession(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="empty-session",
        )
        init_session_file(session.task_id)
        session.complete()

        result = flush_session_to_delta(
            session,
            catalog=ledger_schema["catalog"],
            schema=ledger_schema["schema"],
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "skipped"
        assert result["rows"] == 0

    def test_sql_injection_safe(self, warehouse_id, ledger_schema):
        """Should store malicious-looking text without breaking SQL."""
        from databricks_tools_core.sql.sql import execute_sql

        session = AgentGuardSession(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="injection'; DROP TABLE evil; --",
            agent_id="test-agent",
        )
        init_session_file(session.task_id)

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"sql_query": "SELECT 'O''Brien' AS name"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        action.checkpoint_result = CheckpointResult()
        action.final_decision = "executed"
        action.execution_success = True
        session.record_action(action)
        append_action(session.task_id, action, session)
        session.complete()

        result = flush_session_to_delta(
            session,
            catalog=ledger_schema["catalog"],
            schema=ledger_schema["schema"],
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "success"

        rows = execute_sql(
            f"SELECT session_description FROM {ledger_schema['full_schema']}.action_log "
            f"WHERE task_id = '{session.task_id}'",
            warehouse_id=warehouse_id,
        )
        assert len(rows) == 1
        assert "DROP TABLE evil" in rows[0]["session_description"]


@pytest.mark.integration
class TestAuditLedgerJSONLPersistence:
    """Tests for JSONL hot path."""

    def test_append_action_writes_jsonl(self):
        """Should append one JSON line per action."""
        session = AgentGuardSession(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="jsonl-write-test",
            agent_id="test-agent",
        )
        jsonl_path = init_session_file(session.task_id)

        for i in range(2):
            action = Action.from_tool_call(
                tool_name="execute_sql",
                tool_params={"sql_query": f"SELECT {i}"},
                task_id=session.task_id,
                agent_id="test-agent",
                sequence=session.next_sequence(),
            )
            action.checkpoint_result = CheckpointResult()
            action.final_decision = "executed"
            session.record_action(action)
            append_action(session.task_id, action, session)

        assert jsonl_path.exists()
        lines = [line for line in jsonl_path.read_text().splitlines() if line.strip()]
        assert len(lines) == 2

        row = json.loads(lines[0])
        assert row["tool_name"] == "execute_sql"
        assert row["task_id"] == session.task_id

    def test_delta_failure_preserves_jsonl(self, monkeypatch):
        """Should keep JSONL when Delta write fails."""
        session = AgentGuardSession(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="delta-failure-test",
            agent_id="test-agent",
        )
        jsonl_path = init_session_file(session.task_id)

        for i in range(2):
            action = Action.from_tool_call(
                tool_name="execute_sql",
                tool_params={"sql_query": f"SELECT {i}"},
                task_id=session.task_id,
                agent_id="test-agent",
                sequence=session.next_sequence(),
            )
            action.checkpoint_result = CheckpointResult()
            action.final_decision = "executed"
            session.record_action(action)
            append_action(session.task_id, action, session)

        session.complete()

        def _failing_write(*args, **kwargs):
            raise ConnectionError("Simulated Delta failure")

        monkeypatch.setattr(
            "databricks_tools_core.agentguard.ledger._write_to_delta",
            _failing_write,
        )

        result = flush_session_to_delta(session)

        assert result["status"] == "pending"
        assert result["rows"] == 2
        assert result["method"] == "local_jsonl"
        assert jsonl_path.exists(), "JSONL should be preserved when Delta fails"
