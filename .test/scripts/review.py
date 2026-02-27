#!/usr/bin/env python3
"""Review pending candidates for a skill.

Usage:
    python review.py <skill_name> [--batch] [--filter-success]

Reviews candidates in candidates.yaml interactively, allowing you to
approve, reject, skip, or edit each candidate. Approved candidates
are promoted to ground_truth.yaml.

Options:
    --batch, -b          Batch approve all pending candidates
    --filter-success, -f Only approve candidates with execution_success=True
                         (only used with --batch)
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(
        description="Review pending candidates for a skill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Interactive review
    python review.py databricks-spark-declarative-pipelines

    # Batch approve all pending candidates
    python review.py databricks-spark-declarative-pipelines --batch

    # Batch approve only successful candidates
    python review.py databricks-spark-declarative-pipelines --batch --filter-success
"""
    )
    parser.add_argument("skill_name", help="Name of skill to review candidates for")
    parser.add_argument(
        "--batch", "-b",
        action="store_true",
        help="Batch approve all pending candidates without prompts"
    )
    parser.add_argument(
        "--filter-success", "-f",
        action="store_true",
        help="Only approve candidates with execution_success=True (use with --batch)"
    )
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import review

        ctx = create_cli_context()

        result = review(
            args.skill_name,
            ctx,
            batch=args.batch,
            filter_success=args.filter_success
        )

        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
