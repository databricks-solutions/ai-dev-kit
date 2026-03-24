#!/usr/bin/env python3
"""Quick trigger validation for skills.

Tests whether a skill triggers correctly by running prompts through
`claude -p` and checking if the skill name appears in the output.
This is a lightweight smoke test for development — use routing_eval.py
for comprehensive routing evaluation.

Inspired by Anthropic's skill-creator run_eval.py (Apache 2.0).

Usage:
    uv run python .test/scripts/quick_trigger.py <skill-name> [options]

Options:
    --prompts    Comma-separated list of test prompts (overrides auto-discovery)
    --negative   Comma-separated list of prompts that should NOT trigger the skill
    --verbose    Show full claude output
    --timeout    Timeout per prompt in seconds (default: 30)
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from _common import find_repo_root, setup_path

repo_root = setup_path()

SKILLS_DIR = repo_root / "databricks-skills"
ROUTING_TESTS = repo_root / ".test" / "skills" / "_routing" / "ground_truth.yaml"


def load_skill_description(skill_name: str) -> str | None:
    """Load description from a skill's SKILL.md frontmatter."""
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_md.exists():
        return None
    content = skill_md.read_text()
    match = re.match(r"^---\n(.+?)\n---", content, re.DOTALL)
    if match:
        import yaml

        fm = yaml.safe_load(match.group(1))
        return fm.get("description", "")
    return None


def load_routing_tests(skill_name: str) -> tuple[list[str], list[str]]:
    """Load routing test prompts for this skill from ground_truth.yaml.

    Returns (positive_prompts, negative_prompts).
    """
    positive = []
    negative = []

    if not ROUTING_TESTS.exists():
        return positive, negative

    import yaml

    data = yaml.safe_load(ROUTING_TESTS.read_text())
    for tc in data.get("test_cases", []):
        expected = tc.get("expectations", {}).get("expected_skills", [])
        prompt = tc.get("inputs", {}).get("prompt", "")
        if not prompt:
            continue
        if skill_name in expected:
            positive.append(prompt)
        elif not expected and skill_name in tc.get("id", ""):
            negative.append(prompt)

    return positive, negative


def run_prompt(prompt: str, timeout: int = 30) -> tuple[str, float]:
    """Run a prompt through claude -p and return (output, elapsed_seconds)."""
    start = time.time()
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.time() - start
        return result.stdout + result.stderr, elapsed
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return f"TIMEOUT after {timeout}s", elapsed
    except FileNotFoundError:
        return "ERROR: claude CLI not found. Install Claude Code first.", 0.0


def check_skill_triggered(output: str, skill_name: str) -> bool:
    """Check if the skill name appears in the output, suggesting it triggered."""
    # Look for skill name in output (case-insensitive, hyphen/underscore flexible)
    pattern = skill_name.replace("-", "[-_\\s]?")
    return bool(re.search(pattern, output, re.IGNORECASE))


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick trigger validation for skills")
    parser.add_argument("skill_name", help="Name of the skill to test")
    parser.add_argument("--prompts", help="Comma-separated positive test prompts")
    parser.add_argument("--negative", help="Comma-separated negative test prompts")
    parser.add_argument("--verbose", action="store_true", help="Show full output")
    parser.add_argument(
        "--timeout", type=int, default=30, help="Timeout per prompt (seconds)"
    )
    args = parser.parse_args()

    skill_name = args.skill_name

    # Validate skill exists
    desc = load_skill_description(skill_name)
    if desc is None:
        print(f"ERROR: Skill '{skill_name}' not found in {SKILLS_DIR}")
        return 1

    print(f"Quick Trigger Test: {skill_name}")
    print(f"Description: {desc[:100]}...")
    print()

    # Gather prompts
    if args.prompts:
        positive_prompts = [p.strip() for p in args.prompts.split(",")]
    else:
        positive_prompts, _ = load_routing_tests(skill_name)

    if args.negative:
        negative_prompts = [p.strip() for p in args.negative.split(",")]
    else:
        _, negative_prompts = load_routing_tests(skill_name)

    if not positive_prompts:
        print(
            "WARNING: No test prompts found. Add routing tests to "
            ".test/skills/_routing/ground_truth.yaml or use --prompts"
        )
        print(
            "Example: uv run python .test/scripts/quick_trigger.py "
            f'{skill_name} --prompts "Create a vector search index"'
        )
        return 1

    # Run positive tests (should trigger)
    results = {"positive": [], "negative": [], "summary": {}}
    pass_count = 0
    total = len(positive_prompts)

    print(f"=== Should Trigger ({total} prompts) ===\n")
    for i, prompt in enumerate(positive_prompts, 1):
        output, elapsed = run_prompt(prompt, args.timeout)
        triggered = check_skill_triggered(output, skill_name)
        status = "PASS" if triggered else "FAIL"
        if triggered:
            pass_count += 1

        print(f"  [{status}] ({elapsed:.1f}s) {prompt[:80]}")
        if args.verbose:
            print(f"    Output: {output[:200]}")

        results["positive"].append(
            {
                "prompt": prompt,
                "triggered": triggered,
                "elapsed_seconds": round(elapsed, 2),
            }
        )

    # Run negative tests (should NOT trigger)
    neg_pass_count = 0
    neg_total = len(negative_prompts)

    if negative_prompts:
        print(f"\n=== Should NOT Trigger ({neg_total} prompts) ===\n")
        for prompt in negative_prompts:
            output, elapsed = run_prompt(prompt, args.timeout)
            triggered = check_skill_triggered(output, skill_name)
            status = "PASS" if not triggered else "FAIL"
            if not triggered:
                neg_pass_count += 1

            print(f"  [{status}] ({elapsed:.1f}s) {prompt[:80]}")
            if args.verbose:
                print(f"    Output: {output[:200]}")

            results["negative"].append(
                {
                    "prompt": prompt,
                    "triggered": triggered,
                    "elapsed_seconds": round(elapsed, 2),
                }
            )

    # Summary
    print(f"\n=== Summary ===")
    print(f"  Positive (should trigger):     {pass_count}/{total}")
    if negative_prompts:
        print(f"  Negative (should NOT trigger): {neg_pass_count}/{neg_total}")

    all_passed = pass_count == total and neg_pass_count == neg_total
    results["summary"] = {
        "skill_name": skill_name,
        "positive_pass_rate": pass_count / total if total > 0 else 0,
        "negative_pass_rate": neg_pass_count / neg_total if neg_total > 0 else 0,
        "all_passed": all_passed,
    }

    # Write results to JSON
    output_path = (
        repo_root / ".test" / "skills" / skill_name / "quick_trigger_results.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\n  Results saved to: {output_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
