#!/usr/bin/env python3
"""Update scorer configuration for a skill.

Usage:
    python scorers_update.py <skill_name> [options]

Options:
    --add-scorer <name>       Add a scorer to the enabled list (can be used multiple times)
    --remove-scorer <name>    Remove a scorer (can be used multiple times)
    --add-guideline <text>    Add a default guideline (can be used multiple times)
    --remove-guideline <text> Remove a guideline (can be used multiple times)
    --set-guidelines <text>   Replace all guidelines (comma-separated)

Examples:
    python scorers_update.py my-skill --add-scorer pattern_adherence
    python scorers_update.py my-skill --add-guideline "Must use CLUSTER BY for large tables"
    python scorers_update.py my-skill --remove-scorer sql_syntax --add-scorer custom_validator
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="Update scorer configuration for a skill")
    parser.add_argument("skill_name", help="Name of skill to update")
    parser.add_argument("--add-scorer", action="append", dest="add_scorers",
                        help="Add scorer (can be repeated)")
    parser.add_argument("--remove-scorer", action="append", dest="remove_scorers",
                        help="Remove scorer (can be repeated)")
    parser.add_argument("--add-guideline", action="append", dest="add_guidelines",
                        help="Add guideline (can be repeated)")
    parser.add_argument("--remove-guideline", action="append", dest="remove_guidelines",
                        help="Remove guideline (can be repeated)")
    parser.add_argument("--set-guidelines",
                        help="Replace all guidelines (comma-separated)")
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import scorers_update

        ctx = create_cli_context()

        # Parse set-guidelines if provided
        set_guidelines = None
        if args.set_guidelines:
            set_guidelines = [g.strip() for g in args.set_guidelines.split(",")]

        result = scorers_update(
            args.skill_name,
            ctx,
            add_scorers=args.add_scorers,
            remove_scorers=args.remove_scorers,
            add_guidelines=args.add_guidelines,
            remove_guidelines=args.remove_guidelines,
            set_guidelines=set_guidelines,
        )
        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
