"""ASI diagnostics: convert MLflow Feedback to optimize_anything SideInfo.

Builds an Actionable Side Information dict from scorer feedback so GEPA's
reflection LM gets structured context about what went wrong with each scorer.
Failure details are surfaced via the ``_failures`` key in the returned dict.
"""

from typing import Any

from mlflow.entities import Feedback


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
