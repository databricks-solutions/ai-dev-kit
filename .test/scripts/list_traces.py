#!/usr/bin/env python3
"""List available traces from MLflow or local.

Usage:
    python list_traces.py <skill_name> [--limit <n>] [--local]

Examples:
    # List MLflow traces (if configured) or local traces
    python list_traces.py databricks-spark-declarative-pipelines

    # Force local trace listing
    python list_traces.py databricks-spark-declarative-pipelines --local

    # Limit results
    python list_traces.py databricks-spark-declarative-pipelines --limit 5

    # Custom MLflow experiment
    python list_traces.py databricks-spark-declarative-pipelines --experiment "/Users/user@example.com/traces"

Environment Variables:
    DATABRICKS_HOST - Databricks workspace URL
    DATABRICKS_TOKEN - Personal access token
"""
import sys
import argparse

from _common import setup_path, create_cli_context, print_result, handle_error


def main():
    parser = argparse.ArgumentParser(description="List available traces")
    parser.add_argument(
        "skill_name", help="Skill name (used for default experiment path)"
    )
    parser.add_argument("--experiment", help="Custom MLflow experiment path")
    parser.add_argument("--limit", type=int, default=10, help="Max traces to return")
    parser.add_argument("--local", action="store_true", help="List only local traces")

    args = parser.parse_args()

    setup_path()

    try:
        from skill_test.trace.source import check_autolog_status, list_local_traces

        status = check_autolog_status()

        # If local only or MLflow not configured, list local traces
        if args.local or not status.enabled:
            result = list_local_traces(args.limit)
            if not status.enabled and not args.local:
                result["note"] = "MLflow not configured, showing local traces"
            sys.exit(print_result(result))

        # MLflow is configured, list from experiment
        from skill_test.cli.commands import list_traces

        experiment_name = (
            args.experiment or f"/Shared/{args.skill_name}-skill-test-traces"
        )

        ctx = create_cli_context()
        result = list_traces(
            experiment_name=experiment_name,
            ctx=ctx,
            limit=args.limit,
        )
        result["source"] = "mlflow"

        sys.exit(print_result(result))

    except Exception as e:
        sys.exit(handle_error(e, "list-traces"))


if __name__ == "__main__":
    main()
