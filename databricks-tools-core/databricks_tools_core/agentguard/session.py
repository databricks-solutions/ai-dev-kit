"""
AgentGuard session lifecycle

Start: optional scope load, JSONL init, orphan report. Stop: flush ledger to Delta, clear context.
"""

from __future__ import annotations

import logging
from typing import Optional

from databricks_tools_core.agentguard.context import (
    clear_active_session,
    get_active_session,
    set_active_session,
)
from databricks_tools_core.agentguard.models import (
    AgentGuardMode,
    AgentGuardSession,
    SessionStatus,
)

logger = logging.getLogger(__name__)


def start_session(
    mode: AgentGuardMode = AgentGuardMode.MONITOR_ONLY,
    description: str = "",
    scope_template: Optional[str] = None,
    scope_variables: Optional[dict[str, str]] = None,
    agent_id: str = "unknown",
    user_id: str = "unknown",
) -> AgentGuardSession:
    """Raises ValueError if an active session already exists."""
    existing = get_active_session()
    if existing and existing.status == SessionStatus.ACTIVE:
        raise ValueError(f"An AgentGuard session is already active: {existing.task_id}. Run /agentguard stop first.")

    project_name = "unknown"
    try:
        from databricks_tools_core.identity import detect_project_name

        project_name = detect_project_name()
    except Exception:
        pass

    session = AgentGuardSession(
        mode=mode,
        description=description,
        scope_template=scope_template,
        scope_variables=scope_variables,
        agent_id=agent_id,
        user_id=user_id,
        project_name=project_name,
    )

    if scope_template:
        try:
            from databricks_tools_core.agentguard.scope import load_template

            session.scope = load_template(scope_template, scope_variables)
            logger.info(f"Scope template '{scope_template}' loaded for task {session.task_id}")
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"Failed to load scope template '{scope_template}': {e}")

    try:
        from databricks_tools_core.agentguard.ledger import init_session_file

        init_session_file(session.task_id)
    except Exception as e:
        logger.warning(f"Could not initialize session JSONL: {e}")

    _report_orphans()

    set_active_session(session)

    mode_label = "monitor-only" if mode == AgentGuardMode.MONITOR_ONLY else "enforce"
    scope_label = f" | Scope: {scope_template}" if scope_template else " | No scope"
    logger.info(f"AgentGuard session started ({mode_label}{scope_label}). Task ID: {session.task_id}")
    return session


def stop_session() -> Optional[AgentGuardSession]:
    """Complete session, flush JSONL to Delta, return session (or None if none active)."""
    session = get_active_session()
    if session is None:
        return None

    session.complete()
    clear_active_session()

    try:
        from databricks_tools_core.agentguard.ledger import flush_session_to_delta

        ledger_result = flush_session_to_delta(session)
        session._ledger_result = ledger_result
        logger.info(
            f"Audit ledger flush: {ledger_result.get('status')} "
            f"({ledger_result.get('rows', 0)} rows -> {ledger_result.get('destination', 'unknown')})"
        )
    except Exception as e:
        logger.warning(f"Audit ledger flush failed: {e}")
        session._ledger_result = {"status": "error", "error": str(e)}

    logger.info(f"AgentGuard session stopped. {session.summary()}")
    return session


def get_session_status() -> Optional[str]:
    session = get_active_session()
    if session is None:
        return None
    return session.summary()


def _report_orphans() -> None:
    try:
        from databricks_tools_core.agentguard.ledger import find_orphaned_sessions

        orphans = find_orphaned_sessions()
        if orphans:
            ids = ", ".join(o["task_id"] for o in orphans)
            logger.warning(
                f"Found {len(orphans)} orphaned AgentGuard session(s) from previous runs. "
                f"Data is preserved locally at ~/.agentguard/sessions/. Sessions: {ids}"
            )
    except Exception:
        pass
