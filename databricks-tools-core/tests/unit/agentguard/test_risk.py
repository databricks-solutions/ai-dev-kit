"""
Unit tests for AgentGuard risk scoring.

Tests:
- per-factor scores and compute_risk_score
"""

from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    CheckpointDecision,
)
from databricks_tools_core.agentguard.risk import (
    _score_action_type,
    _score_blast_radius,
    _score_data_sensitivity,
    _score_environment,
    compute_risk_score,
)


class TestActionTypeScoring:
    def test_select_is_zero(self):
        action = Action(tool_name="t", operation="SELECT", action_category=ActionCategory.READ)
        assert _score_action_type(action) == 0

    def test_delete_is_high(self):
        action = Action(tool_name="t", operation="DELETE", action_category=ActionCategory.WRITE)
        assert _score_action_type(action) == 80

    def test_drop_is_very_high(self):
        action = Action(tool_name="t", operation="DROP", action_category=ActionCategory.DDL)
        assert _score_action_type(action) == 95

    def test_delete_app_uses_prefix_rule(self):
        action = Action(tool_name="t", operation="DELETE_APP", action_category=ActionCategory.ADMIN)
        assert _score_action_type(action) == 80

    def test_restart_not_confused_with_start(self):
        """Should score RESTART_PIPELINE using the RESTART keyword, not START."""
        action = Action(tool_name="t", operation="RESTART_PIPELINE", action_category=ActionCategory.ADMIN)
        score = _score_action_type(action)
        assert score == 40, f"Expected RESTART score (40), got {score}"

    def test_start_cluster_exact_match(self):
        action = Action(tool_name="t", operation="START_CLUSTER", action_category=ActionCategory.WRITE)
        assert _score_action_type(action) == 45

    def test_execute_code(self):
        action = Action(tool_name="t", operation="EXECUTE_CODE", action_category=ActionCategory.ADMIN)
        assert _score_action_type(action) == 75

    def test_unknown_falls_to_category_default(self):
        action = Action(tool_name="t", operation="FOOBAR", action_category=ActionCategory.WRITE)
        assert _score_action_type(action) == 40

    def test_multi_operation(self):
        action = Action(tool_name="t", operation="MULTI(DROP)", action_category=ActionCategory.DDL)
        assert _score_action_type(action) == 95


class TestEnvironmentScoring:
    def test_production_high_risk(self):
        action = Action(tool_name="t", target_resource_id="main.production.orders")
        assert _score_environment(action) == 90

    def test_prod_dot_high_risk(self):
        action = Action(tool_name="t", sql_statement="SELECT * FROM prod.billing")
        assert _score_environment(action) == 90

    def test_staging_moderate(self):
        action = Action(tool_name="t", target_resource_id="main.staging.temp")
        assert _score_environment(action) == 40

    def test_dev_low(self):
        action = Action(tool_name="t", target_resource_id="main.dev.scratch")
        assert _score_environment(action) == 10

    def test_no_signal_default(self):
        action = Action(tool_name="t", target_resource_id="my-job-123")
        assert _score_environment(action) == 30


class TestBlastRadiusScoring:
    def test_delete_without_where_high(self):
        action = Action(tool_name="t", sql_statement="DELETE FROM orders", action_category=ActionCategory.WRITE)
        assert _score_blast_radius(action) == 90

    def test_delete_with_where_moderate(self):
        action = Action(
            tool_name="t", sql_statement="DELETE FROM orders WHERE id = 1", action_category=ActionCategory.WRITE
        )
        assert _score_blast_radius(action) == 30

    def test_drop_table_max_blast(self):
        action = Action(tool_name="t", sql_statement="DROP TABLE orders", action_category=ActionCategory.DDL)
        assert _score_blast_radius(action) == 100

    def test_select_low_blast(self):
        action = Action(tool_name="t", sql_statement="SELECT * FROM orders", action_category=ActionCategory.READ)
        assert _score_blast_radius(action) == 10

    def test_rows_affected_scales(self):
        action = Action(tool_name="t", rows_affected=5)
        assert _score_blast_radius(action) == 15

        action_large = Action(tool_name="t", rows_affected=5_000_000)
        assert _score_blast_radius(action_large) == 85


class TestDataSensitivityScoring:
    def test_pii_detected(self):
        action = Action(tool_name="t", target_resource_id="main.prod.customer_pii_data")
        assert _score_data_sensitivity(action) >= 70

    def test_ssn_highest(self):
        action = Action(tool_name="t", sql_statement="SELECT ssn FROM users")
        assert _score_data_sensitivity(action) == 95

    def test_no_sensitive_data(self):
        action = Action(tool_name="t", target_resource_id="main.staging.temp_metrics")
        assert _score_data_sensitivity(action) == 0

    def test_hipaa_in_table_name(self):
        action = Action(tool_name="t", target_resource_id="main.prod.hipaa_records")
        assert _score_data_sensitivity(action) == 90


class TestComputeRiskScore:
    def test_read_operation_low_score(self):
        action = Action(
            tool_name="execute_sql",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_id="main.dev.scratch",
            sql_statement="SELECT * FROM main.dev.scratch",
        )
        risk = compute_risk_score(action)
        assert risk.score < 35
        assert risk.decision == CheckpointDecision.AUTO_APPROVE

    def test_drop_prod_table_high_score(self):
        action = Action(
            tool_name="execute_sql",
            operation="DROP",
            action_category=ActionCategory.DDL,
            target_resource_id="main.production.orders",
            sql_statement="DROP TABLE main.production.orders",
        )
        risk = compute_risk_score(action)
        assert risk.score >= 70
        assert risk.decision in (
            CheckpointDecision.HOLD_FOR_APPROVAL,
            CheckpointDecision.BLOCK,
        )

    def test_scope_violation_adds_penalty(self):
        action = Action(
            tool_name="execute_sql",
            operation="INSERT",
            action_category=ActionCategory.WRITE,
            sql_statement="INSERT INTO staging.t VALUES (1)",
        )
        score_no_violation = compute_risk_score(action, scope_violated=False)
        score_with_violation = compute_risk_score(action, scope_violated=True)
        assert score_with_violation.score == score_no_violation.score + 25

    def test_breakdown_contains_all_factors(self):
        action = Action(tool_name="t", operation="SELECT", action_category=ActionCategory.READ)
        risk = compute_risk_score(action)
        expected_keys = {
            "action_type",
            "environment",
            "blast_radius",
            "time_context",
            "behavioral",
            "data_sensitivity",
            "scope_violation_penalty",
        }
        assert set(risk.breakdown.keys()) == expected_keys

    def test_threshold_auto_approve(self):
        """Should auto-approve when the combined score stays below the flag threshold."""
        action = Action(
            tool_name="t",
            operation="SELECT",
            action_category=ActionCategory.READ,
            target_resource_id="main.dev.x",
            sql_statement="SELECT 1",
        )
        risk = compute_risk_score(action)
        assert risk.decision == CheckpointDecision.AUTO_APPROVE

    def test_threshold_hold_for_approval_used(self):
        """Should yield FLAG or HOLD_FOR_APPROVAL for a high-risk production DELETE."""
        action = Action(
            tool_name="t",
            operation="DELETE",
            action_category=ActionCategory.WRITE,
            target_resource_id="main.production.orders",
            sql_statement="DELETE FROM main.production.orders",
        )
        risk = compute_risk_score(action)
        assert risk.decision in (
            CheckpointDecision.FLAG,
            CheckpointDecision.HOLD_FOR_APPROVAL,
        )

    def test_custom_thresholds(self):
        action = Action(tool_name="t", operation="SELECT", action_category=ActionCategory.READ)
        risk = compute_risk_score(
            action,
            thresholds={"flag_above": 1, "hold_above": 2, "block_above": 3},
        )
        assert risk.decision == CheckpointDecision.BLOCK
