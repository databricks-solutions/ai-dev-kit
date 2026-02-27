"""Review and apply workflow for optimization results.

Provides human-readable output of optimization results and the ability
to apply the optimized SKILL.md to the repository.

After each optimization run, results are saved to:
    .test/skills/<skill-name>/optimized_SKILL.md   — the optimized content
    .test/skills/<skill-name>/last_optimization.md  — summary with scores and diff

Use ``--apply-last`` to apply a saved result without re-running optimization.
"""

import difflib
import json
from datetime import datetime, timezone
from pathlib import Path

from .runner import OptimizationResult
from .evaluator import _find_skill_md


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
    if result.improvement <= 0 and result.original_content == result.optimized_content:
        return None, None

    results_dir = _get_results_dir(result.skill_name)

    optimized_path = None
    metadata_path = None

    # Write the optimized SKILL.md
    if result.optimized_content and result.optimized_content != result.original_content:
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
        tool_components = {
            k: v for k, v in result.components.items() if k.startswith("tools_")
        }
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


def _review_skillbench(result: OptimizationResult) -> None:
    """Print SkillBench-style effectiveness metrics."""
    print(f"\n{'=' * 60}")
    print(f"  Optimization Results: {result.skill_name} (skillbench)")
    print(f"{'=' * 60}")

    # Aggregate effectiveness metrics from side_info
    si = result.skillbench_side_info or {}

    # Compute aggregate pass rates from per-task scores
    task_count = 0
    sum_with = 0.0
    sum_without = 0.0
    sum_eff = 0.0
    per_task_lines: list[str] = []

    for task_id in sorted(si.keys()):
        info = si[task_id]
        scores = info.get("scores", {})
        pw = scores.get("pass_rate_with", 0.0)
        pwo = scores.get("pass_rate_without", 0.0)
        eff = scores.get("skill_effectiveness", 0.0)
        sum_with += pw
        sum_without += pwo
        sum_eff += eff
        task_count += 1

        # Build per-task notes from the new Error key
        error = info.get("Error", "")
        notes = []
        if "NEEDS_SKILL" in error:
            # Extract assertion names from Error lines
            failing = [
                line.split(":", 1)[1].strip().split(" — ")[0]
                for line in error.split("\n")
                if line.startswith("NEEDS_SKILL")
            ]
            notes.append(f"NEEDS: {', '.join(failing[:3])}")
        if "REGRESSION" in error:
            reg_count = error.count("REGRESSION")
            notes.append(f"REGRESSION x{reg_count}")
        if not notes:
            notes.append("OK/NEUTRAL")
        note_str = f"  [{'; '.join(notes)}]"
        per_task_lines.append(
            f"    {task_id:<30s} WITH {pw:.2f}  WITHOUT {pwo:.2f}  "
            f"delta {eff:+.2f}{note_str}"
        )

    # Aggregate rates
    if task_count > 0:
        agg_with = sum_with / task_count
        agg_without = sum_without / task_count
        agg_eff = sum_eff / task_count
    else:
        agg_with = agg_without = agg_eff = 0.0

    # Score summary
    improvement_sign = "+" if result.improvement >= 0 else ""
    print(f"  Score:              {result.original_score:.3f} -> {result.optimized_score:.3f} "
          f"({improvement_sign}{result.improvement:.3f})")
    print(f"  Skill Effectiveness: {agg_eff:.2f}")
    print(f"  Pass Rate (with):    {agg_with:.2f}")
    print(f"  Pass Rate (without): {agg_without:.2f} (baseline)")

    # Token counts
    reduction_sign = "+" if result.token_reduction_pct >= 0 else ""
    print(f"  Tokens:   {result.original_token_count:,} -> {result.optimized_token_count:,} "
          f"({reduction_sign}{result.token_reduction_pct:.1f}%)")

    # GEPA iterations
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
        diff_lines = list(difflib.unified_diff(
            result.original_content.splitlines(keepends=True),
            result.optimized_content.splitlines(keepends=True),
            fromfile="original SKILL.md",
            tofile="optimized SKILL.md",
            n=2,
        ))
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
        print(f"  No improvement found -- nothing saved.")
    print(f"{'=' * 60}\n")


def review_optimization(result: OptimizationResult) -> None:
    """Print optimization summary for human review.

    Automatically saves the result to disk so it can be applied later
    with ``--apply-last`` without re-running optimization.

    Shows: score improvement, token reduction, diff of changed sections,
    per-test-case score breakdown, validation set performance.

    Delegates to ``_review_skillbench()`` when ``evaluator_type == "skillbench"``.
    """
    if getattr(result, "evaluator_type", "legacy") == "skillbench":
        return _review_skillbench(result)

    print(f"\n{'=' * 60}")
    print(f"  Optimization Results: {result.skill_name}")
    print(f"{'=' * 60}")

    # Quality scores
    improvement_sign = "+" if result.improvement >= 0 else ""
    print(f"  Quality:  {result.original_score:.3f} -> {result.optimized_score:.3f} "
          f"({improvement_sign}{result.improvement:.3f})")

    # Token counts
    reduction_sign = "+" if result.token_reduction_pct >= 0 else ""
    print(f"  Tokens:   {result.original_token_count:,} -> {result.optimized_token_count:,} "
          f"({reduction_sign}{result.token_reduction_pct:.1f}%)")

    # Validation scores
    if result.val_scores:
        avg_val = sum(result.val_scores.values()) / len(result.val_scores)
        print(f"  Validation: avg={avg_val:.3f} ({len(result.val_scores)} cases)")

    # GEPA iterations
    if result.gepa_result and hasattr(result.gepa_result, "iterations"):
        print(f"  Iterations: {result.gepa_result.iterations}")

    # MLflow run
    if result.mlflow_run_id:
        print(f"  MLflow run: {result.mlflow_run_id}")

    print()

    # Diff summary
    if result.diff_summary and result.diff_summary != "No changes":
        print("  Changes:")
        for line in result.diff_summary.split("\n"):
            print(f"    {line}")
        print()

    # Detailed diff (first 50 lines)
    if result.original_content != result.optimized_content:
        diff_lines = list(difflib.unified_diff(
            result.original_content.splitlines(keepends=True),
            result.optimized_content.splitlines(keepends=True),
            fromfile="original SKILL.md",
            tofile="optimized SKILL.md",
            n=2,
        ))
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
        print(f"  No improvement found — nothing saved.")
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
            f"Optimization regressed quality ({result.improvement:+.3f}). "
            "Refusing to apply. Use --force to override."
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

    print(f"  Quality: {result.original_score:.3f} -> {result.optimized_score:.3f} "
          f"({result.improvement:+.3f})")
    print(f"  Tokens: {result.original_token_count:,} -> {result.optimized_token_count:,} "
          f"({result.token_reduction_pct:+.1f}%)")

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
            print(f"  Baseline updated.")
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
