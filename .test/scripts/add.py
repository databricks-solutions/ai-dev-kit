#!/usr/bin/env python3
"""Interactive test case addition for a skill.

Usage:
    python add.py <skill_name> [--prompt "Your prompt here"]

Interactively adds a test case by:
1. Getting a prompt (from CLI arg or interactive input)
2. Running it through the skill
3. Executing code blocks on Databricks (if available)
4. Saving to ground_truth.yaml (if all pass) or candidates.yaml (if any fail)
"""
import sys
import argparse

# Import common utilities
from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="Interactive test case addition")
    parser.add_argument("skill_name", help="Name of skill to add test case for")
    parser.add_argument("--prompt", help="Test prompt (will be requested interactively if not provided)")
    parser.add_argument("--response", help="Skill response (if already generated)")
    parser.add_argument("--no-auto-approve", action="store_true", help="Don't auto-approve on success")
    parser.add_argument(
        "--trace",
        action="store_true",
        default=False,
        help="Evaluate trace after skill invocation (MLflow if configured, else local)",
    )
    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli import interactive

        ctx = create_cli_context()

        # Get prompt interactively if not provided
        prompt = args.prompt
        if not prompt:
            print("Enter the test prompt (press Ctrl+D or Ctrl+Z when done):")
            try:
                prompt = sys.stdin.read().strip()
            except EOFError:
                pass

        if not prompt:
            print("Error: No prompt provided")
            sys.exit(1)

        # Get response if not provided
        response = args.response
        if not response:
            print("\nEnter the skill response (press Ctrl+D or Ctrl+Z when done):")
            try:
                response = sys.stdin.read().strip()
            except EOFError:
                pass

        if not response:
            print("Error: No response provided")
            sys.exit(1)

        result = interactive(
            args.skill_name,
            prompt,
            response,
            ctx,
            auto_approve_on_success=not args.no_auto_approve,
            capture_trace=args.trace,
        )

        # Convert InteractiveResult to dict for JSON output
        result_dict = {
            "success": result.success,
            "test_id": result.test_id,
            "skill_name": result.skill_name,
            "execution_mode": result.execution_mode,
            "total_blocks": result.total_blocks,
            "passed_blocks": result.passed_blocks,
            "saved_to": result.saved_to,
            "auto_approved": result.auto_approved,
            "message": result.message,
        }
        if result.error:
            result_dict["error"] = result.error

        # Include trace results if captured
        if hasattr(result, "trace_source") and result.trace_source:
            result_dict["trace_source"] = result.trace_source
        if hasattr(result, "trace_results") and result.trace_results:
            result_dict["trace_results"] = result.trace_results
        if hasattr(result, "trace_error") and result.trace_error:
            result_dict["trace_error"] = result.trace_error

        sys.exit(print_result(result_dict))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
