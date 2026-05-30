"""
Unit tests for AgentGuard core models.

Tests:
- Action.from_tool_call (SQL, read-only, delete, action-based, writes, fallback)
- CheckpointResult, AgentGuardSession
"""

import pytest
from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    AgentGuardMode,
    AgentGuardSession,
    CheckpointDecision,
    CheckpointResult,
    SessionStatus,
)


class TestActionSQL:
    def test_execute_sql_select(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.prod.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.READ
        assert action.operation == "SELECT"
        assert action.target_resource_type == "sql"
        assert action.sql_statement == "SELECT * FROM main.prod.orders"

    def test_execute_sql_insert(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO staging.t VALUES (1)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.WRITE
        assert action.operation == "INSERT"

    def test_execute_sql_drop(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP TABLE main.prod.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DDL
        assert action.operation == "DROP"

    def test_execute_sql_grant(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "GRANT SELECT ON TABLE main.t TO user1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DCL
        assert action.operation == "GRANT"

    def test_execute_sql_empty_query(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": ""},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.READ
        assert action.operation == "SQL_EMPTY"

    def test_execute_sql_multi_batch(self):
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={"sqls": ["SELECT 1", "DROP TABLE t"]},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DDL
        assert action.operation == "MULTI(DROP)"
        assert "SELECT 1; DROP TABLE t" in action.sql_statement

    def test_execute_sql_multi_empty(self):
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={"sqls": []},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.READ
        assert action.operation == "SQL_MULTI_EMPTY"


class TestActionReadOnly:
    @pytest.mark.parametrize(
        "tool_name",
        [
            "get_table_details",
            "list_warehouses",
            "get_best_warehouse",
            "list_clusters",
            "get_cluster_status",
            "get_app",
            "get_dashboard",
            "get_current_user",
            "list_volume_files",
        ],
    )
    def test_read_only_tools(self, tool_name):
        action = Action.from_tool_call(
            tool_name=tool_name,
            tool_params={},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.READ
        assert action.operation == "READ"


class TestActionDelete:
    def test_delete_app(self):
        action = Action.from_tool_call(
            tool_name="delete_app",
            tool_params={"name": "my-app"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.ADMIN
        assert action.operation == "DELETE_APP"
        assert action.target_resource_type == "app"
        assert action.target_resource_id == "my-app"

    def test_delete_pipeline(self):
        action = Action.from_tool_call(
            tool_name="delete_pipeline",
            tool_params={"pipeline_id": "p-123"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.ADMIN
        assert action.operation == "DELETE_PIPELINE"
        assert action.target_resource_id == "p-123"

    def test_delete_volume_file(self):
        action = Action.from_tool_call(
            tool_name="delete_volume_file",
            tool_params={"volume_path": "/Volumes/cat/sch/vol/file.csv"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.ADMIN
        assert action.operation == "DELETE_FILE"
        assert action.target_resource_id == "/Volumes/cat/sch/vol/file.csv"

    def test_delete_tracked_resource_dynamic_type(self):
        action = Action.from_tool_call(
            tool_name="delete_tracked_resource",
            tool_params={"type": "job", "resource_id": "j-456"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.ADMIN
        assert action.operation == "DELETE_JOB"
        assert action.target_resource_type == "job"
        assert action.target_resource_id == "j-456"


class TestActionBased:
    def test_manage_jobs_create(self):
        action = Action.from_tool_call(
            tool_name="manage_jobs",
            tool_params={"action": "create", "name": "etl-daily"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.WRITE
        assert action.operation == "CREATE"
        assert action.target_resource_type == "job"

    def test_manage_jobs_delete(self):
        action = Action.from_tool_call(
            tool_name="manage_jobs",
            tool_params={"action": "delete", "job_id": "j-1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.ADMIN
        assert action.operation == "DELETE_JOB"

    def test_manage_jobs_get(self):
        action = Action.from_tool_call(
            tool_name="manage_jobs",
            tool_params={"action": "get", "job_id": "j-1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.READ
        assert action.operation == "GET"

    def test_manage_uc_grants_grant(self):
        action = Action.from_tool_call(
            tool_name="manage_uc_grants",
            tool_params={"action": "grant", "name": "main.prod"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DCL
        assert action.operation == "GRANT"


class TestActionStandaloneWrite:
    def test_start_cluster(self):
        action = Action.from_tool_call(
            tool_name="start_cluster",
            tool_params={"name": "my-cluster"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.WRITE
        assert action.operation == "START_CLUSTER"

    def test_upload_file(self):
        action = Action.from_tool_call(
            tool_name="upload_file",
            tool_params={"name": "data.csv"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.WRITE
        assert action.operation == "UPLOAD"

    def test_execute_databricks_command(self):
        action = Action.from_tool_call(
            tool_name="execute_databricks_command",
            tool_params={"cluster_id": "c-123"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.ADMIN
        assert action.operation == "EXECUTE_CODE"
        assert action.target_resource_type == "code_execution"
        assert action.target_resource_id == "c-123"


class TestActionFallback:
    def test_unknown_tool(self):
        action = Action.from_tool_call(
            tool_name="some_new_tool_not_mapped",
            tool_params={},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.UNKNOWN
        assert action.operation == "SOME_NEW_TOOL_NOT_MAPPED"


class TestCheckpointResult:
    def test_blocked_only_on_block(self):
        assert CheckpointResult(decision=CheckpointDecision.BLOCK).blocked is True

    def test_not_blocked_on_would_block(self):
        assert CheckpointResult(decision=CheckpointDecision.WOULD_BLOCK).blocked is False

    def test_not_blocked_on_flag(self):
        assert CheckpointResult(decision=CheckpointDecision.FLAG).blocked is False

    def test_not_blocked_on_auto_approve(self):
        assert CheckpointResult(decision=CheckpointDecision.AUTO_APPROVE).blocked is False

    def test_total_overhead(self):
        from databricks_tools_core.agentguard.models import TimingRecord

        result = CheckpointResult(
            timings=[
                TimingRecord(name="cp1", duration_ms=1.5),
                TimingRecord(name="cp2", duration_ms=2.3),
            ]
        )
        assert abs(result.total_overhead_ms - 3.8) < 0.01


class TestSession:
    def test_sequence_counter(self):
        session = AgentGuardSession()
        assert session.next_sequence() == 1
        assert session.next_sequence() == 2
        assert session.next_sequence() == 3

    def test_action_count(self):
        session = AgentGuardSession()
        assert session.action_count == 0
        action = Action(tool_name="test")
        session.record_action(action)
        assert session.action_count == 1

    def test_write_count_incremented_for_writes(self):
        session = AgentGuardSession()
        read_action = Action(tool_name="t", action_category=ActionCategory.READ)
        write_action = Action(tool_name="t", action_category=ActionCategory.WRITE)
        ddl_action = Action(tool_name="t", action_category=ActionCategory.DDL)
        admin_action = Action(tool_name="t", action_category=ActionCategory.ADMIN)

        session.record_action(read_action)
        assert session.write_count == 0

        session.record_action(write_action)
        assert session.write_count == 1

        session.record_action(ddl_action)
        assert session.write_count == 2

        session.record_action(admin_action)
        assert session.write_count == 3

    def test_risk_score_tracking(self):
        session = AgentGuardSession()
        a1 = Action(tool_name="t", checkpoint_result=CheckpointResult(risk_score=30.0))
        a2 = Action(tool_name="t", checkpoint_result=CheckpointResult(risk_score=70.0))

        session.record_action(a1)
        session.record_action(a2)

        assert session.total_risk_score == 100.0
        assert session.max_risk_score == 70.0
        assert session.avg_risk_score == 50.0

    def test_blocked_count(self):
        session = AgentGuardSession()
        blocked = Action(
            tool_name="t",
            checkpoint_result=CheckpointResult(decision=CheckpointDecision.BLOCK),
        )
        session.record_action(blocked)
        assert session.blocked_count == 1
        assert session.would_block_count == 0

    def test_would_block_count(self):
        session = AgentGuardSession()
        wb = Action(
            tool_name="t",
            checkpoint_result=CheckpointResult(decision=CheckpointDecision.WOULD_BLOCK),
        )
        session.record_action(wb)
        assert session.would_block_count == 1
        assert session.blocked_count == 0

    def test_complete(self):
        session = AgentGuardSession()
        assert session.status == SessionStatus.ACTIVE
        assert session.completed_at is None

        session.complete()
        assert session.status == SessionStatus.COMPLETED
        assert session.completed_at is not None

    def test_summary_contains_key_info(self):
        session = AgentGuardSession(mode=AgentGuardMode.MONITOR_ONLY)
        summary = session.summary()
        assert "monitor-only" in summary
        assert session.task_id in summary
        assert "Actions: 0" in summary

    def test_avg_risk_score_zero_division(self):
        session = AgentGuardSession()
        assert session.avg_risk_score == 0.0
