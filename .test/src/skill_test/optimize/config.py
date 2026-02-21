"""GEPA configuration presets for skill optimization.

GEPA's optimize() accepts flat kwargs. Presets are stored as dicts
that get unpacked into gepa.optimize(**preset).
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class GEPAPreset:
    """Configuration preset for gepa.optimize() calls."""

    max_metric_calls: int
    reflection_lm: str = "openai/gpt-4o"
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


def get_preset(name: str) -> GEPAPreset:
    """Get a GEPA config preset by name.

    Args:
        name: One of "quick", "standard", "thorough"

    Returns:
        GEPAPreset instance

    Raises:
        KeyError: If preset name is not recognized
    """
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Choose from: {list(PRESETS.keys())}")
    return PRESETS[name]
