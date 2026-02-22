"""GEPA configuration presets for skill optimization.

GEPA's optimize() accepts flat kwargs. Presets are stored as dataclasses
that get unpacked into gepa.optimize(**preset.to_kwargs()).

The reflection LM defaults to Databricks Model Serving (databricks-gpt-5-2).
Override via the GEPA_REFLECTION_LM environment variable or the --reflection-lm flag.
"""

import os
from dataclasses import dataclass
from typing import Any


DEFAULT_REFLECTION_LM = os.environ.get(
    "GEPA_REFLECTION_LM", "databricks/databricks-gpt-5-2"
)


@dataclass
class GEPAPreset:
    """Configuration preset for gepa.optimize() calls."""

    max_metric_calls: int
    reflection_lm: str = DEFAULT_REFLECTION_LM
    candidate_selection_strategy: str = "pareto"
    reflection_minibatch_size: int = 3
    skip_perfect_score: bool = True
    display_progress_bar: bool = True

    def to_kwargs(self) -> dict[str, Any]:
        """Convert to kwargs dict for gepa.optimize()."""
        return {
            "max_metric_calls": self.max_metric_calls,
            "reflection_lm": self.reflection_lm,
            "candidate_selection_strategy": self.candidate_selection_strategy,
            "reflection_minibatch_size": self.reflection_minibatch_size,
            "skip_perfect_score": self.skip_perfect_score,
            "display_progress_bar": self.display_progress_bar,
        }


PRESETS: dict[str, GEPAPreset] = {
    "quick": GEPAPreset(max_metric_calls=15),
    "standard": GEPAPreset(max_metric_calls=50),
    "thorough": GEPAPreset(max_metric_calls=150),
}


def get_preset(name: str, reflection_lm: str | None = None) -> GEPAPreset:
    """Get a GEPA config preset by name, optionally overriding the reflection LM.

    Args:
        name: One of "quick", "standard", "thorough"
        reflection_lm: Override reflection LM model string (e.g., "databricks/databricks-gpt-5-2")

    Returns:
        GEPAPreset instance

    Raises:
        KeyError: If preset name is not recognized
    """
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Choose from: {list(PRESETS.keys())}")
    preset = PRESETS[name]
    if reflection_lm:
        preset = GEPAPreset(
            max_metric_calls=preset.max_metric_calls,
            reflection_lm=reflection_lm,
            candidate_selection_strategy=preset.candidate_selection_strategy,
            reflection_minibatch_size=preset.reflection_minibatch_size,
            skip_perfect_score=preset.skip_perfect_score,
            display_progress_bar=preset.display_progress_bar,
        )
    return preset
