"""
Unit tests for AgentGuard scope enforcement and templates.

Tests:
- check_scope, check_scope_limits, load_template, list_templates
"""

import pytest
from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    AgentGuardMode,
    CheckpointDecision,
)
from databricks_tools_core.agentguard.scope import (
    ResourceScope,
    ScopeManifest,
    check_scope,
    check_scope_limits,
    list_templates,
    load_template,
)


class TestCheckScopeInScope:
    def test_exact_match(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.production.orders"]),
        )
        action = Action(
            tool_name="execute_sql",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_type="sql",
            target_resource_id="main.production.orders",
        )
        decision, violation = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE
        assert violation is None

    def test_glob_pattern_match(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.staging.*"]),
        )
        action = Action(
            tool_name="execute_sql",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_type="sql",
            target_resource_id="main.staging.temp_orders",
        )
        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_case_insensitive_matching(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["Main.Production.Orders"]),
        )
        action = Action(
            tool_name="execute_sql",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_type="sql",
            target_resource_id="main.production.orders",
        )
        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE


class TestCheckScopeOutOfScope:
    def test_no_matching_pattern(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.staging.*"]),
        )
        action = Action(
            tool_name="execute_sql",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_type="sql",
            target_resource_id="main.production.billing",
        )
        decision, violation = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK
        assert "billing" in violation
        assert "not in scope" in violation

    def test_out_of_scope_monitor_mode(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.staging.*"]),
        )
        action = Action(
            tool_name="execute_sql",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_type="sql",
            target_resource_id="main.production.billing",
        )
        decision, violation = check_scope(action, scope, AgentGuardMode.MONITOR_ONLY)
        assert decision == CheckpointDecision.WOULD_BLOCK
        assert "[monitor]" in violation

    def test_write_to_read_only_scope(self):
        scope = ScopeManifest(
            tables=ResourceScope(
                read=["main.production.*"],
                write=["main.staging.temp_*"],
            ),
        )
        action = Action(
            tool_name="execute_sql",
            operation="INSERT",
            action_category=ActionCategory.WRITE,
            target_resource_type="sql",
            target_resource_id="main.production.orders",
        )
        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK


class TestDefaultDeny:
    def test_empty_patterns_allowed_when_default_deny_false(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.*"]),
            default_deny=False,
        )
        action = Action(
            tool_name="execute_sql",
            operation="INSERT",
            action_category=ActionCategory.WRITE,
            target_resource_type="sql",
            target_resource_id="main.staging.t",
        )
        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_empty_patterns_blocked_when_default_deny_true(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.*"]),
            default_deny=True,
        )
        action = Action(
            tool_name="execute_sql",
            operation="INSERT",
            action_category=ActionCategory.WRITE,
            target_resource_type="sql",
            target_resource_id="main.staging.t",
        )
        decision, violation = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.BLOCK
        assert "default_deny" in violation

    def test_default_deny_passes_for_completely_unscoped_resource(self):
        """Should not apply default_deny when the resource type has no scope patterns."""
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.*"]),
            default_deny=True,
        )
        action = Action(
            tool_name="delete_app",
            operation="DELETE_APP",
            action_category=ActionCategory.ADMIN,
            target_resource_type="app",
            target_resource_id="my-app",
        )
        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_default_deny_monitor_mode(self):
        scope = ScopeManifest(
            tables=ResourceScope(read=["main.*"]),
            default_deny=True,
        )
        action = Action(
            tool_name="execute_sql",
            operation="INSERT",
            action_category=ActionCategory.WRITE,
            target_resource_type="sql",
            target_resource_id="main.staging.t",
        )
        decision, violation = check_scope(action, scope, AgentGuardMode.MONITOR_ONLY)
        assert decision == CheckpointDecision.WOULD_BLOCK
        assert "[monitor]" in violation


class TestScopePassthrough:
    def test_no_resource_id_passes(self):
        scope = ScopeManifest(tables=ResourceScope(read=["main.*"]))
        action = Action(
            tool_name="execute_sql",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_type="sql",
            target_resource_id="",
        )
        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_unknown_resource_type_passes(self):
        scope = ScopeManifest(tables=ResourceScope(read=["main.*"]))
        action = Action(
            tool_name="t",
            operation="SOMETHING",
            action_category=ActionCategory.UNKNOWN,
            target_resource_type="alien_resource",
            target_resource_id="x",
        )
        decision, _ = check_scope(action, scope, AgentGuardMode.ENFORCE)
        assert decision == CheckpointDecision.AUTO_APPROVE


class TestScopeLimits:
    def test_max_actions_exceeded(self):
        scope = ScopeManifest(max_actions=10)
        action = Action(tool_name="t", action_category=ActionCategory.READ)
        decision, violation = check_scope_limits(
            action,
            scope,
            session_action_count=10,
            session_write_count=0,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.BLOCK
        assert "max_actions" in violation

    def test_max_actions_not_exceeded(self):
        scope = ScopeManifest(max_actions=10)
        action = Action(tool_name="t", action_category=ActionCategory.READ)
        decision, _ = check_scope_limits(
            action,
            scope,
            session_action_count=5,
            session_write_count=0,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_max_write_actions_exceeded(self):
        scope = ScopeManifest(max_write_actions=5)
        action = Action(tool_name="t", action_category=ActionCategory.WRITE)
        decision, violation = check_scope_limits(
            action,
            scope,
            session_action_count=20,
            session_write_count=5,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.BLOCK
        assert "max_write_actions" in violation

    def test_max_write_actions_only_checks_writes(self):
        scope = ScopeManifest(max_write_actions=5)
        action = Action(tool_name="t", action_category=ActionCategory.READ)
        decision, _ = check_scope_limits(
            action,
            scope,
            session_action_count=100,
            session_write_count=10,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.AUTO_APPROVE

    def test_limits_in_monitor_mode(self):
        scope = ScopeManifest(max_actions=5)
        action = Action(tool_name="t", action_category=ActionCategory.READ)
        decision, violation = check_scope_limits(
            action,
            scope,
            session_action_count=5,
            session_write_count=0,
            mode=AgentGuardMode.MONITOR_ONLY,
        )
        assert decision == CheckpointDecision.WOULD_BLOCK
        assert "[monitor]" in violation

    def test_no_limits_passes(self):
        scope = ScopeManifest()
        action = Action(tool_name="t", action_category=ActionCategory.WRITE)
        decision, _ = check_scope_limits(
            action,
            scope,
            session_action_count=9999,
            session_write_count=9999,
            mode=AgentGuardMode.ENFORCE,
        )
        assert decision == CheckpointDecision.AUTO_APPROVE


class TestTemplates:
    def test_list_templates_returns_available(self):
        templates = list_templates()
        assert "etl_pipeline_fix" in templates
        assert "data_quality_check" in templates
        assert "model_deployment" in templates

    def test_load_etl_template(self):
        scope = load_template(
            "etl_pipeline_fix",
            {
                "catalog": "main",
                "target_table": "customer_orders",
            },
        )
        assert isinstance(scope, ScopeManifest)
        assert scope.default_deny is True
        assert "main.production.customer_orders" in scope.tables.read
        assert "main.staging.temp_*" in scope.tables.write
        assert scope.max_actions == 100

    def test_load_data_quality_template(self):
        scope = load_template(
            "data_quality_check",
            {
                "catalog": "main",
                "schema": "production",
                "target_table": "orders",
            },
        )
        assert scope.default_deny is True
        assert "main.production.orders" in scope.tables.read
        assert "main.dq_results.*" in scope.tables.write

    def test_load_model_deployment_template(self):
        scope = load_template(
            "model_deployment",
            {
                "catalog": "main",
                "endpoint_name": "fraud_v2",
            },
        )
        assert scope.default_deny is True
        assert "fraud_v2" in scope.serving_endpoints.write
        assert scope.tables.write == []

    def test_load_nonexistent_template_raises(self):
        with pytest.raises(FileNotFoundError, match="not found"):
            load_template("does_not_exist", {})

    def test_load_template_missing_variable_raises(self):
        with pytest.raises(ValueError, match="unresolved variables"):
            load_template("etl_pipeline_fix", {"catalog": "main"})
