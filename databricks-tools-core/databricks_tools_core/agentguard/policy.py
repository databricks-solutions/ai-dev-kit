"""
AgentGuard policy

Rules match normalized action text (not raw SQL) so optional keywords and whitespace
do not bypass patterns. Example: `DROP TABLE IF EXISTS main.foo;` → `DROP TABLE main.foo`.
"""

from __future__ import annotations

import re
from typing import Optional

from databricks_tools_core.agentguard.models import (
    Action,
    AgentGuardMode,
    CheckpointDecision,
)


class PolicyRule:
    """Glob pattern against normalized text; `*` → any substring. Case-insensitive."""

    def __init__(self, pattern: str, decision: CheckpointDecision, description: str = ""):
        self.pattern = pattern
        self.decision = decision
        self.description = description
        escaped = re.escape(pattern)
        regex_str = "^" + escaped.replace(r"\*", ".*")
        self._regex = re.compile(regex_str, re.IGNORECASE)

    def matches(self, text: str) -> bool:
        return self._regex.search(text) is not None


_DEFAULT_ALWAYS_BLOCK: list[tuple[str, str]] = [
    ("DROP DATABASE *", "Dropping databases is globally blocked"),
    ("DROP SCHEMA *", "Dropping schemas is globally blocked"),
    ("TRUNCATE TABLE *", "Truncating tables is globally blocked"),
    ("GRANT ALL PRIVILEGES *", "Granting all privileges is globally blocked"),
    ("REVOKE * FROM *", "Revoking privileges is globally blocked"),
]

_DEFAULT_REQUIRE_APPROVAL: list[tuple[str, str]] = [
    ("DROP TABLE *", "Dropping tables requires approval"),
    ("ALTER TABLE * DROP COLUMN *", "Dropping columns requires approval"),
    ("DELETE FROM *", "Deleting data requires approval"),
    ("CREATE OR REPLACE TABLE *", "Overwriting tables requires approval"),
    ("CREATE OR REPLACE VIEW *", "Overwriting views requires approval"),
    ("DELETE_APP *", "Deleting Databricks apps requires approval"),
    ("DELETE_JOB *", "Deleting jobs requires approval"),
    ("DELETE_JOB_RUN *", "Cancelling/deleting job runs requires approval"),
    ("DELETE_PIPELINE *", "Deleting pipelines requires approval"),
    ("DELETE_DASHBOARD *", "Deleting dashboards requires approval"),
    ("DELETE_UNITY_CATALOG *", "Deleting Unity Catalog objects requires approval"),
    ("DELETE_UC_GRANT *", "Revoking UC grants requires approval"),
    ("DELETE_UC_STORAGE *", "Deleting UC storage credentials requires approval"),
    ("DELETE_UC_CONNECTION *", "Deleting UC connections requires approval"),
    ("DELETE_UC_SECURITY *", "Deleting UC security policies requires approval"),
    ("DELETE_UC_MONITOR *", "Deleting UC monitors requires approval"),
    ("DELETE_UC_SHARING *", "Deleting UC sharing requires approval"),
    ("DELETE_METRIC_VIEW *", "Deleting metric views requires approval"),
    ("DELETE_KNOWLEDGE_ASSISTANT *", "Deleting knowledge assistants requires approval"),
    ("DELETE_SUPERVISOR_AGENT *", "Deleting supervisor agents requires approval"),
    ("DELETE_GENIE_SPACE *", "Deleting Genie spaces requires approval"),
    ("DELETE_VS_ENDPOINT *", "Deleting vector search endpoints requires approval"),
    ("DELETE_VS_INDEX *", "Deleting vector search indexes requires approval"),
    ("DELETE_VECTOR_SEARCH *", "Deleting vector search resources requires approval"),
    ("DELETE_LAKEBASE_DATABASE *", "Deleting Lakebase databases requires approval"),
    ("DELETE_LAKEBASE_BRANCH *", "Deleting Lakebase branches requires approval"),
    ("DELETE_LAKEBASE_SYNC *", "Deleting Lakebase sync configs requires approval"),
    ("DELETE_FILE *", "Deleting files requires approval"),
    ("DELETE_WORKSPACE *", "Deleting workspace resources requires approval"),
    ("GRANT *", "Granting permissions via UC tool requires approval"),
    ("REVOKE *", "Revoking permissions via UC tool requires approval"),
    ("EXECUTE_CODE *", "Executing arbitrary code on a cluster requires approval"),
]


def _normalize_sql(sql: str) -> str:
    """Strip comments, IF EXISTS noise, collapse whitespace."""
    text = sql.strip().rstrip(";").strip()
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text = re.sub(r"--[^\n]*", " ", text)
    text = re.sub(r"\bIF\s+NOT\s+EXISTS\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bIF\s+EXISTS\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class PolicyEngine:
    """Match actions against always-block and require-approval rules."""

    def __init__(self, use_defaults: bool = True) -> None:
        self.always_block: list[PolicyRule] = []
        self.require_approval: list[PolicyRule] = []

        if use_defaults:
            for pattern, desc in _DEFAULT_ALWAYS_BLOCK:
                self.always_block.append(PolicyRule(pattern, CheckpointDecision.BLOCK, desc))
            for pattern, desc in _DEFAULT_REQUIRE_APPROVAL:
                self.require_approval.append(PolicyRule(pattern, CheckpointDecision.HOLD_FOR_APPROVAL, desc))

    def check(self, action: Action, mode: AgentGuardMode) -> tuple[CheckpointDecision, Optional[str]]:
        """Returns (decision, matching rule description or None)."""
        texts_to_check = self._action_to_policy_texts(action)
        if not texts_to_check:
            return CheckpointDecision.AUTO_APPROVE, None

        worst_decision = CheckpointDecision.AUTO_APPROVE
        worst_rule: Optional[str] = None

        for text in texts_to_check:
            for rule in self.always_block:
                if rule.matches(text):
                    if mode == AgentGuardMode.MONITOR_ONLY:
                        return (
                            CheckpointDecision.WOULD_BLOCK,
                            f"[monitor] {rule.description} (pattern: {rule.pattern})",
                        )
                    return (
                        CheckpointDecision.BLOCK,
                        f"{rule.description} (pattern: {rule.pattern})",
                    )

            for rule in self.require_approval:
                if rule.matches(text):
                    if worst_decision != CheckpointDecision.FLAG:
                        worst_decision = CheckpointDecision.FLAG
                        worst_rule = f"{rule.description} (pattern: {rule.pattern})"

        if worst_decision != CheckpointDecision.AUTO_APPROVE:
            return worst_decision, worst_rule

        return CheckpointDecision.AUTO_APPROVE, None

    def _action_to_policy_texts(self, action: Action) -> list[str]:
        """Normalized SQL lines or `OPERATION resource_id` for non-SQL."""
        if action.sql_statement:
            raw_statements = action.sql_statement.split(";")
            texts = []
            for stmt in raw_statements:
                normalized = _normalize_sql(stmt)
                if normalized:
                    texts.append(normalized)
            return texts if texts else []

        if action.operation:
            resource = action.target_resource_id or ""
            return [f"{action.operation} {resource}"]

        return []
