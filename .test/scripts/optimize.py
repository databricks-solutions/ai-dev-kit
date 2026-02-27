#!/usr/bin/env python3
"""CLI entry point for GEPA skill optimization.

Usage:
    # Standard workflow: evaluate + optimize a skill
    uv run python .test/scripts/optimize.py databricks-metric-views

    # Quick pass (15 iterations)
    uv run python .test/scripts/optimize.py databricks-metric-views --preset quick

    # Thorough optimization (150 iterations)
    uv run python .test/scripts/optimize.py databricks-metric-views --preset thorough

    # Dry run (show config, dataset info, estimate cost)
    uv run python .test/scripts/optimize.py databricks-metric-views --dry-run

    # Review the saved result then apply (no re-run needed)
    uv run python .test/scripts/optimize.py databricks-metric-views --apply-last

    # Run optimization and immediately apply
    uv run python .test/scripts/optimize.py databricks-metric-views --apply

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
        help="(Deprecated, use --gen-model) LLM model for generative mode",
    )
    parser.add_argument(
        "--gen-model",
        default=None,
        help="LLM model for generative evaluation (default: GEPA_GEN_LM env or "
             "databricks/databricks-claude-sonnet-4-6). The evaluator sends the "
             "candidate SKILL.md to this model and scores the generated response.",
    )
    parser.add_argument(
        "--reflection-lm",
        default=None,
        help="Override GEPA reflection model (default: GEPA_REFLECTION_LM env or databricks/databricks-claude-opus-4-6)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show config and cost estimate without running optimization",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Run optimization and immediately apply the result",
    )
    parser.add_argument(
        "--apply-last",
        action="store_true",
        help="Apply the last saved optimization result without re-running "
             "(reads from .test/skills/<skill>/optimized_SKILL.md)",
    )
    parser.add_argument(
        "--include-tools",
        action="store_true",
        help="Include MCP tool descriptions as additional optimization components",
    )
    parser.add_argument(
        "--tool-modules",
        nargs="*",
        default=None,
        help="Specific tool modules to optimize (e.g., sql compute serving). Default: all.",
    )
    parser.add_argument(
        "--tools-only",
        action="store_true",
        help="Optimize ONLY tool descriptions, not the SKILL.md",
    )
    parser.add_argument(
        "--max-passes",
        type=int,
        default=5,
        help="Maximum optimization passes per component (default: 5). "
             "Each pass re-seeds from the previous best. Stops early if no improvement.",
    )
    parser.add_argument(
        "--max-metric-calls",
        type=int,
        default=None,
        help="Override max metric calls per pass (default: auto-scaled by preset × components, "
             "capped at 300 for non-Opus models). Example: --max-metric-calls 100",
    )
    parser.add_argument(
        "--evaluator",
        choices=["legacy", "skillbench"],
        default="skillbench",
        help="Evaluator type: 'skillbench' (measures skill effectiveness via WITH vs "
             "WITHOUT comparison, default) or 'legacy' (weighted scoring with keyword "
             "matching and token efficiency)",
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=None,
        help="Token budget ceiling. Candidates exceeding this are penalized. "
             "Recommended: 50000. Default: GEPA_TOKEN_BUDGET env or disabled.",
    )
    parser.add_argument(
        "--use-judges",
        action="store_true",
        help="Enable MLflow LLM judges (Correctness + Guidelines) for richer NL "
             "feedback to GEPA's reflection LM. Adds ~10%% judge_quality weight.",
    )
    parser.add_argument(
        "--generate-from",
        type=str,
        default=None,
        metavar="REQUIREMENTS_FILE",
        help="Generate test cases from a requirements file before optimizing. "
             "Each line in the file is a requirement.",
    )
    parser.add_argument(
        "--requirement",
        action="append",
        default=None,
        dest="requirements",
        help="Inline requirement for test case generation (repeatable). "
             "Example: --requirement 'Must explain MEASURE() wrapping'",
    )

    args = parser.parse_args()

    if not args.skill_name and not args.all:
        parser.error("Either provide a skill name or use --all")

    from skill_test.optimize.runner import optimize_skill
    from skill_test.optimize.review import review_optimization, apply_optimization, load_last_result

    # Handle requirements-driven example generation
    if args.generate_from or args.requirements:
        if not args.skill_name:
            parser.error("Test case generation requires a skill name")
        requirements = []
        if args.generate_from:
            req_path = Path(args.generate_from)
            if not req_path.exists():
                print(f"Error: requirements file not found: {req_path}")
                sys.exit(1)
            requirements.extend(
                line.strip() for line in req_path.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            )
        if args.requirements:
            requirements.extend(args.requirements)
        if requirements:
            from generate_examples import run_generation
            gen_model = args.gen_model
            if gen_model is None:
                from skill_test.optimize.config import DEFAULT_GEN_LM
                gen_model = DEFAULT_GEN_LM
            run_generation(
                skill_name=args.skill_name,
                requirements=requirements,
                gen_model=gen_model,
                trust=True,  # append directly since we're about to optimize
            )
            print()

    # Handle --apply-last: load saved result and apply without re-running
    if args.apply_last:
        if not args.skill_name:
            parser.error("--apply-last requires a skill name")
        result = load_last_result(args.skill_name)
        if result is None:
            print(f"No saved optimization found for '{args.skill_name}'.")
            print(f"Run optimization first: uv run python .test/scripts/optimize.py {args.skill_name}")
            sys.exit(1)
        print(f"Applying saved optimization for '{args.skill_name}':")
        print(f"  Score: {result.original_score:.3f} -> {result.optimized_score:.3f} "
              f"({result.improvement:+.3f})")
        print(f"  Tokens: {result.original_token_count:,} -> {result.optimized_token_count:,}")
        try:
            apply_optimization(result)
            sys.exit(0)
        except Exception as e:
            print(f"Error applying: {e}")
            sys.exit(1)

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
                    gen_model=args.gen_model,
                    reflection_lm=args.reflection_lm,
                    include_tools=args.include_tools,
                    tool_modules=args.tool_modules,
                    tools_only=args.tools_only,
                    dry_run=args.dry_run,
                    max_passes=args.max_passes,
                    max_metric_calls=args.max_metric_calls,
                    evaluator_type=args.evaluator,
                    token_budget=args.token_budget,
                    use_judges=args.use_judges,
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
                gen_model=args.gen_model,
                reflection_lm=args.reflection_lm,
                include_tools=args.include_tools,
                tool_modules=args.tool_modules,
                tools_only=args.tools_only,
                dry_run=args.dry_run,
                max_passes=args.max_passes,
                max_metric_calls=args.max_metric_calls,
                evaluator_type=args.evaluator,
                token_budget=args.token_budget,
                use_judges=args.use_judges,
            )
            review_optimization(result)
            if args.apply and not args.dry_run:
                apply_optimization(result)
            sys.exit(0)
        except Exception as e:
            sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
