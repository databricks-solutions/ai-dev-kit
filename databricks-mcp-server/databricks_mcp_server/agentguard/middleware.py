"""MCP middleware: runs AgentGuard checkpoints on each tool call when a session is active."""

import asyncio
import json
import logging
import time
from typing import Any

from databricks_tools_core.agentguard.context import get_active_session
from databricks_tools_core.agentguard.models import (
    Action,
    AgentGuardMode,
    CheckpointDecision,
    CheckpointResult,
)
from databricks_tools_core.agentguard.policy import PolicyEngine
from databricks_tools_core.agentguard.risk import compute_risk_score
from databricks_tools_core.agentguard.scope import check_scope, check_scope_limits
from databricks_tools_core.agentguard.timing import Timer
from fastmcp.server.context import (
    AcceptedElicitation,
    CancelledElicitation,
    DeclinedElicitation,
)
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp.types import CallToolRequestParams, TextContent

_APPROVAL_TIMEOUT_SECONDS = 300

logger = logging.getLogger(__name__)

_AGENTGUARD_TOOLS = frozenset(
    {
        "agentguard_start",
        "agentguard_stop",
        "agentguard_status",
        "agentguard_history",
    }
)


class AgentGuardMiddleware(Middleware):
    """Wraps tool calls with policy/scope/risk checks and optional human approval."""

    def __init__(self) -> None:
        self.policy_engine = PolicyEngine()

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        session = get_active_session()

        if session is None:
            return await call_next(context)

        tool_name = context.message.name
        tool_params = context.message.arguments or {}

        if tool_name in _AGENTGUARD_TOOLS:
            return await call_next(context)

        timer = Timer()

        action = timer.measure(
            "build_action",
            Action.from_tool_call,
            tool_name=tool_name,
            tool_params=tool_params,
            task_id=session.task_id,
            agent_id=session.agent_id,
            sequence=session.next_sequence(),
        )

        checkpoint_result = timer.measure(
            "checkpoint_pipeline",
            self._run_checkpoints,
            action,
            session,
        )
        action.checkpoint_result = checkpoint_result
        checkpoint_result.timings = timer.records

        if (
            checkpoint_result.decision
            in (
                CheckpointDecision.FLAG,
                CheckpointDecision.HOLD_FOR_APPROVAL,
            )
            and session.mode == AgentGuardMode.ENFORCE
        ):
            checkpoint_result.original_decision = checkpoint_result.decision
            checkpoint_result.approval_requested = True

            approved = await self._request_human_approval(context, action, checkpoint_result)
            if not approved:
                checkpoint_result.decision = CheckpointDecision.BLOCK
                checkpoint_result.blocking_checkpoint = "CP-4: Human Approval"
                action.final_decision = "rejected_by_user"
                action.overhead_ms = timer.total_ms
                session.record_action(action)
                self._log_action(action, checkpoint_result)
                self._persist_action(session, action)
                return self._blocked_result(tool_name, checkpoint_result)

            checkpoint_result.approval_outcome = "approved"
            action.final_decision = "approved_by_user"
            logger.info(
                "[AgentGuard] #%d %s — approved by user",
                action.action_sequence,
                tool_name,
            )

        should_block = checkpoint_result.decision == CheckpointDecision.BLOCK and session.mode == AgentGuardMode.ENFORCE

        if should_block:
            action.final_decision = action.final_decision or "blocked"
            action.overhead_ms = timer.total_ms
            session.record_action(action)
            self._log_action(action, checkpoint_result)
            self._persist_action(session, action)
            return self._blocked_result(tool_name, checkpoint_result)

        exec_start = time.perf_counter()
        execution_failed = False
        try:
            tool_result = await call_next(context)
            action.execution_success = True
        except Exception as e:
            execution_failed = True
            action.execution_success = False
            action.execution_error = str(e)
            raise
        finally:
            action.execution_duration_ms = (time.perf_counter() - exec_start) * 1000
            action.overhead_ms = timer.total_ms

            if execution_failed:
                action.final_decision = action.final_decision or "failed"
            elif not action.final_decision:
                if checkpoint_result.decision in (
                    CheckpointDecision.WOULD_BLOCK,
                    CheckpointDecision.BLOCK,
                    CheckpointDecision.HOLD_FOR_APPROVAL,
                ):
                    action.final_decision = "would_block"
                elif checkpoint_result.decision == CheckpointDecision.FLAG:
                    action.final_decision = "flagged"
                else:
                    action.final_decision = "executed"

            session.record_action(action)
            self._log_action(action, checkpoint_result)
            self._persist_action(session, action)

        return tool_result

    async def _request_human_approval(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        action: Action,
        result: CheckpointResult,
    ) -> bool:
        """Elicit yes/no approval; False on timeout, missing context, or decline."""
        ctx = context.fastmcp_context
        if ctx is None:
            logger.warning(
                "[AgentGuard] CP-4 BLOCKED (no context): %s %s — %s",
                action.tool_name,
                action.operation,
                result.block_reason,
            )
            result.approval_outcome = "unavailable"
            result.approval_note = "No FastMCP context available"
            return False

        message = self._format_approval_message(action, result)

        try:
            elicit_result = await asyncio.wait_for(
                ctx.elicit(message=message, response_type=bool),
                timeout=_APPROVAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[AgentGuard] CP-4 BLOCKED (timeout after %ds): %s %s — %s",
                _APPROVAL_TIMEOUT_SECONDS,
                action.tool_name,
                action.operation,
                result.block_reason,
            )
            result.approval_outcome = "timeout"
            result.approval_note = f"No response within {_APPROVAL_TIMEOUT_SECONDS}s. Action blocked for safety."
            return False
        except Exception as exc:
            logger.warning(
                "[AgentGuard] CP-4 BLOCKED (elicitation unavailable): %s %s — %s "
                "(client may not support elicitation: %s). "
                "Action blocked for safety.",
                action.tool_name,
                action.operation,
                result.block_reason,
                exc,
            )
            result.approval_outcome = "unavailable"
            result.approval_note = (
                f"Client does not support interactive approval dialogs ({exc}). Action blocked for safety."
            )
            return False

        if isinstance(elicit_result, AcceptedElicitation):
            result.approval_outcome = "approved"
            return True

        if isinstance(elicit_result, DeclinedElicitation):
            result.approval_outcome = "declined"
            result.approval_note = "User declined the action"
        elif isinstance(elicit_result, CancelledElicitation):
            result.approval_outcome = "cancelled"
            result.approval_note = "User cancelled the approval dialog"

        return False

    @staticmethod
    def _format_approval_message(action: Action, result: CheckpointResult) -> str:
        severity = (
            "HIGH RISK — Approval Required"
            if result.decision == CheckpointDecision.HOLD_FOR_APPROVAL
            else "Review Required"
        )
        parts = [
            f"AgentGuard — {severity}",
            "",
            f"  Tool:      {action.tool_name}",
            f"  Operation: {action.operation}",
        ]
        if action.target_resource_id:
            parts.append(f"  Target:    {action.target_resource_id}")
        if action.sql_statement:
            stmt = action.sql_statement
            display = (stmt[:100] + "...") if len(stmt) > 100 else stmt
            parts.append(f"  SQL:       {display}")
        if result.risk_score > 0:
            parts.append(f"  Risk:      {result.risk_score:.0f}/100")
        parts += [
            "",
            f"  Reason:    {result.block_reason or 'Flagged by policy'}",
            "",
            "Check the box (Space), then select Accept or Decline (Enter).",
        ]
        return "\n".join(parts)

    def _run_checkpoints(
        self,
        action: Action,
        session,
    ) -> CheckpointResult:
        """Policy, optional scope/limits, then risk; later stages cannot undo a block."""
        result = CheckpointResult()
        scope_violated = False

        policy_decision, rule_hit = self.policy_engine.check(action, session.mode)
        result.policy_result = policy_decision.value
        result.policy_rule_hit = rule_hit

        if policy_decision in (
            CheckpointDecision.BLOCK,
            CheckpointDecision.WOULD_BLOCK,
        ):
            result.decision = policy_decision
            result.block_reason = rule_hit
            result.blocking_checkpoint = "CP-1: Policy"
        elif policy_decision == CheckpointDecision.FLAG:
            result.decision = CheckpointDecision.FLAG
            result.block_reason = rule_hit
            result.blocking_checkpoint = "CP-1: Policy -> CP-4: Approval"

        if session.scope is not None:
            scope_decision, scope_violation = check_scope(
                action,
                session.scope,
                session.mode,
            )
            result.scope_result = scope_decision.value
            result.scope_violation = scope_violation

            if scope_decision in (
                CheckpointDecision.BLOCK,
                CheckpointDecision.WOULD_BLOCK,
            ):
                scope_violated = True
                if result.decision in (
                    CheckpointDecision.AUTO_APPROVE,
                    CheckpointDecision.FLAG,
                ):
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
            if limit_decision in (
                CheckpointDecision.BLOCK,
                CheckpointDecision.WOULD_BLOCK,
            ):
                if result.decision in (
                    CheckpointDecision.AUTO_APPROVE,
                    CheckpointDecision.FLAG,
                ):
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
            if result.decision in (
                CheckpointDecision.AUTO_APPROVE,
                CheckpointDecision.FLAG,
            ):
                result.decision = CheckpointDecision.HOLD_FOR_APPROVAL
                result.block_reason = result.block_reason or f"Risk score {risk.score:.0f} requires human approval"
                result.blocking_checkpoint = "CP-3: Risk Score -> CP-4: Approval"
        elif risk.decision == CheckpointDecision.FLAG:
            if result.decision == CheckpointDecision.AUTO_APPROVE:
                result.decision = CheckpointDecision.FLAG
                result.block_reason = result.block_reason or f"Risk score {risk.score:.0f} exceeds flag threshold"
                result.blocking_checkpoint = "CP-3: Risk Score -> CP-4: Approval"

        # In monitor mode, never hard-BLOCK — downgrade to WOULD_BLOCK so
        # session counters and summaries are consistent with policy/scope behavior.
        if session.mode == AgentGuardMode.MONITOR_ONLY and result.decision == CheckpointDecision.BLOCK:
            result.decision = CheckpointDecision.WOULD_BLOCK

        return result

    @staticmethod
    def _blocked_result(tool_name: str, result: CheckpointResult) -> ToolResult:
        return ToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "agentguard_blocked": True,
                            "tool": tool_name,
                            "reason": result.block_reason,
                            "checkpoint": result.blocking_checkpoint,
                            "risk_score": result.risk_score,
                            "suggestion": (
                                "This action was blocked by AgentGuard. "
                                "If you believe this is correct, ask the user "
                                "to approve it or contact an admin to adjust the policy."
                            ),
                        }
                    ),
                )
            ]
        )

    @staticmethod
    def _log_action(action: Action, result: CheckpointResult) -> None:
        overhead = f"{action.overhead_ms:.0f}ms" if action.overhead_ms else "?"
        risk = f"risk={result.risk_score:.0f}"
        decision = result.decision.value

        logger.info(
            "[AgentGuard] #%d %s %s | %s | %s | policy=%s | overhead=%s",
            action.action_sequence,
            action.tool_name,
            action.operation,
            decision,
            risk,
            result.policy_result,
            overhead,
        )

    @staticmethod
    def _persist_action(session: Any, action: Action) -> None:
        try:
            from databricks_tools_core.agentguard.ledger import append_action

            append_action(session.task_id, action, session)
        except Exception as e:
            logger.debug("Audit persist failed for %s: %s", action.action_id, e)
