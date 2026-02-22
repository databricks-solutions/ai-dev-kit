"""Evaluator bridge: wrap existing MLflow scorers into a GEPA adapter.

This is the core integration point between the skill-test scorer framework
and GEPA's optimize(). It implements GEPAAdapter to evaluate candidate
SKILL.md texts against test cases using existing scorers.
"""

import inspect
from pathlib import Path
from typing import Any, Literal

import tiktoken
from gepa import EvaluationBatch, GEPAAdapter
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
from .splitter import SkillTask


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


def token_efficiency_score(candidate_text: str, original_token_count: int) -> float:
    """Score 0-1 based on how concise the candidate is vs. the original.

    - Same size or smaller = 1.0
    - 10% larger = 0.9, 20% larger = 0.8, etc.
    - Capped at 0.0 for 100%+ bloat
    """
    if original_token_count <= 0:
        return 1.0
    enc = tiktoken.get_encoding("cl100k_base")
    candidate_tokens = len(enc.encode(candidate_text))
    ratio = candidate_tokens / original_token_count
    return max(0.0, min(1.0, 2.0 - ratio))


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def token_efficiency_score_raw(candidate_tokens: int, original_tokens: int) -> float:
    """Score 0-1 based on token count ratio. Same logic as token_efficiency_score."""
    if original_tokens <= 0:
        return 1.0
    ratio = candidate_tokens / original_tokens
    return max(0.0, min(1.0, 2.0 - ratio))


def _run_scorer(scorer_fn: Any, outputs: dict, expectations: dict, inputs: dict) -> list[Feedback]:
    """Run a single scorer and normalize the result to a list of Feedbacks."""
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
    task: SkillTask,
    scorer_config: dict[str, Any],
) -> list[Feedback]:
    """Run deterministic scorers against a task's expected response."""
    outputs = {"response": task.get("answer", "")}
    expectations = task.get("expectations", {})
    inputs = {"prompt": task.get("input", "")}

    if scorer_config:
        scorers = build_scorers(scorer_config)
    else:
        scorers = [
            python_syntax,
            sql_syntax,
            pattern_adherence,
            no_hallucinated_apis,
            expected_facts_present,
        ]

    all_feedbacks = []
    for scorer_fn in scorers:
        # Skip LLM-based scorers -- only deterministic
        scorer_name = getattr(scorer_fn, "__name__", "") or getattr(scorer_fn, "name", "")
        if scorer_name in ("Safety", "Guidelines", "skill_quality"):
            continue
        feedbacks = _run_scorer(scorer_fn, outputs, expectations, inputs)
        all_feedbacks.extend(feedbacks)

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


# Type aliases for GEPA adapter generics
_Trajectory = dict[str, Any]
_RolloutOutput = dict[str, Any]


class SkillAdapter(GEPAAdapter):
    """GEPA adapter that evaluates candidate texts using existing scorers.

    Supports multi-component optimization:
    - "skill_md": SKILL.md content (primary)
    - "tools_*": MCP tool description blocks (optional, one per module)

    GEPA's RoundRobinReflectionComponentSelector cycles through all components.
    """

    SKILL_KEY = "skill_md"

    def __init__(
        self,
        skill_name: str,
        mode: Literal["static", "generative"] = "static",
        task_lm: str | None = None,
        original_token_counts: dict[str, int] | None = None,
    ):
        self.skill_name = skill_name
        self.mode = mode
        self.task_lm = task_lm
        self.scorer_config = load_scorer_config(skill_name)

        # Per-component original token counts for efficiency scoring
        if original_token_counts:
            self.original_token_counts = original_token_counts
        else:
            skill_path = _find_skill_md(skill_name)
            self.original_token_counts = {
                self.SKILL_KEY: count_tokens(skill_path.read_text()) if skill_path else 0
            }

    @property
    def original_token_count(self) -> int:
        """Total original token count across all components."""
        return sum(self.original_token_counts.values())

    def evaluate(
        self,
        batch: list[dict[str, Any]],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch:
        """Evaluate candidate SKILL.md against a batch of test cases.

        Args:
            batch: List of DefaultDataInst dicts ({input, additional_context, answer})
            candidate: Dict with key "skill_md" -> SKILL.md content
            capture_traces: Whether to capture traces (for reflection dataset)

        Returns:
            EvaluationBatch with trajectories containing scores and diagnostics
        """
        candidate_text = candidate.get(self.SKILL_KEY, "")
        outputs: list[dict[str, Any]] = []
        scores: list[float] = []
        trajectories = []

        for data_inst in batch:
            all_feedbacks = []

            # Build a SkillTask from the data instance for scorer compatibility
            task: SkillTask = {
                "id": data_inst.get("additional_context", {}).get("id", ""),
                "input": data_inst.get("input", ""),
                "answer": data_inst.get("answer", ""),
                "additional_context": data_inst.get("additional_context", {}),
                "metadata": {},
            }

            # Decode expectations if stored in additional_context
            expectations_json = data_inst.get("additional_context", {}).get("expectations", "")
            if expectations_json:
                import json
                try:
                    task["expectations"] = json.loads(expectations_json)
                except (json.JSONDecodeError, TypeError):
                    task["expectations"] = {}

            if self.mode == "generative" and self.task_lm:
                # Generate a fresh response using the candidate skill
                import litellm
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are an AI assistant with the following skill documentation:\n\n"
                            f"{candidate_text}\n\n"
                            "Use this documentation to answer the user's question."
                        ),
                    },
                    {"role": "user", "content": task.get("input", "")},
                ]
                response = litellm.completion(model=self.task_lm, messages=messages)
                task["answer"] = response.choices[0].message.content

            # 1. Run deterministic scorers against the response
            response_feedbacks = _run_deterministic_scorers(task, self.scorer_config)
            all_feedbacks.extend(response_feedbacks)

            # 2. Validate the skill structure itself
            structure_feedbacks = _validate_skill_structure(candidate_text)
            all_feedbacks.extend(structure_feedbacks)

            # 3. Convert to score + diagnostics
            composite, diagnostics = feedback_to_asi(all_feedbacks)

            # 4. Factor in token efficiency (across ALL components)
            total_candidate_tokens = sum(count_tokens(v) for v in candidate.values())
            total_original_tokens = self.original_token_count
            efficiency = token_efficiency_score_raw(total_candidate_tokens, total_original_tokens)

            # Weighted composite: 80% quality, 20% token efficiency
            final_score = 0.8 * composite + 0.2 * efficiency

            output = {"full_assistant_response": task.get("answer", "")}
            outputs.append(output)
            scores.append(final_score)

            trajectory = {
                "data": data_inst,
                "full_assistant_response": task.get("answer", ""),
                "score": final_score,
                "quality_score": composite,
                "efficiency_score": efficiency,
                "diagnostics": diagnostics,
                "failure_messages": diagnostics.get("_failure_messages", []),
            }
            trajectories.append(trajectory)

        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Build reflective dataset from evaluation results for GEPA's mutation proposer.

        Extracts failure messages from diagnostics so the reflection LM
        knows exactly what went wrong and can propose targeted mutations.
        """
        reflective_data: dict[str, list[dict[str, Any]]] = {}

        for component in components_to_update:
            examples = []
            for traj in eval_batch.trajectories:
                failure_msgs = traj.get("failure_messages", [])
                if not failure_msgs:
                    continue

                examples.append({
                    "input": traj.get("data", {}).get("input", ""),
                    "current_text": candidate.get(component, ""),
                    "feedback": "\n".join(failure_msgs),
                    "score": traj.get("score", 0.0),
                })

            reflective_data[component] = examples

        return reflective_data


def create_skill_adapter(
    skill_name: str,
    mode: Literal["static", "generative"] = "static",
    task_lm: str | None = None,
    original_token_counts: dict[str, int] | None = None,
) -> SkillAdapter:
    """Create a SkillAdapter for GEPA optimization.

    Args:
        skill_name: Name of the skill being optimized
        mode: "static" or "generative"
        task_lm: LLM model string for generative mode
        original_token_counts: Per-component original token counts (for multi-component)

    Returns:
        Configured SkillAdapter instance
    """
    return SkillAdapter(
        skill_name=skill_name,
        mode=mode,
        task_lm=task_lm,
        original_token_counts=original_token_counts,
    )


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
            "Tool descriptions are docstrings on @mcp.tool functions. They tell the AI agent "
            "what each tool does, its parameters, and return values. Keep descriptions "
            "accurate, concise, and action-oriented. Include usage hints that help the agent "
            "choose the right tool.\n"
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
        f"IMPORTANT: The current skill is {original_token_count:,} tokens. "
        "Optimized skills should be MORE CONCISE, not larger. "
        "Remove redundant examples, consolidate similar patterns, "
        "and eliminate verbose explanations that don't add value. "
        "Every token consumed is agent context window budget -- keep skills lean and focused."
        f"{components_desc}"
    )
