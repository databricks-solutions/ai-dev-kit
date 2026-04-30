"""
Integration tests for AgentGuard risk scoring.

Tests:
- compute_risk_score on realistic actions, breakdown, thresholds, scope penalty
"""

import pytest

from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    CheckpointDecision,
)
from databricks_tools_core.agentguard.risk import compute_risk_score


@pytest.mark.integration
class TestRiskScoreComputation:
    """Tests for end-to-end risk scores."""

    def test_select_low_risk(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.analytics.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)

        assert risk.score < 35, f"SELECT should be low risk, got {risk.score}"
        assert risk.decision == CheckpointDecision.AUTO_APPROVE

    def test_drop_table_high_risk(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP TABLE main.production.billing"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)

        assert risk.score >= 35, f"DROP TABLE on production should be high risk, got {risk.score}"
        assert risk.decision in (
            CheckpointDecision.FLAG,
            CheckpointDecision.HOLD_FOR_APPROVAL,
            CheckpointDecision.BLOCK,
        )

    def test_insert_into_production_flagged(self):
        """Should score INSERT into production above the low-risk band."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO main.production.billing VALUES (1, 100)"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)

        assert risk.score >= 35, f"INSERT into production should be flaggable, got {risk.score}"

    def test_update_without_where_high_risk(self):
        """Should treat unbounded UPDATE on production as high risk."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "UPDATE main.production.users SET status = 'inactive'"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)

        assert risk.score >= 35, f"Unbounded UPDATE on production should flag, got {risk.score}"

    def test_read_only_tool_low_risk(self):
        action = Action.from_tool_call(
            tool_name="list_clusters",
            tool_params={},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)
        assert risk.score < 35
        assert risk.decision == CheckpointDecision.AUTO_APPROVE

    def test_delete_app_moderate_risk(self):
        action = Action.from_tool_call(
            tool_name="delete_app",
            tool_params={"name": "my-staging-app"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)

        assert risk.score > 20, f"DELETE_APP should have meaningful risk, got {risk.score}"

    def test_execute_code_high_risk(self):
        action = Action.from_tool_call(
            tool_name="execute_databricks_command",
            tool_params={"cluster_id": "prod-cluster", "code": "df.write.mode('overwrite').saveAsTable('t')"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)
        assert risk.score >= 35, f"Code execution should be flaggable, got {risk.score}"


@pytest.mark.integration
class TestRiskBreakdown:
    """Tests for risk breakdown keys and environment signal."""

    def test_breakdown_has_all_factors(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP TABLE main.production.billing"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)

        expected_factors = {
            "action_type",
            "environment",
            "blast_radius",
            "time_context",
            "behavioral",
            "data_sensitivity",
        }
        assert expected_factors.issubset(set(risk.breakdown.keys())), (
            f"Missing factors: {expected_factors - set(risk.breakdown.keys())}"
        )

    def test_production_environment_scores_high(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.production.orders"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)

        assert risk.breakdown.get("environment", 0) >= 60


@pytest.mark.integration
class TestRiskThresholds:
    """Tests for threshold-driven decisions."""

    def test_auto_approve_below_35(self):
        """Should auto-approve trivial reads."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT 1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)
        assert risk.score < 35
        assert risk.decision == CheckpointDecision.AUTO_APPROVE

    def test_truncate_production_very_high_risk(self):
        """Should score TRUNCATE on production very high."""
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "TRUNCATE TABLE main.production.billing_records"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk = compute_risk_score(action)
        assert risk.score >= 50, f"TRUNCATE production should be very high risk, got {risk.score}"


@pytest.mark.integration
class TestScopeViolationPenalty:
    """Tests for scope_violated scoring."""

    def test_scope_violation_increases_score(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.staging.temp"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk_normal = compute_risk_score(action, scope_violated=False)
        risk_violated = compute_risk_score(action, scope_violated=True)

        assert risk_violated.score > risk_normal.score, (
            f"Scope violation should increase risk: normal={risk_normal.score}, violated={risk_violated.score}"
        )

    def test_scope_violation_penalty_is_25_points(self):
        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT 1"},
            task_id="t1",
            agent_id="a1",
            sequence=1,
        )

        risk_normal = compute_risk_score(action, scope_violated=False)
        risk_violated = compute_risk_score(action, scope_violated=True)

        penalty = risk_violated.score - risk_normal.score
        assert abs(penalty - 25) < 1, f"Expected ~25 point penalty, got {penalty}"
