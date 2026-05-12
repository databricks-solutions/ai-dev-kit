"""
Integration tests for the full AgentGuard checkpoint pipeline.

Tests:
- monitor vs enforce sessions, scope, limits, risk escalation, summary
"""

import pytest

from databricks_tools_core.agentguard.models import (
    Action,
    AgentGuardMode,
    CheckpointDecision,
    CheckpointResult,
    SessionStatus,
)
from databricks_tools_core.agentguard.policy import PolicyEngine
from databricks_tools_core.agentguard.risk import compute_risk_score
from databricks_tools_core.agentguard.scope import (
    ScopeManifest,
    ResourceScope,
    check_scope,
    check_scope_limits,
)
from databricks_tools_core.agentguard.session import start_session, stop_session


def _run_checkpoint_pipeline(
    action: Action,
    session,
    policy_engine: PolicyEngine,
) -> CheckpointResult:
    """Runs policy, scope/limits, and risk like AgentGuardMiddleware."""
    result = CheckpointResult()
    scope_violated = False

    policy_decision, rule_hit = policy_engine.check(action, session.mode)
    result.policy_result = policy_decision.value
    result.policy_rule_hit = rule_hit

    if policy_decision in (CheckpointDecision.BLOCK, CheckpointDecision.WOULD_BLOCK):
        result.decision = policy_decision
        result.block_reason = rule_hit
        result.blocking_checkpoint = "CP-1: Policy"
    elif policy_decision == CheckpointDecision.FLAG:
        result.decision = CheckpointDecision.FLAG
        result.block_reason = rule_hit
        result.blocking_checkpoint = "CP-1: Policy -> CP-4: Approval"

    if session.scope is not None:
        scope_decision, scope_violation = check_scope(action, session.scope, session.mode)
        result.scope_result = scope_decision.value
        result.scope_violation = scope_violation

        if scope_decision in (CheckpointDecision.BLOCK, CheckpointDecision.WOULD_BLOCK):
            scope_violated = True
            if result.decision in (CheckpointDecision.AUTO_APPROVE, CheckpointDecision.FLAG):
                result.decision = scope_decision
                result.block_reason = scope_violation
                result.blocking_checkpoint = "CP-2: Scope"

        limit_decision, limit_violation = check_scope_limits(
            action,
            session.scope,
            session.action_count,
            session.write_count,
            session.mode,
        )
        if limit_decision in (CheckpointDecision.BLOCK, CheckpointDecision.WOULD_BLOCK):
            if result.decision in (CheckpointDecision.AUTO_APPROVE, CheckpointDecision.FLAG):
                result.decision = limit_decision
                result.block_reason = limit_violation
                result.blocking_checkpoint = "CP-2: Scope (limit)"

    risk = compute_risk_score(action, scope_violated=scope_violated)
    result.risk_score = risk.score
    result.risk_breakdown = risk.breakdown

    if risk.decision == CheckpointDecision.BLOCK:
        if result.decision in (
            CheckpointDecision.AUTO_APPROVE,
            CheckpointDecision.FLAG,
            CheckpointDecision.HOLD_FOR_APPROVAL,
        ):
            result.decision = CheckpointDecision.BLOCK
            result.block_reason = result.block_reason or f"Risk score {risk.score:.0f} exceeds block threshold"
            result.blocking_checkpoint = "CP-3: Risk Score"
    elif risk.decision == CheckpointDecision.HOLD_FOR_APPROVAL:
        if result.decision in (CheckpointDecision.AUTO_APPROVE, CheckpointDecision.FLAG):
            result.decision = CheckpointDecision.HOLD_FOR_APPROVAL
            result.block_reason = result.block_reason or f"Risk score {risk.score:.0f} requires human approval"
            result.blocking_checkpoint = "CP-3: Risk Score -> CP-4: Approval"
    elif risk.decision == CheckpointDecision.FLAG:
        if result.decision == CheckpointDecision.AUTO_APPROVE:
            result.decision = CheckpointDecision.FLAG
            result.block_reason = result.block_reason or f"Risk score {risk.score:.0f} exceeds flag threshold"
            result.blocking_checkpoint = "CP-3: Risk Score -> CP-4: Approval"

    return result


@pytest.mark.integration
class TestFullPipelineMonitorMode:
    """Tests for pipeline behavior in MONITOR_ONLY."""

    def test_mixed_operations_all_recorded(self):
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="full-pipeline-monitor",
        )

        tool_calls = [
            ("execute_sql", {"query": "SELECT * FROM main.analytics.orders"}),
            ("execute_sql", {"query": "INSERT INTO main.staging.temp VALUES (1)"}),
            ("execute_sql", {"query": "DROP TABLE main.staging.old_temp"}),
            ("list_clusters", {}),
            ("delete_app", {"name": "test-app"}),
        ]

        for tool_name, tool_params in tool_calls:
            action = Action.from_tool_call(
                tool_name=tool_name,
                tool_params=tool_params,
                task_id=session.task_id,
                agent_id="test-agent",
                sequence=session.next_sequence(),
            )
            result = _run_checkpoint_pipeline(action, session, policy_engine)
            action.checkpoint_result = result

            if result.decision in (CheckpointDecision.BLOCK, CheckpointDecision.WOULD_BLOCK):
                action.final_decision = "would_block"
            elif result.decision == CheckpointDecision.FLAG:
                action.final_decision = "flagged"
            else:
                action.final_decision = "executed"
            action.execution_success = True
            session.record_action(action)

        completed = stop_session()

        assert completed is not None
        assert completed.status == SessionStatus.COMPLETED
        assert completed.action_count == 5
        assert completed.would_block_count >= 0

    def test_dangerous_sql_recorded_as_would_block(self):
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.MONITOR_ONLY,
            description="monitor-dangerous-sql",
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "TRUNCATE TABLE main.production.billing"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        result = _run_checkpoint_pipeline(action, session, policy_engine)
        action.checkpoint_result = result
        action.final_decision = "would_block"
        action.execution_success = True
        session.record_action(action)

        assert result.decision == CheckpointDecision.WOULD_BLOCK
        assert result.blocking_checkpoint == "CP-1: Policy"
        assert session.would_block_count == 1

        stop_session()


@pytest.mark.integration
class TestFullPipelineEnforceMode:
    """Tests for pipeline behavior in ENFORCE."""

    def test_safe_read_passes_all_checkpoints(self):
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="enforce-safe-read",
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT count(*) FROM main.staging.temp"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        result = _run_checkpoint_pipeline(action, session, policy_engine)
        action.checkpoint_result = result
        action.final_decision = "executed"
        action.execution_success = True
        session.record_action(action)

        assert result.decision == CheckpointDecision.AUTO_APPROVE
        assert result.risk_score < 35

        stop_session()

    def test_drop_database_hard_blocked(self):
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="enforce-drop-db",
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "DROP DATABASE production"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        result = _run_checkpoint_pipeline(action, session, policy_engine)
        action.checkpoint_result = result
        action.final_decision = "blocked"
        session.record_action(action)

        assert result.decision == CheckpointDecision.BLOCK
        assert result.blocking_checkpoint == "CP-1: Policy"
        assert session.blocked_count == 1

        stop_session()

    def test_delete_app_flagged_for_approval(self):
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="enforce-delete-app",
        )

        action = Action.from_tool_call(
            tool_name="delete_app",
            tool_params={"name": "critical-production-app"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        result = _run_checkpoint_pipeline(action, session, policy_engine)

        assert result.decision == CheckpointDecision.FLAG
        assert result.blocking_checkpoint is not None

        stop_session()


@pytest.mark.integration
class TestFullPipelineWithScope:
    """Tests for pipeline with scope attached."""

    def test_in_scope_read_passes(self):
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="scope-in",
        )
        session.scope = ScopeManifest(
            tables=ResourceScope(
                read=["main.analytics.*"],
                write=["main.staging.temp_*"],
            ),
            default_deny=True,
            max_actions=100,
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.analytics.orders"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        action.target_resource_id = "main.analytics.orders"

        result = _run_checkpoint_pipeline(action, session, policy_engine)

        assert result.decision == CheckpointDecision.AUTO_APPROVE

        stop_session()

    def test_out_of_scope_read_blocked(self):
        """Should block reads outside allowed table patterns."""
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="scope-out",
        )
        session.scope = ScopeManifest(
            tables=ResourceScope(
                read=["main.analytics.orders"],
            ),
            default_deny=True,
            max_actions=100,
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT * FROM main.analytics.customer_pii"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )
        action.target_resource_id = "main.analytics.customer_pii"

        result = _run_checkpoint_pipeline(action, session, policy_engine)

        assert result.decision == CheckpointDecision.BLOCK
        assert result.blocking_checkpoint == "CP-2: Scope"
        assert "not in scope" in result.scope_violation

        stop_session()

    def test_scope_limit_blocks_after_max_actions(self):
        """Should block once session action count reaches max_actions."""
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="scope-limit",
        )
        session.scope = ScopeManifest(max_actions=3)

        for i in range(3):
            action = Action.from_tool_call(
                tool_name="execute_sql",
                tool_params={"query": f"SELECT {i}"},
                task_id=session.task_id,
                agent_id="test-agent",
                sequence=session.next_sequence(),
            )
            action.checkpoint_result = CheckpointResult()
            action.final_decision = "executed"
            session.record_action(action)

        action_4 = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "SELECT 3"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )

        result = _run_checkpoint_pipeline(action_4, session, policy_engine)

        assert result.decision == CheckpointDecision.BLOCK
        assert "max_actions" in result.block_reason

        stop_session()


@pytest.mark.integration
class TestRiskEscalation:
    """Tests for risk overriding policy auto-approve."""

    def test_policy_approve_risk_flag_escalates(self):
        """Should escalate to FLAG or HOLD when risk is high despite policy approve."""
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="risk-escalation",
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "INSERT INTO main.production.billing VALUES (1, 100)"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )

        result = _run_checkpoint_pipeline(action, session, policy_engine)

        assert result.policy_result == CheckpointDecision.AUTO_APPROVE.value
        assert result.risk_score >= 35
        assert result.decision in (CheckpointDecision.FLAG, CheckpointDecision.HOLD_FOR_APPROVAL)

        stop_session()

    def test_policy_block_not_downgraded_by_low_risk(self):
        """Should keep policy BLOCK even when environment risk is lower."""
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="no-downgrade",
        )

        action = Action.from_tool_call(
            tool_name="execute_sql",
            tool_params={"query": "TRUNCATE TABLE main.staging.small_table"},
            task_id=session.task_id,
            agent_id="test-agent",
            sequence=session.next_sequence(),
        )

        result = _run_checkpoint_pipeline(action, session, policy_engine)

        assert result.decision == CheckpointDecision.BLOCK
        assert result.blocking_checkpoint == "CP-1: Policy"

        stop_session()


@pytest.mark.integration
class TestSessionSummaryAccuracy:
    """Tests for session.summary() after pipeline runs."""

    def test_summary_counts_match(self):
        policy_engine = PolicyEngine()

        session = start_session(
            mode=AgentGuardMode.ENFORCE,
            description="summary-test",
        )

        actions_spec = [
            ("execute_sql", {"query": "SELECT 1"}),
            ("execute_sql", {"query": "SELECT 2"}),
            ("execute_sql", {"query": "DROP DATABASE test_db"}),
            ("delete_app", {"name": "test-app"}),
        ]

        for tool_name, tool_params in actions_spec:
            action = Action.from_tool_call(
                tool_name=tool_name,
                tool_params=tool_params,
                task_id=session.task_id,
                agent_id="test-agent",
                sequence=session.next_sequence(),
            )
            result = _run_checkpoint_pipeline(action, session, policy_engine)
            action.checkpoint_result = result

            if result.decision == CheckpointDecision.BLOCK:
                action.final_decision = "blocked"
            elif result.decision == CheckpointDecision.FLAG:
                action.final_decision = "flagged"
            else:
                action.final_decision = "executed"
            session.record_action(action)

        summary = session.summary()

        assert "Actions: 4" in summary
        assert "Blocked: 1" in summary

        completed = stop_session()
        assert completed.action_count == 4
        assert completed.blocked_count == 1
