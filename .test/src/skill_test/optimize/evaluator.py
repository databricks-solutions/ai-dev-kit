"""Evaluator bridge: wrap existing MLflow scorers into optimize_anything evaluators.

Creates GEPA-compatible evaluator functions that take a candidate (str or dict)
and a task example, run existing scorers, and return (score, SideInfo).
"""

import inspect
import re
from pathlib import Path
from typing import Any, Callable, Literal

import tiktoken
import gepa.optimize_anything as oa
from mlflow.entities import Feedback

from ..runners.evaluate import build_scorers, load_scorer_config
from ..scorers.universal import (
    python_syntax,
    sql_syntax,
    no_hallucinated_apis,
    pattern_adherence,
    expected_facts_present,
)
from .asi import feedback_to_asi
from .skillbench_evaluator import (  # noqa: F401 — re-exported for runner.py
    create_skillbench_evaluator,
    build_skillbench_background,
)


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

def _find_repo_root() -> Path:
    """Find the repo root by searching upward for .test/src/."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".test" / "src").exists():
            return current
        if (current / "src" / "skill_test").exists() and current.name == ".test":
            return current.parent
        current = current.parent
    return Path.cwd()


def _find_skill_md(skill_name: str) -> Path | None:
    """Locate the SKILL.md file for a given skill name."""
    repo_root = _find_repo_root()
    candidates = [
        repo_root / ".claude" / "skills" / skill_name / "SKILL.md",
        repo_root / "databricks-skills" / skill_name / "SKILL.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def token_efficiency_score(candidate_text: str, original_token_count: int) -> float:
    """Score based on how concise the candidate is vs. the original.

    Smaller than original = bonus up to 1.15, same size = 1.0,
    larger = linear penalty to 0.0 at 2x.
    """
    if original_token_count <= 0:
        return 1.0
    enc = tiktoken.get_encoding("cl100k_base")
    candidate_tokens = len(enc.encode(candidate_text))
    ratio = candidate_tokens / original_token_count
    if ratio <= 1.0:
        return 1.0 + 0.15 * (1.0 - ratio)
    else:
        return max(0.0, 2.0 - ratio)


# ---------------------------------------------------------------------------
# Scorer execution
# ---------------------------------------------------------------------------

def _run_scorer(scorer_fn: Any, outputs: dict, expectations: dict, inputs: dict) -> list[Feedback]:
    """Run a single scorer and normalize result to a list of Feedbacks."""
    sig = inspect.signature(scorer_fn)
    params = list(sig.parameters.keys())

    kwargs = {}
    if "outputs" in params:
        kwargs["outputs"] = outputs
    if "expectations" in params:
        kwargs["expectations"] = expectations
    if "inputs" in params:
        kwargs["inputs"] = inputs

    try:
        result = scorer_fn(**kwargs)
    except Exception as e:
        return [Feedback(name=getattr(scorer_fn, "__name__", "unknown"), value="no", rationale=str(e))]

    if isinstance(result, list):
        return result
    elif isinstance(result, Feedback):
        return [result]
    return []


def _run_deterministic_scorers(
    response: str,
    expectations: dict[str, Any],
    prompt: str,
    scorer_config: dict[str, Any],
) -> list[Feedback]:
    """Run deterministic scorers against a response."""
    outputs = {"response": response}
    inputs = {"prompt": prompt}

    if scorer_config:
        scorers = build_scorers(scorer_config)
    else:
        scorers = [python_syntax, sql_syntax, pattern_adherence, no_hallucinated_apis, expected_facts_present]

    all_feedbacks = []
    for scorer_fn in scorers:
        scorer_name = getattr(scorer_fn, "__name__", "") or getattr(scorer_fn, "name", "")
        if scorer_name in ("Safety", "Guidelines", "skill_quality"):
            continue
        all_feedbacks.extend(_run_scorer(scorer_fn, outputs, expectations, inputs))

    return all_feedbacks


def _validate_skill_structure(candidate_text: str) -> list[Feedback]:
    """Validate the SKILL.md structure itself."""
    outputs = {"response": candidate_text}
    feedbacks = []
    for scorer_fn in [python_syntax, sql_syntax, no_hallucinated_apis]:
        result = _run_scorer(scorer_fn, outputs, {}, {})
        for fb in result:
            feedbacks.append(Feedback(name=f"skill_{fb.name}", value=fb.value, rationale=fb.rationale))
    return feedbacks


_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "been", "being", "have", "has", "had", "does", "did", "but",
    "not", "you", "all", "can", "her", "his", "its", "may", "our",
    "out", "use", "uses", "will", "how", "who", "get", "which", "would",
    "make", "like", "into", "than", "them", "then", "each", "other",
    "should", "could",
})


def _keyword_fact_score(fact: str, text: str) -> float:
    """Score 0-1 based on keyword overlap between a fact and text."""
    words = [w for w in re.findall(r'\w{3,}', fact.lower()) if w not in _STOP_WORDS]
    if not words:
        return 1.0
    text_lower = text.lower()
    found = sum(1 for w in words if w in text_lower)
    return found / len(words)


def _score_skill_content_facts(candidate_text: str, expected_facts: list[str]) -> list[Feedback]:
    """Score SKILL.md content against expected facts using keyword matching.

    Unlike the universal ``expected_facts_present`` scorer which requires exact
    substring matches, this uses keyword extraction so descriptive facts like
    "Uses CREATE OR REPLACE VIEW with WITH METRICS LANGUAGE YAML" match when
    the individual keywords appear in the skill text.
    """
    feedbacks = []
    for fact in expected_facts:
        score = _keyword_fact_score(fact, candidate_text)
        feedbacks.append(Feedback(
            name=f"skill_content_fact_{fact[:40]}",
            value=score,  # continuous 0.0-1.0
            rationale=f"(skill content) Keyword match {score:.0%} for: {fact}",
        ))
    return feedbacks


def _score_skill_content(candidate_text: str, expectations: dict[str, Any]) -> list[Feedback]:
    """Score the SKILL.md candidate itself for pattern/fact coverage.

    Runs pattern_adherence and expected_facts_present against the skill text
    (not the response). This gives GEPA immediate dynamic signal: if a key
    pattern is removed from SKILL.md, the score drops.

    Feedback names are prefixed with ``skill_content_`` to distinguish from
    response-level scores.
    """
    outputs = {"response": candidate_text}
    feedbacks = []

    # Pattern adherence on skill content
    pa_results = _run_scorer(pattern_adherence, outputs, expectations, {})
    for fb in pa_results:
        feedbacks.append(Feedback(
            name=f"skill_content_{fb.name}",
            value=fb.value,
            rationale=f"(skill content) {fb.rationale or ''}",
        ))

    # Expected facts on skill content (keyword matching for descriptive facts)
    expected_facts = expectations.get("expected_facts", [])
    if expected_facts:
        feedbacks.extend(_score_skill_content_facts(candidate_text, expected_facts))

    return feedbacks


# ---------------------------------------------------------------------------
# Evaluator factory (optimize_anything compatible)
# ---------------------------------------------------------------------------

SKILL_KEY = "skill_md"


def create_skill_evaluator(
    skill_name: str,
    mode: Literal["static", "generative"] = "static",
    task_lm: str | None = None,
    gen_model: str | None = None,
    original_token_counts: dict[str, int] | None = None,
) -> Callable:
    """Create an optimize_anything-compatible evaluator for a skill.

    Returns a function: (candidate, example) -> (score, side_info)

    The candidate is dict[str, str] (may have "skill_md" + "tools_*" keys).
    The example is a task dict from the dataset.

    Evaluation layers:
        1. Skill-content scoring: pattern/fact presence in SKILL.md itself
        2. Generative evaluation: LLM generates response from skill, scored
        3. Reference response check: fixed ground truth scoring (sanity)
        4. Structure validation: syntax, no hallucinated APIs on SKILL.md
        5. Token efficiency: conciseness vs original

    Args:
        skill_name: Name of the skill being evaluated
        mode: "static" uses ground truth response, "generative" generates fresh
        task_lm: LLM for generative mode (deprecated, use gen_model)
        gen_model: LLM model for generative evaluation
        original_token_counts: Token counts of original artifacts
    """
    scorer_config = load_scorer_config(skill_name)
    effective_gen_model = gen_model or task_lm

    # Track whether we've warned about generation failure
    _gen_warned = [False]

    # Compute original token count for efficiency scoring
    if original_token_counts is None:
        skill_path = _find_skill_md(skill_name)
        original_token_counts = {
            SKILL_KEY: count_tokens(skill_path.read_text()) if skill_path else 0
        }
    total_original_tokens = sum(original_token_counts.values())

    # Mutable closure state: per-task baseline scorer scores for comparison.
    # Populated via evaluator.set_baseline() after evaluating the seed.
    _baseline: dict[str, dict[str, float | None]] = {}

    def evaluator(candidate: dict[str, str], example: dict) -> tuple[float, dict]:
        """Evaluate a candidate against a single task example.

        Args:
            candidate: dict[str, str] with "skill_md" and/or "tools_*" keys
            example: Task dict with "input", "answer", "additional_context"

        Returns:
            (score, side_info) tuple for optimize_anything
        """
        candidate_text = candidate.get(SKILL_KEY, "")

        # Decode expectations from additional_context
        expectations = {}
        expectations_json = example.get("additional_context", {}).get("expectations", "")
        if expectations_json:
            import json
            try:
                expectations = json.loads(expectations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        # ------------------------------------------------------------------
        # Layer 1: Skill-content scoring (pattern/fact presence in SKILL.md)
        # ------------------------------------------------------------------
        skill_content_feedbacks: list[Feedback] = []
        if candidate_text and expectations:
            skill_content_feedbacks = _score_skill_content(candidate_text, expectations)

        skill_content_composite, skill_content_si = feedback_to_asi(skill_content_feedbacks)

        # ------------------------------------------------------------------
        # Layer 2: Generative evaluation (LLM generates from skill, score that)
        # ------------------------------------------------------------------
        generated_response = None
        gen_feedbacks: list[Feedback] = []
        gen_composite = 0.0

        _gen_available = False  # Track if generation actually worked
        if effective_gen_model and candidate_text and example.get("input"):
            import litellm
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Use ONLY the following skill documentation to answer "
                        "the user's question. Do not use any other knowledge.\n\n"
                        f"{candidate_text}"
                    ),
                },
                {"role": "user", "content": example.get("input", "")},
            ]
            try:
                from .skillbench_evaluator import _completion_with_backoff
                resp = _completion_with_backoff(model=effective_gen_model, messages=messages)
                generated_response = resp.choices[0].message.content
                _gen_available = True
            except Exception as e:
                generated_response = None
                gen_feedbacks.append(Feedback(
                    name="generation_error",
                    value="no",
                    rationale=f"LLM generation failed: {e}",
                ))
                if not _gen_warned[0]:
                    _gen_warned[0] = True
                    import warnings
                    warnings.warn(
                        f"\nGeneration model '{effective_gen_model}' failed: {e}\n"
                        "Falling back to skill-content + reference scoring (no generative eval).\n"
                        "The 20% 'generated response quality' layer will be inactive.\n"
                        "Fix: set DATABRICKS_API_KEY + DATABRICKS_API_BASE, or use "
                        "--gen-model with a working provider (e.g., --gen-model openai/gpt-4o).\n",
                        stacklevel=2,
                    )

            if generated_response:
                gen_feedbacks = _run_deterministic_scorers(
                    generated_response, expectations, example.get("input", ""), scorer_config
                )

            gen_composite, gen_si = feedback_to_asi(gen_feedbacks)

        # ------------------------------------------------------------------
        # Layer 3: Reference response check (ground truth — sanity baseline)
        # ------------------------------------------------------------------
        reference_response = example.get("answer", "")
        ref_feedbacks: list[Feedback] = []
        ref_composite = 0.0

        if reference_response:
            ref_feedbacks = _run_deterministic_scorers(
                reference_response, expectations, example.get("input", ""), scorer_config
            )
            ref_composite, _ = feedback_to_asi(ref_feedbacks)

        # ------------------------------------------------------------------
        # Layer 4: Validate skill structure
        # ------------------------------------------------------------------
        structure_feedbacks: list[Feedback] = []
        if candidate_text:
            structure_feedbacks = _validate_skill_structure(candidate_text)

        structure_composite, _ = feedback_to_asi(structure_feedbacks)

        # ------------------------------------------------------------------
        # Layer 5: Token efficiency across ALL components
        # ------------------------------------------------------------------
        total_candidate_tokens = sum(count_tokens(v) for v in candidate.values())
        if total_original_tokens > 0:
            ratio = total_candidate_tokens / total_original_tokens
            if ratio <= 1.0:
                efficiency = 1.0 + 0.15 * (1.0 - ratio)
            else:
                efficiency = max(0.0, 2.0 - ratio)
        else:
            efficiency = 1.0

        # ------------------------------------------------------------------
        # Weighted final score
        # ------------------------------------------------------------------
        # When generative eval succeeds, it gets the dominant weight.
        # When gen fails (auth error, timeout, etc), fall back to
        # skill-content-heavy weighting — this is the only layer that
        # changes dynamically as GEPA mutates the skill.
        if _gen_available and generated_response is not None:
            # Full layered evaluation
            final_score = (
                0.20 * gen_composite          # Generated response quality
                + 0.35 * skill_content_composite  # Skill content coverage
                + 0.05 * ref_composite            # Reference response (sanity)
                + 0.10 * structure_composite      # Structure validation
                + 0.30 * efficiency               # Token efficiency
            )
        else:
            # Fallback: no generative eval, emphasize skill content + efficiency
            final_score = (
                0.40 * skill_content_composite  # Skill content coverage
                + 0.20 * ref_composite            # Reference response
                + 0.10 * structure_composite      # Structure validation
                + 0.30 * efficiency               # Token efficiency
            )

        # ------------------------------------------------------------------
        # Build unified side_info for GEPA reflection
        # ------------------------------------------------------------------
        # Merge all feedbacks for the side_info dict
        all_feedbacks = skill_content_feedbacks + gen_feedbacks + ref_feedbacks + structure_feedbacks
        _, side_info = feedback_to_asi(all_feedbacks)

        side_info["scores"] = {
            "generated_response_quality": gen_composite,
            "skill_content_coverage": skill_content_composite,
            "reference_response_check": ref_composite,
            "structure_validation": structure_composite,
            "token_efficiency": efficiency,
            "final": final_score,
        }
        side_info["token_counts"] = {
            "candidate_total": total_candidate_tokens,
            "original_total": total_original_tokens,
        }

        # Enrich ASI for GEPA reflection (Step 4 from plan)
        if generated_response is not None:
            side_info["_generated_response"] = generated_response[:2000]
        side_info["_task_prompt"] = example.get("input", "")[:500]

        # Skill coverage summary
        if skill_content_feedbacks:
            found = [fb.name for fb in skill_content_feedbacks if fb.value == "yes"]
            missing = [fb.name for fb in skill_content_feedbacks if fb.value == "no"]
            side_info["_skill_coverage"] = {
                "found": found,
                "missing": missing,
                "coverage_ratio": len(found) / max(len(found) + len(missing), 1),
            }

        # Baseline comparison -- show GEPA's reflection LM what improved/regressed
        task_key = example.get("input", "")
        if task_key and task_key in _baseline:
            comparisons = []
            for scorer_name, baseline_val in _baseline[task_key].items():
                current_val = side_info.get(scorer_name, {}).get("score")
                if current_val is None or baseline_val is None:
                    continue
                if current_val > baseline_val + 0.01:
                    comparisons.append(
                        f"Improved on {scorer_name} ({baseline_val:.2f} -> {current_val:.2f})"
                    )
                elif current_val < baseline_val - 0.01:
                    comparisons.append(
                        f"Regressed on {scorer_name} ({baseline_val:.2f} -> {current_val:.2f})"
                    )
            if comparisons:
                side_info["_baseline_comparison"] = "; ".join(comparisons)

        return final_score, side_info

    def set_baseline(per_task_side_info: dict[str, dict]) -> None:
        """Cache per-task per-scorer scores from the seed evaluation.

        Args:
            per_task_side_info: {task_input_text: side_info_dict} from seed eval.
        """
        for task_key, info in per_task_side_info.items():
            _baseline[task_key] = {
                name: data.get("score")
                for name, data in info.items()
                if isinstance(data, dict) and "score" in data
                and not name.startswith("_")
            }

    evaluator.set_baseline = set_baseline  # type: ignore[attr-defined]
    return evaluator


def build_optimization_background(
    skill_name: str,
    original_token_count: int,
    component_names: list[str] | None = None,
    baseline_scores: dict[str, float] | None = None,
    baseline_side_info: dict[str, dict] | None = None,
) -> str:
    """Build the background context string for GEPA's reflection LM.

    Args:
        skill_name: Name of the skill being optimized.
        original_token_count: Total token count of the original artifacts.
        component_names: Names of the candidate components (e.g. "skill_md", "tools_*").
        baseline_scores: Per-task overall scores from evaluating the seed candidate.
        baseline_side_info: Per-task side_info dicts from evaluating the seed candidate.
    """
    components_desc = ""
    if component_names and any(c.startswith("tools_") for c in component_names):
        tool_modules = [c.replace("tools_", "") for c in component_names if c.startswith("tools_")]
        components_desc = (
            "\n\nYou are also optimizing MCP tool descriptions for these modules: "
            f"{', '.join(tool_modules)}. "
            "Tool descriptions are docstrings on @mcp.tool functions. Keep them "
            "accurate, concise, and action-oriented.\n"
        )

    # Build baseline performance summary
    baseline_desc = ""
    if baseline_scores:
        mean_score = sum(baseline_scores.values()) / len(baseline_scores)
        perfect = [tid for tid, s in baseline_scores.items() if s >= 0.99]
        weak = sorted(
            [(tid, s) for tid, s in baseline_scores.items() if s < 0.99],
            key=lambda x: x[1],
        )

        baseline_desc = (
            f"\n\nBASELINE PERFORMANCE (seed candidate):\n"
            f"  Mean score: {mean_score:.3f} across {len(baseline_scores)} test cases.\n"
        )
        if perfect:
            baseline_desc += f"  Perfect/near-perfect ({len(perfect)}): {', '.join(perfect)}\n"
        if weak:
            baseline_desc += "  Needs improvement:\n"
            for tid, score in weak:
                baseline_desc += f"    - {tid}: {score:.3f}"
                # Add per-scorer detail if available
                if baseline_side_info and tid in baseline_side_info:
                    info = baseline_side_info[tid]
                    failing = [
                        name for name, data in info.items()
                        if isinstance(data, dict) and data.get("status") == "fail"
                        and not name.startswith("_")
                    ]
                    if failing:
                        baseline_desc += f" (failing: {', '.join(failing)})"
                baseline_desc += "\n"

        baseline_desc += (
            "\n  PRIORITY: Focus optimization effort on the weak test cases above. "
            "Do NOT break test cases that already score well.\n"
        )

    return (
        f"You are REFINING an existing, working SKILL.md file for the '{skill_name}' "
        "Databricks skill. The seed candidate is a production skill that already works -- "
        "preserve what already works and improve what doesn't.\n\n"
        "SKILL.md files teach AI agents (like Claude Code) how to use specific Databricks features. "
        "They contain patterns, code examples, API references, and best practices.\n\n"
        "EVALUATION: The skill is evaluated by having a small LLM generate responses from it. "
        "Better skill documentation produces more correct responses. Scores come from:\n"
        "- Generated response quality (20%): An LLM reads ONLY the skill and answers a test prompt. "
        "Its response is scored against expected patterns and facts.\n"
        "- Skill content coverage (35%): Does the SKILL.md itself contain the patterns and facts "
        "needed to answer test prompts? Removing key content directly drops this score.\n"
        "- Reference response check (5%): Sanity check against a known-good response.\n"
        "- Structure validation (10%): Python/SQL syntax, no hallucinated APIs.\n"
        "- Token efficiency (30%): Conciseness vs original -- smaller is ACTIVELY REWARDED. "
        "Shrinking the skill below its original size gives a bonus score (up to 1.15x at 0% of original). "
        "Growing the skill is penalized linearly to 0.0 at 2x original size.\n\n"
        "KEY INSIGHT: Token efficiency is the second-highest weight. Every token you remove "
        "directly improves the score. SkillsBench research shows long skills hurt agent performance "
        "via 'cognitive overhead' -- agents get confused by verbose docs. Be ruthlessly concise.\n\n"
        f"IMPORTANT: The current artifacts total {original_token_count:,} tokens. "
        "Optimized versions MUST be MORE CONCISE. Target at least 10-20% token reduction. "
        "Remove redundant examples, consolidate similar patterns, "
        "eliminate verbose explanations, and merge overlapping sections. "
        "Every token consumed is agent context window budget -- keep skills lean and focused."
        f"{baseline_desc}"
        f"{components_desc}"
    )
