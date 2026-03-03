"""Shared utilities for skill optimization.

Extracted from evaluator.py — provides path resolution, token counting,
and the SKILL_KEY constant used across the optimization package.
"""

from pathlib import Path

import tiktoken

SKILL_KEY = "skill_md"


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------


def find_repo_root() -> Path:
    """Find the repo root by searching upward for .test/src/."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".test" / "src").exists():
            return current
        if (current / "src" / "skill_test").exists() and current.name == ".test":
            return current.parent
        current = current.parent
    return Path.cwd()


def find_skill_md(skill_name: str) -> Path | None:
    """Locate the SKILL.md file for a given skill name."""
    repo_root = find_repo_root()
    candidates = [
        repo_root / ".claude" / "skills" / skill_name / "SKILL.md",
        repo_root / "databricks-skills" / skill_name / "SKILL.md",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def token_efficiency_score(candidate_text: str, original_token_count: int) -> float:
    """Score based on how concise the candidate is vs. the original.

    Smaller than original = bonus up to 1.15, same size = 1.0,
    larger = linear penalty to 0.0 at 2x.
    """
    if original_token_count <= 0:
        return 1.0
    enc = tiktoken.get_encoding("cl100k_base")
    candidate_tokens = len(enc.encode(candidate_text))
    ratio = candidate_tokens / original_token_count
    if ratio <= 1.0:
        return 1.0 + 0.15 * (1.0 - ratio)
    else:
        return max(0.0, 2.0 - ratio)
