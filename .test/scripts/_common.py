"""Shared utilities for skill-test scripts.

Provides common functions used across all CLI wrapper scripts:
- find_repo_root(): Locate repository root
- setup_path(): Add skill_test to Python path
- create_cli_context(): Create CLIContext with proper base_path
"""
import sys
from pathlib import Path

# Load .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip


def find_repo_root() -> Path:
    """Find repo root by looking for .test/src/ directory.

    Searches upward from the script location to find the repository root.
    Returns the path containing the .test/ directory.
    """
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".test" / "src").exists():
            return current
        # Also check if we're inside .test/
        if (current / "src" / "skill_test").exists() and current.name == ".test":
            return current.parent
        current = current.parent
    raise RuntimeError("Could not find repo root with .test/src/")


def setup_path() -> Path:
    """Add skill_test to Python path and return repo root.

    Call this at the start of any script that needs to import skill_test.
    """
    repo_root = find_repo_root()
    src_path = str(repo_root / ".test" / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    return repo_root


def create_cli_context(repo_root: Path | None = None):
    """Create CLIContext with proper base_path.

    Args:
        repo_root: Repository root path. If None, will be detected automatically.

    Returns:
        CLIContext configured for local execution (without MCP tools).
    """
    if repo_root is None:
        repo_root = setup_path()
    else:
        setup_path()

    from skill_test.cli import CLIContext

    return CLIContext(base_path=repo_root / ".test" / "skills")


def print_result(result: dict) -> int:
    """Print result as JSON and return exit code.

    Args:
        result: Dictionary with results, should have 'success' key.

    Returns:
        0 if success, 1 otherwise.
    """
    import json

    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("success", False) else 1


def handle_error(e: Exception, skill_name: str) -> int:
    """Handle exception and return exit code.

    Args:
        e: The exception that was raised.
        skill_name: Name of the skill being processed.

    Returns:
        1 (error exit code).
    """
    import json

    print(
        json.dumps(
            {"error": str(e), "success": False, "skill_name": skill_name}, indent=2
        )
    )
    return 1
