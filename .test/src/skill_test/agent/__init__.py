"""Agent-based evaluation using Claude Agent SDK.

Runs a real Claude Code instance with candidate SKILL.md injected,
captures streaming events, and builds TraceMetrics for scoring.
"""

from .executor import AgentResult, run_agent

__all__ = ["AgentResult", "run_agent"]
