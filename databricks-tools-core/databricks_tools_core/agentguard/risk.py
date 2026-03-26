"""
AgentGuard risk (CP-3)

Weighted 0–100 score per action; optional scope violation adds a fixed penalty.
Thresholds map to flag / hold / block decisions.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from databricks_tools_core.agentguard.models import (
    Action,
    ActionCategory,
    CheckpointDecision,
)


class RiskScore(BaseModel):
    """Score, decision, and per-factor breakdown."""

    score: float = 0.0
    decision: CheckpointDecision = CheckpointDecision.AUTO_APPROVE
    breakdown: dict[str, float] = Field(default_factory=dict)


_ACTION_TYPE_SCORES = {
    "SELECT": 0,
    "DESCRIBE": 0,
    "SHOW": 0,
    "EXPLAIN": 0,
    "READ": 0,
    "LIST": 0,
    "GET": 0,
    "FIND_BY_NAME": 0,
    "INSERT": 30,
    "COPY_INTO": 35,
    "CREATE": 25,
    "UPLOAD": 25,
    "CREATE_DIRECTORY": 15,
    "GENERATE_PDF": 20,
    "UPDATE": 50,
    "MERGE": 60,
    "START": 35,
    "RESTART": 40,
    "STOP": 30,
    "MIGRATE": 40,
    "DEPLOY": 50,
    "DELETE": 80,
    "TRUNCATE": 90,
    "DROP": 95,
    "GRANT": 85,
    "REVOKE": 85,
    "EXECUTE_CODE": 75,
    "GENERATE_CREDENTIAL": 70,
    "START_CLUSTER": 45,
}

_ACTION_TYPE_SCORES_SORTED = sorted(
    _ACTION_TYPE_SCORES.items(),
    key=lambda x: len(x[0]),
    reverse=True,
)


def _score_action_type(action: Action) -> float:
    op = action.operation.upper()
    if op in _ACTION_TYPE_SCORES:
        return _ACTION_TYPE_SCORES[op]

    for keyword, score in _ACTION_TYPE_SCORES_SORTED:
        if keyword in op:
            return score

    if op.startswith("DELETE_"):
        return 80

    if op.startswith("MULTI("):
        inner = op.replace("MULTI(", "").rstrip(")")
        return _ACTION_TYPE_SCORES.get(inner, 50)

    category_defaults = {
        ActionCategory.READ: 0,
        ActionCategory.WRITE: 40,
        ActionCategory.DDL: 50,
        ActionCategory.DCL: 80,
        ActionCategory.ADMIN: 60,
        ActionCategory.EXTERNAL: 50,
        ActionCategory.UNKNOWN: 30,
    }
    return category_defaults.get(action.action_category, 30)


def _score_environment(action: Action) -> float:
    resource = (action.target_resource_id or "").lower()
    sql = (action.sql_statement or "").lower()
    combined = f"{resource} {sql}"

    if "production" in combined or "prod." in combined:
        return 90
    if "staging" in combined or "stg." in combined:
        return 40
    if "dev." in combined or "sandbox" in combined or "test" in combined:
        return 10

    return 30


def _score_blast_radius(action: Action) -> float:
    if action.rows_affected is not None:
        if action.rows_affected <= 1:
            return 5
        if action.rows_affected <= 100:
            return 15
        if action.rows_affected <= 10000:
            return 35
        if action.rows_affected <= 1000000:
            return 60
        return 85

    sql = (action.sql_statement or "").upper()
    if sql:
        if ("DELETE" in sql or "UPDATE" in sql) and "WHERE" not in sql:
            return 90
        if "DROP " in sql or "TRUNCATE " in sql:
            return 100
        if action.action_category == ActionCategory.READ:
            return 10
        if "WHERE" in sql:
            return 30

    op = action.operation.upper()
    if op.startswith("DELETE_"):
        return 70
    if op in ("START_CLUSTER", "EXECUTE_CODE"):
        return 40

    return 20


def _score_time_context(action: Action) -> float:
    return 25


def _score_behavioral(action: Action) -> float:
    return 15


def _sensitive_re(keyword: str) -> re.Pattern:
    return re.compile(rf"(?:^|[_.\/\s]){keyword}(?:$|[_.\/\s])", re.IGNORECASE)


_SENSITIVE_PATTERNS = [
    (_sensitive_re("pii"), 75),
    (_sensitive_re("phi"), 90),
    (_sensitive_re("financial"), 85),
    (_sensitive_re("credit.?card"), 90),
    (_sensitive_re("ssn"), 95),
    (_sensitive_re("password"), 90),
    (_sensitive_re("secret"), 80),
    (_sensitive_re("token"), 70),
    (_sensitive_re("salary"), 75),
    (_sensitive_re("medical"), 85),
    (_sensitive_re("hipaa"), 90),
    (_sensitive_re("gdpr"), 80),
    (_sensitive_re("sensitive"), 65),
    (_sensitive_re("confidential"), 70),
    (_sensitive_re("restricted"), 65),
    (_sensitive_re("personal"), 60),
]


def _score_data_sensitivity(action: Action) -> float:
    text = " ".join(
        filter(
            None,
            [
                action.target_resource_id,
                action.sql_statement,
                " ".join(action.tables_read),
                " ".join(action.tables_written),
            ],
        )
    )

    if not text:
        return 0

    max_score = 0
    for pattern, score in _SENSITIVE_PATTERNS:
        if pattern.search(text):
            max_score = max(max_score, score)

    return max_score


_DEFAULT_WEIGHTS = {
    "action_type": 0.25,
    "environment": 0.25,
    "blast_radius": 0.20,
    "time_context": 0.10,
    "behavioral": 0.10,
    "data_sensitivity": 0.10,
}

_DEFAULT_THRESHOLDS = {
    "flag_above": 35,
    "hold_above": 70,
    "block_above": 90,
}

_SCOPE_VIOLATION_PENALTY = 25


def compute_risk_score(
    action: Action,
    scope_violated: bool = False,
    weights: Optional[dict[str, float]] = None,
    thresholds: Optional[dict[str, float]] = None,
) -> RiskScore:
    """Weighted score; `scope_violated` adds a fixed penalty."""
    w = weights or _DEFAULT_WEIGHTS
    t = thresholds or _DEFAULT_THRESHOLDS

    breakdown = {
        "action_type": _score_action_type(action),
        "environment": _score_environment(action),
        "blast_radius": _score_blast_radius(action),
        "time_context": _score_time_context(action),
        "behavioral": _score_behavioral(action),
        "data_sensitivity": _score_data_sensitivity(action),
    }

    base_score = sum(breakdown[k] * w[k] for k in breakdown)

    penalty = _SCOPE_VIOLATION_PENALTY if scope_violated else 0
    breakdown["scope_violation_penalty"] = penalty

    final_score = min(100, base_score + penalty)

    if final_score >= t["block_above"]:
        decision = CheckpointDecision.BLOCK
    elif final_score >= t["hold_above"]:
        decision = CheckpointDecision.HOLD_FOR_APPROVAL
    elif final_score >= t["flag_above"]:
        decision = CheckpointDecision.FLAG
    else:
        decision = CheckpointDecision.AUTO_APPROVE

    return RiskScore(
        score=round(final_score, 2),
        decision=decision,
        breakdown={k: round(v, 2) for k, v in breakdown.items()},
    )
