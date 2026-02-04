#!/usr/bin/env python3
"""Run evaluation against ground truth for a skill.

Usage:
    python run_eval.py <skill_name> [--test-ids <id1> <id2> ...]

This executes code blocks from ground truth test cases and reports pass/fail results.
Without MCP tools, it runs in local mode (syntax validation only).
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="Run evaluation against ground truth")
    parser.add_argument("skill_name", help="Name of skill to evaluate")
    parser.add_argument("--test-ids", nargs="+", help="Specific test IDs to run")
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import run

        ctx = create_cli_context()
        result = run(args.skill_name, ctx, test_ids=args.test_ids)
        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
