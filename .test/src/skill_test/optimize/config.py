"""GEPA configuration presets for skill optimization.

Uses the optimize_anything API with GEPAConfig/EngineConfig/ReflectionConfig.
"""

import os

from gepa.optimize_anything import GEPAConfig, EngineConfig, ReflectionConfig

DEFAULT_REFLECTION_LM = os.environ.get(
    "GEPA_REFLECTION_LM", "databricks/databricks-gpt-5-2"
)

PRESETS: dict[str, GEPAConfig] = {
    "quick": GEPAConfig(
        engine=EngineConfig(max_metric_calls=15, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
    ),
    "standard": GEPAConfig(
        engine=EngineConfig(max_metric_calls=50, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
    ),
    "thorough": GEPAConfig(
        engine=EngineConfig(max_metric_calls=150, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
    ),
}


def get_preset(name: str, reflection_lm: str | None = None) -> GEPAConfig:
    """Get a GEPA config preset by name, optionally overriding the reflection LM.

    Args:
        name: One of "quick", "standard", "thorough"
        reflection_lm: Override reflection LM model string

    Returns:
        GEPAConfig instance
    """
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Choose from: {list(PRESETS.keys())}")
    config = PRESETS[name]
    if reflection_lm:
        config = GEPAConfig(
            engine=config.engine,
            reflection=ReflectionConfig(
                reflection_lm=reflection_lm,
                reflection_minibatch_size=config.reflection.reflection_minibatch_size,
                skip_perfect_score=config.reflection.skip_perfect_score,
            ),
            merge=config.merge,
            refiner=config.refiner,
            tracking=config.tracking,
        )
    return config
