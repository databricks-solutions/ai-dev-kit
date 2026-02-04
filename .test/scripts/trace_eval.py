#!/usr/bin/env python3
"""Evaluate traces against skill expectations.

Usage:
    python trace_eval.py <skill_name> [--trace <path>] [--run-id <id>] [--trace-id <id>] [--trace-dir <dir>] [--local]

Examples:
    # Auto-detect best source (MLflow if configured, else local)
    python trace_eval.py spark-declarative-pipelines

    # Force local trace evaluation
    python trace_eval.py spark-declarative-pipelines --local

    # Evaluate from MLflow run ID (from mlflow.search_runs)
    python trace_eval.py spark-declarative-pipelines --run-id abc123def456

    # Evaluate from MLflow trace ID (from mlflow.get_trace)
    python trace_eval.py spark-declarative-pipelines --trace-id tr-d416fccdab46e2dea6bad1d0bd8aaaa8

    # Evaluate a specific local trace file
    python trace_eval.py spark-declarative-pipelines --trace ~/.claude/projects/.../session.jsonl

    # Evaluate all traces in a directory
    python trace_eval.py spark-declarative-pipelines --trace-dir /path/to/traces/

Environment Variables:
    DATABRICKS_HOST - Databricks workspace URL
    DATABRICKS_TOKEN - Personal access token
"""
import sys
import argparse

from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate traces against skill expectations"
    )
    parser.add_argument("skill_name", help="Name of skill to evaluate against")

    # Trace source options (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument("--trace", help="Path to local JSONL trace file")
    source_group.add_argument("--run-id", help="MLflow run ID containing the trace")
    source_group.add_argument("--trace-id", help="MLflow trace ID (e.g., tr-...)")
    source_group.add_argument("--trace-dir", help="Directory containing trace files")
    source_group.add_argument(
        "--local",
        action="store_true",
        help="Force use of local session trace (skip MLflow)",
    )
    source_group.add_argument(
        "--auto",
        action="store_true",
        default=True,
        help="Auto-detect best source (default)",
    )

    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.cli.commands import trace_eval
        from skill_test.trace.source import (
            check_autolog_status,
            get_setup_instructions,
            get_current_session_trace_path,
            get_trace_from_best_source,
        )

        # Show status info if auto-detecting
        if not args.trace and not args.run_id and not args.trace_id and not args.trace_dir:
            status = check_autolog_status()
            if status.enabled:
                print(
                    f"MLflow autolog: enabled (experiment: {status.experiment_name})",
                    file=sys.stderr,
                )
            else:
                print(
                    "MLflow autolog: not configured (using local fallback)",
                    file=sys.stderr,
                )
                if not args.local:
                    print(
                        get_setup_instructions(args.skill_name),
                        file=sys.stderr,
                    )

        ctx = create_cli_context()

        # Determine trace source
        trace_path = args.trace
        run_id = args.run_id
        trace_id = args.trace_id
        trace_dir = args.trace_dir

        if args.local:
            # Force local - get current session trace
            local_path = get_current_session_trace_path()
            if local_path:
                trace_path = str(local_path)
            else:
                print(
                    '{"success": false, "error": "No local session trace found"}',
                )
                sys.exit(1)
        elif not any([args.trace, args.run_id, args.trace_id, args.trace_dir]):
            # Auto mode - use best available source
            try:
                metrics, source = get_trace_from_best_source(args.skill_name)

                # For auto mode, route to the right source
                if source.startswith("mlflow:"):
                    run_id = source.split(":", 1)[1]
                else:
                    trace_path = source.split(":", 1)[1]
            except FileNotFoundError as e:
                print(
                    f'{{"success": false, "error": "{e}"}}',
                )
                sys.exit(1)

        result = trace_eval(
            skill_name=args.skill_name,
            ctx=ctx,
            trace_path=trace_path,
            run_id=run_id,
            trace_id=trace_id,
            trace_dir=trace_dir,
        )

        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, args.skill_name))


if __name__ == "__main__":
    main()
