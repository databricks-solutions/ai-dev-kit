#!/usr/bin/env python3
"""Compare current evaluation results against baseline.

Usage:
    python regression.py <skill_name> [--baseline-run-id <run_id>]

Runs the evaluation and compares metrics against the saved baseline.
Reports any regressions or improvements.
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="Compare against baseline")
    parser.add_argument("skill_name", help="Name of skill to check for regressions")
    parser.add_argument("--baseline-run-id", help="Specific baseline run ID to compare against")
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import regression

        ctx = create_cli_context()
        result = regression(args.skill_name, ctx, baseline_run_id=args.baseline_run_id)
        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
