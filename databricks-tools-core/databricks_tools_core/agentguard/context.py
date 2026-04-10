"""
AgentGuard context

Module-level active session so it survives separate MCP tool calls. ContextVar would not,
because each message is a new async context (same idea as auth’s _active_profile / _active_host).
"""

from __future__ import annotations

import threading
from typing import Optional

from databricks_tools_core.agentguard.models import AgentGuardSession

_lock = threading.Lock()
_active_session: Optional[AgentGuardSession] = None


def get_active_session() -> Optional[AgentGuardSession]:
    with _lock:
        return _active_session


def set_active_session(session: AgentGuardSession) -> None:
    global _active_session
    with _lock:
        _active_session = session


def clear_active_session() -> None:
    global _active_session
    with _lock:
        _active_session = None


def has_active_session() -> bool:
    with _lock:
        return _active_session is not None
