"""
Integration tests for AgentGuard scope enforcement.

Tests:
- templates, in/out of scope, default_deny, limits, monitor mode
"""

import pytest

from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    AgentGuardMode,
    CheckpointDecision,
)
from databricks_tools_core.agentguard.scope import (
    ScopeManifest,
    ResourceScope,
    check_scope,
    check_scope_limits,
    list_templates,
    load_template,
)


@pytest.mark.integration
class TestScopeTemplateLoading:
    """Tests for loading scope templates."""

    def test_list_templates_returns_known_templates(self):
        templates = list_templates()
        assert "etl_pipeline_fix" in templates
        assert "data_quality_check" in templates
        assert "model_deployment" in templates

    def test_load_etl_template_with_variables(self):
        scope = load_template(
            "etl_pipeline_fix",
            {
                "catalog": "main",
                "target_table": "customer_orders",
            },
        )

        assert isinstance(scope, ScopeManifest)
        assert scope.default_deny is True
        assert scope.max_actions is not None
        assert scope.max_write_actions is not None

        assert any("customer_orders" in p for p in scope.tables.read)

    def test_load_data_quality_template(self):
        scope = load_template(
            "data_quality_check",
            {
                "catalog": "main",
                "schema": "production",
                "target_table": "customer_orders",
            },
        )

        assert isinstance(scope, ScopeManifest)
        assert scope.default_deny is True

    def test_load_model_deployment_template(self):
        scope = load_template(
            "model_deployment",
            {
                "catalog": "ml_catalog",
                "endpoint_name": "fraud_detection_v2",
            },
        )

        assert isinstance(scope, ScopeManifest)

    def test_missing_variables_raises(self):
        with pytest.raises(ValueError, match="unresolved variables"):
            load_template("etl_pipeline_fix", {})

    def test_unknown_template_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_template("nonexistent_template_xyz", {})


@pytest.mark.integration
class TestScopeMatchingInScope:
    """Tests for actions inside the declared scope."""

    @pytest.fixture
    def etl_scope(self):
        return load_template(
            "etl_pipeline_fix",
            {
                "catalog": "main",
                "target_table": "customer_orders",
            },
        )

    def test_read_allowed_table_in_scope(self, etl_scope):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.production.customer_orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        action.target_resource_id = "main.production.customer_orders"
        action.action_category = ActionCategory.READ

        decision, violation = check_scope(action, etl_scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE
        assert violation is None


@pytest.mark.integration
class TestScopeMatchingOutOfScope:
    """Tests for actions outside the declared scope."""

    @pytest.fixture
    def strict_scope(self):
        return ScopeManifest(
            tables=ResourceScope(
                read=["main.analytics.orders"],
                write=["main.staging.temp_*"],
            ),
            default_deny=True,
            max_actions=50,
            max_write_actions=10,
        )

    def test_read_pii_table_blocked(self, strict_scope):
        """Should block reads outside allowed table patterns."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.analytics.customer_pii_data"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        action.target_resource_id = "main.analytics.customer_pii_data"
        action.action_category = ActionCategory.READ

        decision, violation = check_scope(action, strict_scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK
        assert "not in scope" in violation

    def test_write_to_non_matching_table_blocked(self, strict_scope):
        """Should block writes that do not match write patterns."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO main.production.billing VALUES (1)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        action.target_resource_id = "main.production.billing"
        action.action_category = ActionCategory.WRITE

        decision, violation = check_scope(action, strict_scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK

    def test_write_to_matching_table_allowed(self, strict_scope):
        """Should allow writes matching temp_* under staging."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO main.staging.temp_results VALUES (1)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        action.target_resource_id = "main.staging.temp_results"
        action.action_category = ActionCategory.WRITE

        decision, _ = check_scope(action, strict_scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_create_unrelated_job_blocked(self, strict_scope):
        """Should pass or block job create depending on whether jobs are in scope."""
        action = Action.from_tool_call(
            tool_name="manage_jobs",
            tool_params={"action": "create", "name": "unrelated-etl-job"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = check_scope(action, strict_scope, AgentGuardMode.ENFORCE)
        assert decision in (CheckpointDecision.AUTO_APPROVE, CheckpointDecision.BLOCK)


@pytest.mark.integration
class TestScopeMonitorMode:
    """Tests for scope decisions in MONITOR_ONLY."""

    def test_out_of_scope_would_block_in_monitor(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.allowed.*"]),
            default_deny=True,
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.forbidden.secrets"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        action.target_resource_id = "main.forbidden.secrets"
        action.action_category = ActionCategory.READ

        decision, violation = check_scope(action, scope, AgentGuardMode.MONITOR_ONLY)
        assert decision == CheckpointDecision.WOULD_BLOCK
        assert "[monitor]" in violation


@pytest.mark.integration
class TestDefaultDenyBehavior:
    """Tests for default_deny on table scope."""

    def test_default_deny_false_allows_unspecified(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.analytics.*"]),
            default_deny=False,
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO main.analytics.temp VALUES (1)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        action.target_resource_id = "main.analytics.temp"
        action.action_category = ActionCategory.WRITE

        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_default_deny_true_blocks_unspecified(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.analytics.*"]),
            default_deny=True,
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO main.analytics.temp VALUES (1)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )
        action.target_resource_id = "main.analytics.temp"
        action.action_category = ActionCategory.WRITE

        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK


@pytest.mark.integration
class TestScopeLimits:
    """Tests for max_actions and max_write_actions."""

    def test_max_actions_exceeded(self):
        scope = ScopeManifest(max_actions=5, max_write_actions=3)

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT 1"},
            task_id="t1",
            agent_id="a1",
            sequence=6,
        )

        decision, violation = check_scope_limits(
            action,
            scope,
            session_action_count=5,
            session_write_count=0,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.BLOCK
        assert "max_actions" in violation

    def test_max_write_actions_exceeded(self):
        scope = ScopeManifest(max_actions=100, max_write_actions=3)

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO test VALUES (1)"},
            task_id="t1",
            agent_id="a1",
            sequence=4,
        )

        decision, violation = check_scope_limits(
            action,
            scope,
            session_action_count=10,
            session_write_count=3,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.BLOCK
        assert "max_write_actions" in violation

    def test_within_limits_passes(self):
        scope = ScopeManifest(max_actions=100, max_write_actions=20)

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT 1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        decision, _ = check_scope_limits(
            action,
            scope,
            session_action_count=5,
            session_write_count=2,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.AUTO_APPROVE
