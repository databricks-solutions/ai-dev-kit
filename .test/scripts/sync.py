#!/usr/bin/env python3
"""Sync YAML test definitions with Unity Catalog (Phase 2).

Usage:
    python sync.py <skill_name> [--direction to_uc|from_uc]

This is a stub for Phase 2 functionality. Currently returns a not-implemented error.

Options:
    --direction   Sync direction: "to_uc" (local->UC) or "from_uc" (UC->local)
                  Default: to_uc
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="Sync YAML with Unity Catalog")
    parser.add_argument("skill_name", help="Name of skill to sync")
    parser.add_argument("--direction", choices=["to_uc", "from_uc"], default="to_uc",
                        help="Sync direction (default: to_uc)")
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import sync

        ctx = create_cli_context()
        result = sync(args.skill_name, ctx, direction=args.direction)
        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
