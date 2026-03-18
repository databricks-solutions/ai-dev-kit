"""MLflow judge factories for skill evaluation.

Multi-judge architecture with three focused custom ``make_judge`` instances:

    correctness_judge      — Are facts, API references, and code syntax accurate?
    completeness_judge     — Are all parts of the question addressed?
    guideline_adherence_judge — Does the response follow Databricks-specific patterns?

Each judge uses categorical ``Literal["excellent", "acceptable", "poor"]``
feedback types for more reliable, alignable judgments. Scores are converted
to floats via ``CATEGORICAL_SCORES``.

Additional judges:
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

import concurrent.futures
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal

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
            "network is unreachable",
            "name or service not known",
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
# Categorical scoring
# ---------------------------------------------------------------------------

CATEGORICAL_SCORES: dict[str, float] = {
    "excellent": 1.0,
    "acceptable": 0.6,
    "poor": 0.0,
}


def _categorical_to_float(verdict: str | float) -> float:
    """Convert a categorical verdict to a float score.

    Handles ``Literal["excellent", "acceptable", "poor"]`` from the new
    multi-judge architecture as well as raw floats from legacy judges.
    """
    if isinstance(verdict, (int, float)):
        return max(0.0, min(1.0, float(verdict)))
    key = str(verdict).strip().lower()
    return CATEGORICAL_SCORES.get(key, 0.0)


# ---------------------------------------------------------------------------
# Correctness judge — facts, API references, code syntax accuracy
# ---------------------------------------------------------------------------

_CORRECTNESS_KEYWORDS = {
    "api",
    "syntax",
    "correct",
    "deprecated",
    "modern",
    "function",
    "parameter",
    "error",
    "version",
}

_CORRECTNESS_INSTRUCTIONS = """\
You are an expert evaluator for Databricks skill documentation CORRECTNESS.
Focus ONLY on whether facts, API references, and code syntax are accurate.

## What to evaluate

1. **Factual accuracy** — are stated facts correct?
2. **API accuracy** — are function names, parameters, and return types correct?
3. **Code syntax** — is the code syntactically valid and runnable?
4. **Currency** — are APIs current (not deprecated)?

Do NOT evaluate completeness or style — only correctness.

## Expected Information

{{ expectations }}

## Input

Question: {{ inputs }}
Response: {{ outputs }}

## Instructions

Return one of exactly: "excellent", "acceptable", "poor".

- "excellent" = all facts, APIs, and syntax are correct
- "acceptable" = mostly correct with minor inaccuracies that don't break functionality
- "poor" = contains significant factual errors, wrong APIs, or broken syntax

Provide detailed rationale explaining:
- Specific factual errors found (or confirming correctness)
- API references that are wrong or deprecated
- Syntax issues in code examples
"""


def create_correctness_judge(
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a correctness-focused judge with categorical feedback.

    Args:
        skill_guidelines: Optional guidelines — only correctness-related ones
            (matching keywords like api, syntax, correct, deprecated) are injected.
        judge_model: LLM model for the judge.
    """
    instructions = _CORRECTNESS_INSTRUCTIONS
    if skill_guidelines:
        # Filter for correctness-related guidelines
        filtered = [g for g in skill_guidelines if any(kw in g.lower() for kw in _CORRECTNESS_KEYWORDS)]
        if filtered:
            principles = "\n".join(f"- {g}" for g in filtered)
            instructions += f"\n\n## Domain-Specific Correctness Principles\n{principles}\n"

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="skill_correctness",
        model=model_uri,
        instructions=instructions,
        feedback_value_type=Literal["excellent", "acceptable", "poor"],
        inference_params=inference_params,
    )


# ---------------------------------------------------------------------------
# Completeness judge — all parts addressed, all expected info present
# ---------------------------------------------------------------------------

_COMPLETENESS_INSTRUCTIONS = """\
You are an expert evaluator for Databricks skill documentation COMPLETENESS.
Focus ONLY on whether all parts of the question are addressed and all expected
information is present.

## What to evaluate

1. **Question coverage** — are all parts of the question answered?
2. **Expected facts** — are all expected facts present?
3. **Expected patterns** — are all expected code patterns demonstrated?
4. **Depth** — is the response detailed enough to be actionable?

Do NOT evaluate correctness or style — only completeness.

## Expected Information

{{ expectations }}

## Input

Question: {{ inputs }}
Response: {{ outputs }}

## Instructions

Return one of exactly: "excellent", "acceptable", "poor".

- "excellent" = all parts addressed, all expected facts and patterns present
- "acceptable" = most parts addressed, minor gaps in coverage
- "poor" = significant parts of the question unanswered or major facts missing

Provide detailed rationale explaining:
- Which parts of the question are addressed vs unanswered
- Which expected facts are present vs missing
- Which expected patterns are demonstrated vs absent
"""


def create_completeness_judge(
    judge_model: str | None = None,
) -> Any:
    """Create a completeness-focused judge with categorical feedback.

    Args:
        judge_model: LLM model for the judge.
    """
    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="skill_completeness",
        model=model_uri,
        instructions=_COMPLETENESS_INSTRUCTIONS,
        feedback_value_type=Literal["excellent", "acceptable", "poor"],
        inference_params=inference_params,
    )


# ---------------------------------------------------------------------------
# Guideline adherence judge — Databricks patterns and practices
# ---------------------------------------------------------------------------

_GUIDELINE_ADHERENCE_INSTRUCTIONS = """\
You are an expert evaluator for Databricks skill documentation GUIDELINE ADHERENCE.
Focus ONLY on whether the response follows Databricks-specific patterns,
conventions, and guidelines.

## What to evaluate

1. **Pattern adherence** — does the response follow expected code patterns?
2. **Convention compliance** — does it use Databricks-specific conventions?
3. **Best practice alignment** — does it follow recommended practices?
4. **Guideline compliance** — does it adhere to the specific guidelines listed below?

Do NOT evaluate general correctness or completeness — only guideline adherence.

## Expected Information

{{ expectations }}

## Input

Question: {{ inputs }}
Response: {{ outputs }}

## Instructions

Return one of exactly: "excellent", "acceptable", "poor".

- "excellent" = follows all guidelines and patterns precisely
- "acceptable" = follows most guidelines with minor deviations
- "poor" = ignores or violates important guidelines

Provide detailed rationale explaining:
- Which guidelines are followed vs violated
- Which patterns are correctly demonstrated vs missing
- Specific deviations from expected practices
"""


def create_guideline_adherence_judge(
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a guideline adherence judge with categorical feedback.

    Receives ALL guidelines (default_guidelines + per-test guidelines +
    [FOCUS] guidelines from ``--focus``), making focus areas directly evaluable.

    Args:
        skill_guidelines: All guidelines to evaluate against.
        judge_model: LLM model for the judge.
    """
    instructions = _GUIDELINE_ADHERENCE_INSTRUCTIONS
    if skill_guidelines:
        principles = "\n".join(f"- {g}" for g in skill_guidelines)
        instructions += f"\n\n## Required Guidelines\n{principles}\n"

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="skill_guideline_adherence",
        model=model_uri,
        instructions=instructions,
        feedback_value_type=Literal["excellent", "acceptable", "poor"],
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
    inputs: Any = None,
    outputs: Any | None = None,
    expectations: Any | None = None,
    trace: Any | None = None,
    name: str = "judge",
    timeout: int = 90,
) -> JudgeFeedback:
    """Run a judge with error handling, timeout, and model fallback.

    Supports both field-based judges (``inputs``/``outputs``/``expectations``)
    and trace-based judges (``trace``/``expectations``).

    Each judge call is wrapped in a ``ThreadPoolExecutor`` with a timeout
    to prevent indefinite hangs from trace-based judges (which trigger
    MLflow's multi-round tool-calling loop).

    On rate limit errors, recreates the judge with fallback models and
    retries.  On other errors or timeouts, returns zero-score feedback so
    evaluation never crashes from a judge failure.
    """
    kwargs: dict[str, Any] = {}
    if trace is not None:
        kwargs["trace"] = trace
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


# ---------------------------------------------------------------------------
# Trace-based judges (for --agent-eval)
#
# These use {{ trace }} which activates MLflow's tool-calling loop, giving
# the judge access to list_spans, get_root_span, search_trace_regex, AND
# our custom read_eval_criteria / read_eval_reference tools.
# ---------------------------------------------------------------------------

_TRACE_CORRECTNESS_INSTRUCTIONS_PREFIX = """\
You are evaluating a Claude Code agent's execution trace for CORRECTNESS.
Focus ONLY on whether the agent's actions and outputs are factually and technically correct.

"""

_TRACE_CORRECTNESS_INSTRUCTIONS_BODY = """\

## What to evaluate

1. **Output accuracy** — Is the final response factually correct?
2. **API correctness** — Are tool calls using correct parameters and syntax?
3. **Code correctness** — Is any generated code syntactically valid and runnable?
4. **Tool call correctness** — Did the agent use the right tools for the task?

## How to evaluate

1. Use list_spans to see the full execution flow
2. Use get_root_span to read the final response
3. Use read_eval_criteria to load domain-specific rubrics matching the trace
4. Use search_trace_regex to verify specific patterns in the output

## Task expectations

{{ expectations }}

Analyze {{ trace }} and return one of exactly: "excellent", "acceptable", "poor".

- "excellent" = all outputs correct, right tools used, valid code/SQL
- "acceptable" = mostly correct, minor issues that don't break functionality
- "poor" = significant errors, wrong tools, broken code

Provide detailed rationale referencing specific spans and tool calls.
"""

_TRACE_COMPLETENESS_INSTRUCTIONS_PREFIX = """\
You are evaluating a Claude Code agent's execution trace for COMPLETENESS.
Focus ONLY on whether all parts of the task were addressed.

"""

_TRACE_COMPLETENESS_INSTRUCTIONS_BODY = """\

## What to evaluate

1. **Task completion** — Did the agent finish the requested task?
2. **Coverage** — Are all parts of the question addressed?
3. **Expected facts** — Are all expected facts present in the output?
4. **Expected patterns** — Are all expected code patterns demonstrated?

## How to evaluate

1. Use get_root_span to read the final response text
2. Use list_spans to verify multi-step tasks were fully executed
3. Use search_trace_regex to check for expected patterns in outputs
4. Use read_eval_criteria for domain-specific completeness rubrics

## Task expectations

{{ expectations }}

Analyze {{ trace }} and return one of exactly: "excellent", "acceptable", "poor".

- "excellent" = all parts addressed, all expected facts/patterns present
- "acceptable" = most parts addressed, minor gaps
- "poor" = significant parts missing or incomplete

Provide detailed rationale referencing what was found vs missing.
"""

_TRACE_GUIDELINE_INSTRUCTIONS_PREFIX = """\
You are evaluating a Claude Code agent's execution trace for GUIDELINE ADHERENCE.
Focus ONLY on whether the agent followed Databricks-specific patterns and conventions.

"""

_TRACE_GUIDELINE_INSTRUCTIONS_BODY = """\

## What to evaluate

1. **Tool selection** — Did the agent use MCP tools instead of Bash workarounds?
2. **Pattern compliance** — Does output follow Databricks conventions?
3. **Best practices** — Did the agent follow recommended workflows?
4. **Efficiency** — Was the execution path reasonable (not excessive tool calls)?

## How to evaluate

1. Use list_spans to review the tool call sequence
2. Use read_eval_criteria to load domain-specific guidelines
3. Use get_span on individual tool calls to check parameters
4. Use search_trace_regex to verify Databricks-specific patterns

## Task expectations and guidelines

{{ expectations }}

Analyze {{ trace }} and return one of exactly: "excellent", "acceptable", "poor".

- "excellent" = correct tools, Databricks patterns, efficient execution
- "acceptable" = mostly correct approach, minor deviations
- "poor" = wrong tools, anti-patterns, or wasteful execution

Provide detailed rationale referencing specific spans and tool choices.
"""


def create_trace_correctness_judge(
    eval_criteria: Any,
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a trace-based correctness judge with adaptive eval criteria.

    Uses ``{{ trace }}`` to activate MLflow's tool-calling loop.  The judge
    can call ``read_eval_criteria`` and ``read_eval_reference`` to load
    domain-specific rubrics.

    Args:
        eval_criteria: ``EvalCriteriaSet`` with loaded criteria skills.
        skill_guidelines: Optional per-skill guidelines from manifest/ground_truth.
        judge_model: LLM model for the judge.  Resolved via ``--judge-model``
            CLI flag, ``GEPA_JUDGE_LM`` env var, or default.
    """
    criteria_block = eval_criteria.to_prompt(judge_model) if eval_criteria else ""
    instructions = _TRACE_CORRECTNESS_INSTRUCTIONS_PREFIX + criteria_block + _TRACE_CORRECTNESS_INSTRUCTIONS_BODY

    if skill_guidelines:
        filtered = [g for g in skill_guidelines if any(kw in g.lower() for kw in _CORRECTNESS_KEYWORDS)]
        if filtered:
            principles = "\n".join(f"- {g}" for g in filtered)
            instructions += f"\n\n## Domain Correctness Principles\n{principles}\n"

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="trace_correctness",
        model=model_uri,
        instructions=instructions,
        feedback_value_type=Literal["excellent", "acceptable", "poor"],
        inference_params=inference_params,
    )


def create_trace_completeness_judge(
    eval_criteria: Any,
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a trace-based completeness judge with adaptive eval criteria.

    Args:
        eval_criteria: ``EvalCriteriaSet`` with loaded criteria skills.
        skill_guidelines: Optional per-skill guidelines from manifest/ground_truth.
        judge_model: LLM model for the judge.
    """
    criteria_block = eval_criteria.to_prompt(judge_model) if eval_criteria else ""
    instructions = _TRACE_COMPLETENESS_INSTRUCTIONS_PREFIX + criteria_block + _TRACE_COMPLETENESS_INSTRUCTIONS_BODY

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="trace_completeness",
        model=model_uri,
        instructions=instructions,
        feedback_value_type=Literal["excellent", "acceptable", "poor"],
        inference_params=inference_params,
    )


def create_trace_guideline_judge(
    eval_criteria: Any,
    skill_guidelines: list[str] | None = None,
    judge_model: str | None = None,
) -> Any:
    """Create a trace-based guideline adherence judge with adaptive eval criteria.

    Receives ALL guidelines (default_guidelines + per-test guidelines +
    ``[FOCUS]`` guidelines from ``--focus``), making focus areas directly
    evaluable by the trace-based judge.

    Args:
        eval_criteria: ``EvalCriteriaSet`` with loaded criteria skills.
        skill_guidelines: All guidelines to evaluate against.
        judge_model: LLM model for the judge.
    """
    criteria_block = eval_criteria.to_prompt(judge_model) if eval_criteria else ""
    instructions = _TRACE_GUIDELINE_INSTRUCTIONS_PREFIX + criteria_block + _TRACE_GUIDELINE_INSTRUCTIONS_BODY

    if skill_guidelines:
        principles = "\n".join(f"- {g}" for g in skill_guidelines)
        instructions += f"\n\n## Required Guidelines\n{principles}\n"

    model_uri, inference_params = _to_judge_model_and_params(judge_model or DEFAULT_JUDGE_LM)
    return make_judge(
        name="trace_guideline_adherence",
        model=model_uri,
        instructions=instructions,
        feedback_value_type=Literal["excellent", "acceptable", "poor"],
        inference_params=inference_params,
    )
