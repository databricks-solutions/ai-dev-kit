"""ASI diagnostics: convert MLflow Feedback to optimize_anything SideInfo.

Builds an Actionable Side Information dict from scorer feedback so GEPA's
reflection LM gets structured context about what went wrong with each scorer.
Failure details are surfaced via the ``_failures`` key in the returned dict.

Also provides ``skillbench_to_asi()`` for the SkillBench-style evaluator,
which produces GEPA-optimized side info with standard diagnostic keys
(Error, Expected, Actual) and ``skill_md_specific_info`` for per-component
routing.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from mlflow.entities import Feedback

if TYPE_CHECKING:
    from .assertions import AssertionResult

from .assertions import (
    summarize_failures as _summarize_failures,
    _classify_assertion,
    _extract_content,
)


def feedback_to_score(feedback: Feedback) -> float | None:
    """Convert a single MLflow Feedback to a numeric score.

    Mapping:
        "yes" -> 1.0
        "no"  -> 0.0
        "skip" -> None (excluded from scoring)
        numeric -> float(value)
    """
    value = feedback.value
    if value == "yes":
        return 1.0
    elif value == "no":
        return 0.0
    elif value == "skip":
        return None
    else:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def feedback_to_asi(feedbacks: list[Feedback]) -> tuple[float, dict[str, Any]]:
    """Convert MLflow Feedback objects to optimize_anything (score, SideInfo).

    Computes the mean score across non-skipped feedbacks and builds a
    SideInfo dict.  Failure diagnostics are collected in the ``_failures``
    key so GEPA's reflection LM sees actionable context directly in the
    side_info dict (no ``oa.log()`` needed).

    Args:
        feedbacks: List of MLflow Feedback objects from running scorers

    Returns:
        Tuple of (composite_score, side_info_dict)
    """
    scores = []
    side_info: dict[str, Any] = {}
    failures: list[str] = []

    for fb in feedbacks:
        score = feedback_to_score(fb)
        name = fb.name or "unnamed"

        if score is None:
            side_info[name] = {
                "score": None,
                "value": fb.value,
                "rationale": fb.rationale or "",
                "status": "skipped",
            }
            continue

        scores.append(score)
        side_info[name] = {
            "score": score,
            "value": fb.value,
            "rationale": fb.rationale or "",
            "status": "pass" if score >= 0.5 else "fail",
        }

        # Collect failure diagnostics for GEPA reflection
        if score < 1.0:
            failures.append(
                f"Scorer '{name}' returned {fb.value}: {fb.rationale or 'no rationale'}"
            )

    composite = sum(scores) / len(scores) if scores else 0.0

    side_info["_summary"] = {
        "composite_score": composite,
        "total_scorers": len(feedbacks),
        "scored": len(scores),
        "skipped": len(feedbacks) - len(scores),
        "passed": sum(1 for s in scores if s >= 0.5),
        "failed": sum(1 for s in scores if s < 0.5),
    }

    if failures:
        side_info["_failures"] = "\n".join(failures)

    return composite, side_info


def build_rich_asi(
    feedbacks: list[Feedback],
    *,
    generated_response: str | None = None,
    skill_coverage: dict[str, Any] | None = None,
    task_prompt: str | None = None,
    per_dimension_scores: dict[str, float] | None = None,
) -> tuple[float, dict[str, Any]]:
    """Build enriched ASI with categorized diagnostics for GEPA reflection.

    Extends ``feedback_to_asi()`` with additional context that helps GEPA's
    reflection LM understand *why* scores changed and make better edits.

    Args:
        feedbacks: MLflow Feedback objects from all scoring layers
        generated_response: Truncated LLM output (so reflection sees what skill produced)
        skill_coverage: Which patterns/facts found vs missing in SKILL.md
        task_prompt: The test prompt (so reflection understands context)
        per_dimension_scores: Per-dimension scores dict for Pareto-frontier selection

    Returns:
        Tuple of (composite_score, enriched_side_info_dict)
    """
    composite, side_info = feedback_to_asi(feedbacks)

    # Categorize feedbacks by layer
    categories: dict[str, list[str]] = {
        "skill_content": [],
        "generated_response": [],
        "reference": [],
        "structure": [],
    }
    for fb in feedbacks:
        name = fb.name or ""
        score = feedback_to_score(fb)
        if score is None:
            continue
        entry = f"{name}: {'pass' if score >= 0.5 else 'FAIL'} ({fb.rationale or ''})"
        if name.startswith("skill_content_"):
            categories["skill_content"].append(entry)
        elif name.startswith("skill_"):
            categories["structure"].append(entry)
        else:
            categories["generated_response"].append(entry)

    side_info["_diagnostics_by_layer"] = {
        k: v for k, v in categories.items() if v
    }

    if generated_response is not None:
        side_info["_generated_response"] = generated_response[:2000]

    if skill_coverage:
        side_info["_skill_coverage"] = skill_coverage

    if task_prompt:
        side_info["_task_prompt"] = task_prompt[:500]

    if per_dimension_scores:
        side_info["scores"] = per_dimension_scores

    return composite, side_info


# ---------------------------------------------------------------------------
# SkillBench → GEPA side info
# ---------------------------------------------------------------------------


def skillbench_to_asi(
    with_results: list[AssertionResult],
    without_results: list[AssertionResult],
    *,
    task_prompt: str | None = None,
    scores: dict[str, float] | None = None,
    with_response: str | None = None,
    without_response: str | None = None,
    reference_answer: str | None = None,
    candidate: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Convert SkillBench assertion results to GEPA-optimized side info.

    Produces a flat dict with GEPA's standard diagnostic keys plus actual
    agent output and reference answers so the reflection LM can make
    targeted SKILL.md edits.

    Budget: ~1480 chars/example (Task 200 + Error ~80 + Expected 500 +
    Actual 500 + scores ~200). With minibatch=3: ~4440 chars (~1100 tokens).

    Keys produced (all optional, only non-empty included):
        ``Task``     — the task prompt (truncated at 200 chars)
        ``Error``    — compact NEEDS_SKILL/REGRESSION assertion labels
        ``Expected`` — reference answer from ground_truth.yaml (truncated at 500 chars)
        ``Actual``   — agent response WITH skill (truncated at 500 chars)
        ``skill_md_specific_info`` — sub-dict with ``Regressions`` for per-component routing
        ``scores``   — score breakdown promoted to objective_scores by GEPA

    Args:
        with_results: Assertion results from the WITH-skill run.
        without_results: Assertion results from the WITHOUT-skill run.
        task_prompt: The test prompt (for reflection context).
        scores: Score breakdown dict (effectiveness, pass_with, structure, final).
        with_response: Agent output WITH skill (truncated at 500 chars).
        without_response: Agent output WITHOUT skill (reserved for future use).
        reference_answer: Ground truth answer from ground_truth.yaml.
        candidate: Full candidate dict for tool-specific diagnostic routing.

    Returns:
        Side info dict for optimize_anything.
    """
    diag = _summarize_failures(with_results, without_results)

    side_info: dict[str, Any] = {}

    # 1. Task context (short — just enough for the reflection LM)
    if task_prompt:
        side_info["Task"] = task_prompt[:200]

    # 2. Error: what specific assertions fail (from assertions.py)
    if diag.get("Error"):
        side_info["Error"] = diag["Error"]

    # 3. Expected: reference answer (what correct output looks like)
    if reference_answer:
        side_info["Expected"] = reference_answer[:500]

    # 4. Actual: agent response WITH skill (what was produced)
    if with_response is not None:
        side_info["Actual"] = with_response[:500]

    # 5. Regressions: routed to skill_md component
    if diag.get("Regressions"):
        side_info["skill_md_specific_info"] = {"Regressions": diag["Regressions"]}

    # 5b. Route tool-specific failures to {component}_specific_info
    if candidate:
        tool_components = {k: v for k, v in candidate.items() if k.startswith("tools_")}
        for comp_name, comp_text in tool_components.items():
            comp_text_lower = comp_text.lower()
            tool_failures = []
            for w, wo in zip(with_results, without_results):
                label = _classify_assertion(w, wo)
                if label in ("NEEDS_SKILL", "REGRESSION"):
                    content = _extract_content(w)
                    if content.lower() in comp_text_lower:
                        tool_failures.append(f"{label}: {w.assertion_type} — '{content}'")
            if tool_failures:
                side_info[f"{comp_name}_specific_info"] = {
                    "Related_assertions": "\n".join(tool_failures)
                }

    # 6. Scores: needed for GEPA Pareto tracking
    if scores:
        side_info["scores"] = scores

    return side_info
