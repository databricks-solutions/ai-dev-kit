#!/usr/bin/env python3
"""Save current evaluation results as baseline for regression testing.

Usage:
    python baseline.py <skill_name>

Runs the evaluation and saves metrics as a baseline that can be compared
against in future runs using the regression script.
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="Save evaluation results as baseline")
    parser.add_argument("skill_name", help="Name of skill to baseline")
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import baseline

        ctx = create_cli_context()
        result = baseline(args.skill_name, ctx)
        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
