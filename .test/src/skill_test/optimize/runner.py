"""End-to-end orchestrator for GEPA skill optimization.

Uses optimize_anything API: evaluator function + GEPAConfig.
"""

import copy
import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from gepa.optimize_anything import optimize_anything, GEPAConfig

from ..config import SkillTestConfig
from ..runners.evaluate import setup_mlflow
from .config import get_preset, validate_reflection_context, estimate_pass_duration, DEFAULT_GEN_LM
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
    """Run evaluator on tasks and return mean score, per-task scores, and per-task side_info.

    Returns:
        (mean_score, per_task_scores, side_info_by_id, side_info_by_input)
        - per_task_scores: {task_id: float}
        - side_info_by_id: {task_id: side_info_dict} -- for background builder
        - side_info_by_input: {input_text: side_info_dict} -- for evaluator baseline
    """
    gepa_instances = to_gepa_instances(tasks)
    per_task = {}
    side_info_by_id = {}
    side_info_by_input = {}
    for i, inst in enumerate(gepa_instances):
        score, side_info = evaluator(candidate, inst)
        task_id = tasks[i].get("id", f"task_{i}")
        per_task[task_id] = score
        side_info_by_id[task_id] = side_info
        side_info_by_input[inst.get("input", f"task_{i}")] = side_info
    mean = sum(per_task.values()) / len(per_task) if per_task else 0.0
    return mean, per_task, side_info_by_id, side_info_by_input


def optimize_skill(
    skill_name: str,
    mode: Literal["static", "generative"] = "static",
    preset: Literal["quick", "standard", "thorough"] = "standard",
    task_lm: str | None = None,
    gen_model: str | None = None,
    reflection_lm: str | None = None,
    include_tools: bool = False,
    tool_modules: list[str] | None = None,
    tools_only: bool = False,
    dry_run: bool = False,
    max_passes: int = 5,
    max_metric_calls: int | None = None,
) -> OptimizationResult:
    """Run end-to-end GEPA optimization on a skill and/or tools.

    Uses optimize_anything API with a simple evaluator function.
    Runs up to ``max_passes`` optimization passes per component, feeding
    each pass's best candidate as the seed for the next.  Stops early
    when a pass produces no score improvement.

    Args:
        skill_name: Name of the skill to optimize
        mode: "static" or "generative"
        preset: "quick" (15), "standard" (50), "thorough" (150)
        task_lm: LLM for generative mode (deprecated, use gen_model)
        gen_model: LLM for generative evaluation (default: GEPA_GEN_LM env)
        reflection_lm: Override reflection LM
        include_tools: Include MCP tool descriptions as additional components
        tool_modules: Specific tool modules (None = all)
        tools_only: Optimize ONLY tool descriptions
        dry_run: Show config without running
        max_passes: Maximum optimization passes (default 5). Each pass
            re-seeds from the previous best and runs a full GEPA cycle.
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
    # Resolve gen_model: explicit arg > task_lm (deprecated) > env default
    effective_gen_model = gen_model or task_lm or DEFAULT_GEN_LM
    if effective_gen_model:
        print(f"Generation model: {effective_gen_model}")

    evaluator = create_skill_evaluator(
        skill_name, mode=mode, task_lm=task_lm,
        gen_model=effective_gen_model,
        original_token_counts=original_token_counts,
    )

    # 5. Get config (scaled by component count)
    num_components = len(seed_candidate)
    config = get_preset(
        preset,
        reflection_lm=reflection_lm,
        num_components=num_components,
        max_metric_calls_override=max_metric_calls,
    )
    print(f"Reflection model: {config.reflection.reflection_lm}")

    # 5b. Validate reflection model context window
    validate_reflection_context(
        config.reflection.reflection_lm, total_original_tokens,
    )

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
        print(f"Generation model: {effective_gen_model or 'None (static only)'}")
        print(f"Preset: {preset} (max_metric_calls={config.engine.max_metric_calls}, "
              f"scaled for {num_components} component(s))")
        print(f"Max passes: {max_passes}")
        print(f"Reflection LM: {config.reflection.reflection_lm}")

        original_score, original_per_task, si_by_id, _ = _evaluate_on_tasks(
            evaluator, seed_candidate, train
        )
        print(f"Current score: {original_score:.3f}")

        # Show per-task baseline in dry-run output
        for task_id, score in original_per_task.items():
            print(f"  {task_id}: {score:.3f}")

        background = build_optimization_background(
            skill_name, total_original_tokens,
            component_names=list(seed_candidate.keys()),
            baseline_scores=original_per_task,
            baseline_side_info=si_by_id,
        )
        print(f"\nBackground preview:\n{background[:500]}...")

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

    # Evaluate original and capture per-task detail for baseline context
    original_score, original_per_task, si_by_id, si_by_input = _evaluate_on_tasks(
        evaluator, seed_candidate, train
    )

    # Set baseline on evaluator so future calls include regression/improvement info
    if hasattr(evaluator, "set_baseline"):
        evaluator.set_baseline(si_by_input)

    # 6. Build background (with baseline scores) and objective
    background = build_optimization_background(
        skill_name, total_original_tokens,
        component_names=list(seed_candidate.keys()),
        baseline_scores=original_per_task,
        baseline_side_info=si_by_id,
    )
    objective = (
        f"Refine and improve the existing '{skill_name}' skill. "
        "Preserve patterns and examples that already score well. "
        "Focus on fixing scorer failures and reducing token count without sacrificing correctness. "
        "Higher quality scores and fewer tokens are both better."
    )

    # 7. Convert datasets to GEPA format
    trainset = to_gepa_instances(train)
    valset = to_gepa_instances(val) if val else None

    # 8. Multi-pass optimization loop
    #    Each pass feeds the previous best as the new seed.
    #    Stops early when a pass produces no score improvement.
    current_seed = dict(seed_candidate)
    best = dict(seed_candidate)
    best_score = original_score
    last_result = None
    total_metric_calls = 0
    improvement_threshold = 0.001  # minimum improvement to continue

    print(f"\n  Starting multi-pass optimization (up to {max_passes} passes, "
          f"{num_components} component(s), {config.engine.max_metric_calls} metric calls/pass)")

    # Print estimated time per pass
    est_secs = estimate_pass_duration(
        config.engine.max_metric_calls,
        config.reflection.reflection_lm,
        total_original_tokens,
        num_dataset_examples=len(train),
    )
    if est_secs is not None:
        est_mins = est_secs / 60
        if est_mins > 5:
            print(f"  Estimated ~{est_mins:.0f} min/pass ({est_mins * max_passes:.0f} min total for {max_passes} passes)")

    for pass_num in range(1, max_passes + 1):
        print(f"\n  --- Pass {pass_num}/{max_passes} (best score so far: {best_score:.4f}) ---")

        # Deep-copy config: optimize_anything mutates
        # config.reflection.reflection_prompt_template when objective/background
        # are provided, which would cause a "mutually exclusive" error on pass 2+.
        pass_config = copy.deepcopy(config)

        result = optimize_anything(
            seed_candidate=current_seed,
            evaluator=evaluator,
            dataset=trainset,
            valset=valset,
            objective=objective,
            background=background,
            config=pass_config,
        )
        total_metric_calls += result.total_metric_calls or 0

        # Evaluate this pass's best candidate
        candidate = result.best_candidate
        pass_score, _, _, _ = _evaluate_on_tasks(evaluator, candidate, train)
        improvement = pass_score - best_score

        print(f"  Pass {pass_num} score: {pass_score:.4f} "
              f"(delta: {'+' if improvement >= 0 else ''}{improvement:.4f})")

        if pass_score > best_score + improvement_threshold:
            best = dict(candidate)
            best_score = pass_score
            last_result = result
            # Use the improved candidate as seed for next pass
            current_seed = dict(candidate)
        else:
            print(f"  No significant improvement in pass {pass_num} -- stopping early.")
            if last_result is None:
                last_result = result
            break
    else:
        print(f"  Completed all {max_passes} passes.")

    if last_result is None:
        last_result = result

    # 9. Extract results
    optimized_content = best.get(SKILL_KEY, original_content)
    optimized_token_count = sum(count_tokens(v) for v in best.values())

    optimized_score = best_score

    val_scores: dict[str, float] = {}
    if val:
        _, val_scores, _, _ = _evaluate_on_tasks(evaluator, best, val)

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
                "total_metric_calls": float(total_metric_calls),
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
        gepa_result=last_result,
        components=dict(best),
        original_components=dict(seed_candidate),
        tool_map=tool_map,
    )
