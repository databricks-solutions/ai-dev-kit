"""Review and apply workflow for optimization results.

Provides human-readable output of optimization results and the ability
to apply the optimized SKILL.md to the repository.
"""

import difflib
from pathlib import Path

from .runner import OptimizationResult
from .evaluator import _find_skill_md


def review_optimization(result: OptimizationResult) -> None:
    """Print optimization summary for human review.

    Shows: score improvement, token reduction, diff of changed sections,
    per-test-case score breakdown, validation set performance.
    """
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

    # Apply hint
    print(f"  To apply: uv run python .test/scripts/optimize.py {result.skill_name} --apply")
    print(f"{'=' * 60}\n")


def apply_optimization(result: OptimizationResult) -> Path:
    """Overwrite the original SKILL.md with the optimized version.

    Also updates baseline via existing baseline workflow if possible.

    Args:
        result: OptimizationResult from optimize_skill()

    Returns:
        Path to the updated SKILL.md

    Raises:
        FileNotFoundError: If original SKILL.md cannot be found
        ValueError: If optimization did not improve the skill
    """
    skill_path = _find_skill_md(result.skill_name)
    if skill_path is None:
        raise FileNotFoundError(f"Cannot find SKILL.md for '{result.skill_name}'")

    if result.optimized_content == result.original_content:
        print(f"No changes to apply for '{result.skill_name}'.")
        return skill_path

    if result.improvement < 0:
        raise ValueError(
            f"Optimization regressed quality ({result.improvement:+.3f}). "
            "Refusing to apply. Use --force to override."
        )

    # Write optimized content
    skill_path.write_text(result.optimized_content)

    print(f"Applied optimized SKILL.md to {skill_path}")
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
