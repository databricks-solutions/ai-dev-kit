"""SkillBench evaluator: measure skill effectiveness via WITH vs WITHOUT comparison.

Evaluates skills by measuring agent performance WITH the skill vs WITHOUT it
on real tasks. Uses three focused MLflow judges (correctness, completeness,
guideline adherence) as the primary scoring mechanism — each judge provides
categorical verdicts AND rich rationale for GEPA's reflection LM.

  Phase 1: WITH-SKILL  -- LLM generates response with SKILL.md in context
  Phase 2: WITHOUT-SKILL -- LLM generates response with NO skill (cached once)
  Phase 3: JUDGES -- correctness + completeness (WITH+WITHOUT), guideline_adherence (WITH only),
           regression (conditional on delta < -0.05)
  Phase 4: ASSERTIONS -- deterministic fact/pattern checking (zero LLM cost)

Scoring weights:
  30% Effectiveness Delta (mean of correctness_delta + completeness_delta)
  20% Quality Composite (mean of correctness + completeness + guideline_adherence WITH scores)
  15% Fact/Pattern Coverage (deterministic assertions from assertions.py)
  10% Guideline Adherence (dedicated weight for practices)
   5% Structure (syntax validity)
  10% Token Efficiency (smaller candidates score higher)
  10% Regression Penalty (explicit penalty when regression_judge fires)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Callable

from mlflow.entities import Feedback

from ..scorers.universal import python_syntax, sql_syntax, no_hallucinated_apis
from .assertions import run_all_assertions, summarize_failures
from .judges import (
    JudgeFeedback,
    _safe_parse_score,
    create_correctness_judge,
    create_completeness_judge,
    create_guideline_adherence_judge,
    create_regression_judge,
    discover_skill_paths,
    run_judge_safe,
    completion_with_fallback,
)
from .utils import count_tokens

logger = logging.getLogger(__name__)


def _prompt_hash(prompt: str) -> str:
    """Stable hash for caching baseline results by prompt."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


class _RateLimiter:
    """Thread-safe token-bucket rate limiter for LLM API calls."""

    def __init__(self, max_concurrent: int = 2, min_interval: float = 1.0):
        self._semaphore = threading.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last_call: float = 0.0

    def acquire(self) -> None:
        self._semaphore.acquire()
        with self._lock:
            now = time.monotonic()
            wait = self._last_call + self._min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def release(self) -> None:
        self._semaphore.release()


# Module-level rate limiter shared across evaluator instances.
# Configurable via env vars for workspaces with stricter rate limits.
_rate_limiter = _RateLimiter(
    max_concurrent=int(os.environ.get("GEPA_MAX_CONCURRENT_LLM", "4")),
    min_interval=float(os.environ.get("GEPA_MIN_LLM_INTERVAL", "0.2")),
)


def _completion_with_backoff(*, max_retries: int = 3, **kwargs) -> Any:
    """Call litellm.completion with rate limiting and model fallback.

    Uses the centralized completion_with_fallback which handles:
    - Rate limit errors with exponential backoff
    - Model fallback chain on persistent rate limits
    - AI Gateway routing when configured
    """
    _rate_limiter.acquire()
    try:
        return completion_with_fallback(max_retries=max_retries, **kwargs)
    finally:
        _rate_limiter.release()


def _run_structure_scorers(text: str) -> float:
    """Run structure validation scorers on text, return 0.0-1.0 composite."""
    outputs = {"response": text}
    scores: list[float] = []
    for scorer_fn in [python_syntax, sql_syntax, no_hallucinated_apis]:
        try:
            result = scorer_fn(outputs=outputs)
            if isinstance(result, list):
                for fb in result:
                    if fb.value == "yes":
                        scores.append(1.0)
                    elif fb.value == "no":
                        scores.append(0.0)
            elif isinstance(result, Feedback):
                if result.value == "yes":
                    scores.append(1.0)
                elif result.value == "no":
                    scores.append(0.0)
        except Exception:
            pass
    return sum(scores) / len(scores) if scores else 1.0


def _effectiveness_score(verdict: str | float) -> float:
    """Convert effectiveness verdict to numeric score for weighting."""
    if isinstance(verdict, (int, float)):
        return max(0.0, min(1.0, float(verdict)))
    v = str(verdict).strip().lower()
    if v == "improved":
        return 1.0
    elif v == "same":
        return 0.5
    elif v == "regressed":
        return 0.0
    # Fallback: try bool-like
    if v in ("yes", "true"):
        return 1.0
    if v in ("no", "false"):
        return 0.0
    return 0.5


class SkillBenchEvaluator:
    """GEPA-compatible evaluator using three focused judges for scoring + diagnostics.

    Uses correctness, completeness, and guideline adherence judges with
    binary ``Literal["yes", "no"]`` feedback types.
    Produces decomposed signals for GEPA's reflection LM.

    Args:
        gen_model: LLM model for generating responses. Required.
        original_token_counts: Token counts of original artifacts for efficiency scoring.
        token_budget: Hard token ceiling; candidates exceeding this are penalized.
        skill_guidelines: Deduplicated guidelines from ground_truth.yaml for judges.
        judge_model: LLM model for judges. Defaults to GEPA_JUDGE_LM env
            or databricks/databricks-claude-sonnet-4-6.
    """

    def __init__(
        self,
        gen_model: str,
        original_token_counts: dict[str, int] | None = None,
        token_budget: int | None = None,
        skill_guidelines: list[str] | None = None,
        judge_model: str | None = None,
        tool_context: str | None = None,
        assessment_by_task: dict[str, list] | None = None,
    ):
        if not gen_model:
            raise ValueError("SkillBench evaluator requires a gen_model. Pass --gen-model or set GEPA_GEN_LM env var.")
        self.gen_model = gen_model
        self._baseline_response_cache: dict[str, str] = {}
        # Per-judge baseline caches (WITHOUT responses are stable across iterations)
        self._baseline_correctness_cache: dict[str, JudgeFeedback] = {}
        self._baseline_completeness_cache: dict[str, JudgeFeedback] = {}
        self._original_token_counts = original_token_counts or {}
        self._total_original_tokens = sum(self._original_token_counts.values())
        self._token_budget = token_budget
        self._tool_context = tool_context or ""
        self._assessment_by_task = assessment_by_task or {}

        # Cache WITH-skill evaluation results keyed on (prompt_hash, candidate_hash)
        # to avoid re-evaluation when GEPA calls the evaluator multiple times on
        # the same candidate-task pair.
        self._with_skill_cache: dict[str, tuple[float, dict]] = {}

        # Discover eval criteria skill paths (static spine + adaptive layer)
        skill_paths = discover_skill_paths()

        # Create three focused judge instances
        self._correctness_judge = create_correctness_judge(skill_paths=skill_paths, judge_model=judge_model)
        self._completeness_judge = create_completeness_judge(skill_paths=skill_paths, judge_model=judge_model)
        self._guideline_adherence_judge = create_guideline_adherence_judge(
            skill_paths=skill_paths, skill_guidelines=skill_guidelines, judge_model=judge_model
        )
        self._regression_judge = create_regression_judge(judge_model=judge_model)

    def _generate_response(self, prompt: str, skill_context: str | None = None) -> str:
        """Generate a response with or without skill context."""
        messages = []
        if skill_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Use ONLY the following skill documentation to answer "
                        "the user's question. Do not use any other knowledge.\n\n"
                        f"{skill_context}"
                    ),
                }
            )
        messages.append({"role": "user", "content": prompt})

        resp = _completion_with_backoff(
            model=self.gen_model,
            messages=messages,
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    def _get_baseline_response(self, prompt: str) -> str:
        """Get WITHOUT-skill baseline response, computing once then caching."""
        key = _prompt_hash(prompt)
        if key not in self._baseline_response_cache:
            response = self._generate_response(prompt, skill_context=None)
            self._baseline_response_cache[key] = response
        return self._baseline_response_cache[key]

    def __call__(
        self,
        candidate: dict[str, str],
        example: dict,
    ) -> tuple[float, dict]:
        """Evaluate a candidate skill against a single task example.

        GEPA-compatible signature: (candidate, example) -> (score, side_info)
        """
        skill_md = candidate.get("skill_md", "")

        # Check candidate-level cache
        prompt = example.get("input", "")
        candidate_hash = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()[:16]
        cache_key = f"{_prompt_hash(prompt)}:{candidate_hash}"
        if cache_key in self._with_skill_cache:
            return self._with_skill_cache[cache_key]

        # Build combined context: skill + read-only tool descriptions
        # During skill optimization, tools come from self._tool_context (read-only).
        # During tool optimization, tools come from candidate keys (optimizable).
        tool_parts = []
        for key in sorted(candidate):
            if key.startswith("tools_"):
                tool_parts.append(candidate[key])

        full_context = skill_md
        if tool_parts:
            full_context += "\n\n## Available MCP Tools\n\n" + "\n\n".join(tool_parts)
        elif self._tool_context:
            full_context += "\n\n## Available MCP Tools\n\n" + self._tool_context

        # Decode expectations
        expectations: dict[str, Any] = {}
        expectations_json = example.get("additional_context", {}).get("expectations", "")
        if expectations_json:
            try:
                expectations = json.loads(expectations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        if not prompt or not expectations:
            return 0.0, {"_error": "No prompt or expectations for this task"}

        # Phase 1: Generate WITH-skill response
        with_response = self._generate_response(prompt, skill_context=full_context)

        # Phase 2: Generate WITHOUT-skill response (cached)
        without_response = self._get_baseline_response(prompt)

        # Phase 3: Multi-judge scoring
        facts = expectations.get("expected_facts", [])
        patterns = expectations.get("expected_patterns", [])
        guidelines = expectations.get("guidelines", [])

        # Build flat strings for judge templates — make_judge only supports
        # top-level {{ inputs }}, {{ outputs }}, {{ expectations }} variables.
        facts_str = "\n".join(f"- {f}" for f in facts) if facts else "None specified"
        patterns_str = (
            "\n".join(
                f"- {p}" if isinstance(p, str) else f"- {p.get('description', p.get('pattern', ''))}" for p in patterns
            )
            if patterns
            else "None specified"
        )
        guidelines_str = "\n".join(f"- {g}" for g in guidelines) if guidelines else "None specified"

        expectations_text = (
            f"Expected facts:\n{facts_str}\n\nExpected patterns:\n{patterns_str}\n\nGuidelines:\n{guidelines_str}"
        )

        # make_judge requires expectations as dict, inputs/outputs as Any.
        expectations_dict = {"criteria": expectations_text}

        baseline_key = _prompt_hash(prompt)

        # --- Correctness judge: WITH + WITHOUT (WITHOUT cached) ---
        correctness_with_fb = run_judge_safe(
            self._correctness_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="correctness_with",
        )
        if baseline_key not in self._baseline_correctness_cache:
            self._baseline_correctness_cache[baseline_key] = run_judge_safe(
                self._correctness_judge,
                inputs=prompt,
                outputs=without_response,
                expectations=expectations_dict,
                name="correctness_without",
            )
        correctness_without_fb = self._baseline_correctness_cache[baseline_key]

        # --- Completeness judge: WITH + WITHOUT (WITHOUT cached) ---
        completeness_with_fb = run_judge_safe(
            self._completeness_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="completeness_with",
        )
        if baseline_key not in self._baseline_completeness_cache:
            self._baseline_completeness_cache[baseline_key] = run_judge_safe(
                self._completeness_judge,
                inputs=prompt,
                outputs=without_response,
                expectations=expectations_dict,
                name="completeness_without",
            )
        completeness_without_fb = self._baseline_completeness_cache[baseline_key]

        # --- Guideline adherence judge: WITH only (meaningless without skill) ---
        guideline_adherence_fb = run_judge_safe(
            self._guideline_adherence_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="guideline_adherence",
        )

        # Convert categorical verdicts to float scores
        correctness_with = _safe_parse_score(correctness_with_fb.value)
        correctness_without = _safe_parse_score(correctness_without_fb.value)
        completeness_with = _safe_parse_score(completeness_with_fb.value)
        completeness_without = _safe_parse_score(completeness_without_fb.value)
        guideline_adherence_score = _safe_parse_score(guideline_adherence_fb.value)

        # Per-dimension effectiveness deltas
        correctness_delta = correctness_with - correctness_without
        completeness_delta = completeness_with - completeness_without
        effectiveness_delta = (correctness_delta + completeness_delta) / 2.0

        # Quality composite: mean of all three WITH scores
        quality_composite = (correctness_with + completeness_with + guideline_adherence_score) / 3.0

        # Derive effectiveness verdict
        if effectiveness_delta > 0.05:
            effectiveness_verdict = "improved"
        elif effectiveness_delta < -0.05:
            effectiveness_verdict = "regressed"
        else:
            effectiveness_verdict = "same"

        # --- Regression judge: conditional on delta < -0.05 ---
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
            # bool/yes → 1.0 (regression found), no → 0.0
            reg_val = regression_fb.value
            if isinstance(reg_val, bool):
                regression_penalty = 1.0 if reg_val else 0.0
            elif isinstance(reg_val, str) and reg_val.strip().lower() in ("yes", "true"):
                regression_penalty = 1.0

        # Phase 4: Deterministic fact/pattern assertions (zero LLM cost)
        with_results = run_all_assertions(with_response, expectations)
        without_results = run_all_assertions(without_response, expectations)

        fact_results = [r for r in with_results if r.assertion_type == "fact"]
        pattern_results = [r for r in with_results if r.assertion_type == "pattern"]
        fact_score = sum(1 for r in fact_results if r.passed) / len(fact_results) if fact_results else 1.0
        pattern_score = sum(1 for r in pattern_results if r.passed) / len(pattern_results) if pattern_results else 1.0

        # GEPA-friendly diagnostics from assertion comparison
        failure_summary = summarize_failures(with_results, without_results)

        # Structure validation on the skill itself
        structure = _run_structure_scorers(skill_md) if skill_md else 1.0

        # Token efficiency scoring
        total_candidate_tokens = sum(count_tokens(v) for v in candidate.values())

        if self._total_original_tokens > 0:
            ratio = total_candidate_tokens / self._total_original_tokens
            if ratio <= 1.0:
                efficiency = 1.0 + 0.15 * (1.0 - ratio)
            else:
                efficiency = max(0.0, 2.0 - ratio)

            if self._token_budget and total_candidate_tokens > self._token_budget:
                over_ratio = total_candidate_tokens / self._token_budget
                efficiency = min(efficiency, max(0.0, 2.0 - over_ratio))
        else:
            efficiency = 1.0

        # Weighted final score with new multi-judge weights
        fact_pattern = 0.5 * fact_score + 0.5 * pattern_score
        final_score = max(
            0.0,
            min(
                1.0,
                0.30 * effectiveness_delta
                + 0.20 * quality_composite
                + 0.15 * fact_pattern
                + 0.10 * guideline_adherence_score
                + 0.05 * structure
                + 0.10 * efficiency
                - 0.10 * regression_penalty,
            ),
        )

        # Build side info with FULL judge rationale (not truncated!)
        reference_answer = example.get("answer", "")

        side_info: dict[str, Any] = {}

        # Task context
        if prompt:
            side_info["Task"] = prompt[:500]

        # Per-dimension judge feedback — GEPA sees each as a separate section
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

        # Assertion-based structured feedback — GEPA renders each key as a markdown header
        side_info["Missing_Facts"] = [r.rationale for r in fact_results if not r.passed]
        side_info["Missing_Patterns"] = [r.rationale for r in pattern_results if not r.passed]
        side_info["Passed_Facts"] = [r.rationale for r in fact_results if r.passed]
        side_info["Passed_Patterns"] = [r.rationale for r in pattern_results if r.passed]

        # skill_md_specific_info — shown ONLY when reflecting on the skill component
        if failure_summary.get("Error") or failure_summary.get("Regressions"):
            side_info["skill_md_specific_info"] = {
                "Assertion_Diagnostics": failure_summary.get("Error", ""),
                "Regressions": failure_summary.get("Regressions", ""),
            }

        # Expected vs Actual for GEPA reflection
        if reference_answer:
            side_info["Expected"] = reference_answer[:2000]
        if with_response:
            side_info["Actual"] = with_response[:2000]

        # Score breakdown (scores dict feeds GEPA's Pareto frontier)
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
            "structure": structure,
            "token_efficiency": efficiency,
            "final": final_score,
        }

        # Token counts for GEPA Pareto tracking
        side_info["token_counts"] = {
            "candidate_total": total_candidate_tokens,
            "original_total": self._total_original_tokens,
        }
        if self._token_budget:
            side_info["token_counts"]["budget"] = self._token_budget

        # Inject matched real-world assessments from MLflow traces
        if self._assessment_by_task:
            task_id = example.get("additional_context", {}).get("task_id", "")
            matched = self._assessment_by_task.get(task_id) or self._assessment_by_task.get(_prompt_hash(prompt), [])
            if matched:
                side_info["real_world_assessments"] = [
                    {"name": a.name, "value": a.value, "rationale": a.rationale} for a in matched
                ]

        # Derive diagnostic labels from assertions + judge verdicts
        # Find weakest dimension for targeted GEPA feedback
        weakest_dim = "correctness" if correctness_with <= completeness_with else "completeness"
        weakest_score = min(correctness_with, completeness_with)

        if failure_summary.get("Error"):
            # Assertions detected specific NEEDS_SKILL/REGRESSION items
            side_info["Error"] = failure_summary["Error"]
        elif effectiveness_delta < -0.05:
            # Per-dimension regression info
            regressed_dims = []
            if correctness_delta < -0.05:
                regressed_dims.append(f"correctness({correctness_delta:+.2f})")
            if completeness_delta < -0.05:
                regressed_dims.append(f"completeness({completeness_delta:+.2f})")
            dims_str = ", ".join(regressed_dims) if regressed_dims else f"overall({effectiveness_delta:+.2f})"
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

        # Store in candidate-level cache
        self._with_skill_cache[cache_key] = (final_score, side_info)

        return final_score, side_info


def _collect_skill_guidelines(skill_name: str) -> list[str]:
    """Collect and deduplicate guidelines from ground_truth.yaml and manifest.yaml."""
    from pathlib import Path
    import yaml

    seen: set[str] = set()
    guidelines: list[str] = []

    # Collect from ground_truth.yaml test cases
    gt_path = Path(".test/skills") / skill_name / "ground_truth.yaml"
    if gt_path.exists():
        try:
            with open(gt_path) as f:
                data = yaml.safe_load(f) or {}
            for tc in data.get("test_cases", []):
                for g in tc.get("expectations", {}).get("guidelines", []):
                    g_norm = g.strip()
                    if g_norm and g_norm not in seen:
                        seen.add(g_norm)
                        guidelines.append(g_norm)
        except Exception:
            pass

    # Collect from manifest.yaml default_guidelines (includes [FOCUS] guidelines)
    manifest_path = Path(".test/skills") / skill_name / "manifest.yaml"
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f) or {}
            for g in manifest.get("scorers", {}).get("default_guidelines", []):
                g_norm = g.strip()
                if g_norm and g_norm not in seen:
                    seen.add(g_norm)
                    guidelines.append(g_norm)
        except Exception:
            pass

    return guidelines


def create_skillbench_evaluator(
    skill_name: str,
    gen_model: str,
    original_token_counts: dict[str, int] | None = None,
    token_budget: int | None = None,
    judge_model: str | None = None,
    tool_context: str | None = None,
    assessment_by_task: dict[str, list] | None = None,
) -> Callable:
    """Factory for SkillBench-style evaluator.

    Returns a GEPA-compatible callable: (candidate, example) -> (score, side_info)

    Judges are always enabled — they are the primary scoring mechanism.
    Guidelines from ground_truth.yaml are incorporated into the quality judge.

    Args:
        skill_name: Name of the skill being evaluated.
        gen_model: LLM model for generating responses. Required.
        original_token_counts: Token counts of original artifacts for efficiency scoring.
        token_budget: Hard token ceiling; candidates exceeding this are penalized.
        judge_model: LLM model for judges. Defaults to GEPA_JUDGE_LM env
            or databricks/databricks-claude-sonnet-4-6.
        tool_context: Read-only tool descriptions included in generation context
            but not optimized. Used during skill optimization so tools provide
            context without being GEPA components.
    """
    skill_guidelines = _collect_skill_guidelines(skill_name)
    if skill_guidelines:
        logger.info(
            "Loaded %d domain guidelines for quality judge",
            len(skill_guidelines),
        )

    from .judges import DEFAULT_JUDGE_LM

    effective_judge_model = judge_model or DEFAULT_JUDGE_LM
    logger.info("Judge model: %s", effective_judge_model)

    return SkillBenchEvaluator(
        gen_model=gen_model,
        original_token_counts=original_token_counts,
        token_budget=token_budget,
        skill_guidelines=skill_guidelines,
        judge_model=judge_model,
        tool_context=tool_context,
        assessment_by_task=assessment_by_task,
    )


def build_skillbench_background(
    skill_name: str,
    original_token_count: int,
    component_names: list[str] | None = None,
    baseline_scores: dict[str, float] | None = None,
    baseline_side_info: dict[str, dict] | None = None,
    token_budget: int | None = None,
    assessment_summary: str | None = None,
    focus_areas: list[str] | None = None,
) -> str:
    """Build concise GEPA reflection context for SkillBench optimization.

    Kept short so GEPA's reflection LM spends its context on the per-example
    diagnostics (judge rationale) rather than methodology.
    """
    baseline_desc = ""
    if baseline_scores:
        mean_score = sum(baseline_scores.values()) / len(baseline_scores)
        baseline_desc = f"\nBASELINE: mean {mean_score:.3f} across {len(baseline_scores)} tasks."

        if baseline_side_info:
            needs_skill_ids = []
            regression_ids = []
            for tid, info in baseline_side_info.items():
                error = info.get("Error", "")
                if "NEEDS_SKILL" in error:
                    needs_skill_ids.append(tid)
                if "REGRESSION" in error:
                    regression_ids.append(tid)
            if needs_skill_ids:
                baseline_desc += f"\n  NEEDS_SKILL ({len(needs_skill_ids)} tasks): {', '.join(needs_skill_ids[:5])}"
            if regression_ids:
                baseline_desc += f"\n  REGRESSION ({len(regression_ids)} tasks): {', '.join(regression_ids[:5])}"

    components_desc = ""
    if component_names and any(c.startswith("tools_") for c in component_names):
        tool_modules = [c.replace("tools_", "") for c in component_names if c.startswith("tools_")]
        components_desc = (
            f"\nAlso optimizing MCP tool descriptions for: {', '.join(tool_modules)}. "
            "Keep docstrings accurate and concise — every token counts toward the budget."
        )

    token_desc = (
        f"\nTOKEN EFFICIENCY (15% of score): Current artifacts total {original_token_count:,} tokens. "
        "Smaller candidates score HIGHER. Be ruthlessly concise."
    )
    if token_budget:
        token_desc += f"\nTOKEN BUDGET: {token_budget:,} tokens. Candidates exceeding this are heavily penalized."

    assessment_desc = ""
    if assessment_summary:
        assessment_desc = f"\n\n{assessment_summary}"

    focus_desc = ""
    if focus_areas:
        focus_items = "\n".join(f"  - {f}" for f in focus_areas)
        focus_desc = (
            f"\n\nUSER FOCUS PRIORITIES:\n{focus_items}\n"
            "These are high-priority areas the user wants the skill to emphasize. "
            "Weight these heavily in your optimization decisions."
        )

    return (
        f"You are refining SKILL.md for '{skill_name}'.\n"
        "The skill is scored by THREE focused MLflow judges:\n"
        "  1. CORRECTNESS — facts, API references, code syntax accuracy\n"
        "  2. COMPLETENESS — all parts addressed, all expected info present\n"
        "  3. GUIDELINE ADHERENCE — Databricks-specific patterns and practices\n"
        "Each judge returns 'excellent', 'acceptable', or 'poor' with rationale.\n\n"
        "Judge rationale in side_info explains exactly WHAT failed and WHY per dimension.\n"
        "Use Judge_correctness_with/without for accuracy feedback.\n"
        "Use Judge_completeness_with/without for coverage feedback.\n"
        "Use Judge_guideline_adherence for pattern compliance feedback.\n"
        "Use Judge_effectiveness for per-dimension deltas (correctness_delta, completeness_delta).\n"
        "Missing_Facts and Missing_Patterns show exact pass/fail for each expected assertion.\n"
        "Passed_Facts and Passed_Patterns show what the skill already covers.\n"
        "Focus on: specific API syntax, version requirements, non-obvious patterns.\n"
        "Do NOT add generic knowledge the agent already has."
        f"{baseline_desc}"
        f"{components_desc}"
        f"{token_desc}"
        f"{assessment_desc}"
        f"{focus_desc}"
    )
