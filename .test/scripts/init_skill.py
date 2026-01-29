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
import json
import argparse
from pathlib import Path


def find_repo_root() -> Path:
    """Find repo root by looking for .test/src/ directory."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".test" / "src").exists():
            return current
        if (current / "src" / "skill_test").exists() and current.name == ".test":
            return current.parent
        current = current.parent
    raise RuntimeError("Could not find repo root with .test/src/")


def main():
    parser = argparse.ArgumentParser(description="Initialize test scaffolding for a skill")
    parser.add_argument("skill_name", help="Name of skill to initialize")
    args = parser.parse_args()

    # Add skill_test to Python path
    repo_root = find_repo_root()
    sys.path.insert(0, str(repo_root / ".test" / "src"))

    try:
        from skill_test.cli import CLIContext, init

        # Create context
        ctx = CLIContext(
            base_path=repo_root / ".test" / "skills"
        )

        results = init(args.skill_name, ctx)
        print(json.dumps(results, indent=2, default=str))
        sys.exit(0 if results.get("success", False) else 1)

    except Exception as e:
        print(json.dumps({
            "error": str(e),
            "success": False,
            "skill_name": args.skill_name
        }, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
