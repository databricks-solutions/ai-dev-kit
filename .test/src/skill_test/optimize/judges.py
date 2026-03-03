"""MLflow judge factories for skill evaluation.

Replaces the 6 separate judge calls and binary assertion layer with three
focused judges that provide both scores AND rich rationale for GEPA's
reflection LM.

Judges:
    quality_judge   — Scores a single response (0.0-1.0) against expectations.
    effectiveness_judge — Compares WITH vs WITHOUT responses, returns verdict.
    regression_judge — Identifies specific ways a skill harms responses.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from mlflow.genai.judges import make_judge

logger = logging.getLogger(__name__)


@dataclass
class JudgeFeedback:
    """Structured feedback from a judge call."""

    value: float | str
    rationale: str
    name: str


def _safe_parse_score(raw_value: Any) -> float:
    """Convert judge output to a float score in [0.0, 1.0].

    Handles: bool, "yes"/"no", numeric, float-as-string.
    """
    if isinstance(raw_value, (int, float)):
        return max(0.0, min(1.0, float(raw_value)))
    if isinstance(raw_value, bool):
        return 1.0 if raw_value else 0.0
    if isinstance(raw_value, str):
        low = raw_value.strip().lower()
        if low == "yes":
            return 1.0
        if low == "no":
            return 0.0
        try:
            return max(0.0, min(1.0, float(low)))
        except ValueError:
            pass
    return 0.0


# ---------------------------------------------------------------------------
# Quality judge — primary scorer for a single response
# ---------------------------------------------------------------------------

_QUALITY_INSTRUCTIONS = """\
You are an expert evaluator for Databricks skill documentation quality.
Rate the response on a scale from 0.0 to 1.0 based on how well it addresses
the user's question using correct, complete, and relevant information.

## Evaluation Criteria

1. **Relevance** (does the response address the question?)
2. **Completeness** (are all parts of the question answered?)
3. **Correctness** (are the facts and API references accurate?)
4. **Pattern adherence** (does the response follow expected code patterns?)
5. **API accuracy** (are function names, parameters, and syntax correct?)

## Expected Facts and Patterns

{{ expectations.expected_facts }}

{{ expectations.expected_patterns }}

## Skill-Specific Guidelines

{{ expectations.guidelines }}

## Input

Question: {{ inputs.prompt }}
Response: {{ outputs.response }}

## Instructions

Return a score between 0.0 and 1.0 where:
- 1.0 = perfect response, all facts present, all patterns correct
- 0.7 = good response, most facts present, minor gaps
- 0.4 = partial response, significant gaps or inaccuracies
- 0.1 = poor response, mostly wrong or off-topic
- 0.0 = completely wrong or empty

Provide detailed rationale explaining:
- Which expected facts are present vs missing
- Which patterns are correctly followed vs violated
- Specific API or syntax errors found
- What would need to change to improve the score
"""


def create_skill_quality_judge(
    skill_guidelines: list[str] | None = None,
) -> Any:
    """Create a universal quality judge for scoring responses.

    Uses ``make_judge`` with float output. Incorporates skill-specific
    guidelines as "semantic memory" when available.

    Args:
        skill_guidelines: Optional per-skill evaluation principles from
            ground_truth.yaml guidelines across all test cases.

    Returns:
        A callable judge that accepts (inputs, outputs, expectations) and
        returns an MLflow Feedback object with float value + rationale.
    """
    instructions = _QUALITY_INSTRUCTIONS
    if skill_guidelines:
        principles = "\n".join(f"- {g}" for g in skill_guidelines)
        instructions += (
            "\n\n## Domain-Specific Principles\n"
            f"{principles}\n"
        )

    return make_judge(
        name="skill_quality",
        instructions=instructions,
        feedback_value_type=float,
    )


# ---------------------------------------------------------------------------
# Effectiveness judge — WITH vs WITHOUT comparison
# ---------------------------------------------------------------------------

_EFFECTIVENESS_INSTRUCTIONS = """\
You are comparing two responses to the same question to determine whether
a skill document helped or hurt the agent's response quality.

## Context

- **WITH-skill response**: Generated with the skill document in context.
- **WITHOUT-skill response**: Generated without any skill document.

## Expected Information

{{ expectations.expected_facts }}

## Input

Question: {{ inputs.prompt }}

WITH-skill response:
{{ inputs.with_response }}

WITHOUT-skill response:
{{ inputs.without_response }}

## Instructions

Determine whether the skill IMPROVED, maintained (SAME), or REGRESSED the
response quality. Return one of exactly: "improved", "same", "regressed".

An "improved" verdict means the WITH-skill response is meaningfully better:
more accurate facts, better code patterns, correct API usage that the
WITHOUT response got wrong.

A "regressed" verdict means the skill actively HURT the response: introduced
incorrect information, deprecated APIs, or confused the agent.

"same" means no meaningful difference.

Provide detailed rationale explaining:
- What the skill added or removed from the response
- Specific facts/patterns that differ between WITH and WITHOUT
- Whether the skill taught something the model didn't already know
- If regressed: what specifically the skill got wrong
"""


def create_effectiveness_judge() -> Any:
    """Create a WITH vs WITHOUT comparison judge.

    Returns a judge that evaluates whether the skill helped, hurt, or made
    no difference. Returns Feedback with value in {"improved", "same", "regressed"}
    and detailed rationale for GEPA.
    """
    return make_judge(
        name="skill_effectiveness",
        instructions=_EFFECTIVENESS_INSTRUCTIONS,
        feedback_value_type=str,
    )


# ---------------------------------------------------------------------------
# Regression judge — identifies how a skill harms responses
# ---------------------------------------------------------------------------

_REGRESSION_INSTRUCTIONS = """\
You are a regression detector for Databricks skill documents. Your job is
to identify specific ways that a skill document HARMS agent responses.

## Context

The skill document was added to an agent's context. Compare the agent's
response WITH the skill to the response WITHOUT it.

## Input

Question: {{ inputs.prompt }}

WITH-skill response:
{{ inputs.with_response }}

WITHOUT-skill response:
{{ inputs.without_response }}

## Instructions

Identify specific regressions introduced by the skill. Return "yes" if
regressions are found, "no" if the skill is harmless.

Common regression patterns:
1. **Deprecated APIs** — skill teaches old APIs the model already uses correctly
2. **Verbosity** — skill adds noise that confuses the model
3. **Contradicting correct knowledge** — model was right, skill made it wrong
4. **Wrong examples** — skill's code examples have errors the model copies
5. **Over-specification** — skill's rigid patterns prevent correct alternatives

For each regression found, explain:
- WHAT specific content in the skill caused the regression
- WHY it made the response worse
- WHAT to remove or change in the skill to fix it
"""


def create_regression_judge() -> Any:
    """Create a regression detection judge.

    Returns structured feedback about what to REMOVE from the skill.
    Rationale goes directly to GEPA's reflection LM for targeted fixes.
    """
    return make_judge(
        name="skill_regression",
        instructions=_REGRESSION_INSTRUCTIONS,
        feedback_value_type=bool,
    )


# ---------------------------------------------------------------------------
# Helper: run a judge safely and return structured feedback
# ---------------------------------------------------------------------------

def run_judge_safe(
    judge: Any,
    *,
    inputs: dict[str, Any],
    outputs: dict[str, Any] | None = None,
    expectations: dict[str, Any] | None = None,
    name: str = "judge",
) -> JudgeFeedback:
    """Run a judge with error handling, return JudgeFeedback.

    Catches exceptions and returns a zero-score feedback with error rationale
    so that evaluation never crashes from a judge failure.
    """
    kwargs: dict[str, Any] = {"inputs": inputs}
    if outputs is not None:
        kwargs["outputs"] = outputs
    if expectations is not None:
        kwargs["expectations"] = expectations

    try:
        fb = judge(**kwargs)
        return JudgeFeedback(
            value=fb.value,
            rationale=fb.rationale or "",
            name=name,
        )
    except Exception as e:
        logger.warning("Judge '%s' failed: %s", name, e)
        return JudgeFeedback(
            value=0.0,
            rationale=f"Judge error: {e}",
            name=name,
        )
