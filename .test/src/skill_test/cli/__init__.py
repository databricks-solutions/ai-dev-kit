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
    interactive,
    scorers,
    scorers_update,
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
        result = mlflow_eval(skill_name, ctx)
    elif subcommand == "scorers":
        result = scorers(skill_name, ctx)
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
    "interactive",
    "scorers",
    "scorers_update",
    "main",
]
