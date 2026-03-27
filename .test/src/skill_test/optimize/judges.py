"""MLflow judge factories for skill evaluation.

Focused single-question judges that each make 1 LLM call:

    correctness_judge       — Is the response factually and technically correct?
    completeness_judge      — Does the response fully address the question?
    guideline_adherence_judge — Does the response follow Databricks conventions?
    regression_judge        — Does the skill harm the response?

Each judge uses binary ``Literal["yes", "no"]`` feedback for unambiguous verdicts
(Anthropic best practice: "two domain experts would reach the same verdict").
Scores are converted to floats via ``_safe_parse_score``.

Eval criteria are loaded on-demand via ``skills=`` parameter on ``make_judge()``
(MLflow PR #21725). When ``skills=`` is not yet supported, judges operate without
criteria — the deterministic scorers and assertions provide the static spine.

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

import concurrent.futures
import inspect
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
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


def _is_workspace_error(exc: Exception) -> bool:
    """Detect workspace-level errors where retrying or falling back is pointless.

    Catches 403/IP ACL blocks, auth failures, and network errors that indicate
    the entire workspace is unreachable — not just a single model rate limit.
    """
    msg = str(exc).lower()
    return any(
        phrase in msg
        for phrase in [
            "403",
            "forbidden",
            "ip access list",
            "ip acl",
            "not on the ip access list",
            "unauthorized",
            "401",
            "authentication failed",
            "invalid token",
            "could not resolve host",
            "connection refused",
            "connection error",
            "network is unreachable",
            "name or service not known",
            "no such host",
            "token refresh",
        ]
    )


# ---------------------------------------------------------------------------
# Global LLM call budget
# ---------------------------------------------------------------------------


class _LLMCallBudget:
    """Thread-safe counter that enforces a global cap on LLM API calls.

    Configurable via GEPA_MAX_LLM_CALLS env var.  When unset or 0 the budget
    is unlimited.
    """

    def __init__(self):
        import threading as _threading

        self._lock = _threading.Lock()
        self._count = 0
        max_str = os.environ.get("GEPA_MAX_LLM_CALLS", "0")
        try:
            self._max = int(max_str)
        except ValueError:
            self._max = 0

    @property
    def max_calls(self) -> int:
        return self._max

    @property
    def count(self) -> int:
        with self._lock:
            return self._count

    def acquire(self) -> bool:
        """Increment counter. Returns False if budget exhausted."""
        with self._lock:
            if self._max > 0 and self._count >= self._max:
                return False
            self._count += 1
            return True

    def exhausted(self) -> bool:
        with self._lock:
            return self._max > 0 and self._count >= self._max


_llm_budget = _LLMCallBudget()


# ---------------------------------------------------------------------------
# AI Gateway support
# ---------------------------------------------------------------------------


def _get_gateway_base_url() -> str | None:
    """Return the AI Gateway base URL if configured, else None.

    Reads os.environ at call time (not import time) so that env vars
    set by runner.py's early config loading are picked up before judges
    are created.

    Strips common API path suffixes (e.g. ``/chat/completions``) that users
    might include by mistake — litellm appends its own path to the base URL.
    """
    url = os.environ.get("DATABRICKS_AI_GATEWAY_URL", "").strip()
    if not url:
        return None
    url = url.rstrip("/")
    # Strip API path suffixes users might include by mistake
    for suffix in ("/chat/completions", "/completions", "/embeddings"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


def _to_litellm_model(model: str) -> tuple[str, str | None, str | None]:
    """Convert a model string to (litellm_model, base_url, api_key) for completion calls.

    If AI Gateway is configured and model is a databricks/ model, routes
    through the gateway as an OpenAI-compatible endpoint.  The OpenAI
    provider in litellm does not auto-read ``DATABRICKS_TOKEN``, so we
    pass it explicitly as ``api_key``.

    Returns:
        (model_string, base_url_or_None, api_key_or_None)
    """
    gateway = _get_gateway_base_url()
    if gateway and model.startswith("databricks/"):
        # Route through AI Gateway as OpenAI-compatible endpoint
        endpoint_name = model.split("/", 1)[1]
        api_key = os.environ.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_API_KEY", "")
        return f"openai/{endpoint_name}", gateway, api_key or None
    return model, None, None


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
        api_key = os.environ.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_API_KEY", "")
        params: dict[str, Any] = {"base_url": gateway}
        if api_key:
            params["api_key"] = api_key
        return params
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
        api_key = os.environ.get("DATABRICKS_TOKEN") or os.environ.get("DATABRICKS_API_KEY", "")
        params: dict[str, Any] = {"base_url": gateway}
        if api_key:
            params["api_key"] = api_key
        return f"openai:/{endpoint_name}", params
    return _to_judge_uri(model), _judge_inference_params()


# ---------------------------------------------------------------------------
# Completion with fallback
# ---------------------------------------------------------------------------


def completion_with_fallback(*, model: str, max_retries: int = 3, **kwargs) -> Any:
    """Call litellm.completion with model fallback on rate limit errors.

    Tries the primary model first. On rate limit errors, cycles through
    the fallback chain. Each model gets ``max_retries`` attempts with
    exponential backoff before moving to the next.

    Workspace-level errors (403/IP ACL/auth) are raised immediately —
    fallback models hit the same blocked workspace and would all fail.

    Respects the global LLM call budget (``GEPA_MAX_LLM_CALLS``).

    Also supports AI Gateway: if DATABRICKS_AI_GATEWAY_URL is set,
    databricks/ models are routed through the gateway.
    """
    import litellm

    if not _llm_budget.acquire():
        raise RuntimeError(
            f"GEPA LLM call budget exhausted ({_llm_budget.max_calls} calls). "
            "Set GEPA_MAX_LLM_CALLS to increase or unset to disable."
        )

    models_to_try = [model] + [m for m in _get_fallback_models() if m != model]

    last_err: Exception | None = None
    for model_str in models_to_try:
        litellm_model, base_url, api_key = _to_litellm_model(model_str)

        call_kwargs = dict(kwargs)
        call_kwargs["model"] = litellm_model
        if base_url:
            call_kwargs["base_url"] = base_url
        if api_key:
            call_kwargs["api_key"] = api_key

        for attempt in range(max_retries):
            if attempt > 0:
                delay = min(2**attempt, 30)
                time.sleep(delay)
            try:
                return litellm.completion(**call_kwargs)
            except Exception as e:
                last_err = e
                # Workspace-level errors: fail fast, no fallback
                if _is_workspace_error(e):
                    logger.error(
                        "Workspace error (fail-fast): %s — not trying fallback models",
                        e,
                    )
                    raise
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
# Skill discovery (static spine + adaptive layer from Issue #21255)
# ---------------------------------------------------------------------------


def discover_skill_paths(criteria_dir: str = ".test/eval-criteria", tool_modules: list[str] | None = None) -> list[str]:
    """Return skill directory paths, optionally filtered by applies_to metadata.

    Static spine: criteria with empty ``applies_to`` are always included.
    Adaptive layer: criteria with ``applies_to`` only included when matching
    ``tool_modules``.

    These paths are passed to ``make_judge(skills=[...])`` when the native
    MLflow skills= parameter is available (PR #21725).
    """
    base = Path(criteria_dir)
    if not base.is_dir():
        return []
    paths = []
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not (d / "SKILL.md").exists():
            continue
        if tool_modules:
            try:
                content = (d / "SKILL.md").read_text(encoding="utf-8")
                parts = content.split("---")
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1]) or {}
                    applies_to = fm.get("metadata", {}).get("applies_to", [])
                    if applies_to and not any(m in applies_to for m in tool_modules):
                        continue
            except Exception:
                pass
        paths.append(str(d))
    if paths:
        logger.info("Discovered %d eval criteria skills: %s", len(paths), ", ".join(Path(p).name for p in paths))
        try:
            from .eval_criteria import SkillSet
            from .judge_tools import register_skill_tools

            register_skill_tools(SkillSet(paths))
        except Exception as exc:
            logger.debug("Could not register skill tools: %s", exc)
    return paths


def _make_judge_with_skills(
    *,
    name: str,
    instructions: str,
    model: str,
    feedback_value_type: Any,
    inference_params: dict[str, Any] | None = None,
    skill_paths: list[str] | None = None,
) -> Any:
    """Create a judge, passing skills= if supported by the installed MLflow.

    Forward-compatible: when MLflow gains ``skills=`` support (PR #21725),
    the eval criteria will be loaded on-demand by the judge. Until then,
    judges operate without criteria and rely on the instructions alone.
    """
    kwargs: dict[str, Any] = {
        "name": name,
        "instructions": instructions,
        "model": model,
        "feedback_value_type": feedback_value_type,
    }
    if inference_params:
        kwargs["inference_params"] = inference_params

    # Pass skills= if make_judge supports it (native path, PR #21725)
    if skill_paths:
        if "skills" in inspect.signature(make_judge).parameters:
            kwargs["skills"] = skill_paths
        else:
            # Local injection for MLflow versions without skills= support
            from .eval_criteria import SkillSet

            skill_set = SkillSet(skill_paths)
            criteria_block = skill_set.to_prompt_inline()
            if criteria_block:
                kwargs["instructions"] = criteria_block + "\n\n" + instructions

    return make_judge(**kwargs)


# ---------------------------------------------------------------------------
# Correctness judge — facts, API references, code syntax accuracy (1 LLM call)
# ---------------------------------------------------------------------------

_CORRECTNESS_INSTRUCTIONS = """\
Is the response factually and technically correct?

Check:
- API names exist and are current (not deprecated)
- Code syntax is valid and runnable
- Function parameters and return types are correct
- No hallucinated features or invented APIs

{{ expectations }}

Question: {{ inputs }}
Response: {{ outputs }}

Return "yes" if correct, "no" if it contains significant factual errors.
"""


def create_correctness_judge(
    skill_paths: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a focused correctness judge with binary yes/no feedback.

    Uses ``{{ inputs }}/{{ outputs }}`` (field-based) — 1 LLM call, no
    agentic tool-calling loop.
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return _make_judge_with_skills(
        name="correctness",
        instructions=_CORRECTNESS_INSTRUCTIONS,
        model=model_uri,
        feedback_value_type=Literal["yes", "no"],
        inference_params=inference_params,
        skill_paths=skill_paths,
    )


# ---------------------------------------------------------------------------
# Completeness judge — all parts addressed, expected info present (1 LLM call)
# ---------------------------------------------------------------------------

_COMPLETENESS_INSTRUCTIONS = """\
Does the response fully address the question?

Check:
- All parts of the question are answered
- Expected facts are present
- Expected code patterns are demonstrated
- Response is detailed enough to be actionable

{{ expectations }}

Question: {{ inputs }}
Response: {{ outputs }}

Return "yes" if complete, "no" if significant parts are missing.
"""


def create_completeness_judge(
    skill_paths: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a focused completeness judge with binary yes/no feedback.

    Uses ``{{ inputs }}/{{ outputs }}`` (field-based) — 1 LLM call, no
    agentic tool-calling loop.
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return _make_judge_with_skills(
        name="completeness",
        instructions=_COMPLETENESS_INSTRUCTIONS,
        model=model_uri,
        feedback_value_type=Literal["yes", "no"],
        inference_params=inference_params,
        skill_paths=skill_paths,
    )


# ---------------------------------------------------------------------------
# Guideline adherence judge — Databricks patterns and practices (1 LLM call)
# ---------------------------------------------------------------------------

_GUIDELINE_ADHERENCE_INSTRUCTIONS = """\
Does the response follow Databricks conventions and best practices?

Check:
- Follows expected code patterns and conventions
- Uses recommended Databricks APIs and workflows
- Adheres to the specific guidelines listed below

{{ expectations }}

Question: {{ inputs }}
Response: {{ outputs }}

Return "yes" if guidelines are followed, "no" if important guidelines are violated.
"""


def create_guideline_adherence_judge(
    skill_paths: list[str] | None = None,
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a focused guideline adherence judge with binary yes/no feedback.

    Receives ALL guidelines (default_guidelines + per-test guidelines +
    [FOCUS] guidelines from ``--focus``), making focus areas directly evaluable.
    """
    instructions = _GUIDELINE_ADHERENCE_INSTRUCTIONS
    if skill_guidelines:
        principles = "\n".join(f"- {g}" for g in skill_guidelines)
        instructions += f"\n\n## Required Guidelines\n{principles}\n"

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return _make_judge_with_skills(
        name="guideline-adherence",
        instructions=instructions,
        model=model_uri,
        feedback_value_type=Literal["yes", "no"],
        inference_params=inference_params,
        skill_paths=skill_paths,
    )


# ---------------------------------------------------------------------------
# Regression judge — identifies how a skill harms responses (1 LLM call)
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
        name="regression",
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
    inputs: Any = None,
    outputs: Any | None = None,
    expectations: Any | None = None,
    name: str = "judge",
    timeout: int = 90,
) -> JudgeFeedback:
    """Run a judge with error handling, timeout, and model fallback.

    All judges are field-based (``inputs``/``outputs``/``expectations``),
    each making exactly 1 LLM call.

    On rate limit errors, recreates the judge with fallback models and
    retries.  On other errors or timeouts, returns zero-score feedback so
    evaluation never crashes from a judge failure.
    """
    kwargs: dict[str, Any] = {}
    if inputs is not None:
        kwargs["inputs"] = inputs
    if outputs is not None:
        kwargs["outputs"] = outputs
    if expectations is not None:
        kwargs["expectations"] = expectations

    def _call_judge(j):
        return j(**kwargs)

    # Budget check — return zero-score gracefully when budget exhausted
    if _llm_budget.exhausted():
        return JudgeFeedback(
            value=0.0,
            rationale=f"LLM call budget exhausted ({_llm_budget.max_calls} calls)",
            name=name,
        )

    # Try the primary judge first
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_call_judge, judge)
        try:
            fb = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning("Judge '%s' timed out after %ds", name, timeout)
            return JudgeFeedback(value=0.0, rationale=f"Judge timed out after {timeout}s", name=name)
        finally:
            # shutdown(wait=False) so a still-running judge thread doesn't block
            pool.shutdown(wait=False)
        return JudgeFeedback(
            value=fb.value,
            rationale=fb.rationale or "",
            name=name,
        )
    except concurrent.futures.TimeoutError:
        # Already handled above, but keep for safety
        return JudgeFeedback(value=0.0, rationale=f"Judge timed out after {timeout}s", name=name)
    except Exception as e:
        pool.shutdown(wait=False)
        # Workspace-level errors: return zero immediately, skip fallback chain
        if _is_workspace_error(e):
            logger.error("Judge '%s' hit workspace error (fail-fast): %s", name, e)
            return JudgeFeedback(value=0.0, rationale=f"Workspace error: {e}", name=name)
        if not _is_rate_limit_error(e):
            logger.debug("Judge '%s' failed: %s", name, e)
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
            fb_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                future = fb_pool.submit(_call_judge, fallback_judge)
                fb = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError:
                fb_pool.shutdown(wait=False)
                logger.warning(
                    "Fallback '%s' timed out after %ds, trying next",
                    fallback_model,
                    timeout,
                )
                continue
            finally:
                fb_pool.shutdown(wait=False)
            logger.info("Judge '%s' succeeded with fallback model '%s'", name, fallback_model)
            return JudgeFeedback(
                value=fb.value,
                rationale=fb.rationale or "",
                name=name,
            )
        except Exception as fallback_err:
            # Workspace errors in fallback: stop trying — same workspace
            if _is_workspace_error(fallback_err):
                logger.error("Fallback '%s' hit workspace error (fail-fast): %s", fallback_model, fallback_err)
                break
            if _is_rate_limit_error(fallback_err):
                logger.warning("Fallback '%s' also rate limited, trying next", fallback_model)
                continue
            logger.warning("Fallback '%s' failed: %s", fallback_model, fallback_err)
            continue

    # All fallbacks exhausted
    logger.error("Judge '%s': all models rate limited or timed out", name)
    return JudgeFeedback(
        value=0.0,
        rationale="All models rate limited or timed out — no judge score available",
        name=name,
    )
