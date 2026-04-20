#!/usr/bin/env python3
"""
Test runner for databricks-skills.

Runs unit tests (mocked, no Databricks connection required) and integration tests
(require Databricks connection). Generates HTML and terminal reports.

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py --unit       # Run only unit tests
    python run_tests.py --integration # Run only integration tests
    python run_tests.py -v           # Verbose output
    python run_tests.py --html       # Generate HTML report
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Run databricks-skills tests with reports"
    )
    parser.add_argument(
        "--unit",
        action="store_true",
        help="Run only unit tests (mocked, no Databricks connection)",
    )
    parser.add_argument(
        "--integration",
        action="store_true",
        help="Run only integration tests (requires Databricks connection)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML report",
    )
    parser.add_argument(
        "--xml",
        action="store_true",
        help="Generate JUnit XML report for CI",
    )
    parser.add_argument(
        "-k",
        metavar="EXPRESSION",
        help="Only run tests matching the given expression",
    )

    args = parser.parse_args()

    # Determine test directory
    tests_dir = Path(__file__).parent
    skills_dir = tests_dir.parent
    repo_root = skills_dir.parent

    # Results directory for reports
    results_dir = tests_dir / ".test-results"
    results_dir.mkdir(exist_ok=True)

    # Build pytest command
    pytest_args = [
        sys.executable,
        "-m", "pytest",
        str(tests_dir),
    ]

    # Filter by test type
    if args.unit and not args.integration:
        # Unit tests: exclude integration marker
        pytest_args.extend(["-m", "not integration"])
    elif args.integration and not args.unit:
        # Integration tests only
        pytest_args.extend(["-m", "integration"])
    # If both or neither specified, run all tests

    # Add verbosity
    if args.verbose:
        pytest_args.append("-v")
    else:
        pytest_args.append("-q")

    # Add expression filter
    if args.k:
        pytest_args.extend(["-k", args.k])

    # Add HTML report
    if args.html:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_path = results_dir / f"report_{timestamp}.html"
        pytest_args.extend(["--html", str(html_path), "--self-contained-html"])
        print(f"HTML report will be saved to: {html_path}")

    # Add XML report
    if args.xml:
        xml_path = results_dir / "junit.xml"
        pytest_args.extend(["--junitxml", str(xml_path)])
        print(f"JUnit XML report will be saved to: {xml_path}")

    # Add color output
    pytest_args.append("--color=yes")

    # Show captured output on failure
    pytest_args.append("-rA")

    # Set PYTHONPATH to include skills directory
    env = os.environ.copy()
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{skills_dir}:{repo_root / 'databricks-tools-core'}:{pythonpath}"

    # Print test configuration
    print("=" * 60)
    print("databricks-skills Test Runner")
    print("=" * 60)
    print(f"Tests directory: {tests_dir}")
    print(f"Results directory: {results_dir}")
    test_type = "all"
    if args.unit and not args.integration:
        test_type = "unit only"
    elif args.integration and not args.unit:
        test_type = "integration only"
    print(f"Test type: {test_type}")
    print("=" * 60)
    print()

    # Run pytest
    result = subprocess.run(pytest_args, env=env)

    # Print summary
    print()
    print("=" * 60)
    if result.returncode == 0:
        print("All tests PASSED")
    else:
        print(f"Tests FAILED (exit code: {result.returncode})")

    if args.html:
        print(f"HTML report: {html_path}")
    if args.xml:
        print(f"JUnit XML: {xml_path}")
    print("=" * 60)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
