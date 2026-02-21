"""ASI diagnostics: convert MLflow Feedback to GEPA (score, diagnostics) contract.

Collects failure diagnostics so the adapter's make_reflective_dataset() can
provide actionable context to GEPA's reflection LM.
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

    Returns:
        Float score or None if the feedback should be excluded.
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
    """Convert a list of MLflow Feedback objects to GEPA (score, diagnostics).

    Computes the mean score across all non-skipped feedbacks and builds
    a diagnostics dict with per-scorer results.

    Args:
        feedbacks: List of MLflow Feedback objects from running scorers

    Returns:
        Tuple of (composite_score, diagnostics_dict)
        - composite_score: 0.0-1.0 mean across all scorable feedbacks
        - diagnostics_dict: per-scorer name -> {score, rationale, value}
    """
    scores = []
    diagnostics: dict[str, Any] = {}
    failure_messages: list[str] = []

    for fb in feedbacks:
        score = feedback_to_score(fb)
        name = fb.name or "unnamed"

        if score is None:
            diagnostics[name] = {
                "score": None,
                "value": fb.value,
                "rationale": fb.rationale or "",
                "status": "skipped",
            }
            continue

        scores.append(score)
        diagnostics[name] = {
            "score": score,
            "value": fb.value,
            "rationale": fb.rationale or "",
            "status": "pass" if score >= 0.5 else "fail",
        }

        # Collect failure messages for reflection dataset
        if score < 1.0:
            failure_messages.append(
                f"Scorer '{name}' returned {fb.value}: {fb.rationale or 'no rationale'}"
            )

    composite = sum(scores) / len(scores) if scores else 0.0

    diagnostics["_summary"] = {
        "composite_score": composite,
        "total_scorers": len(feedbacks),
        "scored": len(scores),
        "skipped": len(feedbacks) - len(scores),
        "passed": sum(1 for s in scores if s >= 0.5),
        "failed": sum(1 for s in scores if s < 0.5),
    }
    diagnostics["_failure_messages"] = failure_messages

    return composite, diagnostics
