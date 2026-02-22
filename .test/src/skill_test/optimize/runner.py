"""End-to-end orchestrator for GEPA skill optimization.

Uses optimize_anything API: evaluator function + GEPAConfig.
"""

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from gepa.optimize_anything import optimize_anything, GEPAConfig

from ..config import SkillTestConfig
from ..runners.evaluate import setup_mlflow
from .config import get_preset
from .evaluator import (
    SKILL_KEY,
    create_skill_evaluator,
    count_tokens,
    build_optimization_background,
    _find_skill_md,
)
from .splitter import create_gepa_datasets, generate_bootstrap_tasks, to_gepa_instances
from .tools import (
    extract_tool_descriptions,
    tools_to_gepa_components,
    get_tool_stats,
)


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
    components: dict[str, str] | None = None
    original_components: dict[str, str] | None = None
    tool_map: Any = None


def _compute_diff_summary(original: str, optimized: str) -> str:
    """Generate a human-readable summary of changes."""
    original_lines = original.splitlines(keepends=True)
    optimized_lines = optimized.splitlines(keepends=True)
    diff = list(difflib.unified_diff(original_lines, optimized_lines, fromfile="original", tofile="optimized", n=1))

    if not diff:
        return "No changes"

    added = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

    parts = []
    if added:
        parts.append(f"+{added} lines added")
    if removed:
        parts.append(f"-{removed} lines removed")

    changed_sections = set()
    for line in diff:
        content = line[1:].strip() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")) else ""
        if content.startswith("#"):
            changed_sections.add(content)

    summary = ", ".join(parts)
    if changed_sections:
        sections = "\n".join(f"  ~ {s}" for s in sorted(changed_sections)[:10])
        summary += f"\n\nChanged sections:\n{sections}"

    return summary


def _evaluate_on_tasks(evaluator, candidate, tasks):
    """Run evaluator on tasks and return mean score + per-task scores."""
    gepa_instances = to_gepa_instances(tasks)
    per_task = {}
    for i, inst in enumerate(gepa_instances):
        score, _ = evaluator(candidate, inst)
        per_task[tasks[i].get("id", f"task_{i}")] = score
    mean = sum(per_task.values()) / len(per_task) if per_task else 0.0
    return mean, per_task


def optimize_skill(
    skill_name: str,
    mode: Literal["static", "generative"] = "static",
    preset: Literal["quick", "standard", "thorough"] = "standard",
    task_lm: str | None = None,
    reflection_lm: str | None = None,
    include_tools: bool = False,
    tool_modules: list[str] | None = None,
    tools_only: bool = False,
    dry_run: bool = False,
) -> OptimizationResult:
    """Run end-to-end GEPA optimization on a skill and/or tools.

    Uses optimize_anything API with a simple evaluator function.

    Args:
        skill_name: Name of the skill to optimize
        mode: "static" or "generative"
        preset: "quick" (15), "standard" (50), "thorough" (150)
        task_lm: LLM for generative mode
        reflection_lm: Override reflection LM
        include_tools: Include MCP tool descriptions as additional components
        tool_modules: Specific tool modules (None = all)
        tools_only: Optimize ONLY tool descriptions
        dry_run: Show config without running
    """
    # 1. Load SKILL.md
    skill_path = _find_skill_md(skill_name)
    if not tools_only and skill_path is None:
        raise FileNotFoundError(f"Could not find SKILL.md for '{skill_name}'")

    original_content = skill_path.read_text() if skill_path else ""

    # 1b. Load MCP tool descriptions
    tool_map = None
    tool_components: dict[str, str] = {}
    if include_tools or tools_only:
        tool_map = extract_tool_descriptions(modules=tool_modules)
        tool_components = tools_to_gepa_components(tool_map, per_module=True)
        stats = get_tool_stats()
        print(f"Tool modules: {stats['modules']}, tools: {stats['total_tools']}, "
              f"description chars: {stats['total_description_chars']:,}")

    # 2. Build seed_candidate (multi-component dict)
    seed_candidate: dict[str, str] = {}
    original_token_counts: dict[str, int] = {}

    if not tools_only:
        seed_candidate[SKILL_KEY] = original_content
        original_token_counts[SKILL_KEY] = count_tokens(original_content)

    for comp_name, comp_text in tool_components.items():
        seed_candidate[comp_name] = comp_text
        original_token_counts[comp_name] = count_tokens(comp_text)

    total_original_tokens = sum(original_token_counts.values())

    # 3. Load datasets
    try:
        train, val = create_gepa_datasets(skill_name)
    except FileNotFoundError:
        train, val = [], None

    if not train:
        train = generate_bootstrap_tasks(skill_name)
        val = None
        print(f"No test cases found. Using {len(train)} auto-generated tasks.")

    # 4. Build evaluator
    evaluator = create_skill_evaluator(
        skill_name, mode=mode, task_lm=task_lm,
        original_token_counts=original_token_counts,
    )

    # 5. Get config
    config = get_preset(preset, reflection_lm=reflection_lm)

    # Dry run
    if dry_run:
        print(f"\n=== Dry Run: {skill_name} ===")
        if not tools_only:
            print(f"SKILL.md path: {skill_path}")
        print(f"Components: {list(seed_candidate.keys())}")
        print(f"Total original tokens: {total_original_tokens:,}")
        for comp, tokens in original_token_counts.items():
            print(f"  {comp}: {tokens:,} tokens")
        print(f"Train tasks: {len(train)}")
        print(f"Val tasks: {len(val) if val else 'None (single-task mode)'}")
        print(f"Mode: {mode}")
        print(f"Preset: {preset} (max_metric_calls={config.engine.max_metric_calls})")
        print(f"Reflection LM: {config.reflection.reflection_lm}")

        original_score, _ = _evaluate_on_tasks(evaluator, seed_candidate, train)
        print(f"Current score: {original_score:.3f}")

        return OptimizationResult(
            skill_name=skill_name,
            original_score=original_score,
            optimized_score=original_score,
            improvement=0.0,
            original_content=original_content,
            optimized_content=original_content,
            original_token_count=total_original_tokens,
            optimized_token_count=total_original_tokens,
            token_reduction_pct=0.0,
            diff_summary="Dry run - no optimization performed",
            val_scores={},
            mlflow_run_id=None,
            gepa_result=None,
            components=dict(seed_candidate),
            original_components=dict(seed_candidate),
            tool_map=tool_map,
        )

    # Evaluate original
    original_score, _ = _evaluate_on_tasks(evaluator, seed_candidate, train)

    # 6. Build background and objective
    background = build_optimization_background(
        skill_name, total_original_tokens,
        component_names=list(seed_candidate.keys()),
    )
    objective = (
        f"Optimize the '{skill_name}' skill for maximum quality and minimum token count. "
        "Higher quality scores and fewer tokens are both better."
    )

    # 7. Convert datasets to GEPA format
    trainset = to_gepa_instances(train)
    valset = to_gepa_instances(val) if val else None

    # 8. Run optimize_anything
    result = optimize_anything(
        seed_candidate=seed_candidate,
        evaluator=evaluator,
        dataset=trainset,
        valset=valset,
        objective=objective,
        background=background,
        config=config,
    )

    # 9. Extract results
    best = result.best_candidate
    optimized_content = best.get(SKILL_KEY, original_content)
    optimized_token_count = sum(count_tokens(v) for v in best.values())

    optimized_score, _ = _evaluate_on_tasks(evaluator, best, train)

    val_scores: dict[str, float] = {}
    if val:
        _, val_scores = _evaluate_on_tasks(evaluator, best, val)

    token_reduction_pct = (
        (total_original_tokens - optimized_token_count) / total_original_tokens * 100
        if total_original_tokens > 0 else 0.0
    )

    diff_summary = _compute_diff_summary(original_content, optimized_content)

    # 10. MLflow logging (best-effort)
    mlflow_run_id = None
    try:
        import mlflow
        stc = SkillTestConfig()
        setup_mlflow(stc)
        with mlflow.start_run(run_name=f"{skill_name}_optimize_{preset}"):
            mlflow.set_tags({"optimizer": "gepa", "skill_name": skill_name, "preset": preset, "mode": mode})
            mlflow.log_metrics({
                "original_score": original_score,
                "optimized_score": optimized_score,
                "improvement": optimized_score - original_score,
                "original_tokens": float(total_original_tokens),
                "optimized_tokens": float(optimized_token_count),
                "token_reduction_pct": token_reduction_pct,
                "total_metric_calls": float(result.total_metric_calls or 0),
            })
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
        original_token_count=total_original_tokens,
        optimized_token_count=optimized_token_count,
        token_reduction_pct=token_reduction_pct,
        diff_summary=diff_summary,
        val_scores=val_scores,
        mlflow_run_id=mlflow_run_id,
        gepa_result=result,
        components=dict(best),
        original_components=dict(seed_candidate),
        tool_map=tool_map,
    )
