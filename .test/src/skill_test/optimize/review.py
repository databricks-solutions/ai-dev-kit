"""Review and apply workflow for optimization results.

Provides human-readable output of optimization results and the ability
to apply the optimized SKILL.md to the repository.

After each optimization run, results are saved to:
    .test/skills/<skill-name>/optimized_SKILL.md   — the optimized content
    .test/skills/<skill-name>/last_optimization.md  — summary with scores and diff
    .test/skills/<skill-name>/runs/<timestamp>/    — detailed per-task results (gitignored)

Use ``--apply-last`` to apply a saved result without re-running optimization.
"""

import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

from .runner import OptimizationResult
from .utils import find_skill_md as _find_skill_md


def save_detailed_run_results(result: OptimizationResult) -> Path | None:
    """Save detailed per-task results to a timestamped run folder.

    Creates a run directory with:
    - run_summary.json: Overall metrics and scores
    - tasks/<task_id>.json: Full details per task including:
      - Actual response (full, not truncated)
      - Without-skill baseline response
      - Judge verdicts and rationales
      - Expected facts/patterns and pass/fail status

    The runs folder is gitignored so these detailed logs don't clutter the repo.

    Returns:
        Path to the run directory, or None if no side_info available.
    """
    si = result.skillbench_side_info or {}
    if not si:
        return None

    # Create timestamped run directory
    results_dir = _get_results_dir(result.skill_name)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_dir = results_dir / "runs" / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write overall summary
    summary = {
        "skill_name": result.skill_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original_score": result.original_score,
        "optimized_score": result.optimized_score,
        "improvement": result.improvement,
        "original_token_count": result.original_token_count,
        "optimized_token_count": result.optimized_token_count,
        "token_reduction_pct": result.token_reduction_pct,
        "evaluator_type": getattr(result, "evaluator_type", "skillbench"),
        "mlflow_run_id": result.mlflow_run_id,
        "task_count": len(si),
        "tasks": {},
    }

    # Per-task score summary
    for task_id, info in si.items():
        scores = info.get("scores", {})
        summary["tasks"][task_id] = {
            "final_score": scores.get("final", 0.0),
            "correctness_with": scores.get("correctness_with", 0.0),
            "completeness_with": scores.get("completeness_with", 0.0),
            "guideline_adherence": scores.get("guideline_adherence", 0.0),
            "skill_effectiveness": scores.get("skill_effectiveness", 0.0),
            "error": info.get("Error", ""),
        }

    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2))

    # Write detailed per-task files
    tasks_dir = run_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)

    for task_id, info in si.items():
        task_detail = {
            "task_id": task_id,
            "task_prompt": info.get("Task", ""),
            # Full responses (not truncated)
            "actual_response": info.get("Actual_Full", info.get("Actual", "")),
            "without_response": info.get("Without_Full", ""),
            "expected_reference": info.get("Expected", ""),
            # Judge feedback with full rationales
            "judges": {
                "correctness_with": info.get("Judge_correctness_with", {}),
                "correctness_without": info.get("Judge_correctness_without", {}),
                "completeness_with": info.get("Judge_completeness_with", {}),
                "completeness_without": info.get("Judge_completeness_without", {}),
                "guideline_adherence": info.get("Judge_guideline_adherence", {}),
                "effectiveness": info.get("Judge_effectiveness", {}),
            },
            # Assertion results
            "missing_facts": info.get("Missing_Facts", []),
            "missing_patterns": info.get("Missing_Patterns", []),
            "passed_facts": info.get("Passed_Facts", []),
            "passed_patterns": info.get("Passed_Patterns", []),
            # Regression analysis if present
            "regression_analysis": info.get("Regression_Analysis", {}),
            # All scores
            "scores": info.get("scores", {}),
            # Error summary
            "error": info.get("Error", ""),
        }

        # Sanitize task_id for filename
        safe_task_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in task_id)
        (tasks_dir / f"{safe_task_id}.json").write_text(json.dumps(task_detail, indent=2))

    return run_dir


def _get_results_dir(skill_name: str) -> Path:
    """Get the results directory for a skill."""
    # Try standard skills dir first
    candidates = [
        Path(".test/skills") / skill_name,
        Path(__file__).resolve().parent.parent.parent / "skills" / skill_name,
    ]
    for d in candidates:
        if d.exists():
            return d
    # Fallback: create under .test/skills
    d = Path(".test/skills") / skill_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_result(result: OptimizationResult) -> tuple[Path | None, Path | None]:
    """Save optimization results to disk for later application.

    Writes two files:
    - ``optimized_SKILL.md`` — the raw optimized content (can be diffed/reviewed)
    - ``last_optimization.json`` — metadata for ``--apply-last``

    Returns:
        Tuple of (optimized_skill_path, metadata_path), either may be None on error.
    """
    # Check if this is a tools-only result (no skill content to save)
    has_tool_components = result.components and any(k.startswith("tools_") for k in result.components)
    is_tools_only = has_tool_components and result.original_content == result.optimized_content

    if result.improvement <= 0 and not is_tools_only:
        return None, None

    results_dir = _get_results_dir(result.skill_name)

    optimized_path = None
    metadata_path = None

    # Write the optimized SKILL.md (skip for tools-only — no skill changes)
    if not is_tools_only and result.optimized_content and result.optimized_content != result.original_content:
        optimized_path = results_dir / "optimized_SKILL.md"
        optimized_path.write_text(result.optimized_content)

    # Write metadata for --apply-last
    metadata = {
        "skill_name": result.skill_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original_score": result.original_score,
        "optimized_score": result.optimized_score,
        "improvement": result.improvement,
        "original_token_count": result.original_token_count,
        "optimized_token_count": result.optimized_token_count,
        "token_reduction_pct": result.token_reduction_pct,
        "diff_summary": result.diff_summary,
        "mlflow_run_id": result.mlflow_run_id,
        "evaluator_type": getattr(result, "evaluator_type", "legacy"),
    }

    # Save tool components if present
    if result.components:
        tool_components = {k: v for k, v in result.components.items() if k.startswith("tools_")}
        if tool_components:
            metadata["has_tool_components"] = True
            # Save each tool component
            for comp_name, comp_text in tool_components.items():
                comp_path = results_dir / f"optimized_{comp_name}.txt"
                comp_path.write_text(comp_text)

    metadata_path = results_dir / "last_optimization.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))

    return optimized_path, metadata_path


def load_last_result(skill_name: str) -> OptimizationResult | None:
    """Load the last saved optimization result for a skill.

    Returns:
        OptimizationResult reconstructed from saved files, or None if not found.
    """
    results_dir = _get_results_dir(skill_name)
    metadata_path = results_dir / "last_optimization.json"
    optimized_path = results_dir / "optimized_SKILL.md"

    if not metadata_path.exists():
        return None

    metadata = json.loads(metadata_path.read_text())

    # Load optimized content
    optimized_content = ""
    if optimized_path.exists():
        optimized_content = optimized_path.read_text()

    # Load original content
    original_content = ""
    skill_path = _find_skill_md(skill_name)
    if skill_path:
        original_content = skill_path.read_text()

    # Reconstruct tool components
    components = None
    if metadata.get("has_tool_components"):
        components = {}
        if optimized_content:
            components["skill_md"] = optimized_content
        for f in results_dir.glob("optimized_tools_*.txt"):
            comp_name = f.stem.replace("optimized_", "")
            components[comp_name] = f.read_text()

    return OptimizationResult(
        skill_name=skill_name,
        original_score=metadata.get("original_score", 0.0),
        optimized_score=metadata.get("optimized_score", 0.0),
        improvement=metadata.get("improvement", 0.0),
        original_content=original_content,
        optimized_content=optimized_content,
        original_token_count=metadata.get("original_token_count", 0),
        optimized_token_count=metadata.get("optimized_token_count", 0),
        token_reduction_pct=metadata.get("token_reduction_pct", 0.0),
        diff_summary=metadata.get("diff_summary", ""),
        val_scores={},
        mlflow_run_id=metadata.get("mlflow_run_id"),
        gepa_result=None,
        components=components,
    )


def review_optimization(result: OptimizationResult) -> None:
    """Print optimization summary for human review.

    Shows: score improvement, token reduction, judge-based effectiveness,
    per-test-case score breakdown, and diff of changes.
    """
    print(f"\n{'=' * 60}")
    print(f"  Optimization Results: {result.skill_name}")
    print(f"{'=' * 60}")

    si = result.skillbench_side_info or {}

    # Aggregate judge-based scores from per-task side_info
    task_count = 0
    sum_corr_w = 0.0
    sum_comp_w = 0.0
    sum_guide = 0.0
    sum_eff = 0.0
    per_task_lines: list[str] = []

    for task_id in sorted(si.keys()):
        info = si[task_id]
        scores = info.get("scores", {})
        corr_w = scores.get("correctness_with", 0.0)
        comp_w = scores.get("completeness_with", 0.0)
        guide = scores.get("guideline_adherence", 0.0)
        eff = scores.get("skill_effectiveness", 0.0)
        sum_corr_w += corr_w
        sum_comp_w += comp_w
        sum_guide += guide
        sum_eff += eff
        task_count += 1

        # Get categorical verdicts for display
        corr_verdict = info.get("Judge_correctness_with", {}).get("verdict", "?")
        comp_verdict = info.get("Judge_completeness_with", {}).get("verdict", "?")
        guide_verdict = info.get("Judge_guideline_adherence", {}).get("verdict", "?")

        # Build per-task notes
        error = info.get("Error", "")
        notes = []
        if "NEEDS_SKILL" in error:
            notes.append("NEEDS_SKILL")
        if "REGRESSION" in error:
            notes.append("REGRESSION")
        if not notes:
            notes.append("OK")
        note_str = f"  [{'; '.join(notes)}]"
        per_task_lines.append(
            f"    {task_id:<30s} corr={corr_verdict:<10s} comp={comp_verdict:<10s} "
            f"guide={guide_verdict:<10s} delta {eff:+.2f}{note_str}"
        )

    if task_count > 0:
        agg_corr = sum_corr_w / task_count
        agg_comp = sum_comp_w / task_count
        agg_guide = sum_guide / task_count
        agg_eff = sum_eff / task_count
    else:
        agg_corr = agg_comp = agg_guide = agg_eff = 0.0

    # Score summary
    improvement_sign = "+" if result.improvement >= 0 else ""
    print(
        f"  Score:              {result.original_score:.3f} -> {result.optimized_score:.3f} "
        f"({improvement_sign}{result.improvement:.3f})"
    )
    print(f"  Skill Effectiveness: {agg_eff:.2f}")
    print(f"  Correctness (with):  {agg_corr:.2f}")
    print(f"  Completeness (with): {agg_comp:.2f}")
    print(f"  Guideline Adherence: {agg_guide:.2f}")

    # Token counts
    reduction_sign = "+" if result.token_reduction_pct >= 0 else ""
    print(
        f"  Tokens:   {result.original_token_count:,} -> {result.optimized_token_count:,} "
        f"({reduction_sign}{result.token_reduction_pct:.1f}%)"
    )

    if result.gepa_result and hasattr(result.gepa_result, "iterations"):
        print(f"  Iterations: {result.gepa_result.iterations}")
    if result.mlflow_run_id:
        print(f"  MLflow run: {result.mlflow_run_id}")

    print()

    # Per-task breakdown
    if per_task_lines:
        print("  Per-task:")
        for line in per_task_lines:
            print(line)
        print()

    # Diff summary
    if result.diff_summary and result.diff_summary != "No changes":
        print("  Changes:")
        for line in result.diff_summary.split("\n"):
            print(f"    {line}")
        print()

    # Detailed diff (first 50 lines)
    if result.original_content != result.optimized_content:
        diff_lines = list(
            difflib.unified_diff(
                result.original_content.splitlines(keepends=True),
                result.optimized_content.splitlines(keepends=True),
                fromfile="original SKILL.md",
                tofile="optimized SKILL.md",
                n=2,
            )
        )
        if len(diff_lines) > 50:
            print(f"  Diff (first 50 of {len(diff_lines)} lines):")
            for line in diff_lines[:50]:
                print(f"    {line}", end="")
            print(f"\n    ... ({len(diff_lines) - 50} more lines)")
        else:
            print("  Diff:")
            for line in diff_lines:
                print(f"    {line}", end="")
        print()
    else:
        print("  No changes to SKILL.md content.")

    # Validation breakdown
    if result.val_scores:
        print("  Validation scores by test case:")
        for task_id, score in sorted(result.val_scores.items()):
            status = "PASS" if score >= 0.5 else "FAIL"
            print(f"    {status} {task_id}: {score:.3f}")
        print()

    # Auto-save result to disk
    saved_skill, saved_meta = save_result(result)
    if saved_skill:
        print(f"  Saved: {saved_skill}")
        print(f"  Apply: uv run python .test/scripts/optimize.py {result.skill_name} --apply-last")
    elif result.original_content == result.optimized_content:
        print("  No improvement found -- nothing saved.")

    # Save detailed run results (full responses, judge rationales)
    run_dir = save_detailed_run_results(result)
    if run_dir:
        print(f"  Detailed results: {run_dir}")
        print(f"    View task details: cat {run_dir}/tasks/<task_id>.json")
    print(f"{'=' * 60}\n")


def apply_optimization(result: OptimizationResult) -> Path | None:
    """Apply optimized SKILL.md and/or tool descriptions.

    Writes back:
    - SKILL.md (if changed)
    - MCP tool docstrings (if tools were included in optimization)

    Args:
        result: OptimizationResult from optimize_skill()

    Returns:
        Path to the updated SKILL.md (or None if tools_only)

    Raises:
        ValueError: If optimization did not improve the skill
    """
    if result.improvement < 0:
        raise ValueError(
            f"Optimization regressed quality ({result.improvement:+.3f}). Refusing to apply. Use --force to override."
        )

    skill_path = None

    # Apply SKILL.md changes
    if result.optimized_content and result.optimized_content != result.original_content:
        skill_path = _find_skill_md(result.skill_name)
        if skill_path:
            skill_path.write_text(result.optimized_content)
            print(f"Applied optimized SKILL.md to {skill_path}")

    # Apply tool description changes
    if result.tool_map and result.components:
        from .tools import parse_gepa_component, write_tool_descriptions

        all_optimized_tools = {}
        for comp_name, comp_text in result.components.items():
            if comp_name.startswith("tools_"):
                parsed = parse_gepa_component(comp_text)
                all_optimized_tools.update(parsed)

        if all_optimized_tools:
            modified = write_tool_descriptions(all_optimized_tools, result.tool_map)
            if modified:
                print(f"Applied optimized tool descriptions to {len(modified)} files:")
                for f in modified:
                    print(f"  {f}")

    print(f"  Quality: {result.original_score:.3f} -> {result.optimized_score:.3f} ({result.improvement:+.3f})")
    print(
        f"  Tokens: {result.original_token_count:,} -> {result.optimized_token_count:,} "
        f"({result.token_reduction_pct:+.1f}%)"
    )

    # Try to update baseline
    try:
        from ..runners.compare import save_baseline

        if result.mlflow_run_id:
            save_baseline(
                skill_name=result.skill_name,
                run_id=result.mlflow_run_id,
                metrics={"optimized_score": result.optimized_score},
                test_count=len(result.val_scores) if result.val_scores else 0,
            )
            print("  Baseline updated.")
    except Exception:
        pass

    return skill_path


def format_cost_estimate(
    train_count: int,
    val_count: int | None,
    preset: str,
    mode: str,
) -> str:
    """Estimate the cost of running optimization.

    Args:
        train_count: Number of training tasks
        val_count: Number of validation tasks (or None)
        preset: Preset name
        mode: "static" or "generative"

    Returns:
        Human-readable cost estimate string
    """
    # Rough estimates based on preset
    max_calls = {"quick": 15, "standard": 50, "thorough": 150}.get(preset, 50)

    # Each metric call runs all scorers on all train tasks
    calls_per_iteration = train_count
    if val_count:
        calls_per_iteration += val_count

    total_scorer_calls = max_calls * calls_per_iteration

    if mode == "static":
        # Static mode: ~$0.001 per scorer call (just deterministic checks)
        est_cost = total_scorer_calls * 0.001
    else:
        # Generative mode: ~$0.01 per call (LLM generation + scoring)
        est_cost = total_scorer_calls * 0.01

    # GEPA reflection calls
    reflection_cost = max_calls * 0.02  # ~$0.02 per reflection

    total = est_cost + reflection_cost

    return (
        f"Estimated cost: ~${total:.2f}\n"
        f"  Scorer calls: {total_scorer_calls:,} x {'$0.001' if mode == 'static' else '$0.01'}\n"
        f"  Reflection calls: {max_calls} x $0.02\n"
        f"  Max iterations: {max_calls}"
    )
