"""Agent-based evaluator: run real Claude Code agent and score behavior.

GEPA-compatible evaluator that runs a Claude Code instance via the Agent SDK,
captures the full execution trace, and scores using both custom judges and
deterministic trace scorers.

Scoring weights:
  20% Content quality (custom quality_judge on response text)
  20% Skill effectiveness (WITH vs WITHOUT delta)
  20% Tool call correctness (MLflow ToolCallCorrectness or trace required_tools)
  10% Tool call efficiency (MLflow ToolCallEfficiency or trace tool_count)
  15% Behavioral (deterministic trace scorers: required_tools, banned_tools, tool_sequence)
  10% Execution success (did tool calls succeed?)
   5% Token efficiency (smaller candidates score higher)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Callable

from mlflow.entities import Feedback

from ..agent.executor import AgentResult, run_agent_sync_wrapper
from ..scorers.trace import (
    required_tools as required_tools_scorer,
    banned_tools as banned_tools_scorer,
    tool_count as tool_count_scorer,
    tool_sequence as tool_sequence_scorer,
)
from .judges import (
    JudgeFeedback,
    create_skill_quality_judge,
    run_judge_safe,
    _safe_parse_score,
)
from .utils import count_tokens

logger = logging.getLogger(__name__)


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


def _run_mlflow_tool_judges(
    trace_dict: dict[str, Any],
    prompt: str,
    response: str,
    trace_expectations: dict[str, Any],
    mlflow_trace: Any | None = None,
) -> dict[str, float]:
    """Run MLflow predefined tool-call judges if available.

    Tries to import ToolCallCorrectness and ToolCallEfficiency from
    mlflow.genai.scorers. Falls back to deterministic trace scorers
    if the experimental judges are not available.

    Returns dict with 'tool_correctness' and 'tool_efficiency' scores (0-1).
    """
    scores: dict[str, float] = {}

    # Use real MLflow trace if available, fall back to dict
    trace_for_judges = mlflow_trace if mlflow_trace is not None else trace_dict

    # Try MLflow experimental judges
    try:
        from mlflow.genai.scorers import ToolCallCorrectness, ToolCallEfficiency

        # ToolCallCorrectness: are tool calls correct for the query?
        try:
            tc_scorer = ToolCallCorrectness()
            tc_result = tc_scorer(
                inputs={"query": prompt},
                outputs={"response": response},
                trace=trace_for_judges,
            )
            if isinstance(tc_result, Feedback):
                scores["tool_correctness"] = 1.0 if tc_result.value == "yes" else 0.0
            elif isinstance(tc_result, list):
                yes_count = sum(1 for fb in tc_result if getattr(fb, "value", None) == "yes")
                scores["tool_correctness"] = yes_count / len(tc_result) if tc_result else 0.5
        except Exception as e:
            logger.debug("ToolCallCorrectness not available: %s", e)

        # ToolCallEfficiency: are tool calls efficient?
        try:
            te_scorer = ToolCallEfficiency()
            te_result = te_scorer(
                inputs={"query": prompt},
                outputs={"response": response},
                trace=trace_for_judges,
            )
            if isinstance(te_result, Feedback):
                scores["tool_efficiency"] = 1.0 if te_result.value == "yes" else 0.0
            elif isinstance(te_result, list):
                yes_count = sum(1 for fb in te_result if getattr(fb, "value", None) == "yes")
                scores["tool_efficiency"] = yes_count / len(te_result) if te_result else 0.5
        except Exception as e:
            logger.debug("ToolCallEfficiency not available: %s", e)

    except ImportError:
        logger.debug("mlflow.genai.scorers experimental judges not available")

    # Fallback to deterministic trace scorers if MLflow judges not available
    if "tool_correctness" not in scores:
        fb = required_tools_scorer(trace=trace_dict, expectations=trace_expectations)
        if fb.value == "yes":
            scores["tool_correctness"] = 1.0
        elif fb.value == "no":
            scores["tool_correctness"] = 0.0
        else:
            scores["tool_correctness"] = 0.5  # skip = neutral

    if "tool_efficiency" not in scores:
        fb = tool_count_scorer(trace=trace_dict, expectations=trace_expectations)
        if fb.value == "yes":
            scores["tool_efficiency"] = 1.0
        elif fb.value == "no":
            scores["tool_efficiency"] = 0.0
        else:
            scores["tool_efficiency"] = 0.5  # skip = neutral

    return scores


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
    """GEPA-compatible evaluator using real Claude Code agent execution.

    Runs the agent with and without the skill, then scores using a combination
    of judge-based evaluation, trace analysis, and deterministic scorers.

    Args:
        original_token_counts: Token counts of original artifacts for efficiency scoring.
        token_budget: Hard token ceiling.
        skill_guidelines: Guidelines from ground_truth.yaml for the quality judge.
        judge_model: LLM model for judges.
        mcp_config: MCP server configuration for the agent.
        allowed_tools: Allowed tools for the agent.
        agent_model: Model to use for the agent execution.
        agent_timeout: Timeout for each agent run in seconds.
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
    ):
        self._original_token_counts = original_token_counts or {}
        self._total_original_tokens = sum(self._original_token_counts.values())
        self._token_budget = token_budget
        self._mcp_config = mcp_config
        self._allowed_tools = allowed_tools
        self._agent_model = agent_model
        self._agent_timeout = agent_timeout
        self._mlflow_experiment = mlflow_experiment

        # Caches for WITHOUT-skill runs (keyed by prompt hash)
        self._baseline_response_cache: dict[str, str] = {}
        self._baseline_trace_cache: dict[str, dict] = {}
        self._baseline_mlflow_trace_cache: dict[str, Any] = {}
        self._baseline_judge_cache: dict[str, JudgeFeedback] = {}

        # Create judge
        self._quality_judge = create_skill_quality_judge(
            skill_guidelines, judge_model=judge_model
        )

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
        )

    def _get_baseline(self, prompt: str) -> tuple[str, dict, Any]:
        """Get WITHOUT-skill baseline response, trace, and MLflow trace, cached by prompt hash."""
        key = _prompt_hash(prompt)
        if key not in self._baseline_response_cache:
            result = self._run_agent(prompt, skill_md=None)
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
        """
        skill_md = candidate.get("skill_md", "")
        prompt = example.get("input", "")

        # Decode expectations
        expectations: dict[str, Any] = {}
        expectations_json = example.get("additional_context", {}).get("expectations", "")
        if expectations_json:
            try:
                expectations = json.loads(expectations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract trace expectations (new field for agent evaluation)
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
        without_response, without_trace, _without_mlflow_trace = self._get_baseline(prompt)

        with_response = with_result.response_text
        with_trace = with_result.trace_metrics.to_dict()

        # Phase 3: Judge-driven quality scoring
        facts = expectations.get("expected_facts", [])
        patterns = expectations.get("expected_patterns", [])
        guidelines = expectations.get("guidelines", [])

        facts_str = "\n".join(f"- {f}" for f in facts) if facts else "None specified"
        patterns_str = (
            "\n".join(
                f"- {p}" if isinstance(p, str)
                else f"- {p.get('description', p.get('pattern', ''))}"
                for p in patterns
            )
            if patterns
            else "None specified"
        )
        guidelines_str = "\n".join(f"- {g}" for g in guidelines) if guidelines else "None specified"
        expectations_text = (
            f"Expected facts:\n{facts_str}\n\n"
            f"Expected patterns:\n{patterns_str}\n\n"
            f"Guidelines:\n{guidelines_str}"
        )
        expectations_dict = {"criteria": expectations_text}

        # Quality judge: score WITH response
        quality_with_fb = run_judge_safe(
            self._quality_judge,
            inputs=prompt,
            outputs=with_response,
            expectations=expectations_dict,
            name="quality_with",
        )

        # Quality judge: score WITHOUT response (cached)
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

        score_with = _safe_parse_score(quality_with_fb.value)
        score_without = _safe_parse_score(quality_without_fb.value)
        effectiveness_delta = score_with - score_without

        # Phase 4: Tool-call judges (MLflow or fallback)
        tool_scores = _run_mlflow_tool_judges(
            with_trace, prompt, with_response, trace_expectations,
            mlflow_trace=with_result.mlflow_trace,
        )
        tool_correctness = tool_scores.get("tool_correctness", 0.5)
        tool_efficiency = tool_scores.get("tool_efficiency", 0.5)

        # Phase 5: Behavioral trace scorers
        behavioral_score, behavioral_details = _run_behavioral_scorers(
            with_trace, trace_expectations
        )

        # Phase 6: Execution success
        execution_success = _compute_execution_success(with_result)

        # Phase 7: Token efficiency
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

        # Composite score with proposed weights
        final_score = (
            0.20 * score_with                        # Content quality
            + 0.20 * max(0.0, effectiveness_delta)   # Skill effectiveness
            + 0.20 * tool_correctness                # Tool call correctness
            + 0.10 * tool_efficiency                 # Tool call efficiency
            + 0.15 * behavioral_score                # Behavioral trace scorers
            + 0.10 * execution_success               # Execution success
            + 0.05 * token_efficiency                # Token efficiency
        )

        # Build rich side_info
        side_info: dict[str, Any] = {}

        if prompt:
            side_info["Task"] = prompt[:200]

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
                "improved" if effectiveness_delta > 0.05
                else "regressed" if effectiveness_delta < -0.05
                else "same"
            ),
            "delta": effectiveness_delta,
        }

        # Agent-specific details
        side_info["agent_trace"] = {
            "total_tool_calls": with_trace.get("tools", {}).get("total_calls", 0),
            "tool_counts": with_trace.get("tools", {}).get("by_name", {}),
            "duration_ms": with_result.duration_ms,
            "success": with_result.success,
            "tokens": with_trace.get("tokens", {}),
        }
        side_info["tool_scores"] = {
            "correctness": tool_correctness,
            "efficiency": tool_efficiency,
        }
        side_info["behavioral_scores"] = behavioral_details
        side_info["execution_success"] = execution_success

        # Expected vs Actual
        reference_answer = example.get("answer", "")
        if reference_answer:
            side_info["Expected"] = reference_answer[:500]
        if with_response:
            side_info["Actual"] = with_response[:500]

        # Score breakdown
        side_info["scores"] = {
            "quality_with": score_with,
            "quality_without": score_without,
            "skill_effectiveness": effectiveness_delta,
            "tool_correctness": tool_correctness,
            "tool_efficiency": tool_efficiency,
            "behavioral": behavioral_score,
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
        if effectiveness_delta < -0.05:
            side_info["Error"] = (
                f"REGRESSION: skill_effectiveness delta={effectiveness_delta:.2f} "
                f"(with={score_with:.2f}, without={score_without:.2f})"
            )
        elif score_with < 0.5:
            side_info["Error"] = (
                f"NEEDS_SKILL: quality_with={score_with:.2f}. "
                f"Judge: {quality_with_fb.rationale[:200]}"
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
) -> Callable:
    """Factory for agent-based evaluator.

    Returns a GEPA-compatible callable: (candidate, example) -> (score, side_info)
    """
    from .skillbench_evaluator import _collect_skill_guidelines

    skill_guidelines = _collect_skill_guidelines(skill_name)
    if skill_guidelines:
        logger.info("Loaded %d domain guidelines for agent quality judge", len(skill_guidelines))

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
    )


def build_agent_eval_background(
    skill_name: str,
    original_token_count: int,
    baseline_scores: dict[str, float] | None = None,
    baseline_side_info: dict[str, dict] | None = None,
) -> str:
    """Build GEPA reflection context specific to agent evaluation.

    Similar to build_skillbench_background but highlights agent-specific signals.
    """
    baseline_desc = ""
    if baseline_scores:
        mean_score = sum(baseline_scores.values()) / len(baseline_scores)
        baseline_desc = f"\nBASELINE: mean {mean_score:.3f} across {len(baseline_scores)} tasks."

        if baseline_side_info:
            tool_issues = []
            for tid, info in baseline_side_info.items():
                behavioral = info.get("behavioral_scores", {})
                for scorer_name, result in behavioral.items():
                    if result.get("value") == "no":
                        tool_issues.append(f"{tid}: {scorer_name} failed - {result.get('rationale', '')[:80]}")
            if tool_issues:
                baseline_desc += f"\n  TOOL ISSUES ({len(tool_issues)}):"
                for issue in tool_issues[:5]:
                    baseline_desc += f"\n    - {issue}"

    return (
        f"You are refining SKILL.md for '{skill_name}'.\n"
        "The skill is scored by a real Claude Code agent that executes tasks.\n"
        "Agent traces show exactly which tools were called and whether they succeeded.\n"
        "Scoring includes: content quality (20%), effectiveness (20%), tool correctness (20%), "
        "tool efficiency (10%), behavioral compliance (15%), execution success (10%), token size (5%).\n"
        "Focus on: guiding the agent to use the RIGHT tools with CORRECT arguments.\n"
        "Avoid: unnecessary tool calls, wrong tool selection, verbose instructions."
        f"{baseline_desc}"
    )
