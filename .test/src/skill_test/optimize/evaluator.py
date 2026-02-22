"""Evaluator bridge: wrap existing MLflow scorers into optimize_anything evaluators.

Creates GEPA-compatible evaluator functions that take a candidate (str or dict)
and a task example, run existing scorers, and return (score, SideInfo).
"""

import inspect
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
    """Score 0-1 based on how concise the candidate is vs. the original.

    Same size or smaller = 1.0, linear penalty up to 0.0 at 2x.
    """
    if original_token_count <= 0:
        return 1.0
    enc = tiktoken.get_encoding("cl100k_base")
    candidate_tokens = len(enc.encode(candidate_text))
    ratio = candidate_tokens / original_token_count
    return max(0.0, min(1.0, 2.0 - ratio))


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


# ---------------------------------------------------------------------------
# Evaluator factory (optimize_anything compatible)
# ---------------------------------------------------------------------------

SKILL_KEY = "skill_md"


def create_skill_evaluator(
    skill_name: str,
    mode: Literal["static", "generative"] = "static",
    task_lm: str | None = None,
    original_token_counts: dict[str, int] | None = None,
) -> Callable:
    """Create an optimize_anything-compatible evaluator for a skill.

    Returns a function: (candidate, example) -> (score, side_info)

    The candidate is dict[str, str] (may have "skill_md" + "tools_*" keys).
    The example is a task dict from the dataset.
    """
    scorer_config = load_scorer_config(skill_name)

    # Compute original token count for efficiency scoring
    if original_token_counts is None:
        skill_path = _find_skill_md(skill_name)
        original_token_counts = {
            SKILL_KEY: count_tokens(skill_path.read_text()) if skill_path else 0
        }
    total_original_tokens = sum(original_token_counts.values())

    def evaluator(candidate: dict[str, str], example: dict) -> tuple[float, dict]:
        """Evaluate a candidate against a single task example.

        Args:
            candidate: dict[str, str] with "skill_md" and/or "tools_*" keys
            example: Task dict with "input", "answer", "additional_context"

        Returns:
            (score, side_info) tuple for optimize_anything
        """
        candidate_text = candidate.get(SKILL_KEY, "")
        all_feedbacks: list[Feedback] = []

        # Decode expectations from additional_context
        expectations = {}
        expectations_json = example.get("additional_context", {}).get("expectations", "")
        if expectations_json:
            import json
            try:
                expectations = json.loads(expectations_json)
            except (json.JSONDecodeError, TypeError):
                pass

        response = example.get("answer", "")

        if mode == "generative" and task_lm:
            import litellm
            messages = [
                {"role": "system", "content": f"Skill documentation:\n\n{candidate_text}\n\nAnswer the user's question."},
                {"role": "user", "content": example.get("input", "")},
            ]
            resp = litellm.completion(model=task_lm, messages=messages)
            response = resp.choices[0].message.content

        # 1. Score the response against test expectations
        response_feedbacks = _run_deterministic_scorers(
            response, expectations, example.get("input", ""), scorer_config
        )
        all_feedbacks.extend(response_feedbacks)

        # 2. Validate skill structure
        if candidate_text:
            structure_feedbacks = _validate_skill_structure(candidate_text)
            all_feedbacks.extend(structure_feedbacks)

        # 3. Convert to score + side_info (with oa.log() for failures)
        composite, side_info = feedback_to_asi(all_feedbacks)

        # 4. Token efficiency across ALL components
        total_candidate_tokens = sum(count_tokens(v) for v in candidate.values())
        if total_original_tokens > 0:
            ratio = total_candidate_tokens / total_original_tokens
            efficiency = max(0.0, min(1.0, 2.0 - ratio))
        else:
            efficiency = 1.0

        # Weighted composite: 80% quality, 20% token efficiency
        final_score = 0.8 * composite + 0.2 * efficiency

        side_info["scores"] = {
            "quality": composite,
            "token_efficiency": efficiency,
        }
        side_info["token_counts"] = {
            "candidate_total": total_candidate_tokens,
            "original_total": total_original_tokens,
        }

        return final_score, side_info

    return evaluator


def build_optimization_background(
    skill_name: str,
    original_token_count: int,
    component_names: list[str] | None = None,
) -> str:
    """Build the background context string for GEPA's reflection LM."""
    components_desc = ""
    if component_names and any(c.startswith("tools_") for c in component_names):
        tool_modules = [c.replace("tools_", "") for c in component_names if c.startswith("tools_")]
        components_desc = (
            "\n\nYou are also optimizing MCP tool descriptions for these modules: "
            f"{', '.join(tool_modules)}. "
            "Tool descriptions are docstrings on @mcp.tool functions. Keep them "
            "accurate, concise, and action-oriented.\n"
        )

    return (
        f"You are optimizing a SKILL.md file for the '{skill_name}' Databricks skill. "
        "SKILL.md files teach AI agents (like Claude Code) how to use specific Databricks features. "
        "They contain patterns, code examples, API references, and best practices.\n\n"
        "The skill is evaluated against test cases that check:\n"
        "- Python/SQL code syntax validity\n"
        "- Adherence to expected patterns (regex matches)\n"
        "- Absence of hallucinated/deprecated APIs\n"
        "- Presence of expected factual information\n"
        "- Overall structural quality of the skill document\n\n"
        f"IMPORTANT: The current artifacts total {original_token_count:,} tokens. "
        "Optimized versions should be MORE CONCISE, not larger. "
        "Remove redundant examples, consolidate similar patterns, "
        "and eliminate verbose explanations that don't add value. "
        "Every token consumed is agent context window budget -- keep skills lean and focused."
        f"{components_desc}"
    )
