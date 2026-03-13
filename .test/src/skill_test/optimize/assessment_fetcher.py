"""Fetch and match MLflow trace assessments for GEPA reflection injection.

Retrieves human/LLM feedback (assessments) from MLflow experiment traces
and matches them to optimization tasks so GEPA's reflection LM can learn
from real-world agent performance.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _prompt_hash(prompt: str) -> str:
    """Stable hash for matching assessments to tasks by prompt content."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def fetch_assessments(
    experiment_name: str,
    skill_name: str | None = None,
    tracking_uri: str = "databricks",
    max_traces: int = 100,
) -> list[dict[str, Any]]:
    """Fetch traces with assessments from an MLflow experiment.

    Each returned record contains the trace's input, assessments (Feedback
    objects), and metadata for downstream matching.

    Args:
        experiment_name: Full MLflow experiment path.
        skill_name: Optional filter — only include traces tagged with this skill.
        tracking_uri: MLflow tracking URI (default: "databricks").
        max_traces: Maximum number of traces to fetch.

    Returns:
        List of dicts with keys: trace_id, input, assessments, tags.
    """
    try:
        import mlflow
    except ImportError:
        logger.warning("mlflow not installed — skipping assessment fetch")
        return []

    from ..trace.mlflow_integration import _configure_mlflow

    _configure_mlflow(tracking_uri)

    try:
        experiment = mlflow.get_experiment_by_name(experiment_name)
    except Exception:
        experiment = None

    if experiment is None:
        logger.warning("Experiment not found: %s", experiment_name)
        return []

    try:
        traces_df = mlflow.search_traces(
            experiment_ids=[experiment.experiment_id],
            max_results=max_traces,
        )
    except Exception as e:
        logger.warning("Failed to search traces: %s", e)
        return []

    if traces_df is None or traces_df.empty:
        return []

    records: list[dict[str, Any]] = []
    for _, row in traces_df.iterrows():
        trace_id = getattr(row, "request_id", None) or getattr(row, "trace_id", "")
        if not trace_id:
            continue

        # Fetch the full trace to get assessments/feedback
        try:
            trace = mlflow.get_trace(trace_id)
        except Exception:
            continue

        if trace is None:
            continue

        # Extract assessments (Feedback objects attached to the trace)
        assessments = []
        if hasattr(trace, "data") and hasattr(trace.data, "assessments"):
            assessments = trace.data.assessments or []
        elif hasattr(trace, "assessments"):
            assessments = trace.assessments or []

        if not assessments:
            continue

        # Extract trace input
        trace_input = ""
        if hasattr(trace, "data") and hasattr(trace.data, "request"):
            trace_input = str(trace.data.request or "")
        elif hasattr(row, "request"):
            trace_input = str(row.request or "")

        # Extract tags
        tags = {}
        if hasattr(trace, "info") and hasattr(trace.info, "tags"):
            tags = dict(trace.info.tags or {})

        # Filter by skill if specified
        if skill_name:
            trace_skill = tags.get("skill_name", tags.get("mlflow.source.name", ""))
            if skill_name.lower() not in trace_skill.lower() and trace_skill:
                continue

        records.append(
            {
                "trace_id": trace_id,
                "input": trace_input,
                "input_hash": _prompt_hash(trace_input) if trace_input else "",
                "assessments": assessments,
                "tags": tags,
            }
        )

    logger.info("Fetched %d traces with assessments from %s", len(records), experiment_name)
    return records


def summarize_assessment_patterns(records: list[dict[str, Any]]) -> str:
    """Summarize assessment patterns into text for GEPA reflection context.

    Aggregates thumbs-up/down counts and extracts common rationale themes
    so the reflection LM understands real-world feedback patterns.

    Args:
        records: Output of ``fetch_assessments()``.

    Returns:
        Human-readable summary string, or empty string if no data.
    """
    if not records:
        return ""

    total_assessments = 0
    positive = 0
    negative = 0
    rationales: list[str] = []

    for rec in records:
        for a in rec.get("assessments", []):
            total_assessments += 1
            name = getattr(a, "name", "") if not isinstance(a, dict) else a.get("name", "")
            value = getattr(a, "value", None) if not isinstance(a, dict) else a.get("value")
            rationale = getattr(a, "rationale", "") if not isinstance(a, dict) else a.get("rationale", "")

            # Classify as positive/negative
            if isinstance(value, (int, float)):
                if value >= 0.5:
                    positive += 1
                else:
                    negative += 1
            elif isinstance(value, str):
                lower = value.lower()
                if lower in ("thumbs_up", "positive", "yes", "good", "true"):
                    positive += 1
                elif lower in ("thumbs_down", "negative", "no", "bad", "false"):
                    negative += 1

            if rationale:
                rationales.append(f"[{name}] {rationale}")

    lines = [
        f"REAL-WORLD FEEDBACK ({total_assessments} assessments from {len(records)} traces):",
        f"  Positive: {positive}, Negative: {negative}",
    ]

    if rationales:
        lines.append("  Sample rationales:")
        for r in rationales[:10]:
            lines.append(f"    - {r[:200]}")

    return "\n".join(lines)


def match_assessments_to_tasks(
    records: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
) -> dict[str, list]:
    """Match assessment records to optimization tasks by ID or prompt hash.

    Returns a dict mapping task_id (or prompt hash) to the list of
    assessment Feedback objects from matching traces.

    Args:
        records: Output of ``fetch_assessments()``.
        tasks: Training tasks (each with "id" and/or "prompt" keys).

    Returns:
        Dict mapping task_id/prompt_hash to list of Feedback objects.
    """
    if not records or not tasks:
        return {}

    # Build lookup: input_hash → assessments
    hash_to_assessments: dict[str, list] = {}
    for rec in records:
        h = rec.get("input_hash", "")
        if h:
            hash_to_assessments.setdefault(h, []).extend(rec.get("assessments", []))

    matched: dict[str, list] = {}
    for task in tasks:
        task_id = task.get("id", "")
        prompt = task.get("prompt", task.get("input", ""))

        # Try matching by prompt hash
        if prompt:
            task_hash = _prompt_hash(prompt)
            if task_hash in hash_to_assessments:
                matched[task_id or task_hash] = hash_to_assessments[task_hash]
                continue

        # Try matching by task_id in trace tags
        if task_id:
            for rec in records:
                trace_task_id = rec.get("tags", {}).get("task_id", "")
                if trace_task_id == task_id:
                    matched.setdefault(task_id, []).extend(rec.get("assessments", []))

    return matched
