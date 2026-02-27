"""SkillBench-inspired evaluator: measure skill effectiveness via WITH vs WITHOUT comparison.

Evaluates skills by measuring agent performance WITH the skill vs WITHOUT it
on real tasks, then computing a skill effectiveness delta. This replaces the
5-layer weighted scoring with a 3-phase approach:

  Phase 1: WITH-SKILL  -- LLM generates response with SKILL.md in context
  Phase 2: WITHOUT-SKILL -- LLM generates response with NO skill (cached once)
  Phase 3: COMPUTE -- binary pass/fail assertions on both, derive effectiveness

Scoring weights (default / with --use-judges):
  45% / 35% Skill Effectiveness (delta: pass_rate_with - pass_rate_without)
  25% / 25% Absolute Quality (pass_rate_with_skill)
   0% / 10% Judge Quality (LLM judge pass rate — 6 judges, see below)
   5% /  5% Structure (syntax validity)
  25% / 25% Token Efficiency (smaller candidates score higher)

LLM Judges (when --use-judges is enabled):
  1. RelevanceToQuery  — does the response address the user's input? (always runs)
  2. Completeness      — does the response fully answer all parts? (always runs)
  3. Correctness       — are expected facts present? (requires expected_facts)
  4. Guidelines        — does response follow per-test rules? (requires guidelines)
  5. ExpectationsGuidelines — combined facts+guidelines check (when both present)
  6. Custom skill judge — MemAlign-inspired domain judge with skill-specific
                          evaluation criteria extracted from ground_truth guidelines
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable

import litellm
from mlflow.entities import Feedback

from ..scorers.universal import python_syntax, sql_syntax, no_hallucinated_apis
from .assertions import AssertionResult, run_all_assertions
from .asi import skillbench_to_asi

logger = logging.getLogger(__name__)


def _prompt_hash(prompt: str) -> str:
    """Stable hash for caching baseline results by prompt."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


class _RateLimiter:
    """Thread-safe token-bucket rate limiter for LLM API calls.

    Limits both concurrency (via semaphore) and request rate (via
    minimum inter-call spacing).  When --include-tools sends large
    contexts to Opus, this prevents bursts that exceed
    token-per-minute quotas.
    """

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
_rate_limiter = _RateLimiter(max_concurrent=2, min_interval=1.0)


def _completion_with_backoff(*, max_retries: int = 6, **kwargs) -> Any:
    """Call litellm.completion with explicit exponential backoff for rate limits.

    This is a safety net on top of litellm's built-in retries.  litellm's
    global num_retries handles most transient errors, but sustained
    token-per-minute exhaustion on Opus can outlast them.  This wrapper
    adds longer waits between retry bursts.
    """
    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt > 0:
            delay = min(2 ** attempt, 60)  # 2, 4, 8, 16, 32, 60
            logger.warning(
                "Rate limited (attempt %d/%d), backing off %.0fs",
                attempt, max_retries, delay,
            )
            time.sleep(delay)
        _rate_limiter.acquire()
        try:
            result = litellm.completion(**kwargs)
            return result
        except litellm.RateLimitError as e:
            last_err = e
        finally:
            _rate_limiter.release()
    raise last_err  # type: ignore[misc]


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
                    # skip doesn't count
            elif isinstance(result, Feedback):
                if result.value == "yes":
                    scores.append(1.0)
                elif result.value == "no":
                    scores.append(0.0)
        except Exception:
            pass
    return sum(scores) / len(scores) if scores else 1.0


class SkillBenchEvaluator:
    """GEPA-compatible evaluator using SkillBench WITH vs WITHOUT methodology.

    Args:
        gen_model: LLM model for generating responses. Required -- no silent fallback.
        scorer_config: Optional scorer config (unused, kept for interface compat).
        original_token_counts: Token counts of original artifacts for efficiency scoring.
        token_budget: Hard token ceiling; candidates exceeding this are penalized.
    """

    def __init__(
        self,
        gen_model: str,
        scorer_config: dict[str, Any] | None = None,
        original_token_counts: dict[str, int] | None = None,
        token_budget: int | None = None,
        use_judges: bool = False,
        skill_guidelines: list[str] | None = None,
    ):
        if not gen_model:
            raise ValueError(
                "SkillBench evaluator requires a gen_model. "
                "Pass --gen-model or set GEPA_GEN_LM env var."
            )
        self.gen_model = gen_model
        self._baseline_cache: dict[str, list[AssertionResult]] = {}
        self._baseline_response_cache: dict[str, str] = {}
        self._original_token_counts = original_token_counts or {}
        self._total_original_tokens = sum(self._original_token_counts.values())
        self._token_budget = token_budget
        self._use_judges = use_judges
        self._skill_guidelines = skill_guidelines or []

    def _generate_response(self, prompt: str, skill_context: str | None = None) -> str:
        """Generate a response with or without skill context.

        Uses temperature=0 for deterministic outputs.
        """
        messages = []
        if skill_context:
            messages.append({
                "role": "system",
                "content": (
                    "Use ONLY the following skill documentation to answer "
                    "the user's question. Do not use any other knowledge.\n\n"
                    f"{skill_context}"
                ),
            })
        messages.append({"role": "user", "content": prompt})

        resp = _completion_with_backoff(
            model=self.gen_model,
            messages=messages,
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    def _get_baseline(
        self, prompt: str, expectations: dict[str, Any],
    ) -> tuple[list[AssertionResult], str]:
        """Get WITHOUT-skill baseline, computing once then caching.

        Returns:
            Tuple of (assertion_results, raw_response).
        """
        key = _prompt_hash(prompt)
        if key not in self._baseline_cache:
            response = self._generate_response(prompt, skill_context=None)
            self._baseline_response_cache[key] = response
            self._baseline_cache[key] = run_all_assertions(response, expectations)
        return self._baseline_cache[key], self._baseline_response_cache[key]

    def _run_llm_judges(
        self, response: str, expectations: dict, prompt: str, reference: str,
    ) -> list[dict]:
        """Run MLflow LLM judges and return NL feedback dicts.

        Runs up to 6 judges for comprehensive evaluation:
          1. RelevanceToQuery  — always (no ground truth needed)
          2. Completeness      — always (no ground truth needed)
          3. Correctness       — when expected_facts present
          4. Guidelines        — when per-test guidelines present
          5. ExpectationsGuidelines — when BOTH facts + guidelines present
          6. Custom skill judge — MemAlign-inspired domain-specific judge

        Each judge returns {judge, passed, rationale} for GEPA reflection.
        """
        results = []

        inputs_dict = {"prompt": prompt}
        outputs_dict = {"response": response}

        facts = expectations.get("expected_facts", [])
        guidelines = expectations.get("guidelines", [])

        # 1. RelevanceToQuery: does response address the user's input?
        # Always runs — catches off-topic or confused responses that binary
        # assertions can't detect.
        try:
            from mlflow.genai.scorers import RelevanceToQuery
            judge = RelevanceToQuery()
            fb = judge(inputs=inputs_dict, outputs=outputs_dict)
            results.append({
                "judge": "relevance",
                "passed": fb.value == "yes",
                "rationale": fb.rationale or "",
            })
        except Exception as e:
            logger.debug("RelevanceToQuery judge failed: %s", e)

        # 2. Completeness: does response fully answer all parts of the prompt?
        # Always runs — catches partial answers where a response mentions the
        # right topic but skips sub-questions.
        try:
            from mlflow.genai.scorers import Completeness
            judge = Completeness()
            fb = judge(inputs=inputs_dict, outputs=outputs_dict)
            results.append({
                "judge": "completeness",
                "passed": fb.value == "yes",
                "rationale": fb.rationale or "",
            })
        except Exception as e:
            logger.debug("Completeness judge failed: %s", e)

        # 3. Correctness: are expected facts present in the response?
        if facts and reference:
            try:
                from mlflow.genai.scorers import Correctness
                judge = Correctness()
                fb = judge(
                    inputs=inputs_dict,
                    outputs=outputs_dict,
                    expectations={"expected_facts": facts},
                )
                results.append({
                    "judge": "correctness",
                    "passed": fb.value == "yes",
                    "rationale": fb.rationale or "",
                })
            except Exception as e:
                logger.debug("Correctness judge failed: %s", e)

        # 4. Guidelines: per-test custom evaluation rules
        if guidelines:
            try:
                from mlflow.genai.scorers import Guidelines
                judge = Guidelines(
                    name="skill_guidelines", guidelines=guidelines,
                )
                fb = judge(inputs=inputs_dict, outputs=outputs_dict)
                results.append({
                    "judge": "guidelines",
                    "passed": fb.value == "yes",
                    "rationale": fb.rationale or "",
                })
            except Exception as e:
                logger.debug("Guidelines judge failed: %s", e)

        # 5. ExpectationsGuidelines: combined facts + guidelines in one pass.
        # When both are available, this judge evaluates them together and
        # produces a single holistic rationale — often more insightful than
        # separate Correctness + Guidelines calls.
        if facts and guidelines:
            try:
                from mlflow.genai.scorers import ExpectationsGuidelines
                judge = ExpectationsGuidelines(
                    name="expectations_guidelines",
                    guidelines=guidelines,
                )
                fb = judge(
                    inputs=inputs_dict,
                    outputs=outputs_dict,
                    expectations={"expected_facts": facts},
                )
                results.append({
                    "judge": "expectations_guidelines",
                    "passed": fb.value == "yes",
                    "rationale": fb.rationale or "",
                })
            except Exception as e:
                logger.debug("ExpectationsGuidelines judge failed: %s", e)

        # 6. Custom skill judge (MemAlign-inspired): uses domain-specific
        # evaluation principles extracted from the skill's ground_truth
        # guidelines. This mimics MemAlign's "semantic memory" — a set of
        # generalizable principles learned from labeled examples — without
        # requiring MLflow trace alignment infrastructure.
        if self._skill_guidelines:
            try:
                self._run_custom_skill_judge(
                    results, prompt, response, facts,
                )
            except Exception as e:
                logger.debug("Custom skill judge failed: %s", e)

        return results

    def _run_custom_skill_judge(
        self,
        results: list[dict],
        prompt: str,
        response: str,
        facts: list[str],
    ) -> None:
        """Run a MemAlign-inspired custom judge with skill-domain principles.

        Uses ``mlflow.genai.judges.make_judge`` to create a domain-specific
        judge whose instructions incorporate evaluation principles extracted
        from all ground_truth.yaml guidelines across the skill's test cases.

        This is the "semantic memory" component of the MemAlign approach:
        rather than aligning from traces, we extract and deduplicate the
        skill's evaluation principles upfront and inject them as judge
        instructions.

        Appends result dicts directly to ``results``.
        """
        from mlflow.genai.judges import make_judge

        # Build instruction prompt from collected skill guidelines
        principles = "\n".join(
            f"- {g}" for g in self._skill_guidelines
        )

        judge = make_judge(
            name="skill_domain_judge",
            instructions=(
                "You are an expert evaluator for a Databricks skill. "
                "Evaluate whether the response correctly follows the "
                "domain-specific principles below.\n\n"
                "## Domain Principles (from skill evaluation criteria)\n"
                f"{principles}\n\n"
                "## Evaluation\n"
                "Given the user question and response, determine if the "
                "response adheres to the domain principles above. Focus on "
                "technical accuracy, correct API usage, and completeness "
                "of the domain-specific guidance.\n\n"
                "Question: {{ inputs.prompt }}\n"
                "Response: {{ outputs.response }}"
            ),
            feedback_value_type=bool,
        )

        fb = judge(
            inputs={"prompt": prompt},
            outputs={"response": response},
        )
        results.append({
            "judge": "skill_domain",
            "passed": fb.value == "yes" if isinstance(fb.value, str) else bool(fb.value),
            "rationale": fb.rationale or "",
        })

    def __call__(
        self, candidate: dict[str, str], example: dict,
    ) -> tuple[float, dict]:
        """Evaluate a candidate skill against a single task example.

        GEPA-compatible signature: (candidate, example) -> (score, side_info)
        """
        skill_md = candidate.get("skill_md", "")

        # Build combined context: skill + tool descriptions
        tool_parts = []
        for key in sorted(candidate):
            if key.startswith("tools_"):
                tool_parts.append(candidate[key])

        full_context = skill_md
        if tool_parts:
            full_context += "\n\n## Available MCP Tools\n\n" + "\n\n".join(tool_parts)

        prompt = example.get("input", "")

        # Decode expectations
        expectations: dict[str, Any] = {}
        expectations_json = example.get("additional_context", {}).get("expectations", "")
        if expectations_json:
            try:
                expectations = json.loads(expectations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        # If no prompt or no expectations, return minimal score
        if not prompt or not expectations:
            return 0.0, {"_error": "No prompt or expectations for this task"}

        # Phase 1: WITH skill + tools
        with_response = self._generate_response(prompt, skill_context=full_context)
        with_results = run_all_assertions(with_response, expectations)

        # Phase 2: WITHOUT skill (cached)
        without_results, without_response = self._get_baseline(prompt, expectations)

        # Phase 3: Compute scores
        total = len(with_results)
        if total == 0:
            return 0.0, {"_error": "No assertions to evaluate"}

        pass_with = sum(r.passed for r in with_results) / total
        pass_without = sum(r.passed for r in without_results) / total
        effectiveness = pass_with - pass_without

        # LLM judge scoring (optional)
        judge_results = []
        if self._use_judges:
            judge_results = self._run_llm_judges(
                with_response, expectations, prompt,
                reference=example.get("answer", ""),
            )

        judge_pass_rate = 1.0  # default when judges disabled
        if judge_results:
            judge_pass_rate = sum(j["passed"] for j in judge_results) / len(judge_results)

        # Structure validation on the skill itself
        structure = _run_structure_scorers(skill_md) if skill_md else 1.0

        # Token efficiency scoring
        from .evaluator import count_tokens
        total_candidate_tokens = sum(count_tokens(v) for v in candidate.values())

        if self._total_original_tokens > 0:
            ratio = total_candidate_tokens / self._total_original_tokens
            if ratio <= 1.0:
                efficiency = 1.0 + 0.15 * (1.0 - ratio)  # Bonus for smaller
            else:
                efficiency = max(0.0, 2.0 - ratio)  # Penalty for growth

            # Hard penalty if over explicit budget
            if self._token_budget and total_candidate_tokens > self._token_budget:
                over_ratio = total_candidate_tokens / self._token_budget
                efficiency = min(efficiency, max(0.0, 2.0 - over_ratio))
        else:
            efficiency = 1.0

        # Weighted final score
        # When judges enabled: steal 10% from effectiveness for judge_quality
        # When judges disabled: 10% folds back into effectiveness (original weights)
        if self._use_judges and judge_results:
            final_score = (
                0.35 * max(0.0, effectiveness)
                + 0.25 * pass_with
                + 0.10 * judge_pass_rate
                + 0.05 * structure
                + 0.25 * efficiency
            )
        else:
            final_score = (
                0.45 * max(0.0, effectiveness)
                + 0.25 * pass_with
                + 0.05 * structure
                + 0.25 * efficiency
            )

        # Build side info via skillbench_to_asi
        score_breakdown = {
            "skill_effectiveness": effectiveness,
            "pass_rate_with": pass_with,
            "pass_rate_without": pass_without,
            "structure": structure,
            "token_efficiency": efficiency,
            "final": final_score,
        }
        if self._use_judges and judge_results:
            score_breakdown["judge_quality"] = judge_pass_rate

        reference_answer = example.get("answer", "")

        side_info = skillbench_to_asi(
            with_results,
            without_results,
            task_prompt=prompt,
            scores=score_breakdown,
            with_response=with_response,
            without_response=without_response,
            reference_answer=reference_answer or None,
            candidate=candidate,
        )

        # Feed judge rationale into side_info for GEPA reflection
        if judge_results:
            failing_judges = [j for j in judge_results if not j["passed"]]
            if failing_judges:
                rationale_lines = [
                    f"{j['judge']}: {j['rationale'][:200]}" for j in failing_judges
                ]
                side_info["Judge_feedback"] = "\n".join(rationale_lines)

                # Also route to skill_md_specific_info for component targeting
                if "skill_md_specific_info" not in side_info:
                    side_info["skill_md_specific_info"] = {}
                side_info["skill_md_specific_info"]["Judge_analysis"] = "\n".join(rationale_lines)

        # Add token counts to side_info for GEPA Pareto tracking
        side_info["token_counts"] = {
            "candidate_total": total_candidate_tokens,
            "original_total": self._total_original_tokens,
        }
        if self._token_budget:
            side_info["token_counts"]["budget"] = self._token_budget

        return final_score, side_info


def _collect_skill_guidelines(skill_name: str) -> list[str]:
    """Collect and deduplicate all guidelines from a skill's ground_truth.yaml.

    These form the "semantic memory" for the MemAlign-inspired custom judge.
    Returns a deduplicated list of guideline strings.
    """
    from pathlib import Path
    import yaml

    gt_path = Path(".test/skills") / skill_name / "ground_truth.yaml"
    if not gt_path.exists():
        return []

    try:
        with open(gt_path) as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return []

    seen: set[str] = set()
    guidelines: list[str] = []
    for tc in data.get("test_cases", []):
        for g in tc.get("expectations", {}).get("guidelines", []):
            g_norm = g.strip()
            if g_norm and g_norm not in seen:
                seen.add(g_norm)
                guidelines.append(g_norm)

    return guidelines


def create_skillbench_evaluator(
    skill_name: str,
    gen_model: str,
    original_token_counts: dict[str, int] | None = None,
    token_budget: int | None = None,
    use_judges: bool = False,
) -> Callable:
    """Factory for SkillBench-style evaluator.

    Returns a GEPA-compatible callable: (candidate, example) -> (score, side_info)

    When ``use_judges`` is enabled, collects all guidelines from the skill's
    ground_truth.yaml to build a MemAlign-inspired custom domain judge
    alongside the standard MLflow predefined judges.

    Args:
        skill_name: Name of the skill being evaluated.
        gen_model: LLM model for generating responses. Required.
        original_token_counts: Token counts of original artifacts for efficiency scoring.
        token_budget: Hard token ceiling; candidates exceeding this are penalized.
        use_judges: Enable MLflow LLM judges for NL feedback.
    """
    skill_guidelines: list[str] = []
    if use_judges:
        skill_guidelines = _collect_skill_guidelines(skill_name)
        if skill_guidelines:
            logger.info(
                "Loaded %d domain guidelines for custom skill judge",
                len(skill_guidelines),
            )

    return SkillBenchEvaluator(
        gen_model=gen_model,
        original_token_counts=original_token_counts,
        token_budget=token_budget,
        use_judges=use_judges,
        skill_guidelines=skill_guidelines,
    )


def build_skillbench_background(
    skill_name: str,
    original_token_count: int,
    component_names: list[str] | None = None,
    baseline_scores: dict[str, float] | None = None,
    baseline_side_info: dict[str, dict] | None = None,
    token_budget: int | None = None,
    use_judges: bool = False,
) -> str:
    """Build concise GEPA reflection context for SkillBench optimization.

    Kept short so GEPA's reflection LM spends its context on the per-example
    diagnostics (Error/Expected/Actual) rather than methodology.
    """
    # Concise per-task baseline summary
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
                baseline_desc += (
                    f"\n  NEEDS_SKILL ({len(needs_skill_ids)} tasks): "
                    f"{', '.join(needs_skill_ids[:5])}"
                )
            if regression_ids:
                baseline_desc += (
                    f"\n  REGRESSION ({len(regression_ids)} tasks): "
                    f"{', '.join(regression_ids[:5])}"
                )

    components_desc = ""
    if component_names and any(c.startswith("tools_") for c in component_names):
        tool_modules = [c.replace("tools_", "") for c in component_names if c.startswith("tools_")]
        components_desc = (
            f"\nAlso optimizing MCP tool descriptions for: {', '.join(tool_modules)}. "
            "Tool descriptions are included in the agent's context alongside the skill. "
            "The agent uses them to decide which tools to call and how. "
            "Keep docstrings accurate and concise — every token counts toward the budget."
        )

    # Token efficiency guidance
    token_desc = (
        f"\nTOKEN EFFICIENCY (25% of score): Current artifacts total {original_token_count:,} tokens. "
        "Smaller candidates score HIGHER. Remove redundant examples, consolidate "
        "overlapping sections, eliminate verbose explanations. Be ruthlessly concise."
    )
    if token_budget:
        token_desc += (
            f"\nTOKEN BUDGET: {token_budget:,} tokens. Candidates exceeding this "
            "are heavily penalized. Stay well under the budget."
        )

    judge_desc = ""
    if use_judges:
        judge_desc = (
            "\nLLM JUDGES (10% of score): Six judges provide natural-language feedback "
            "in 'Judge_feedback': RelevanceToQuery (on-topic?), Completeness (fully "
            "answered?), Correctness (facts present?), Guidelines (rules followed?), "
            "ExpectationsGuidelines (combined holistic check), and a custom skill "
            "domain judge (MemAlign-inspired, evaluates domain-specific principles). "
            "Use judge rationale to understand WHY responses fail — it's more "
            "actionable than binary NEEDS_SKILL/REGRESSION labels."
        )

    return (
        f"You are refining SKILL.md for '{skill_name}'.\n"
        "The skill is scored by how much it HELPS an agent answer correctly.\n"
        "Assertions labeled NEEDS_SKILL = add this content. REGRESSION = simplify or remove.\n"
        "Focus on: specific API syntax, version requirements, non-obvious patterns.\n"
        "Do NOT add generic knowledge the agent already has (NEUTRAL assertions)."
        f"{baseline_desc}"
        f"{components_desc}"
        f"{token_desc}"
        f"{judge_desc}"
    )
