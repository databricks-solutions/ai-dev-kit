#!/usr/bin/env python3
"""CLI entry point for GEPA skill optimization.

Usage:
    # Standard workflow: evaluate + optimize a skill
    uv run python .test/scripts/optimize.py databricks-metric-views

    # Quick pass (15 iterations)
    uv run python .test/scripts/optimize.py databricks-metric-views --preset quick

    # Thorough optimization (150 iterations)
    uv run python .test/scripts/optimize.py databricks-metric-views --preset thorough

    # Generative mode (generates fresh responses, more expensive)
    uv run python .test/scripts/optimize.py databricks-metric-views --mode generative

    # Apply the optimized result
    uv run python .test/scripts/optimize.py databricks-metric-views --apply

    # Dry run (show config, dataset info, estimate cost)
    uv run python .test/scripts/optimize.py databricks-metric-views --dry-run

    # Optimize all skills that have ground_truth.yaml test cases
    uv run python .test/scripts/optimize.py --all
"""

import argparse
import sys
from pathlib import Path

# Setup path using shared utilities
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import setup_path, handle_error, print_result

setup_path()


def main():
    parser = argparse.ArgumentParser(
        description="Optimize Databricks skills using GEPA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "skill_name",
        nargs="?",
        help="Name of the skill to optimize (e.g., databricks-model-serving)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Optimize all skills that have ground_truth.yaml",
    )
    parser.add_argument(
        "--preset", "-p",
        choices=["quick", "standard", "thorough"],
        default="standard",
        help="GEPA optimization preset (default: standard)",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["static", "generative"],
        default="static",
        help="Evaluation mode (default: static)",
    )
    parser.add_argument(
        "--task-lm",
        default=None,
        help="LLM model for generative mode (e.g., openai/gpt-4o)",
    )
    parser.add_argument(
        "--reflection-lm",
        default=None,
        help="Override GEPA reflection model (default: GEPA_REFLECTION_LM env or databricks/databricks-gpt-5-2)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show config and cost estimate without running optimization",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the optimized SKILL.md (overwrites original)",
    )

    args = parser.parse_args()

    if not args.skill_name and not args.all:
        parser.error("Either provide a skill name or use --all")

    from skill_test.optimize.runner import optimize_skill
    from skill_test.optimize.review import review_optimization, apply_optimization

    if args.all:
        # Find all skills with ground_truth.yaml
        skills_dir = Path(".test/skills")
        skill_names = [
            d.name
            for d in sorted(skills_dir.iterdir())
            if d.is_dir() and (d / "ground_truth.yaml").exists() and not d.name.startswith("_")
        ]
        print(f"Found {len(skill_names)} skills to optimize: {', '.join(skill_names)}\n")

        results = []
        for name in skill_names:
            print(f"\n{'=' * 60}")
            print(f"  Optimizing: {name}")
            print(f"{'=' * 60}")
            try:
                result = optimize_skill(
                    skill_name=name,
                    mode=args.mode,
                    preset=args.preset,
                    task_lm=args.task_lm,
                    reflection_lm=args.reflection_lm,
                    dry_run=args.dry_run,
                )
                review_optimization(result)
                if args.apply and not args.dry_run:
                    apply_optimization(result)
                results.append({"skill": name, "success": True, "improvement": result.improvement})
            except Exception as e:
                print(f"  ERROR: {e}")
                results.append({"skill": name, "success": False, "error": str(e)})

        # Summary
        print(f"\n{'=' * 60}")
        print("  Summary")
        print(f"{'=' * 60}")
        for r in results:
            status = "OK" if r["success"] else "FAIL"
            detail = f"+{r['improvement']:.3f}" if r["success"] else r["error"]
            print(f"  [{status}] {r['skill']}: {detail}")

        sys.exit(0 if all(r["success"] for r in results) else 1)

    else:
        try:
            result = optimize_skill(
                skill_name=args.skill_name,
                mode=args.mode,
                preset=args.preset,
                task_lm=args.task_lm,
                reflection_lm=args.reflection_lm,
                dry_run=args.dry_run,
            )
            review_optimization(result)
            if args.apply and not args.dry_run:
                apply_optimization(result)
            sys.exit(0)
        except Exception as e:
            sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
