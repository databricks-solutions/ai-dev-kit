#!/usr/bin/env python3
"""
Integration Test Runner

Run all integration tests in parallel with detailed reporting.

Usage:
    python tests/integration/run_tests.py              # Run all tests (excluding slow)
    python tests/integration/run_tests.py --all        # Run all tests including slow
    python tests/integration/run_tests.py --report     # Show report from latest run
    python tests/integration/run_tests.py --status     # Check status of ongoing/recent runs
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ANSI color codes
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


@dataclass
class TestResult:
    """Result from a single test folder."""
    folder: str
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    duration: float = 0.0
    log_file: str = ""
    error_details: list = field(default_factory=list)
    status: str = "unknown"  # unknown, running, completed

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.skipped + self.errors

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0


def format_timestamp(ts_str: str) -> str:
    """Format a timestamp string (YYYYMMDD_HHMMSS or ISO) into human-readable format."""
    try:
        # Try ISO format first
        if "T" in ts_str:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            # Try YYYYMMDD_HHMMSS format
            dt = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts_str


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"


def get_test_folders() -> list[str]:
    """Get all test folders in the integration directory."""
    integration_dir = Path(__file__).parent
    folders = []
    for item in sorted(integration_dir.iterdir()):
        if item.is_dir() and not item.name.startswith(("__", ".")):
            # Check if it contains test files
            if list(item.glob("test_*.py")):
                folders.append(item.name)
    return folders


def get_results_dir() -> Path:
    """Get the results directory path."""
    return Path(__file__).parent / ".test-results"


def run_test_folder(
    folder: str,
    output_dir: Path,
    include_slow: bool = False,
) -> TestResult:
    """Run tests for a single folder and return results."""
    result = TestResult(folder=folder, status="running")
    log_file = output_dir / f"{folder}.txt"
    result.log_file = str(log_file)

    # Write initial status
    log_file.write_text(f"[RUNNING] Started at {datetime.now().isoformat()}\n")

    # Build pytest command
    test_path = Path(__file__).parent / folder
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_path),
        "-v",
        "-s",  # Stream output to see real-time logs
        "--tb=short",
        "-m", "integration" if not include_slow else "integration or slow",
    ]

    start_time = time.time()

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1200,  # 20 minute timeout per folder
        )
        output = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        output = f"TIMEOUT: Tests in {folder} exceeded 10 minute limit"
        result.errors = 1
    except Exception as e:
        output = f"ERROR: {e}"
        result.errors = 1

    result.duration = time.time() - start_time
    result.status = "completed"

    # Save log file
    log_file.write_text(output)

    # Parse results from output
    result = parse_pytest_output(output, result)

    return result


def parse_pytest_output(output: str, result: TestResult) -> TestResult:
    """Parse pytest output to extract test counts and errors."""
    # Look for summary line like "5 passed, 2 failed, 1 skipped in 10.5s"
    summary_pattern = r"(\d+)\s+passed"
    failed_pattern = r"(\d+)\s+failed"
    skipped_pattern = r"(\d+)\s+skipped"
    error_pattern = r"(\d+)\s+error"

    if match := re.search(summary_pattern, output):
        result.passed = int(match.group(1))
    if match := re.search(failed_pattern, output):
        result.failed = int(match.group(1))
    if match := re.search(skipped_pattern, output):
        result.skipped = int(match.group(1))
    if match := re.search(error_pattern, output):
        result.errors = int(match.group(1))

    # Extract failure details
    if result.failed > 0 or result.errors > 0:
        # Find FAILURES section
        failures_start = output.find("=== FAILURES ===")
        if failures_start == -1:
            failures_start = output.find("FAILED")

        if failures_start != -1:
            # Extract test names and short error messages
            failed_tests = re.findall(r"FAILED\s+([\w/:.]+)", output)
            for test in failed_tests[:5]:  # Limit to 5 failures
                result.error_details.append(test)

            # Also capture assertion errors
            assertions = re.findall(r"AssertionError:\s*(.+?)(?:\n|$)", output)
            for assertion in assertions[:3]:
                result.error_details.append(f"  -> {assertion[:100]}")

    return result


def parse_log_file_status(log_file: Path) -> tuple[str, Optional[TestResult]]:
    """Parse a log file to determine if test is running or completed."""
    if not log_file.exists():
        return "pending", None

    content = log_file.read_text()

    # Check if still running
    if content.startswith("[RUNNING]"):
        return "running", None

    # Check for timeout (test was killed due to exceeding time limit)
    if "TIMEOUT:" in content:
        result = TestResult(folder=log_file.stem, log_file=str(log_file))
        result.errors = 1
        result.status = "timeout"
        result.error_details = ["Test timed out"]
        return "timeout", result

    # Parse completed results
    result = TestResult(folder=log_file.stem, log_file=str(log_file))
    result = parse_pytest_output(content, result)

    if result.total > 0 or "passed" in content.lower() or "failed" in content.lower():
        result.status = "completed"
        return "completed", result

    return "running", None


def print_progress(folder: str, status: str, duration: float = 0):
    """Print progress update."""
    if status == "running":
        print(f"  {Colors.CYAN}[RUNNING]{Colors.RESET} {folder}...")
    elif status == "done":
        print(f"  {Colors.GREEN}[DONE]{Colors.RESET} {folder} ({format_duration(duration)})")
    elif status == "failed":
        print(f"  {Colors.RED}[FAILED]{Colors.RESET} {folder} ({format_duration(duration)})")


def print_header(text: str):
    """Print a section header."""
    width = 70
    print()
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * width}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(width)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'=' * width}{Colors.RESET}")
    print()


def print_summary(results: list[TestResult], total_duration: float, output_dir: Path, run_timestamp: str = None):
    """Print a detailed summary of test results."""
    print_header("TEST RESULTS SUMMARY")

    # Show run timestamp
    if run_timestamp:
        print(f"  {Colors.BOLD}Run Date:{Colors.RESET} {format_timestamp(run_timestamp)}")
        print()

    # Calculate totals
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_skipped = sum(r.skipped for r in results)
    total_errors = sum(r.errors for r in results)
    total_tests = total_passed + total_failed + total_skipped + total_errors

    # Overall status
    all_passed = total_failed == 0 and total_errors == 0
    status_color = Colors.GREEN if all_passed else Colors.RED
    status_text = "ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED"

    print(f"  {status_color}{Colors.BOLD}{status_text}{Colors.RESET}")
    print()

    # Summary stats
    print(f"  {Colors.BOLD}Overall Statistics:{Colors.RESET}")
    print(f"    Total Tests:  {total_tests}")
    print(f"    {Colors.GREEN}Passed:{Colors.RESET}       {total_passed}")
    if total_failed > 0:
        print(f"    {Colors.RED}Failed:{Colors.RESET}       {total_failed}")
    if total_errors > 0:
        print(f"    {Colors.RED}Errors:{Colors.RESET}       {total_errors}")
    if total_skipped > 0:
        print(f"    {Colors.YELLOW}Skipped:{Colors.RESET}      {total_skipped}")
    print(f"    Duration:     {format_duration(total_duration)}")
    print()

    # Per-folder breakdown
    print(f"  {Colors.BOLD}Results by Folder:{Colors.RESET}")
    print()

    # Header
    print(f"    {'Folder':<20} {'Status':<10} {'Passed':<8} {'Failed':<8} {'Skip':<8} {'Time':<10}")
    print(f"    {'-' * 20} {'-' * 10} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 10}")

    for r in sorted(results, key=lambda x: (x.success, -x.failed)):
        status = f"{Colors.GREEN}PASS{Colors.RESET}" if r.success else f"{Colors.RED}FAIL{Colors.RESET}"
        failed_str = f"{Colors.RED}{r.failed}{Colors.RESET}" if r.failed > 0 else str(r.failed)
        print(f"    {r.folder:<20} {status:<19} {r.passed:<8} {failed_str:<17} {r.skipped:<8} {format_duration(r.duration)}")

    print()

    # Show failures
    failed_results = [r for r in results if not r.success]
    if failed_results:
        print(f"  {Colors.BOLD}{Colors.RED}Failed Tests:{Colors.RESET}")
        print()
        for r in failed_results:
            print(f"    {Colors.RED}{r.folder}:{Colors.RESET}")
            for detail in r.error_details[:5]:
                print(f"      {Colors.DIM}{detail}{Colors.RESET}")
            print(f"      {Colors.DIM}Log: {r.log_file}{Colors.RESET}")
            print()

    # Output location
    print(f"  {Colors.BOLD}Output Location:{Colors.RESET}")
    print(f"    {output_dir}")
    print()

    # Quick commands
    print(f"  {Colors.BOLD}Useful Commands:{Colors.RESET}")
    print(f"    View report:    python tests/integration/run_tests.py --report")
    print(f"    Check status:   python tests/integration/run_tests.py --status")
    print(f"    Re-run failed:  python -m pytest <folder> -v --tb=long")
    print()


def save_results_json(results: list[TestResult], total_duration: float, output_dir: Path, status: str = "completed"):
    """Save results as JSON for later reporting."""
    data = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "total_duration": total_duration,
        "results": [
            {
                "folder": r.folder,
                "passed": r.passed,
                "failed": r.failed,
                "skipped": r.skipped,
                "errors": r.errors,
                "duration": r.duration,
                "log_file": r.log_file,
                "error_details": r.error_details,
                "status": r.status,
            }
            for r in results
        ],
    }

    json_file = output_dir / "results.json"
    json_file.write_text(json.dumps(data, indent=2))


def list_all_runs() -> list[dict]:
    """List all test runs with their status."""
    results_dir = get_results_dir()
    if not results_dir.exists():
        return []

    runs = []
    for run_dir in sorted(results_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue

        json_file = run_dir / "results.json"
        if json_file.exists():
            try:
                data = json.loads(json_file.read_text())
                runs.append({
                    "dir": run_dir,
                    "timestamp": run_dir.name,
                    "status": data.get("status", "completed"),
                    "data": data,
                })
            except json.JSONDecodeError:
                runs.append({
                    "dir": run_dir,
                    "timestamp": run_dir.name,
                    "status": "error",
                    "data": None,
                })
        else:
            # Check if any log files indicate running tests
            log_files = list(run_dir.glob("*.txt"))
            has_running = any(
                f.read_text().startswith("[RUNNING]")
                for f in log_files if f.exists()
            )
            runs.append({
                "dir": run_dir,
                "timestamp": run_dir.name,
                "status": "running" if has_running else "incomplete",
                "data": None,
            })

    return runs


def show_status():
    """Show status of the most recent test run."""
    print_header("TEST RUN STATUS")

    runs = list_all_runs()

    if not runs:
        print(f"  {Colors.YELLOW}No test runs found.{Colors.RESET}")
        print(f"  Run tests with: python tests/integration/run_tests.py")
        return

    # Get the most recent run (running or completed)
    latest = runs[0]
    run_dir = latest["dir"]
    is_running = latest["status"] == "running"

    # Header
    status_label = f"{Colors.CYAN}RUNNING{Colors.RESET}" if is_running else "completed"
    print(f"  {Colors.BOLD}Last run:{Colors.RESET} {format_timestamp(latest['timestamp'])} ({status_label})")
    print()

    # Collect status for all folders
    all_folders = get_test_folders()
    folder_status = {}

    for folder in all_folders:
        log_file = run_dir / f"{folder}.txt"
        if log_file.exists():
            status, result = parse_log_file_status(log_file)
            folder_status[folder] = (status, result)
        else:
            folder_status[folder] = ("pending", None)

    # Count totals
    total_passed = 0
    total_failed = 0
    running_count = 0
    completed_count = 0

    for folder, (status, result) in folder_status.items():
        if status == "running":
            running_count += 1
        elif result:
            completed_count += 1
            total_passed += result.passed
            total_failed += result.failed + result.errors

    # Show progress if running
    if is_running:
        print(f"  Progress: {completed_count}/{len(all_folders)} folders completed, {running_count} running")
        print()

    # Show per-folder status
    print(f"  {'Folder':<20} {'Status':<12} {'Result':<30}")
    print(f"  {'-' * 20} {'-' * 12} {'-' * 30}")

    for folder in sorted(all_folders):
        status, result = folder_status.get(folder, ("pending", None))

        if status == "running":
            status_str = f"{Colors.CYAN}RUNNING{Colors.RESET}"
            result_str = ""
        elif status == "timeout":
            status_str = f"{Colors.RED}TIMEOUT{Colors.RESET}"
            result_str = f"{Colors.RED}Test timed out{Colors.RESET}"
        elif status == "pending":
            status_str = f"{Colors.DIM}pending{Colors.RESET}"
            result_str = ""
        elif result:
            if result.success:
                status_str = f"{Colors.GREEN}PASS{Colors.RESET}"
                result_str = f"{result.passed} passed"
            else:
                status_str = f"{Colors.RED}FAIL{Colors.RESET}"
                result_str = f"{Colors.RED}{result.passed} passed, {result.failed} failed{Colors.RESET}"
        else:
            status_str = f"{Colors.YELLOW}unknown{Colors.RESET}"
            result_str = ""

        print(f"  {folder:<20} {status_str:<21} {result_str}")

    print()

    # Summary line
    if not is_running:
        all_pass = total_failed == 0
        status_color = Colors.GREEN if all_pass else Colors.RED
        status_text = "ALL PASSED" if all_pass else f"{total_failed} FAILED"
        print(f"  {Colors.BOLD}Total:{Colors.RESET} {total_passed} passed, {status_color}{status_text}{Colors.RESET}")
        print()

    print(f"  {Colors.BOLD}Commands:{Colors.RESET}")
    print(f"    View full report:  python tests/integration/run_tests.py --report")
    print()


def load_and_show_report(timestamp: Optional[str] = None):
    """Load and display a report from a previous run."""
    results_dir = get_results_dir()

    if not results_dir.exists():
        print(f"{Colors.RED}No test results found. Run tests first.{Colors.RESET}")
        return

    # Find the results directory
    if timestamp and timestamp != "latest":
        output_dir = results_dir / timestamp
        if not output_dir.exists():
            print(f"{Colors.RED}No results found for timestamp: {timestamp}{Colors.RESET}")
            available = sorted([d.name for d in results_dir.iterdir() if d.is_dir()])[-5:]
            print(f"Available runs: {', '.join(available)}")
            return
    else:
        # Use latest
        dirs = sorted([d for d in results_dir.iterdir() if d.is_dir()])
        if not dirs:
            print(f"{Colors.RED}No test results found.{Colors.RESET}")
            return
        output_dir = dirs[-1]

    # Load JSON results
    json_file = output_dir / "results.json"
    if not json_file.exists():
        # Try to build results from log files
        print(f"  {Colors.YELLOW}No results.json found, parsing log files...{Colors.RESET}")
        results = []
        for log_file in output_dir.glob("*.txt"):
            status, result = parse_log_file_status(log_file)
            if result:
                results.append(result)
            elif status == "running":
                results.append(TestResult(folder=log_file.stem, status="running"))

        if results:
            total_duration = sum(r.duration for r in results)
            print_summary(results, total_duration, output_dir, output_dir.name)
        else:
            print(f"{Colors.RED}No results found in {output_dir}{Colors.RESET}")
        return

    data = json.loads(json_file.read_text())

    # Convert to TestResult objects
    results = [
        TestResult(
            folder=r["folder"],
            passed=r["passed"],
            failed=r["failed"],
            skipped=r["skipped"],
            errors=r["errors"],
            duration=r["duration"],
            log_file=r["log_file"],
            error_details=r["error_details"],
            status=r.get("status", "completed"),
        )
        for r in data["results"]
    ]

    print_summary(results, data["total_duration"], output_dir, data.get("timestamp", output_dir.name))


def cleanup_results(keep_last: int = 5):
    """Delete old test result directories."""
    print_header("CLEANUP TEST RESULTS")

    results_dir = get_results_dir()
    if not results_dir.exists():
        print(f"  No test results to clean up.")
        return

    dirs = sorted([d for d in results_dir.iterdir() if d.is_dir()])

    if len(dirs) <= keep_last:
        print(f"  Only {len(dirs)} runs found, keeping all.")
        return

    to_delete = dirs[:-keep_last]
    print(f"  Keeping last {keep_last} runs, deleting {len(to_delete)} old runs...")
    print()

    for d in to_delete:
        print(f"    Deleting: {d.name}")
        shutil.rmtree(d)

    print()
    print(f"  {Colors.GREEN}Cleaned up {len(to_delete)} old test runs.{Colors.RESET}")


def run_all_tests(include_slow: bool = False, max_workers: int = 8):
    """Run all integration tests in parallel."""
    print_header("INTEGRATION TEST RUNNER")

    # Get test folders
    folders = get_test_folders()
    print(f"  Found {len(folders)} test folders: {', '.join(folders)}")
    print(f"  Include slow tests: {include_slow}")
    print(f"  Max parallel workers: {max_workers}")
    print()

    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = get_results_dir()
    output_dir = results_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Started at: {format_timestamp(timestamp)}")
    print(f"  Output directory: {output_dir}")
    print()

    # Run tests in parallel
    print(f"  {Colors.BOLD}Running tests...{Colors.RESET}")
    print()

    results = []
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_folder = {
            executor.submit(run_test_folder, folder, output_dir, include_slow): folder
            for folder in folders
        }

        # Track running
        for folder in folders:
            print_progress(folder, "running")

        # Collect results as they complete
        for future in as_completed(future_to_folder):
            folder = future_to_folder[future]
            try:
                result = future.result()
                results.append(result)
                status = "done" if result.success else "failed"
                print_progress(folder, status, result.duration)
            except Exception as e:
                print(f"  {Colors.RED}[ERROR]{Colors.RESET} {folder}: {e}")
                results.append(TestResult(folder=folder, errors=1, status="error"))

    total_duration = time.time() - start_time

    # Save results
    save_results_json(results, total_duration, output_dir, status="completed")

    # Print summary
    print_summary(results, total_duration, output_dir, timestamp)

    # Return exit code
    all_passed = all(r.success for r in results)
    return 0 if all_passed else 1


def main():
    parser = argparse.ArgumentParser(
        description="Run integration tests in parallel with detailed reporting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tests/integration/run_tests.py              # Run tests (excluding slow)
  python tests/integration/run_tests.py --all        # Run all tests including slow
  python tests/integration/run_tests.py --report     # Show latest report
  python tests/integration/run_tests.py --status     # Check ongoing/recent runs
  python tests/integration/run_tests.py -j 4         # Run with 4 parallel workers
        """,
    )

    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Include slow tests",
    )
    parser.add_argument(
        "--report", "-r",
        nargs="?",
        const="latest",
        metavar="TIMESTAMP",
        help="Show report from a previous run (default: latest)",
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show status of ongoing and recent test runs",
    )
    parser.add_argument(
        "--cleanup-results",
        action="store_true",
        help="Delete old test result directories (keeps last 5)",
    )
    parser.add_argument(
        "-j", "--jobs",
        type=int,
        default=8,
        help="Number of parallel test workers (default: 8)",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
        return 0

    if args.cleanup_results:
        cleanup_results()
        return 0

    if args.report:
        timestamp = None if args.report == "latest" else args.report
        load_and_show_report(timestamp)
        return 0

    return run_all_tests(include_slow=args.all, max_workers=args.jobs)


if __name__ == "__main__":
    sys.exit(main())
