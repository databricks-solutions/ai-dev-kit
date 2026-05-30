"""
Unit tests for AgentGuard policy engine.

Tests:
- always-block, require-approval, auto-approve rules
- execute_sql_multi splitting
"""

import pytest
from databricks_tools_core.agentguard.models import (
    Action,
    AgentGuardMode,
    CheckpointDecision,
)
from databricks_tools_core.agentguard.policy import PolicyEngine


@pytest.fixture
def engine():
    """Returns a fresh PolicyEngine instance."""
    return PolicyEngine()


class TestAlwaysBlock:
    def test_drop_database_blocked_in_enforce(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP DATABASE my_catalog"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, rule = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK
        assert rule is not None

    def test_drop_database_would_block_in_monitor(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP DATABASE my_catalog"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, rule = engine.check(action, AgentGuardMode.MONITOR_ONLY)
        assert decision == CheckpointDecision.WOULD_BLOCK
        assert rule is not None

    def test_truncate_any_table_blocked(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "TRUNCATE TABLE main.analytics.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_grant_all_privileges_blocked(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "GRANT ALL PRIVILEGES ON TABLE t TO user1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_revoke_from_blocked(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "REVOKE SELECT ON TABLE t FROM user1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_drop_any_schema_blocked(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP SCHEMA main.analytics"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_if_exists_noise_stripped(self, engine):
        """Should block DROP SCHEMA after IF EXISTS is stripped from the statement."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP SCHEMA IF EXISTS main.temp_schema"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK


class TestRequireApproval:
    def test_drop_any_table_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP TABLE main.analytics.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, rule = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert rule is not None

    def test_delete_from_any_table_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DELETE FROM main.staging.temp WHERE id = 1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_create_or_replace_table_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "CREATE OR REPLACE TABLE main.staging.temp AS SELECT 1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_delete_app_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="delete_app",
            tool_params={"name": "my-app"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, rule = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert rule is not None

    def test_delete_pipeline_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="delete_pipeline",
            tool_params={"pipeline_id": "p-1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_execute_code_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_databricks_command",
            tool_params={"cluster_id": "c-1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_grant_via_manage_uc_grants_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="manage_uc_grants",
            tool_params={"action": "grant", "name": "main.prod"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_delete_job_via_manage_jobs_flagged(self, engine):
        action = Action.from_tool_call(
            tool_name="manage_jobs",
            tool_params={"action": "delete", "job_id": "j-1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG


class TestAutoApprove:
    def test_select_approved(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.prod.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, rule = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE
        assert rule is None

    def test_read_only_tool_approved(self, engine):
        action = Action.from_tool_call(
            tool_name="get_table_details",
            tool_params={},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_insert_not_blocked(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO staging.t VALUES (1)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE


class TestMultiSQL:
    def test_multi_sql_with_block_statement(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={"sqls": ["SELECT 1", "DROP DATABASE my_catalog"]},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_multi_sql_with_flag_statement(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={"sqls": ["SELECT 1", "DROP TABLE main.analytics.orders"]},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_multi_sql_safe_statements_approved(self, engine):
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={"sqls": ["SELECT 1", "INSERT INTO main.staging.t VALUES (1)"]},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        decision, _ = engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE
