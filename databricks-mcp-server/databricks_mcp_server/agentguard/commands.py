"""MCP tools for starting, stopping, and inspecting AgentGuard sessions."""

from __future__ import annotations

import json
from typing import Optional

from databricks_tools_core.agentguard.context import get_active_session
from databricks_tools_core.agentguard.models import AgentGuardMode
from databricks_tools_core.agentguard.session import (
    get_session_status,
    start_session,
    stop_session,
)

from ..server import mcp


@mcp.tool
def agentguard_start(
    mode: str = "monitor_only",
    description: str = "",
    scope_template: Optional[str] = None,
    scope_variables: Optional[dict] = None,
) -> str:
    """Start a session: mode monitor_only|enforce, optional scope_template/variables."""
    try:
        guard_mode = AgentGuardMode(mode)
    except ValueError:
        return f"Invalid mode '{mode}'. Use 'monitor_only' or 'enforce'."

    try:
        session = start_session(
            mode=guard_mode,
            description=description,
            scope_template=scope_template,
            scope_variables=scope_variables,
        )
    except ValueError as e:
        return str(e)

    mode_label = "monitor-only" if guard_mode == AgentGuardMode.MONITOR_ONLY else "enforce"
    lines = [
        f"AgentGuard session started ({mode_label}).",
        f"Task ID: {session.task_id}",
        "All actions will be recorded.",
    ]
    if guard_mode == AgentGuardMode.MONITOR_ONLY:
        lines.append("Nothing will be blocked. Use mode='enforce' to enable enforcement.")
    else:
        lines.append("Policy and scope violations will be BLOCKED.")
        if scope_template:
            lines.append(f"Scope template: {scope_template}")
            if scope_variables:
                lines.append(f"Scope variables: {scope_variables}")
        lines.append("Risk scoring is active. High-risk actions will require approval.")

    return "\n".join(lines)


@mcp.tool
def agentguard_stop() -> str:
    """Stop the session, flush audit trail if possible, return summary text."""
    session = stop_session()
    if session is None:
        return "No active AgentGuard session to stop."

    lines = [
        "AgentGuard session stopped.",
        session.summary(),
    ]

    ledger = session._ledger_result
    if ledger:
        status = ledger.get("status", "unknown")
        if status == "success":
            dest = ledger.get("destination", "?")
            lines.append(f"Audit trail: {ledger.get('rows', 0)} actions written to {dest}")
            lines.append(f"Query: SELECT * FROM {dest} WHERE task_id = '{session.task_id}'")
        elif status == "pending":
            lines.append(f"Audit trail: saved locally at {ledger.get('destination', '?')}")
            lines.append(f"Note: {ledger.get('note', 'Delta write unavailable. Data saved locally.')}")
        elif status == "skipped":
            lines.append("Audit trail: no actions to write.")
        else:
            lines.append(f"Audit trail: {status} — {ledger.get('error', ledger.get('note', 'unknown'))}")
    else:
        lines.append(f"Audit trail: agentguard.core.action_log WHERE task_id = '{session.task_id}'")

    return "\n".join(lines)


@mcp.tool
def agentguard_status() -> str:
    """Return session status text, or a hint to call agentguard_start."""
    status = get_session_status()
    if status is None:
        return "No active AgentGuard session. Run agentguard_start to begin."
    return status


@mcp.tool
def agentguard_history(limit: int = 50) -> str:
    """Return recent actions as JSON (limit defaults to 50, tail of the list)."""
    session = get_active_session()
    if session is None:
        return "No active AgentGuard session. Run agentguard_start to begin."

    if not session.actions:
        return "No actions recorded yet in this session."

    actions_to_show = session.actions[-limit:] if limit > 0 else session.actions
    history = []
    for action in actions_to_show:
        entry = {
            "seq": action.action_sequence,
            "tool": action.tool_name,
            "operation": action.operation,
            "category": action.action_category.value,
            "decision": action.final_decision,
            "risk_score": action.checkpoint_result.risk_score if action.checkpoint_result else 0,
            "policy": action.checkpoint_result.policy_result if action.checkpoint_result else "n/a",
            "overhead_ms": round(action.overhead_ms, 1) if action.overhead_ms else 0,
            "success": action.execution_success,
            "timestamp": action.received_at.isoformat(),
        }
        if action.sql_statement:
            stmt = action.sql_statement
            entry["sql"] = stmt[:120] + "..." if len(stmt) > 120 else stmt
        if action.checkpoint_result and action.checkpoint_result.block_reason:
            entry["block_reason"] = action.checkpoint_result.block_reason
        history.append(entry)

    total = len(session.actions)
    shown = len(history)
    suffix = f"\n\n(Showing {shown} of {total} actions)" if shown < total else ""
    return json.dumps(history, indent=2) + suffix
