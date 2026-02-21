"""CLI commands module for /skill-test interactive workflow."""

import sys
from .commands import (
    CLIContext,
    InteractiveResult,
    run,
    regression,
    init,
    sync,
    baseline,
    mlflow_eval,
    routing_eval,
    interactive,
    scorers,
    scorers_update,
    review,
    trace_eval,
    list_traces,
    optimize,
)


def main():
    """CLI entry point for skill-test command.

    Usage:
        skill-test <skill-name> [subcommand]

    Subcommands:
        run         - Run evaluation against ground truth (default)
        regression  - Compare current results against baseline
        init        - Initialize test scaffolding for a new skill
        baseline    - Save current results as regression baseline
        mlflow      - Run full MLflow evaluation with LLM judges
        scorers     - List configured scorers for a skill
        review      - Review pending candidates interactively
        trace-eval  - Evaluate trace against skill expectations
        list-traces - List available trace runs from MLflow
        optimize    - Optimize a skill using GEPA
    """
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        print("\nAvailable commands:")
        print("  run         Run evaluation against ground truth (default)")
        print("  regression  Compare current results against baseline")
        print("  init        Initialize test scaffolding for a new skill")
        print("  baseline    Save current results as regression baseline")
        print("  mlflow      Run full MLflow evaluation with LLM judges")
        print("  scorers     List configured scorers for a skill")
        print("  review      Review pending candidates interactively")
        print("  trace-eval  Evaluate trace against skill expectations")
        print("  list-traces List available trace runs from MLflow")
        print("  optimize    Optimize a skill using GEPA")
        sys.exit(0)

    skill_name = args[0]
    subcommand = args[1] if len(args) > 1 else "run"

    # Create context without MCP tools (for CLI usage)
    ctx = CLIContext()

    if subcommand == "run":
        result = run(skill_name, ctx)
    elif subcommand == "regression":
        result = regression(skill_name, ctx)
    elif subcommand == "init":
        result = init(skill_name, ctx)
    elif subcommand == "baseline":
        result = baseline(skill_name, ctx)
    elif subcommand == "mlflow":
        # Special case: _routing mlflow runs routing evaluation
        if skill_name == "_routing":
            result = routing_eval(ctx)
        else:
            result = mlflow_eval(skill_name, ctx)
    elif subcommand == "scorers":
        result = scorers(skill_name, ctx)
    elif subcommand == "review":
        # Parse review-specific arguments
        batch_mode = False
        filter_success = False

        i = 2
        while i < len(args):
            if args[i] in ("--batch", "-b"):
                batch_mode = True
                i += 1
            elif args[i] in ("--filter-success", "-f"):
                filter_success = True
                i += 1
            else:
                i += 1

        result = review(skill_name, ctx, batch=batch_mode, filter_success=filter_success)
    elif subcommand == "trace-eval":
        # Parse trace-eval specific arguments
        trace_path = None
        run_id = None
        trace_dir = None

        i = 2
        while i < len(args):
            if args[i] in ("--trace", "-t") and i + 1 < len(args):
                trace_path = args[i + 1]
                i += 2
            elif args[i] in ("--run-id", "-r") and i + 1 < len(args):
                run_id = args[i + 1]
                i += 2
            elif args[i] in ("--trace-dir", "-d") and i + 1 < len(args):
                trace_dir = args[i + 1]
                i += 2
            else:
                i += 1

        result = trace_eval(skill_name, ctx, trace_path, run_id, trace_dir)
    elif subcommand == "list-traces":
        # Parse list-traces specific arguments
        import os

        experiment = None
        limit = 10

        i = 2
        while i < len(args):
            if args[i] in ("--experiment", "-e") and i + 1 < len(args):
                experiment = args[i + 1]
                i += 2
            elif args[i] in ("--limit", "-l") and i + 1 < len(args):
                limit = int(args[i + 1])
                i += 2
            else:
                i += 1

        # Default from environment variable
        if experiment is None:
            experiment = os.environ.get("MLFLOW_EXPERIMENT_NAME")

        if experiment is None:
            result = {
                "success": False,
                "error": "Must provide --experiment or set MLFLOW_EXPERIMENT_NAME",
            }
        else:
            result = list_traces(experiment, ctx, limit)
    elif subcommand == "optimize":
        # Parse optimize-specific arguments
        opt_preset = "standard"
        opt_mode = "static"
        opt_task_lm = None
        opt_dry_run = False
        opt_apply = False

        i = 2
        while i < len(args):
            if args[i] in ("--preset", "-p") and i + 1 < len(args):
                opt_preset = args[i + 1]
                i += 2
            elif args[i] in ("--mode", "-m") and i + 1 < len(args):
                opt_mode = args[i + 1]
                i += 2
            elif args[i] == "--task-lm" and i + 1 < len(args):
                opt_task_lm = args[i + 1]
                i += 2
            elif args[i] == "--dry-run":
                opt_dry_run = True
                i += 1
            elif args[i] == "--apply":
                opt_apply = True
                i += 1
            else:
                i += 1

        result = optimize(
            skill_name, ctx,
            preset=opt_preset, mode=opt_mode, task_lm=opt_task_lm,
            dry_run=opt_dry_run, apply=opt_apply,
        )
    else:
        print(f"Unknown subcommand: {subcommand}")
        sys.exit(1)

    # Print result
    import json

    print(json.dumps(result, indent=2, default=str))

    # Exit with appropriate code
    sys.exit(0 if result.get("success", False) else 1)


__all__ = [
    "CLIContext",
    "InteractiveResult",
    "run",
    "regression",
    "init",
    "sync",
    "baseline",
    "mlflow_eval",
    "routing_eval",
    "interactive",
    "scorers",
    "scorers_update",
    "review",
    "trace_eval",
    "list_traces",
    "optimize",
    "main",
]
