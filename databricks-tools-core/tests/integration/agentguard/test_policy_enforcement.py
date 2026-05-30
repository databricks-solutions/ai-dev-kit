"""
Integration tests for AgentGuard policy enforcement.

Tests:
- destructive SQL, grants/revokes, deletions, monitor vs enforce, multi-SQL
- Action.from_tool_call and real MCP parameter names
"""

import pytest

from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    AgentGuardMode,
    CheckpointDecision,
)
from databricks_tools_core.agentguard.policy import PolicyEngine


@pytest.mark.integration
class TestDestructiveSQLBlocked:
    """Tests for blocking or flagging dangerous SQL."""

    def test_drop_database_blocked(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP DATABASE analytics_prod"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, rule = policy_engine.check(action, AgentGuardMode.ENFORCE)

        assert decision == CheckpointDecision.BLOCK
        assert rule is not None
        assert "blocked" in rule.lower()

    def test_drop_schema_blocked(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP SCHEMA main.customer_data"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_truncate_table_blocked(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "TRUNCATE TABLE main.billing.records"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_drop_table_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP TABLE main.analytics.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, rule = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert "approval" in rule.lower()

    def test_delete_from_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DELETE FROM main.warehouse.users WHERE id = 5"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_create_or_replace_table_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "CREATE OR REPLACE TABLE main.staging.temp AS SELECT 1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_drop_table_if_exists_still_caught(self, policy_engine):
        """Should flag DROP TABLE after IF EXISTS is stripped."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP TABLE IF EXISTS main.analytics.temp"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG


@pytest.mark.integration
class TestPrivilegeEscalationCaught:
    """Tests for grant/revoke policy behavior."""

    def test_grant_all_privileges_blocked(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "GRANT ALL PRIVILEGES ON CATALOG main TO `agent-sp`"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_revoke_blocked(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "REVOKE ALL ON main.prod.customers FROM analyst"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_narrow_grant_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "GRANT SELECT ON main.analytics.table TO analyst"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_uc_grants_tool_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="manage_uc_grants",
            tool_params={"action": "grant", "privilege": "SELECT", "principal": "user@test.com"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG


@pytest.mark.integration
class TestResourceDeletionCaught:
    """Tests for non-SQL destructive tools."""

    def test_delete_app_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="delete_app",
            tool_params={"name": "my-production-app"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert action.operation == "DELETE_APP"

    def test_delete_pipeline_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="delete_pipeline",
            tool_params={"pipeline_id": "abc-123"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_delete_volume_file_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="delete_volume_file",
            tool_params={"volume_path": "/Volumes/main/data/configs/rules.json"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert action.target_resource_id == "/Volumes/main/data/configs/rules.json"

    def test_delete_tracked_resource_job_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="delete_tracked_resource",
            tool_params={"type": "job", "resource_id": "job-42"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert action.operation == "DELETE_JOB"

    def test_manage_jobs_delete_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="manage_jobs",
            tool_params={"action": "delete", "job_id": "12345"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert action.operation == "DELETE_JOB"

    def test_code_execution_flagged(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_databricks_command",
            tool_params={"cluster_id": "0123-abc", "code": "print('hello')"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG
        assert action.operation == "EXECUTE_CODE"


@pytest.mark.integration
class TestMonitorModeNeverBlocks:
    """Tests for MONITOR_ONLY policy decisions."""

    def test_drop_database_would_block(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP DATABASE production_db"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.MONITOR_ONLY)
        assert decision == CheckpointDecision.WOULD_BLOCK

    def test_truncate_would_block(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "TRUNCATE TABLE important_data"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.MONITOR_ONLY)
        assert decision == CheckpointDecision.WOULD_BLOCK

    def test_delete_app_would_block(self, policy_engine):
        """Should record FLAG or WOULD_BLOCK for delete_app in monitor mode."""
        action = Action.from_tool_call(
            tool_name="delete_app",
            tool_params={"name": "my-app"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.MONITOR_ONLY)
        assert decision in (CheckpointDecision.FLAG, CheckpointDecision.WOULD_BLOCK)


@pytest.mark.integration
class TestSafeOperationsAllowed:
    """Tests for operations that policy auto-approves."""

    def test_select_auto_approved(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.analytics.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_insert_auto_approved(self, policy_engine):
        """Should auto-approve INSERT statements."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO staging.temp VALUES (1, 'test')"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_read_only_tools_auto_approved(self, policy_engine):
        for tool in ("list_clusters", "get_app", "list_warehouses", "get_current_user"):
            action = Action.from_tool_call(
                tool_name=tool,
                tool_params={},
                task_id="t1",
                agent_id="a1",
                sequence=1,
            )
            decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
            assert decision == CheckpointDecision.AUTO_APPROVE, f"{tool} should be auto-approved"


@pytest.mark.integration
class TestMultiSQLBypassPrevention:
    """Tests for execute_sql_multi policy coverage."""

    def test_hidden_drop_in_multi_sql(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={
                "sqls": [
                    "SELECT * FROM orders",
                    "DROP TABLE main.analytics.orders",
                ]
            },
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_hidden_truncate_in_multi_sql(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={
                "sqls": [
                    "SELECT count(*) FROM billing",
                    "TRUNCATE TABLE main.billing.records",
                    "SELECT 1",
                ]
            },
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK


@pytest.mark.integration
class TestActionClassificationAccuracy:
    """Tests for Action.from_tool_call classifications."""

    def test_sql_select_classified_as_read(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM test_table"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.READ
        assert action.operation == "SELECT"

    def test_sql_drop_classified_as_ddl(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP TABLE main.staging.temp"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DDL
        assert action.operation == "DROP"

    def test_delete_app_classified_as_admin(self):
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

    def test_start_cluster_classified_as_write(self):
        action = Action.from_tool_call(
            tool_name="start_cluster",
            tool_params={"cluster_id": "0123-abc"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.WRITE
        assert action.operation == "START_CLUSTER"

    def test_grant_sql_classified_as_dcl(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "GRANT SELECT ON TABLE main.data.t TO user@test.com"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DCL
        assert action.operation == "GRANT"

    def test_execute_code_classified_as_admin(self):
        action = Action.from_tool_call(
            tool_name="execute_databricks_command",
            tool_params={"cluster_id": "abc", "code": "print(1)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.ADMIN
        assert action.operation == "EXECUTE_CODE"
        assert action.target_resource_type == "code_execution"

    def test_publish_dashboard_classified_as_write(self):
        action = Action.from_tool_call(
            tool_name="publish_dashboard",
            tool_params={"dashboard_id": "dash-42", "publish": True},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.WRITE
        assert action.operation == "PUBLISH"
        assert action.target_resource_id == "dash-42"

    def test_delete_lakebase_sync_has_resource_id(self):
        action = Action.from_tool_call(
            tool_name="delete_lakebase_sync",
            tool_params={"table_name": "my_sync_table"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.operation == "DELETE_LAKEBASE_SYNC"
        assert action.target_resource_id == "my_sync_table"


@pytest.mark.integration
class TestRealMCPParamNames:
    """Tests for MCP-style parameter names on from_tool_call."""

    def test_sql_query_param_classified_correctly(self, policy_engine):
        """Should parse sql_query like execute_sql from MCP."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"sql_query": "DROP TABLE main.analytics.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DDL
        assert action.operation == "DROP"
        assert action.sql_statement == "DROP TABLE main.analytics.orders"

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_sql_query_select_classified_as_read(self, policy_engine):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"sql_query": "SELECT * FROM main.db.table LIMIT 10"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.READ
        assert action.operation == "SELECT"

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_sql_content_multi_classified_correctly(self, policy_engine):
        """Should parse sql_content for execute_sql_multi."""
        action = Action.from_tool_call(
            tool_name="execute_sql_multi",
            tool_params={"sql_content": "SELECT 1; DROP TABLE main.analytics.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.action_category == ActionCategory.DDL
        assert "DROP" in action.sql_statement

        decision, _ = policy_engine.check(action, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.FLAG

    def test_genie_space_id_extracted(self):
        """Should read space_id for delete_genie."""
        action = Action.from_tool_call(
            tool_name="delete_genie",
            tool_params={"space_id": "genie-abc-123"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.target_resource_id == "genie-abc-123"

    def test_display_name_extracted(self):
        """Should use display_name for dashboard create tools."""
        action = Action.from_tool_call(
            tool_name="create_or_update_dashboard",
            tool_params={"display_name": "Revenue Dashboard", "parent_path": "/"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.target_resource_id == "Revenue Dashboard"

    def test_full_name_extracted(self):
        """Should use full_name for manage_uc_grants."""
        action = Action.from_tool_call(
            tool_name="manage_uc_grants",
            tool_params={"action": "grant", "full_name": "main.prod.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.target_resource_id == "main.prod.orders"

    def test_cluster_id_extracted(self):
        """Should use cluster_id for start_cluster."""
        action = Action.from_tool_call(
            tool_name="start_cluster",
            tool_params={"cluster_id": "0123-abc-xyz"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        assert action.target_resource_id == "0123-abc-xyz"
