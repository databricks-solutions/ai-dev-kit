"""End-to-end orchestrator for GEPA skill optimization.

Workflow: load skill -> split dataset -> build adapter -> optimize -> log results
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import gepa

from ..config import SkillTestConfig
from ..runners.evaluate import setup_mlflow
from .config import get_preset
from .evaluator import (
    SkillAdapter,
    create_skill_adapter,
    count_tokens,
    build_optimization_background,
    _find_skill_md,
    token_efficiency_score,
)
from .splitter import create_gepa_datasets, generate_bootstrap_tasks, to_gepa_instances


@dataclass
class OptimizationResult:
    """Result of a GEPA optimization run."""

    skill_name: str
    original_score: float
    optimized_score: float
    improvement: float
    original_content: str
    optimized_content: str
    original_token_count: int
    optimized_token_count: int
    token_reduction_pct: float
    diff_summary: str
    val_scores: dict[str, float]
    mlflow_run_id: str | None
    gepa_result: Any


def _compute_diff_summary(original: str, optimized: str) -> str:
    """Generate a human-readable summary of changes between original and optimized."""
    import difflib
    import re

    original_lines = original.splitlines(keepends=True)
    optimized_lines = optimized.splitlines(keepends=True)

    diff = list(difflib.unified_diff(original_lines, optimized_lines, fromfile="original", tofile="optimized", n=1))

    if not diff:
        return "No changes"

    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    summary_parts = []
    if added:
        summary_parts.append(f"+{added} lines added")
    if removed:
        summary_parts.append(f"-{removed} lines removed")

    # Extract changed section headers for context
    changed_sections = set()
    for line in diff:
        content = line[1:].strip() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")) else ""
        if content.startswith("#"):
            changed_sections.add(content)

    summary = ", ".join(summary_parts)
    if changed_sections:
        sections = "\n".join(f"  ~ {s}" for s in sorted(changed_sections)[:10])
        summary += f"\n\nChanged sections:\n{sections}"

    return summary


def _evaluate_on_tasks(
    adapter: SkillAdapter,
    candidate: dict[str, str],
    tasks: list[dict[str, Any]],
) -> tuple[float, dict[str, float]]:
    """Run adapter on a set of tasks and return mean score + per-task scores."""
    gepa_instances = to_gepa_instances(tasks)
    eval_batch = adapter.evaluate(gepa_instances, candidate)

    per_task: dict[str, float] = {}
    for i, score in enumerate(eval_batch.scores):
        task_id = tasks[i].get("id", f"task_{i}")
        per_task[task_id] = score

    mean_score = sum(per_task.values()) / len(per_task) if per_task else 0.0
    return mean_score, per_task


def optimize_skill(
    skill_name: str,
    mode: Literal["static", "generative"] = "static",
    preset: Literal["quick", "standard", "thorough"] = "standard",
    task_lm: str | None = None,
    reflection_lm: str | None = None,
    dry_run: bool = False,
) -> OptimizationResult:
    """Run end-to-end GEPA optimization on a skill.

    1. Load current SKILL.md as seed_candidate
    2. Create train/val datasets from ground_truth.yaml
    3. Build adapter from existing scorers
    4. Run gepa.optimize()
    5. Log results to MLflow
    6. Return OptimizationResult with original/optimized scores and diff

    Args:
        skill_name: Name of the skill to optimize
        mode: "static" (uses ground truth responses) or "generative" (generates fresh)
        preset: GEPA config preset ("quick", "standard", "thorough")
        task_lm: LLM model for generative mode
        reflection_lm: Override reflection LM (default: GEPA_REFLECTION_LM env or databricks/databricks-gpt-5-2)
        dry_run: If True, show config and dataset info without running optimization

    Returns:
        OptimizationResult with scores, content, and diff

    Raises:
        FileNotFoundError: If SKILL.md cannot be found
    """
    # 1. Load current SKILL.md
    skill_path = _find_skill_md(skill_name)
    if skill_path is None:
        raise FileNotFoundError(
            f"Could not find SKILL.md for '{skill_name}'. "
            "Expected at .claude/skills/{name}/SKILL.md or databricks-skills/{name}/SKILL.md"
        )

    original_content = skill_path.read_text()
    original_token_count = count_tokens(original_content)

    # 2. Create train/val datasets
    try:
        train, val = create_gepa_datasets(skill_name)
    except FileNotFoundError:
        train, val = [], None

    if not train:
        # Bootstrap mode
        train = generate_bootstrap_tasks(skill_name)
        val = None
        print(f"No test cases found for '{skill_name}'. Using {len(train)} auto-generated tasks.")
        print(f"For better results, add test cases: skill-test add {skill_name}")

    # 3. Build adapter
    adapter = create_skill_adapter(skill_name, mode=mode, task_lm=task_lm)

    # seed_candidate is a dict with our SKILL_KEY
    seed_candidate = {SkillAdapter.SKILL_KEY: original_content}

    # 4. Get preset config (with optional reflection LM override)
    preset_config = get_preset(preset, reflection_lm=reflection_lm)

    # Dry run: show info and exit
    if dry_run:
        print(f"\n=== Dry Run: {skill_name} ===")
        print(f"SKILL.md path: {skill_path}")
        print(f"Original tokens: {original_token_count:,}")
        print(f"Train tasks: {len(train)}")
        print(f"Val tasks: {len(val) if val else 'None (single-task mode)'}")
        print(f"Mode: {mode}")
        print(f"Preset: {preset} (max_metric_calls={preset_config.max_metric_calls})")
        print(f"Reflection LM: {preset_config.reflection_lm}")
        if mode == "generative":
            print(f"Task LM: {task_lm or 'not set'}")

        # Evaluate current score
        original_score, _ = _evaluate_on_tasks(adapter, seed_candidate, train)
        print(f"Current score: {original_score:.3f}")

        return OptimizationResult(
            skill_name=skill_name,
            original_score=original_score,
            optimized_score=original_score,
            improvement=0.0,
            original_content=original_content,
            optimized_content=original_content,
            original_token_count=original_token_count,
            optimized_token_count=original_token_count,
            token_reduction_pct=0.0,
            diff_summary="Dry run - no optimization performed",
            val_scores={},
            mlflow_run_id=None,
            gepa_result=None,
        )

    # Evaluate original score
    original_score, _ = _evaluate_on_tasks(adapter, seed_candidate, train)

    # 5. Convert datasets to GEPA format
    trainset = to_gepa_instances(train)
    valset = to_gepa_instances(val) if val else None

    # 6. Run gepa.optimize()
    gepa_kwargs = {
        "seed_candidate": seed_candidate,
        "trainset": trainset,
        "adapter": adapter,
        **preset_config.to_kwargs(),
    }
    if valset:
        gepa_kwargs["valset"] = valset
    if task_lm:
        gepa_kwargs["task_lm"] = task_lm

    result = gepa.optimize(**gepa_kwargs)

    # result.best_candidate is dict[str, str]
    optimized_content = result.best_candidate.get(SkillAdapter.SKILL_KEY, original_content)
    optimized_token_count = count_tokens(optimized_content)

    # Evaluate optimized on train
    optimized_candidate = {SkillAdapter.SKILL_KEY: optimized_content}
    optimized_score, _ = _evaluate_on_tasks(adapter, optimized_candidate, train)

    # Evaluate on val if available
    val_scores: dict[str, float] = {}
    if val:
        _, val_scores = _evaluate_on_tasks(adapter, optimized_candidate, val)

    # Token reduction
    token_reduction_pct = (
        (original_token_count - optimized_token_count) / original_token_count * 100
        if original_token_count > 0
        else 0.0
    )

    # Diff summary
    diff_summary = _compute_diff_summary(original_content, optimized_content)

    # 7. Log to MLflow (best-effort)
    mlflow_run_id = None
    try:
        import mlflow

        stc = SkillTestConfig()
        setup_mlflow(stc)

        with mlflow.start_run(run_name=f"{skill_name}_optimize_{preset}"):
            mlflow.set_tags(
                {
                    "optimizer": "gepa",
                    "skill_name": skill_name,
                    "preset": preset,
                    "mode": mode,
                }
            )
            mlflow.log_metrics(
                {
                    "original_score": original_score,
                    "optimized_score": optimized_score,
                    "improvement": optimized_score - original_score,
                    "original_tokens": float(original_token_count),
                    "optimized_tokens": float(optimized_token_count),
                    "token_reduction_pct": token_reduction_pct,
                    "total_metric_calls": float(result.total_metric_calls or 0),
                }
            )
            mlflow_run_id = mlflow.active_run().info.run_id
    except Exception:
        pass

    return OptimizationResult(
        skill_name=skill_name,
        original_score=original_score,
        optimized_score=optimized_score,
        improvement=optimized_score - original_score,
        original_content=original_content,
        optimized_content=optimized_content,
        original_token_count=original_token_count,
        optimized_token_count=optimized_token_count,
        token_reduction_pct=token_reduction_pct,
        diff_summary=diff_summary,
        val_scores=val_scores,
        mlflow_run_id=mlflow_run_id,
        gepa_result=result,
    )
