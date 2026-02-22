"""ASI diagnostics: convert MLflow Feedback to optimize_anything SideInfo.

Routes failure diagnostics through oa.log() so GEPA's reflection LM gets
actionable context about what went wrong with each scorer.
"""

from typing import Any

import gepa.optimize_anything as oa
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
    SideInfo dict. Logs failures via oa.log() so GEPA's reflection LM
    sees actionable failure context.

    Args:
        feedbacks: List of MLflow Feedback objects from running scorers

    Returns:
        Tuple of (composite_score, side_info_dict)
    """
    scores = []
    side_info: dict[str, Any] = {}

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

        # Route failures through oa.log() for GEPA reflection
        if score < 1.0:
            oa.log(f"Scorer '{name}' returned {fb.value}: {fb.rationale or 'no rationale'}")

    composite = sum(scores) / len(scores) if scores else 0.0

    side_info["_summary"] = {
        "composite_score": composite,
        "total_scorers": len(feedbacks),
        "scored": len(scores),
        "skipped": len(feedbacks) - len(scores),
        "passed": sum(1 for s in scores if s >= 0.5),
        "failed": sum(1 for s in scores if s < 0.5),
    }

    return composite, side_info
