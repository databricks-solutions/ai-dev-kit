#!/usr/bin/env python3
"""List configured scorers for a skill.

Usage:
    python scorers.py <skill_name>

Shows the enabled deterministic scorers, LLM scorers, and default guidelines
configured in the skill's manifest.yaml.
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="List configured scorers for a skill")
    parser.add_argument("skill_name", help="Name of skill to list scorers for")
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import scorers

        ctx = create_cli_context()
        result = scorers(args.skill_name, ctx)
        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
