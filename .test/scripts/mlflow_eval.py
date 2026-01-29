#!/usr/bin/env python3
"""Run MLflow evaluation for a skill.

Usage:
    python mlflow_eval.py <skill_name> [--filter-category <category>]

Environment Variables:
    DATABRICKS_CONFIG_PROFILE - Databricks CLI profile (default: "DEFAULT")
    MLFLOW_TRACKING_URI - Set to "databricks" for Databricks MLflow
    MLFLOW_EXPERIMENT_NAME - Experiment path (e.g., "/Users/{user}/skill-test")
"""
import sys
import json
import argparse
from pathlib import Path


def find_repo_root() -> Path:
    """Find repo root by looking for .test/src/ directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".test" / "src").exists():
            return current
        # Also check if we're inside .test/
        if (current / "src" / "skill_test").exists() and current.name == ".test":
            return current.parent
        current = current.parent
    raise RuntimeError("Could not find repo root with .test/src/")


def main():
    parser = argparse.ArgumentParser(description="Run MLflow evaluation for a skill")
    parser.add_argument("skill_name", help="Name of skill to evaluate")
    parser.add_argument("--filter-category", help="Filter by test category")
    parser.add_argument("--run-name", help="Custom MLflow run name")
    args = parser.parse_args()

    # Add skill_test to Python path
    repo_root = find_repo_root()
    sys.path.insert(0, str(repo_root / ".test" / "src"))

    try:
        from skill_test.runners import evaluate_skill

        results = evaluate_skill(
            args.skill_name,
            filter_category=args.filter_category,
            run_name=args.run_name,
        )
        print(json.dumps(results, indent=2, default=str))
        sys.exit(0 if results.get("run_id") else 1)

    except Exception as e:
        print(json.dumps({
            "error": str(e),
            "success": False,
            "skill_name": args.skill_name
        }, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
