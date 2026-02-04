#!/usr/bin/env python3
"""Initialize test scaffolding for a new skill.

Usage:
    python init_skill.py <skill_name>

Creates the directory structure and template files for testing a skill:
- ground_truth.yaml (test case definitions)
- candidates.yaml (pending test cases)
- manifest.yaml (scorer configuration)
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="Initialize test scaffolding for a skill")
    parser.add_argument("skill_name", help="Name of skill to initialize")
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import init

        ctx = create_cli_context()
        result = init(args.skill_name, ctx)
        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
