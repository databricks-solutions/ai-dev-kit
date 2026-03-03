"""MemAlign integration for aligning judges with human feedback.

MemAlign aligns judges with human feedback via dual-memory:
  - Semantic memory: generalizable evaluation principles
  - Episodic memory: specific edge cases and corrections

Alignment traces are stored per-skill in:
    .test/skills/<skill>/alignment_traces.yaml

Populated via ``scripts/review.py --align`` where a human corrects
judge verdicts. MemAlign learns principles from corrections,
improving judge accuracy over time.

Only 2-10 examples are needed for visible improvement.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_alignment_traces(skill_name: str) -> list[dict[str, Any]]:
    """Load human-corrected alignment traces for a skill.

    Traces are stored in .test/skills/<skill>/alignment_traces.yaml
    with format:
        - inputs: {prompt: "..."}
          outputs: {response: "..."}
          expected_value: true/false or 0.0-1.0
          rationale: "Human explanation of correct verdict"

    Returns:
        List of trace dicts, or empty list if no traces found.
    """
    traces_path = Path(".test/skills") / skill_name / "alignment_traces.yaml"
    if not traces_path.exists():
        return []

    try:
        with open(traces_path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("Failed to load alignment traces for %s: %s", skill_name, e)
        return []


def align_judge(
    skill_name: str,
    judge: Any,
    reflection_lm: str = "openai:/gpt-4o-mini",
) -> Any:
    """Align a judge with human feedback using MemAlign.

    If fewer than 3 alignment traces exist, returns the judge unchanged.
    Otherwise, uses MemAlignOptimizer to learn evaluation principles
    from human corrections and returns an aligned judge.

    Args:
        skill_name: Name of the skill to load traces for.
        judge: An MLflow judge (from make_judge or similar).
        reflection_lm: LLM for MemAlign's reflection step.

    Returns:
        Aligned judge if enough traces exist, otherwise original judge.
    """
    traces = load_alignment_traces(skill_name)
    if len(traces) < 3:
        if traces:
            logger.info(
                "Only %d alignment traces for %s (need >=3). Using base judge.",
                len(traces), skill_name,
            )
        return judge

    try:
        from mlflow.genai.judges.optimizers import MemAlignOptimizer

        optimizer = MemAlignOptimizer(reflection_lm=reflection_lm)
        aligned = judge.align(traces=traces, optimizer=optimizer)
        logger.info(
            "Aligned judge with %d traces for %s",
            len(traces), skill_name,
        )
        return aligned
    except ImportError:
        logger.warning(
            "MemAlignOptimizer not available. Install mlflow-deepeval for alignment support."
        )
        return judge
    except Exception as e:
        logger.warning("MemAlign alignment failed for %s: %s", skill_name, e)
        return judge
