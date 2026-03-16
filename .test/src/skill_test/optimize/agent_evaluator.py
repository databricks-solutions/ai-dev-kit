"""Agent-based evaluator: run real Claude Code agent and score behavior.

GEPA-compatible evaluator that runs a Claude Code instance via the Agent SDK,
captures the full execution trace, and scores using trace-based MLflow judges
with adaptive evaluation criteria plus deterministic trace scorers.

Trace-based judges (using ``{{ trace }}`` template) inspect the actual
execution trace — tool calls, parameters, outputs, errors — and can load
domain-specific evaluation rubrics via ``read_eval_criteria`` /
``read_eval_reference`` tools registered in MLflow's JudgeToolRegistry.

Scoring weights:
  25% Effectiveness delta (WITH vs WITHOUT, per-dimension)
  20% Correctness (trace-based judge: facts, APIs, tool correctness)
  15% Completeness (trace-based judge: task completion, coverage)
  15% Guideline adherence (trace-based judge: patterns, tool selection)
  10% Assertion coverage (deterministic: expected_facts + expected_patterns)
   5% Execution success (deterministic: tool call success ratio)
   5% Token efficiency (deterministic: candidate size)
  -5% Regression penalty (conditional: regression judge)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable

from ..agent.executor import AgentResult, run_agent_sync_wrapper
from ..scorers.trace import (
    required_tools as required_tools_scorer,
    banned_tools as banned_tools_scorer,
    tool_sequence as tool_sequence_scorer,
)
from .assertions import run_all_assertions, summarize_failures
from .judges import (
    JudgeFeedback,
    _categorical_to_float,
    create_correctness_judge,
    create_completeness_judge,
    create_guideline_adherence_judge,
    create_trace_correctness_judge,
    create_trace_completeness_judge,
    create_trace_guideline_judge,
    create_regression_judge,
    run_judge_safe,
)
from .utils import count_tokens

logger = logging.getLogger(__name__)


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def _run_behavioral_scorers(
    trace_dict: dict[str, Any],
    trace_expectations: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Run deterministic trace scorers and return composite score + details.

    Runs: required_tools, banned_tools, tool_sequence.
    Returns (score 0-1, details dict).
    """
    scorers = [
        ("required_tools", required_tools_scorer),
        ("banned_tools", banned_tools_scorer),
        ("tool_sequence", tool_sequence_scorer),
    ]

    results: dict[str, Any] = {}
    passed = 0
    total = 0

    for name, scorer_fn in scorers:
        try:
            fb = scorer_fn(trace=trace_dict, expectations=trace_expectations)
            results[name] = {"value": fb.value, "rationale": fb.rationale}
            if fb.value == "yes":
                passed += 1
                total += 1
            elif fb.value == "no":
                total += 1
            # "skip" doesn't count toward total
        except Exception as e:
            results[name] = {"value": "error", "rationale": str(e)}

    score = passed / total if total > 0 else 0.5  # No expectations = neutral
    return score, results


def _compute_execution_success(agent_result: AgentResult) -> float:
    """Score based on whether tool calls succeeded.

    Returns ratio of successful tool calls (0-1).
    """
    tool_calls = agent_result.trace_metrics.tool_calls
    if not tool_calls:
        return 0.5  # No tool calls = neutral

    successful = sum(1 for tc in tool_calls if tc.success is True)
    total = sum(1 for tc in tool_calls if tc.success is not None)

    if total == 0:
        return 0.5

    return successful / total


class AgentEvaluator:
    """GEPA-compatible evaluator using real Claude Code agent + trace-based judges.

    Three trace-based judges (correctness, completeness, guideline adherence)
    inspect the actual execution trace via MLflow's tool-calling loop.  They
    can call ``read_eval_criteria`` and ``read_eval_reference`` to load
    domain-specific evaluation rubrics.

    Deterministic assertions and trace scorers remain as the static spine.

    Args:
        original_token_counts: Token counts of original artifacts for efficiency scoring.
        token_budget: Hard token ceiling.
        skill_guidelines: Guidelines from ground_truth.yaml and manifest.yaml.
        judge_model: LLM model for judges (from ``--judge-model``).
        mcp_config: MCP server configuration for the agent.
        allowed_tools: Allowed tools for the agent.
        agent_model: Model to use for the agent execution (from ``--agent-model``).
        agent_timeout: Timeout for each agent run in seconds.
        tool_modules: MCP tool modules from manifest.yaml for criteria filtering.
    """

    def __init__(
        self,
        original_token_counts: dict[str, int] | None = None,
        token_budget: int | None = None,
        skill_guidelines: list[str] | None = None,
        judge_model: str | None = None,
        mcp_config: dict[str, Any] | None = None,
        allowed_tools: list[str] | None = None,
        agent_model: str | None = None,
        agent_timeout: int = 300,
        mlflow_experiment: str | None = None,
        skill_name: str | None = None,
        tool_modules: list[str] | None = None,
    ):
        self._original_token_counts = original_token_counts or {}
        self._total_original_tokens = sum(self._original_token_counts.values())
        self._token_budget = token_budget
        self._mcp_config = mcp_config
        self._allowed_tools = allowed_tools
        self._agent_model = agent_model
        self._agent_timeout = agent_timeout
        self._mlflow_experiment = mlflow_experiment
        self._skill_name = skill_name

        # Caches for WITHOUT-skill runs (keyed by prompt hash)
        self._baseline_response_cache: dict[str, str] = {}
        self._baseline_trace_cache: dict[str, dict] = {}
        self._baseline_mlflow_trace_cache: dict[str, Any] = {}
        # Per-judge baseline caches (WITHOUT trace-based results are stable)
        self._baseline_correctness_cache: dict[str, JudgeFeedback] = {}
        self._baseline_completeness_cache: dict[str, JudgeFeedback] = {}
        self._cache_lock = threading.Lock()
        self._trace_judges_disabled = False

        # --- Adaptive eval criteria (from MLflow #21255 design) ---
        from .eval_criteria import discover_eval_criteria
        from .judge_tools import register_eval_tools

        self._eval_criteria = discover_eval_criteria()
        if tool_modules:
            self._eval_criteria = self._eval_criteria.filter_by_modules(tool_modules)
        register_eval_tools(self._eval_criteria)

        # --- Trace-based judges (primary — when mlflow_trace is available) ---
        # All use judge_model from --judge-model CLI flag.
        self._trace_correctness_judge = create_trace_correctness_judge(
            self._eval_criteria, skill_guidelines, judge_model=judge_model
        )
        self._trace_completeness_judge = create_trace_completeness_judge(
            self._eval_criteria, skill_guidelines, judge_model=judge_model
        )
        self._trace_guideline_judge = create_trace_guideline_judge(
            self._eval_criteria, skill_guidelines, judge_model=judge_model
        )

        # --- Field-based judges (fallback — when mlflow_trace is None) ---
        self._field_correctness_judge = create_correctness_judge(
            skill_guidelines, judge_model=judge_model
        )
        self._field_completeness_judge = create_completeness_judge(
            judge_model=judge_model
        )
        self._field_guideline_judge = create_guideline_adherence_judge(
            skill_guidelines, judge_model=judge_model
        )

        self._regression_judge = create_regression_judge(judge_model=judge_model)

    def _run_agent(self, prompt: str, skill_md: str | None = None) -> AgentResult:
        """Run the agent and return result. Synchronous wrapper."""
        return run_agent_sync_wrapper(
            prompt=prompt,
            skill_md=skill_md,
            mcp_config=self._mcp_config,
            allowed_tools=self._allowed_tools,
            timeout_seconds=self._agent_timeout,
            model=self._agent_model,
            mlflow_experiment=self._mlflow_experiment,
            skill_name=self._skill_name,
        )

    def _get_baseline(self, prompt: str) -> tuple[str, dict, Any]:
        """Get WITHOUT-skill baseline response, trace, and MLflow trace, cached by prompt hash."""
        key = _prompt_hash(prompt)
        with self._cache_lock:
            if key in self._baseline_response_cache:
                return (
                    self._baseline_response_cache[key],
                    self._baseline_trace_cache[key],
                    self._baseline_mlflow_trace_cache.get(key),
                )
        # Agent run is expensive — release lock while running
        result = self._run_agent(prompt, skill_md=None)
        with self._cache_lock:
            if key not in self._baseline_response_cache:
                self._baseline_response_cache[key] = result.response_text
                self._baseline_trace_cache[key] = result.trace_metrics.to_dict()
                self._baseline_mlflow_trace_cache[key] = result.mlflow_trace
            return (
                self._baseline_response_cache[key],
                self._baseline_trace_cache[key],
                self._baseline_mlflow_trace_cache.get(key),
            )

    def __call__(
        self,
        candidate: dict[str, str],
        example: dict,
    ) -> tuple[float, dict]:
        """Evaluate a candidate skill against a single task using agent execution.

        GEPA-compatible signature: (candidate, example) -> (score, side_info)

        Wrapped in try-except so that any uncaught exception (timeout, network
        error, etc.) returns a fallback zero score instead of crashing GEPA.
        """
        try:
            return self._evaluate(candidate, example)
        except Exception as e:
            logger.error("AgentEvaluator error for task: %s", e)
            return 0.0, {"_error": str(e), "scores": {"final": 0.0}}

    def _evaluate(
        self,
        candidate: dict[str, str],
        example: dict,
    ) -> tuple[float, dict]:
        """Inner evaluation logic, called by __call__ with error handling."""
        skill_md = candidate.get("skill_md", "")
        prompt = example.get("input", "")

        # Decode expectations
        expectations: dict[str, Any] = {}
        expectations_json = example.get("additional_context", {}).get(
            "expectations", ""
        )
        if expectations_json:
            try:
                expectations = json.loads(expectations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        trace_expectations = expectations.get("trace_expectations", {})

        if not prompt:
            return 0.0, {"_error": "No prompt for this task"}

        # Phase 1: Run agent WITH skill
        logger.info("Running agent WITH skill...")
        start = time.monotonic()
        with_result = self._run_agent(prompt, skill_md=skill_md)
        with_duration = time.monotonic() - start
        logger.info("WITH-skill agent completed in %.1fs", with_duration)

        # Phase 2: Run agent WITHOUT skill (cached)
        logger.info("Running agent WITHOUT skill (cached if available)...")
        without_response, without_trace, without_mlflow_trace = self._get_baseline(
            prompt
        )

        with_response = with_result.response_text
        with_trace = with_result.trace_metrics.to_dict()

        # Build expectations text for judges
        facts = expectations.get("expected_facts", [])
        patterns = expectations.get("expected_patterns", [])
        guidelines = expectations.get("guidelines", [])

        facts_str = "\n".join(f"- {f}" for f in facts) if facts else "None specified"
        patterns_str = (
            "\n".join(
                f"- {p}"
                if isinstance(p, str)
                else f"- {p.get('description', p.get('pattern', ''))}"
                for p in patterns
            )
            if patterns
            else "None specified"
        )
        guidelines_str = (
            "\n".join(f"- {g}" for g in guidelines) if guidelines else "None specified"
        )
        expectations_text = f"Expected facts:\n{facts_str}\n\nExpected patterns:\n{patterns_str}\n\nGuidelines:\n{guidelines_str}"
        expectations_dict = {"criteria": expectations_text}

        baseline_key = _prompt_hash(prompt)

        # Phase 3: Multi-judge scoring
        # Try trace-based judges first (richer signal from actual execution).
        # If trace judge fails (model doesn't support tool-calling + structured
        # output, or trace is None), fall back to field-based judges.
        # Circuit breaker: after first failure, skip trace judges entirely
        # to avoid wasting API calls on a model that can't handle them.
        def _judge_with_fallback(
            trace_judge,
            field_judge,
            *,
            mlflow_trace,
            response_text,
            judge_name,
        ) -> JudgeFeedback:
            """Try trace-based judge, fall back to field-based on failure."""
            with self._cache_lock:
                trace_disabled = self._trace_judges_disabled
            if mlflow_trace is not None and not trace_disabled:
                fb = run_judge_safe(
                    trace_judge,
                    trace=mlflow_trace,
                    expectations=expectations_dict,
                    name=judge_name,
                )
                # Trace judge succeeded if it returned a real verdict
                if "Judge error" not in fb.rationale:
                    return fb
                # Circuit breaker: disable trace judges for this evaluator
                with self._cache_lock:
                    if not self._trace_judges_disabled:
                        self._trace_judges_disabled = True
                        logger.warning(
                            "Trace-based judges not supported by current model — "
                            "using field-based judges for all remaining evaluations"
                        )

            # Field-based judge (always works)
            return run_judge_safe(
                field_judge,
                inputs=prompt,
                outputs=response_text,
                expectations=expectations_dict,
                name=judge_name,
            )

        # Correctness: WITH + WITHOUT (WITHOUT cached)
        correctness_with_fb = _judge_with_fallback(
            self._trace_correctness_judge,
            self._field_correctness_judge,
            mlflow_trace=with_result.mlflow_trace,
            response_text=with_response,
            judge_name="correctness_with",
        )
        with self._cache_lock:
            need_correctness_baseline = (
                baseline_key not in self._baseline_correctness_cache
            )
        if need_correctness_baseline:
            fb = _judge_with_fallback(
                self._trace_correctness_judge,
                self._field_correctness_judge,
                mlflow_trace=without_mlflow_trace,
                response_text=without_response,
                judge_name="correctness_without",
            )
            with self._cache_lock:
                if baseline_key not in self._baseline_correctness_cache:
                    self._baseline_correctness_cache[baseline_key] = fb
        with self._cache_lock:
            correctness_without_fb = self._baseline_correctness_cache[baseline_key]

        # Completeness: WITH + WITHOUT (WITHOUT cached)
        completeness_with_fb = _judge_with_fallback(
            self._trace_completeness_judge,
            self._field_completeness_judge,
            mlflow_trace=with_result.mlflow_trace,
            response_text=with_response,
            judge_name="completeness_with",
        )
        with self._cache_lock:
            need_completeness_baseline = (
                baseline_key not in self._baseline_completeness_cache
            )
        if need_completeness_baseline:
            fb = _judge_with_fallback(
                self._trace_completeness_judge,
                self._field_completeness_judge,
                mlflow_trace=without_mlflow_trace,
                response_text=without_response,
                judge_name="completeness_without",
            )
            with self._cache_lock:
                if baseline_key not in self._baseline_completeness_cache:
                    self._baseline_completeness_cache[baseline_key] = fb
        with self._cache_lock:
            completeness_without_fb = self._baseline_completeness_cache[baseline_key]

        # Guideline adherence: WITH only
        guideline_adherence_fb = _judge_with_fallback(
            self._trace_guideline_judge,
            self._field_guideline_judge,
            mlflow_trace=with_result.mlflow_trace,
            response_text=with_response,
            judge_name="guideline_adherence",
        )

        # Convert categorical verdicts to float scores
        correctness_with = _categorical_to_float(correctness_with_fb.value)
        correctness_without = _categorical_to_float(correctness_without_fb.value)
        completeness_with = _categorical_to_float(completeness_with_fb.value)
        completeness_without = _categorical_to_float(completeness_without_fb.value)
        guideline_adherence_score = _categorical_to_float(guideline_adherence_fb.value)

        # Per-dimension effectiveness deltas
        correctness_delta = correctness_with - correctness_without
        completeness_delta = completeness_with - completeness_without
        effectiveness_delta = (correctness_delta + completeness_delta) / 2.0

        if effectiveness_delta > 0.05:
            effectiveness_verdict = "improved"
        elif effectiveness_delta < -0.05:
            effectiveness_verdict = "regressed"
        else:
            effectiveness_verdict = "same"

        # Regression judge (conditional on delta < -0.05)
        regression_penalty = 0.0
        regression_fb = None
        if effectiveness_delta < -0.05:
            comparison_input = (
                f"QUESTION:\n{prompt}\n\n"
                f"WITH-SKILL RESPONSE:\n{with_response}\n\n"
                f"WITHOUT-SKILL RESPONSE:\n{without_response}"
            )
            regression_fb = run_judge_safe(
                self._regression_judge,
                inputs=comparison_input,
                expectations=expectations_dict,
                name="regression",
            )
            reg_val = regression_fb.value
            if isinstance(reg_val, bool):
                regression_penalty = 1.0 if reg_val else 0.0
            elif isinstance(reg_val, str) and reg_val.strip().lower() in (
                "yes",
                "true",
            ):
                regression_penalty = 1.0

        # Phase 4: Deterministic fact/pattern assertions (zero LLM cost — static spine)
        with_assertion_results = run_all_assertions(with_response, expectations)
        without_assertion_results = run_all_assertions(without_response, expectations)

        fact_results = [r for r in with_assertion_results if r.assertion_type == "fact"]
        pattern_results = [
            r for r in with_assertion_results if r.assertion_type == "pattern"
        ]
        fact_score = (
            sum(1 for r in fact_results if r.passed) / len(fact_results)
            if fact_results
            else 1.0
        )
        pattern_score = (
            sum(1 for r in pattern_results if r.passed) / len(pattern_results)
            if pattern_results
            else 1.0
        )

        failure_summary = summarize_failures(
            with_assertion_results, without_assertion_results
        )

        # Phase 5: Deterministic trace scorers (static spine)
        behavioral_score, behavioral_details = _run_behavioral_scorers(
            with_trace, trace_expectations
        )
        execution_success = _compute_execution_success(with_result)

        # Phase 6: Token efficiency
        total_candidate_tokens = sum(count_tokens(v) for v in candidate.values())
        if self._total_original_tokens > 0:
            ratio = total_candidate_tokens / self._total_original_tokens
            if ratio <= 1.0:
                token_efficiency = 1.0 + 0.15 * (1.0 - ratio)
            else:
                token_efficiency = max(0.0, 2.0 - ratio)

            if self._token_budget and total_candidate_tokens > self._token_budget:
                over_ratio = total_candidate_tokens / self._token_budget
                token_efficiency = min(token_efficiency, max(0.0, 2.0 - over_ratio))
        else:
            token_efficiency = 1.0

        # Composite score: trace judges subsume tool_correctness + behavioral
        quality_composite = (
            correctness_with + completeness_with + guideline_adherence_score
        ) / 3.0
        assertion_coverage = 0.5 * fact_score + 0.5 * pattern_score

        final_score = max(
            0.0,
            min(
                1.0,
                0.25 * effectiveness_delta
                + 0.20 * correctness_with
                + 0.15 * completeness_with
                + 0.15 * guideline_adherence_score
                + 0.10 * assertion_coverage
                + 0.05 * execution_success
                + 0.05 * token_efficiency
                - 0.05 * regression_penalty,
            ),
        )

        # Build rich side_info for GEPA reflection
        side_info: dict[str, Any] = {}

        if prompt:
            side_info["Task"] = prompt[:500]

        # Per-dimension judge feedback (GEPA renders each key as a markdown header)
        side_info["Judge_correctness_with"] = {
            "verdict": str(correctness_with_fb.value),
            "score": correctness_with,
            "rationale": correctness_with_fb.rationale,
        }
        side_info["Judge_correctness_without"] = {
            "verdict": str(correctness_without_fb.value),
            "score": correctness_without,
            "rationale": correctness_without_fb.rationale,
        }
        side_info["Judge_completeness_with"] = {
            "verdict": str(completeness_with_fb.value),
            "score": completeness_with,
            "rationale": completeness_with_fb.rationale,
        }
        side_info["Judge_completeness_without"] = {
            "verdict": str(completeness_without_fb.value),
            "score": completeness_without,
            "rationale": completeness_without_fb.rationale,
        }
        side_info["Judge_guideline_adherence"] = {
            "verdict": str(guideline_adherence_fb.value),
            "score": guideline_adherence_score,
            "rationale": guideline_adherence_fb.rationale,
        }

        # Per-dimension effectiveness deltas
        side_info["Judge_effectiveness"] = {
            "verdict": effectiveness_verdict,
            "correctness_delta": correctness_delta,
            "completeness_delta": completeness_delta,
            "overall_delta": effectiveness_delta,
        }

        # Regression analysis (only when regression detected)
        if regression_fb and regression_penalty > 0:
            side_info["Regression_Analysis"] = {
                "rationale": regression_fb.rationale,
            }

        # Assertion-based structured feedback
        side_info["Missing_Facts"] = [r.rationale for r in fact_results if not r.passed]
        side_info["Missing_Patterns"] = [
            r.rationale for r in pattern_results if not r.passed
        ]
        side_info["Passed_Facts"] = [r.rationale for r in fact_results if r.passed]
        side_info["Passed_Patterns"] = [
            r.rationale for r in pattern_results if r.passed
        ]

        if failure_summary.get("Error") or failure_summary.get("Regressions"):
            side_info["skill_md_specific_info"] = {
                "Assertion_Diagnostics": failure_summary.get("Error", ""),
                "Regressions": failure_summary.get("Regressions", ""),
            }

        # Agent-specific trace details
        side_info["agent_trace"] = {
            "total_tool_calls": with_trace.get("tools", {}).get("total_calls", 0),
            "tool_counts": with_trace.get("tools", {}).get("by_name", {}),
            "duration_ms": with_result.duration_ms,
            "success": with_result.success,
            "tokens": with_trace.get("tokens", {}),
        }
        side_info["behavioral_scores"] = behavioral_details
        side_info["execution_success"] = execution_success

        # Expected vs Actual
        reference_answer = example.get("answer", "")
        if reference_answer:
            side_info["Expected"] = reference_answer[:2000]
        if with_response:
            side_info["Actual"] = with_response[:2000]

        # Score breakdown (feeds GEPA's Pareto frontier)
        side_info["scores"] = {
            "correctness_with": correctness_with,
            "correctness_without": correctness_without,
            "completeness_with": completeness_with,
            "completeness_without": completeness_without,
            "guideline_adherence": guideline_adherence_score,
            "quality_composite": quality_composite,
            "correctness_delta": correctness_delta,
            "completeness_delta": completeness_delta,
            "skill_effectiveness": effectiveness_delta,
            "regression_penalty": regression_penalty,
            "fact_coverage": fact_score,
            "pattern_adherence": pattern_score,
            "execution_success": execution_success,
            "token_efficiency": token_efficiency,
            "final": final_score,
        }

        side_info["token_counts"] = {
            "candidate_total": total_candidate_tokens,
            "original_total": self._total_original_tokens,
        }
        if self._token_budget:
            side_info["token_counts"]["budget"] = self._token_budget

        # Diagnostic labels
        weakest_dim = (
            "correctness" if correctness_with <= completeness_with else "completeness"
        )
        weakest_score = min(correctness_with, completeness_with)

        if failure_summary.get("Error"):
            side_info["Error"] = failure_summary["Error"]
        elif effectiveness_delta < -0.05:
            regressed_dims = []
            if correctness_delta < -0.05:
                regressed_dims.append(f"correctness({correctness_delta:+.2f})")
            if completeness_delta < -0.05:
                regressed_dims.append(f"completeness({completeness_delta:+.2f})")
            dims_str = (
                ", ".join(regressed_dims)
                if regressed_dims
                else f"overall({effectiveness_delta:+.2f})"
            )
            side_info["Error"] = (
                f"REGRESSION: {dims_str}. "
                f"correctness: {correctness_with:.2f} (was {correctness_without:.2f}), "
                f"completeness: {completeness_with:.2f} (was {completeness_without:.2f})"
            )
        elif weakest_score < 0.6:
            side_info["Error"] = (
                f"NEEDS_SKILL: weakest dimension is {weakest_dim}={weakest_score:.2f}. "
                f"correctness={correctness_with:.2f}, completeness={completeness_with:.2f}, "
                f"guideline_adherence={guideline_adherence_score:.2f}"
            )

        return final_score, side_info


def create_agent_evaluator(
    skill_name: str,
    original_token_counts: dict[str, int] | None = None,
    token_budget: int | None = None,
    judge_model: str | None = None,
    mcp_config: dict[str, Any] | None = None,
    allowed_tools: list[str] | None = None,
    agent_model: str | None = None,
    agent_timeout: int = 300,
    mlflow_experiment: str | None = None,
    tool_modules: list[str] | None = None,
) -> Callable:
    """Factory for agent-based evaluator with trace-based judges.

    Returns a GEPA-compatible callable: (candidate, example) -> (score, side_info)

    Args:
        skill_name: Name of the skill being evaluated.
        judge_model: LLM model for judges (from ``--judge-model``).
        agent_model: Model for Claude Code execution (from ``--agent-model``).
        tool_modules: MCP tool modules from manifest.yaml for criteria filtering.
    """
    from .skillbench_evaluator import _collect_skill_guidelines

    skill_guidelines = _collect_skill_guidelines(skill_name)
    if skill_guidelines:
        logger.info(
            "Loaded %d domain guidelines for agent trace judges", len(skill_guidelines)
        )

    return AgentEvaluator(
        original_token_counts=original_token_counts,
        token_budget=token_budget,
        skill_guidelines=skill_guidelines,
        judge_model=judge_model,
        mcp_config=mcp_config,
        allowed_tools=allowed_tools,
        agent_model=agent_model,
        agent_timeout=agent_timeout,
        mlflow_experiment=mlflow_experiment,
        skill_name=skill_name,
        tool_modules=tool_modules,
    )


def build_agent_eval_background(
    skill_name: str,
    original_token_count: int,
    baseline_scores: dict[str, float] | None = None,
    baseline_side_info: dict[str, dict] | None = None,
    focus_areas: list[str] | None = None,
) -> str:
    """Build GEPA reflection context specific to agent evaluation.

    Highlights trace-based judge signals and adaptive eval criteria.
    """
    baseline_desc = ""
    if baseline_scores:
        mean_score = sum(baseline_scores.values()) / len(baseline_scores)
        baseline_desc = (
            f"\nBASELINE: mean {mean_score:.3f} across {len(baseline_scores)} tasks."
        )

        if baseline_side_info:
            needs_skill_ids = []
            regression_ids = []
            tool_issues = []
            for tid, info in baseline_side_info.items():
                error = info.get("Error", "")
                if "NEEDS_SKILL" in error:
                    needs_skill_ids.append(tid)
                if "REGRESSION" in error:
                    regression_ids.append(tid)
                behavioral = info.get("behavioral_scores", {})
                for scorer_name, result in behavioral.items():
                    if result.get("value") == "no":
                        tool_issues.append(
                            f"{tid}: {scorer_name} - {result.get('rationale', '')[:80]}"
                        )

            if needs_skill_ids:
                baseline_desc += f"\n  NEEDS_SKILL ({len(needs_skill_ids)} tasks): {', '.join(needs_skill_ids[:5])}"
            if regression_ids:
                baseline_desc += f"\n  REGRESSION ({len(regression_ids)} tasks): {', '.join(regression_ids[:5])}"
            if tool_issues:
                baseline_desc += f"\n  TOOL ISSUES ({len(tool_issues)}):"
                for issue in tool_issues[:5]:
                    baseline_desc += f"\n    - {issue}"

    focus_desc = ""
    if focus_areas:
        focus_items = "\n".join(f"  - {f}" for f in focus_areas)
        focus_desc = (
            f"\n\nUSER FOCUS PRIORITIES:\n{focus_items}\n"
            "These are high-priority areas the user wants the skill to emphasize. "
            "Weight these priorities heavily in your optimization decisions."
        )

    return (
        f"You are refining SKILL.md for '{skill_name}'.\n"
        "The skill is scored by a real Claude Code agent that executes tasks.\n"
        "Three trace-based MLflow judges inspect the actual execution trace:\n"
        "  1. CORRECTNESS — facts, API references, code syntax, tool call accuracy\n"
        "  2. COMPLETENESS — all parts addressed, expected facts/patterns present\n"
        "  3. GUIDELINE ADHERENCE — Databricks patterns, tool selection, conventions\n"
        "Each judge returns 'excellent', 'acceptable', or 'poor' with rationale.\n\n"
        "Judges can load domain-specific rubrics (SQL patterns, tool selection guides)\n"
        "via read_eval_criteria/read_eval_reference tools — their rationale includes\n"
        "trace-specific evidence (which spans, which tool calls, which errors).\n\n"
        "Use Judge_correctness_with/without for accuracy feedback.\n"
        "Use Judge_completeness_with/without for coverage feedback.\n"
        "Use Judge_guideline_adherence for pattern compliance feedback.\n"
        "Use Judge_effectiveness for per-dimension deltas.\n"
        "Missing_Facts and Missing_Patterns show exact assertion pass/fail.\n\n"
        "Focus on: guiding the agent to use the RIGHT tools with CORRECT arguments.\n"
        "Avoid: unnecessary tool calls, wrong tool selection, verbose instructions."
        f"{baseline_desc}"
        f"{focus_desc}"
    )
