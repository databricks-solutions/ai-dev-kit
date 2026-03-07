#!/usr/bin/env python3
"""Run MLflow evaluation for a skill.

Usage:
    python mlflow_eval.py <skill_name> [--filter-category <category>] [--run-name <name>] [--timeout <seconds>]

Environment Variables:
    DATABRICKS_CONFIG_PROFILE - Databricks CLI profile (default: "DEFAULT")
    MLFLOW_TRACKING_URI - Set to "databricks" for Databricks MLflow
    MLFLOW_EXPERIMENT_NAME - Experiment path (e.g., "/Users/{user}/skill-test")
    MLFLOW_LLM_JUDGE_TIMEOUT - Timeout in seconds for LLM judge evaluation (default: 120)
"""
import os
import sys
import signal
import argparse

# Close stdin and disable tqdm progress bars when run non-interactively
# This fixes hanging issues with tqdm/MLflow progress bars in background tasks
if not sys.stdin.isatty():
    try:
        sys.stdin.close()
        sys.stdin = open(os.devnull, 'r')
    except Exception:
        pass
    # Disable tqdm progress bars
    os.environ.setdefault("TQDM_DISABLE", "1")

# Import common utilities
from _common import setup_path, print_result, handle_error


class TimeoutException(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutException("MLflow evaluation timed out")


def main():
    parser = argparse.ArgumentParser(description="Run MLflow evaluation for a skill")
    parser.add_argument("skill_name", help="Name of skill to evaluate")
    parser.add_argument("--filter-category", help="Filter by test category")
    parser.add_argument("--run-name", help="Custom MLflow run name")
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Timeout in seconds for evaluation (default: 120)",
    )
    args = parser.parse_args()

    setup_path()

    # Set up signal-based timeout (Unix only)
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(args.timeout)
    else:
        # Windows: SIGALRM not available - no timeout enforcement
        print("WARNING: Timeout not supported on Windows - test may run indefinitely", file=sys.stderr)

    try:
        from skill_test.runners import evaluate_skill

        result = evaluate_skill(
            args.skill_name,
            filter_category=args.filter_category,
            run_name=args.run_name,
        )

        # Cancel the alarm if we succeeded
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)

        # Convert to standard result format
        if result.get("run_id"):
            result["success"] = True
        else:
            result["success"] = False

        sys.exit(print_result(result))

    except TimeoutException as e:
        result = {
            "success": False,
            "skill_name": args.skill_name,
            "error": f"Evaluation timed out after {args.timeout} seconds. This may indicate LLM judge endpoint issues.",
            "error_type": "timeout",
        }
        sys.exit(print_result(result))

    except Exception as e:
        # Cancel alarm on any exception
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
