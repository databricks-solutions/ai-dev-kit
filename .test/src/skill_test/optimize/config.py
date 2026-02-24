"""GEPA configuration presets for skill optimization.

Uses the optimize_anything API with GEPAConfig/EngineConfig/ReflectionConfig.
"""

import os
import warnings

from gepa.optimize_anything import GEPAConfig, EngineConfig, ReflectionConfig, RefinerConfig

DEFAULT_REFLECTION_LM = os.environ.get(
    "GEPA_REFLECTION_LM", "databricks/databricks-claude-opus-4-6"
)

DEFAULT_GEN_LM = os.environ.get(
    "GEPA_GEN_LM", "databricks/databricks-claude-sonnet-4-6"
)

# ---------------------------------------------------------------------------
# Register Databricks models with litellm so it knows their true context
# windows.  Without this, litellm may fuzzy-match to a similar model with
# different limits, or worse, the Databricks serving endpoint may reject
# requests that exceed a vLLM-configured max_model_len.
#
# NOTE: This does NOT override the endpoint's own max_model_len setting.
# If the Databricks endpoint itself is configured with a low limit (e.g.
# 8192), you must either reconfigure the endpoint or use a different
# provider (openai/, anthropic/) whose endpoints support larger contexts.
# ---------------------------------------------------------------------------
def _configure_litellm_retries() -> None:
    """Configure litellm to retry on transient errors (429, 529, 500).

    GEPA calls litellm.completion() without passing num_retries, so we
    set it globally.  This handles Anthropic 529 "Overloaded" errors,
    rate limits, and other transient failures with exponential backoff.
    """
    try:
        import litellm
        litellm.num_retries = 5
        litellm.request_timeout = 120  # seconds per attempt
        # Drop log noise from retries
        litellm.suppress_debug_info = True
    except ImportError:
        pass


def _register_litellm_models() -> None:
    """Register Databricks model context windows with litellm."""
    try:
        import litellm
        _models = {
            "databricks/databricks-claude-opus-4-6": {
                "max_tokens": 32_000,
                "max_input_tokens": 200_000,
                "max_output_tokens": 32_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-claude-sonnet-4-6": {
                "max_tokens": 16_000,
                "max_input_tokens": 200_000,
                "max_output_tokens": 16_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
            "databricks/databricks-gpt-5-2": {
                "max_tokens": 128_000,
                "max_input_tokens": 272_000,
                "max_output_tokens": 128_000,
                "litellm_provider": "databricks",
                "mode": "chat",
                "input_cost_per_token": 0,
                "output_cost_per_token": 0,
            },
        }
        for model_name, model_info in _models.items():
            litellm.model_cost[model_name] = model_info
    except ImportError:
        pass


_register_litellm_models()
_configure_litellm_retries()


# Overhead multiplier: the reflection prompt is roughly this many times
# the raw candidate tokens (includes background, ASI, framing).
_REFLECTION_OVERHEAD_MULTIPLIER = 3

PRESETS: dict[str, GEPAConfig] = {
    "quick": GEPAConfig(
        engine=EngineConfig(max_metric_calls=15, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
        refiner=RefinerConfig(max_refinements=1),
    ),
    "standard": GEPAConfig(
        engine=EngineConfig(max_metric_calls=50, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
        refiner=RefinerConfig(max_refinements=1),
    ),
    "thorough": GEPAConfig(
        engine=EngineConfig(max_metric_calls=150, parallel=True),
        reflection=ReflectionConfig(reflection_lm=DEFAULT_REFLECTION_LM),
        refiner=RefinerConfig(max_refinements=1),
    ),
}

# Base max_metric_calls per preset (used to scale by component count)
PRESET_BASE_CALLS: dict[str, int] = {
    "quick": 15,
    "standard": 50,
    "thorough": 150,
}

# Maximum total metric calls per pass to avoid runaway runtimes.
# With many components, uncapped scaling (e.g., 50 * 17 = 850) can cause
# multi-hour hangs with slower reflection models like Sonnet.
MAX_METRIC_CALLS_PER_PASS = 300

# Models known to be fast enough for large multi-component optimization.
# Other models get the metric-call cap applied.
_FAST_REFLECTION_MODELS = {
    "databricks/databricks-claude-opus-4-6",
    "databricks/databricks-gpt-5-2",
    "openai/gpt-4o",
    "anthropic/claude-opus-4-6",
}


def validate_databricks_env() -> None:
    """Check that DATABRICKS_API_BASE is set correctly for litellm.

    litellm's Databricks provider requires:
        DATABRICKS_API_BASE=https://<workspace>.cloud.databricks.com/serving-endpoints

    A common mistake is omitting /serving-endpoints, which causes 404 errors.
    """
    api_base = os.environ.get("DATABRICKS_API_BASE", "")
    if api_base and not api_base.rstrip("/").endswith("/serving-endpoints"):
        fixed = api_base.rstrip("/") + "/serving-endpoints"
        warnings.warn(
            f"DATABRICKS_API_BASE={api_base!r} is missing '/serving-endpoints' suffix. "
            f"litellm will get 404 errors. Automatically fixing to: {fixed}",
            stacklevel=2,
        )
        os.environ["DATABRICKS_API_BASE"] = fixed


def validate_reflection_context(
    reflection_lm: str,
    total_candidate_tokens: int,
) -> None:
    """Warn if the candidate is likely too large for the reflection model.

    Queries litellm's model registry for the model's max_input_tokens and
    compares against the estimated reflection prompt size.

    Note: this checks litellm's *client-side* knowledge of the model.  The
    Databricks serving endpoint may have a *different* (lower) limit set via
    vLLM's ``max_model_len``.  If you see ``BadRequestError`` with
    ``max_model_len`` in the message, the endpoint itself is the bottleneck --
    switch to a provider whose endpoint supports your context needs (e.g.
    ``openai/gpt-4o`` or ``anthropic/claude-sonnet-4-5-20250514``).
    """
    try:
        import litellm
        info = litellm.get_model_info(reflection_lm)
        limit = info.get("max_input_tokens") or info.get("max_tokens") or 0
    except Exception:
        return  # can't determine limit -- skip check

    if limit <= 0:
        return

    estimated_prompt = total_candidate_tokens * _REFLECTION_OVERHEAD_MULTIPLIER
    if estimated_prompt > limit:
        raise ValueError(
            f"\nReflection model '{reflection_lm}' has a {limit:,}-token input limit "
            f"(per litellm), but the estimated reflection prompt is ~{estimated_prompt:,} "
            f"tokens ({total_candidate_tokens:,} candidate tokens x "
            f"{_REFLECTION_OVERHEAD_MULTIPLIER} overhead).\n\n"
            f"Fix: use a model with a larger context window:\n"
            f"  --reflection-lm 'databricks/databricks-claude-opus-4-6'   (200K)\n"
            f"  --reflection-lm 'openai/gpt-4o'                           (128K)\n"
            f"  --reflection-lm 'anthropic/claude-sonnet-4-5-20250514'    (200K)\n\n"
            f"Or set the environment variable:\n"
            f"  export GEPA_REFLECTION_LM='databricks/databricks-claude-opus-4-6'\n\n"
            f"If you already use a large-context model and still see 'max_model_len'\n"
            f"errors, the Databricks serving endpoint itself has a low context limit.\n"
            f"Switch to a non-Databricks provider (openai/ or anthropic/) instead.\n\n"
            f"  Current GEPA_REFLECTION_LM={os.environ.get('GEPA_REFLECTION_LM', '(not set)')}"
        )


def estimate_pass_duration(
    num_metric_calls: int,
    reflection_lm: str,
    total_candidate_tokens: int,
    num_dataset_examples: int = 7,
) -> float | None:
    """Estimate wall-clock seconds for one optimization pass.

    Metric calls are mostly fast local evaluations.  The slow part is
    reflection LLM calls, which happen roughly once per iteration
    (num_metric_calls / num_dataset_examples iterations).

    Returns None if estimation is not possible.
    """
    # Rough per-reflection latency (seconds) based on model class
    if reflection_lm in _FAST_REFLECTION_MODELS:
        secs_per_reflection = 5.0
    elif "sonnet" in reflection_lm.lower():
        secs_per_reflection = 20.0
    elif "haiku" in reflection_lm.lower():
        secs_per_reflection = 8.0
    else:
        secs_per_reflection = 15.0

    # Scale by candidate size (larger candidates → slower)
    size_factor = min(max(1.0, total_candidate_tokens / 10_000), 2.5)
    adjusted = secs_per_reflection * size_factor

    # Approximate iterations (each iteration evaluates all dataset examples)
    num_iterations = max(1, num_metric_calls // max(num_dataset_examples, 1))

    return num_iterations * adjusted


def get_preset(
    name: str,
    reflection_lm: str | None = None,
    num_components: int = 1,
    max_metric_calls_override: int | None = None,
) -> GEPAConfig:
    """Get a GEPA config preset by name, scaled by component count.

    When optimizing multiple components (skill + tool modules), GEPA's
    round-robin selector divides the budget across all of them.  We scale
    ``max_metric_calls`` so that *each component* receives the preset's
    base budget rather than splitting it.

    For slower reflection models (non-Opus/GPT-4o), the total metric calls
    are capped at ``MAX_METRIC_CALLS_PER_PASS`` to avoid multi-hour hangs.

    Args:
        name: One of "quick", "standard", "thorough"
        reflection_lm: Override reflection LM model string
        num_components: Number of GEPA components (used to scale budget)
        max_metric_calls_override: Explicit cap on metric calls per pass

    Returns:
        GEPAConfig instance
    """
    if name not in PRESETS:
        raise KeyError(f"Unknown preset '{name}'. Choose from: {list(PRESETS.keys())}")

    # Validate Databricks env if using databricks/ prefix
    effective_lm = reflection_lm or DEFAULT_REFLECTION_LM
    if isinstance(effective_lm, str) and effective_lm.startswith("databricks/"):
        validate_databricks_env()

    base_calls = PRESET_BASE_CALLS[name]
    scaled_calls = base_calls * max(num_components, 1)

    # Apply explicit override if provided
    if max_metric_calls_override is not None:
        scaled_calls = max_metric_calls_override
    # Cap for slower models to avoid multi-hour hangs
    elif effective_lm not in _FAST_REFLECTION_MODELS and scaled_calls > MAX_METRIC_CALLS_PER_PASS:
        warnings.warn(
            f"Capping metric calls from {scaled_calls} to {MAX_METRIC_CALLS_PER_PASS} "
            f"for reflection model '{effective_lm}'. "
            f"Use --max-metric-calls to override, or use a faster model "
            f"(e.g., databricks/databricks-claude-opus-4-6).",
            stacklevel=2,
        )
        scaled_calls = MAX_METRIC_CALLS_PER_PASS

    config = PRESETS[name]
    config = GEPAConfig(
        engine=EngineConfig(
            max_metric_calls=scaled_calls,
            parallel=config.engine.parallel,
        ),
        reflection=ReflectionConfig(
            reflection_lm=reflection_lm or config.reflection.reflection_lm,
            reflection_minibatch_size=config.reflection.reflection_minibatch_size,
            skip_perfect_score=config.reflection.skip_perfect_score,
        ),
        merge=config.merge,
        refiner=config.refiner,
        tracking=config.tracking,
    )
    return config
