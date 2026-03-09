"""SkillBench evaluator: measure skill effectiveness via WITH vs WITHOUT comparison.

Evaluates skills by measuring agent performance WITH the skill vs WITHOUT it
on real tasks. Uses MLflow judges as the primary scoring mechanism — judges
provide both scores AND rich rationale for GEPA's reflection LM.

  Phase 1: WITH-SKILL  -- LLM generates response with SKILL.md in context
  Phase 2: WITHOUT-SKILL -- LLM generates response with NO skill (cached once)
  Phase 3: JUDGE -- quality_judge scores both, effectiveness derived from delta

Scoring weights:
  40% Skill Effectiveness (quality_with - quality_without delta)
  30% Absolute Quality (quality_with score from judge)
   5% Structure (syntax validity)
  25% Token Efficiency (smaller candidates score higher)
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable

from mlflow.entities import Feedback

from ..scorers.universal import python_syntax, sql_syntax, no_hallucinated_apis
from .judges import (
    JudgeFeedback,
    create_skill_quality_judge,
    create_regression_judge,
    run_judge_safe,
    _safe_parse_score,
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
_rate_limiter = _RateLimiter(max_concurrent=4, min_interval=0.2)


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
    """GEPA-compatible evaluator using judges for scoring + diagnostics.

    Args:
        gen_model: LLM model for generating responses. Required.
        original_token_counts: Token counts of original artifacts for efficiency scoring.
        token_budget: Hard token ceiling; candidates exceeding this are penalized.
        skill_guidelines: Deduplicated guidelines from ground_truth.yaml for the quality judge.
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
            raise ValueError(
                "SkillBench evaluator requires a gen_model. Pass --gen-model or set GEPA_GEN_LM env var."
            )
        self.gen_model = gen_model
        self._baseline_response_cache: dict[str, str] = {}
        self._baseline_judge_cache: dict[str, JudgeFeedback] = {}
        self._original_token_counts = original_token_counts or {}
        self._total_original_tokens = sum(self._original_token_counts.values())
        self._token_budget = token_budget
        self._tool_context = tool_context or ""
        self._assessment_by_task = assessment_by_task or {}

        # Create judge instances with configurable model
        self._quality_judge = create_skill_quality_judge(
            skill_guidelines, judge_model=judge_model
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

        if not prompt or not expectations:
            return 0.0, {"_error": "No prompt or expectations for this task"}

        # Phase 1: Generate WITH-skill response
        with_response = self._generate_response(prompt, skill_context=full_context)

        # Phase 2: Generate WITHOUT-skill response (cached)
        without_response = self._get_baseline_response(prompt)

        # Phase 3: Judge-driven scoring
        facts = expectations.get("expected_facts", [])
        patterns = expectations.get("expected_patterns", [])
        guidelines = expectations.get("guidelines", [])

        # Build flat strings for judge templates — make_judge only supports
        # top-level {{ inputs }}, {{ outputs }}, {{ expectations }} variables.
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

        # make_judge requires expectations as dict, inputs/outputs as Any.
        # The template renders {{ expectations }} as the dict's string repr,
        # so we pack our formatted text into a single-key dict.
        expectations_dict = {"criteria": expectations_text}

        # Quality judge: score WITH response
        quality_with_fb = run_judge_safe(
            self._quality_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="quality_with",
        )

        # Quality judge: score WITHOUT response (cached — baseline never changes)
        baseline_key = _prompt_hash(prompt)
        if baseline_key not in self._baseline_judge_cache:
            self._baseline_judge_cache[baseline_key] = run_judge_safe(
                self._quality_judge,
                inputs=prompt,
                outputs=without_response,
                expectations=expectations_dict,
                name="quality_without",
            )
        quality_without_fb = self._baseline_judge_cache[baseline_key]

        # Parse scores
        score_with = _safe_parse_score(quality_with_fb.value)
        score_without = _safe_parse_score(quality_without_fb.value)
        effectiveness_delta = score_with - score_without

        # Derive effectiveness verdict from quality delta (no LLM call needed)
        if effectiveness_delta > 0.05:
            effectiveness_verdict = 1.0  # improved
        elif effectiveness_delta < -0.05:
            effectiveness_verdict = 0.0  # regressed
        else:
            effectiveness_verdict = 0.5  # same

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

        # Weighted final score
        final_score = (
            0.40 * max(0.0, effectiveness_delta)
            + 0.30 * score_with
            + 0.05 * structure
            + 0.25 * efficiency
        )

        # Build side info with FULL judge rationale (not truncated!)
        reference_answer = example.get("answer", "")

        side_info: dict[str, Any] = {}

        # Task context
        if prompt:
            side_info["Task"] = prompt[:200]

        # Full judge feedback — the critical fix for GEPA optimization
        side_info["Judge_quality_with"] = {
            "score": score_with,
            "rationale": quality_with_fb.rationale,
        }
        side_info["Judge_quality_without"] = {
            "score": score_without,
            "rationale": quality_without_fb.rationale,
        }
        side_info["Judge_effectiveness"] = {
            "verdict": (
                "improved"
                if effectiveness_verdict == 1.0
                else "regressed"
                if effectiveness_verdict == 0.0
                else "same"
            ),
            "delta": effectiveness_delta,
        }

        # Expected vs Actual for GEPA reflection
        if reference_answer:
            side_info["Expected"] = reference_answer[:500]
        if with_response:
            side_info["Actual"] = with_response[:500]

        # Score breakdown
        side_info["scores"] = {
            "quality_with": score_with,
            "quality_without": score_without,
            "skill_effectiveness": effectiveness_delta,
            "effectiveness_verdict": effectiveness_verdict,
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
            matched = self._assessment_by_task.get(
                task_id
            ) or self._assessment_by_task.get(_prompt_hash(prompt), [])
            if matched:
                side_info["real_world_assessments"] = [
                    {"name": a.name, "value": a.value, "rationale": a.rationale}
                    for a in matched
                ]

        # Derive diagnostic labels from judge verdicts for backward compat
        if effectiveness_delta < -0.05:
            side_info["Error"] = (
                f"REGRESSION: skill_effectiveness delta={effectiveness_delta:.2f} "
                f"(with={score_with:.2f}, without={score_without:.2f})"
            )
            side_info["skill_md_specific_info"] = {
                "Regressions": quality_with_fb.rationale,
            }
        elif score_with < 0.5:
            side_info["Error"] = (
                f"NEEDS_SKILL: quality_with={score_with:.2f}, missing content. Judge: {quality_with_fb.rationale[:200]}"
            )

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
        baseline_desc = (
            f"\nBASELINE: mean {mean_score:.3f} across {len(baseline_scores)} tasks."
        )

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
        tool_modules = [
            c.replace("tools_", "") for c in component_names if c.startswith("tools_")
        ]
        components_desc = (
            f"\nAlso optimizing MCP tool descriptions for: {', '.join(tool_modules)}. "
            "Keep docstrings accurate and concise — every token counts toward the budget."
        )

    token_desc = (
        f"\nTOKEN EFFICIENCY (25% of score): Current artifacts total {original_token_count:,} tokens. "
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
        "The skill is scored by MLflow judges that evaluate how much it HELPS an agent.\n"
        "Judge rationale in side_info explains exactly WHAT failed and WHY.\n"
        "Use Judge_quality_with to see missing facts/patterns.\n"
        "Use Judge_effectiveness to see if the skill helped or hurt.\n"
        "Focus on: specific API syntax, version requirements, non-obvious patterns.\n"
        "Do NOT add generic knowledge the agent already has."
        f"{baseline_desc}"
        f"{components_desc}"
        f"{token_desc}"
        f"{assessment_desc}"
        f"{focus_desc}"
    )
