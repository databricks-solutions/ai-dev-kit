"""MLflow judge factories for skill evaluation.

Replaces the 6 separate judge calls and binary assertion layer with three
focused judges that provide both scores AND rich rationale for GEPA's
reflection LM.

Judges:
    quality_judge   — Scores a single response (0.0-1.0) against expectations.
    effectiveness_judge — Compares WITH vs WITHOUT responses, returns verdict.
    regression_judge — Identifies specific ways a skill harms responses.

Judge model resolution (highest priority first):
    1. Explicit ``judge_model`` argument to factory functions
    2. ``GEPA_JUDGE_LM`` environment variable
    3. ``databricks:/databricks-claude-sonnet-4-6`` (default)

Model fallback:
    On rate limit errors (REQUEST_LIMIT_EXCEEDED), automatically retries with
    fallback models. Configure via ``GEPA_FALLBACK_MODELS`` env var (comma-separated)
    or use the built-in Databricks fallback chain.

AI Gateway support:
    Set ``DATABRICKS_AI_GATEWAY_URL`` to route calls through Databricks AI Gateway.
    Example: https://1444828305810485.ai-gateway.cloud.databricks.com/mlflow/v1
    Works alongside the standard serving endpoint approach.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from mlflow.genai.judges import make_judge

logger = logging.getLogger(__name__)

DEFAULT_JUDGE_LM = os.environ.get("GEPA_JUDGE_LM", "databricks:/databricks-claude-sonnet-4-6")

# ---------------------------------------------------------------------------
# Fallback model chain for rate limit errors
# ---------------------------------------------------------------------------

_DEFAULT_FALLBACK_MODELS = [
    "databricks/databricks-gpt-5-2",
    "databricks/databricks-gemini-3-1-pro",
    "databricks/databricks-claude-opus-4-5",
    "databricks/databricks-gpt-5",
    "databricks/databricks-claude-sonnet-4-6",
    "databricks/databricks-claude-sonnet-4-5",
]


def _get_fallback_models() -> list[str]:
    """Get fallback model chain from env or defaults."""
    custom = os.environ.get("GEPA_FALLBACK_MODELS", "")
    if custom.strip():
        return [m.strip() for m in custom.split(",") if m.strip()]
    return list(_DEFAULT_FALLBACK_MODELS)


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception is a rate limit / request limit exceeded error."""
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in [
            "rate_limit",
            "rate limit",
            "request_limit_exceeded",
            "request limit exceeded",
            "too many requests",
            "429",
            "token.*per.*minute",
        ]
    )


# ---------------------------------------------------------------------------
# AI Gateway support
# ---------------------------------------------------------------------------

DATABRICKS_AI_GATEWAY_URL = os.environ.get("DATABRICKS_AI_GATEWAY_URL", "")


def _get_gateway_base_url() -> str | None:
    """Return the AI Gateway base URL if configured, else None."""
    url = DATABRICKS_AI_GATEWAY_URL.strip()
    if not url:
        return None
    return url.rstrip("/")


def _to_litellm_model(model: str) -> tuple[str, str | None]:
    """Convert a model string to (litellm_model, base_url) for completion calls.

    If AI Gateway is configured and model is a databricks/ model, routes
    through the gateway as an OpenAI-compatible endpoint. Otherwise returns
    the model unchanged with no base_url override.

    Returns:
        (model_string, base_url_or_None)
    """
    gateway = _get_gateway_base_url()
    if gateway and model.startswith("databricks/"):
        # Route through AI Gateway as OpenAI-compatible endpoint
        endpoint_name = model.split("/", 1)[1]
        return f"openai/{endpoint_name}", gateway
    return model, None


# ---------------------------------------------------------------------------
# URI conversion
# ---------------------------------------------------------------------------


def _to_judge_uri(model: str) -> str:
    """Convert litellm-style model strings to MLflow judge URI format.

    litellm uses ``provider/model`` (e.g. ``databricks/databricks-claude-sonnet-4-6``).
    MLflow judges use ``provider:/model`` (e.g. ``databricks:/databricks-claude-sonnet-4-6``).
    """
    if ":/" in model:
        return model
    if "/" in model:
        provider, name = model.split("/", 1)
        return f"{provider}:/{name}"
    return model


def _judge_inference_params() -> dict[str, Any] | None:
    """Build inference_params for make_judge if AI Gateway is configured."""
    gateway = _get_gateway_base_url()
    if gateway:
        return {"base_url": gateway}
    return None


def _to_judge_model_and_params(model: str) -> tuple[str, dict[str, Any] | None]:
    """Convert a model string to (judge_uri, inference_params) for make_judge.

    If AI Gateway is configured, uses ``openai:/endpoint-name`` with
    ``inference_params.base_url`` pointing to the gateway. Otherwise
    uses standard ``provider:/model`` format.
    """
    gateway = _get_gateway_base_url()
    if gateway and model.startswith(("databricks/", "databricks:/")):
        # Extract the endpoint name
        if ":/" in model:
            endpoint_name = model.split(":/", 1)[1]
        else:
            endpoint_name = model.split("/", 1)[1]
        return f"openai:/{endpoint_name}", {"base_url": gateway}
    return _to_judge_uri(model), _judge_inference_params()


# ---------------------------------------------------------------------------
# Completion with fallback
# ---------------------------------------------------------------------------


def completion_with_fallback(*, model: str, max_retries: int = 3, **kwargs) -> Any:
    """Call litellm.completion with model fallback on rate limit errors.

    Tries the primary model first. On rate limit errors, cycles through
    the fallback chain. Each model gets ``max_retries`` attempts with
    exponential backoff before moving to the next.

    Also supports AI Gateway: if DATABRICKS_AI_GATEWAY_URL is set,
    databricks/ models are routed through the gateway.
    """
    import litellm

    models_to_try = [model] + [m for m in _get_fallback_models() if m != model]

    last_err: Exception | None = None
    for model_str in models_to_try:
        litellm_model, base_url = _to_litellm_model(model_str)

        call_kwargs = dict(kwargs)
        call_kwargs["model"] = litellm_model
        if base_url:
            call_kwargs["base_url"] = base_url

        for attempt in range(max_retries):
            if attempt > 0:
                delay = min(2**attempt, 30)
                time.sleep(delay)
            try:
                return litellm.completion(**call_kwargs)
            except Exception as e:
                last_err = e
                if _is_rate_limit_error(e):
                    if attempt == max_retries - 1:
                        logger.warning(
                            "Model '%s' rate limited after %d attempts, trying next fallback",
                            model_str,
                            max_retries,
                        )
                    continue
                # Non-rate-limit error: don't retry, try next model
                logger.warning("Model '%s' failed (non-rate-limit): %s", model_str, e)
                break

    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class JudgeFeedback:
    """Structured feedback from a judge call."""

    value: float | str
    rationale: str
    name: str


def _safe_parse_score(raw_value: Any) -> float:
    """Convert judge output to a float score in [0.0, 1.0].

    Handles: bool, "yes"/"no", numeric, float-as-string.
    """
    if isinstance(raw_value, (int, float)):
        return max(0.0, min(1.0, float(raw_value)))
    if isinstance(raw_value, bool):
        return 1.0 if raw_value else 0.0
    if isinstance(raw_value, str):
        low = raw_value.strip().lower()
        if low == "yes":
            return 1.0
        if low == "no":
            return 0.0
        try:
            return max(0.0, min(1.0, float(low)))
        except ValueError:
            pass
    return 0.0


# ---------------------------------------------------------------------------
# Quality judge — primary scorer for a single response
# ---------------------------------------------------------------------------

_QUALITY_INSTRUCTIONS = """\
You are an expert evaluator for Databricks skill documentation quality.
Rate the response on a scale from 0.0 to 1.0 based on how well it addresses
the user's question using correct, complete, and relevant information.

## Evaluation Criteria

1. **Relevance** (does the response address the question?)
2. **Completeness** (are all parts of the question answered?)
3. **Correctness** (are the facts and API references accurate?)
4. **Pattern adherence** (does the response follow expected code patterns?)
5. **API accuracy** (are function names, parameters, and syntax correct?)

## Expected Facts, Patterns, and Guidelines

{{ expectations }}

## Input

Question: {{ inputs }}
Response: {{ outputs }}

## Instructions

Return a score between 0.0 and 1.0 where:
- 1.0 = perfect response, all facts present, all patterns correct
- 0.7 = good response, most facts present, minor gaps
- 0.4 = partial response, significant gaps or inaccuracies
- 0.1 = poor response, mostly wrong or off-topic
- 0.0 = completely wrong or empty

Provide detailed rationale explaining:
- Which expected facts are present vs missing
- Which patterns are correctly followed vs violated
- Specific API or syntax errors found
- What would need to change to improve the score
"""


def create_skill_quality_judge(
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a universal quality judge for scoring responses.

    Args:
        skill_guidelines: Optional per-skill evaluation principles from
            ground_truth.yaml guidelines across all test cases.
        judge_model: LLM model for the judge. Defaults to GEPA_JUDGE_LM env
            or databricks/databricks-claude-sonnet-4-6.
    """
    instructions = _QUALITY_INSTRUCTIONS
    if skill_guidelines:
        principles = "\n".join(f"- {g}" for g in skill_guidelines)
        instructions += f"\n\n## Domain-Specific Principles\n{principles}\n"

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="skill_quality",
        model=model_uri,
        instructions=instructions,
        feedback_value_type=float,
        inference_params=inference_params,
    )


# ---------------------------------------------------------------------------
# Effectiveness judge — WITH vs WITHOUT comparison
# ---------------------------------------------------------------------------

_EFFECTIVENESS_INSTRUCTIONS = """\
You are comparing two responses to the same question to determine whether
a skill document helped or hurt the agent's response quality.

The inputs contain three fields separated by markers:
- QUESTION: the user's question
- WITH-SKILL RESPONSE: generated with the skill document in context
- WITHOUT-SKILL RESPONSE: generated without any skill document

The expectations contain the expected facts and patterns.

## Inputs

{{ inputs }}

## Expected Information

{{ expectations }}

## Instructions

Determine whether the skill IMPROVED, maintained (SAME), or REGRESSED the
response quality. Return one of exactly: "improved", "same", "regressed".

An "improved" verdict means the WITH-skill response is meaningfully better:
more accurate facts, better code patterns, correct API usage that the
WITHOUT response got wrong.

A "regressed" verdict means the skill actively HURT the response: introduced
incorrect information, deprecated APIs, or confused the agent.

"same" means no meaningful difference.

Provide detailed rationale explaining:
- What the skill added or removed from the response
- Specific facts/patterns that differ between WITH and WITHOUT
- Whether the skill taught something the model didn't already know
- If regressed: what specifically the skill got wrong
"""


def create_effectiveness_judge(judge_model: str | None = None) -> Any:
    """Create a WITH vs WITHOUT comparison judge.

    Args:
        judge_model: LLM model for the judge. Defaults to GEPA_JUDGE_LM env
            or databricks/databricks-claude-sonnet-4-6.
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="skill_effectiveness",
        model=model_uri,
        instructions=_EFFECTIVENESS_INSTRUCTIONS,
        feedback_value_type=str,
        inference_params=inference_params,
    )


# ---------------------------------------------------------------------------
# Regression judge — identifies how a skill harms responses
# ---------------------------------------------------------------------------

_REGRESSION_INSTRUCTIONS = """\
You are a regression detector for Databricks skill documents. Your job is
to identify specific ways that a skill document HARMS agent responses.

The inputs contain three fields separated by markers:
- QUESTION: the user's question
- WITH-SKILL RESPONSE: generated with the skill document in context
- WITHOUT-SKILL RESPONSE: generated without any skill document

## Input

{{ inputs }}

## Instructions

Identify specific regressions introduced by the skill. Return "yes" if
regressions are found, "no" if the skill is harmless.

Common regression patterns:
1. **Deprecated APIs** — skill teaches old APIs the model already uses correctly
2. **Verbosity** — skill adds noise that confuses the model
3. **Contradicting correct knowledge** — model was right, skill made it wrong
4. **Wrong examples** — skill's code examples have errors the model copies
5. **Over-specification** — skill's rigid patterns prevent correct alternatives

For each regression found, explain:
- WHAT specific content in the skill caused the regression
- WHY it made the response worse
- WHAT to remove or change in the skill to fix it
"""


def create_regression_judge(judge_model: str | None = None) -> Any:
    """Create a regression detection judge.

    Args:
        judge_model: LLM model for the judge. Defaults to GEPA_JUDGE_LM env
            or databricks/databricks-claude-sonnet-4-6.
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="skill_regression",
        model=model_uri,
        instructions=_REGRESSION_INSTRUCTIONS,
        feedback_value_type=bool,
        inference_params=inference_params,
    )


# ---------------------------------------------------------------------------
# Helper: run a judge safely with fallback on rate limit
# ---------------------------------------------------------------------------


def run_judge_safe(
    judge: Any,
    *,
    inputs: Any,
    outputs: Any | None = None,
    expectations: Any | None = None,
    name: str = "judge",
) -> JudgeFeedback:
    """Run a judge with error handling and model fallback.

    On rate limit errors, recreates the judge with fallback models and
    retries. On other errors, returns zero-score feedback so evaluation
    never crashes from a judge failure.
    """
    kwargs: dict[str, Any] = {"inputs": inputs}
    if outputs is not None:
        kwargs["outputs"] = outputs
    if expectations is not None:
        kwargs["expectations"] = expectations

    # Try the primary judge first
    try:
        fb = judge(**kwargs)
        return JudgeFeedback(
            value=fb.value,
            rationale=fb.rationale or "",
            name=name,
        )
    except Exception as e:
        if not _is_rate_limit_error(e):
            logger.warning("Judge '%s' failed: %s", name, e)
            return JudgeFeedback(value=0.0, rationale=f"Judge error: {e}", name=name)

    # Rate limit hit — try fallback models
    logger.warning("Judge '%s' rate limited, trying fallback models", name)
    fallbacks = _get_fallback_models()

    for fallback_model in fallbacks:
        model_uri, inference_params = _to_judge_model_and_params(fallback_model)
        try:
            fallback_judge = make_judge(
                name=judge.name,
                model=model_uri,
                instructions=judge._instructions,
                feedback_value_type=judge._feedback_value_type,
                inference_params=inference_params,
            )
            fb = fallback_judge(**kwargs)
            logger.info("Judge '%s' succeeded with fallback model '%s'", name, fallback_model)
            return JudgeFeedback(
                value=fb.value,
                rationale=fb.rationale or "",
                name=name,
            )
        except Exception as fallback_err:
            if _is_rate_limit_error(fallback_err):
                logger.warning("Fallback '%s' also rate limited, trying next", fallback_model)
                continue
            logger.warning("Fallback '%s' failed: %s", fallback_model, fallback_err)
            continue

    # All fallbacks exhausted
    logger.error("Judge '%s': all models rate limited", name)
    return JudgeFeedback(
        value=0.0,
        rationale="All models rate limited — no judge score available",
        name=name,
    )
