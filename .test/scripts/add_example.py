#!/usr/bin/env python3
"""Manually add a test case to a skill's ground_truth.yaml.

Usage:
    # Interactive mode — prompts for each field
    uv run python .test/scripts/add_example.py databricks-model-serving

    # Inline mode — provide prompt and response directly
    uv run python .test/scripts/add_example.py databricks-model-serving \
      --prompt "Create a ChatAgent with tool calling" \
      --response-file /path/to/response.md \
      --facts "Uses ChatAgent class" "Implements predict method" \
      --patterns "ChatAgent" "def predict"

    # From clipboard
    uv run python .test/scripts/add_example.py databricks-model-serving --from-clipboard
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import setup_path

setup_path()


def _detect_language(response: str) -> str | None:
    """Auto-detect code language from response code blocks."""
    langs = re.findall(r"```(\w+)\n", response)
    if not langs:
        return None
    # Most common language wins
    from collections import Counter
    counts = Counter(l for l in langs if l != "text")
    return counts.most_common(1)[0][0] if counts else None


def _auto_extract_patterns(response: str) -> list[str]:
    """Extract patterns from code blocks."""
    patterns = []
    for match in re.finditer(r"```(?:python)\n(.*?)```", response, re.DOTALL):
        code = match.group(1)
        for m in re.finditer(r"class\s+(\w+)", code):
            patterns.append(m.group(1))
        for m in re.finditer(r"def\s+(\w+)", code):
            patterns.append(m.group(1))

    for match in re.finditer(r"```(?:sql)\n(.*?)```", response, re.DOTALL):
        code = match.group(1)
        for m in re.finditer(r"(?:CREATE|ALTER)\s+(?:TABLE|VIEW)\s+(\S+)", code, re.I):
            patterns.append(m.group(1))

    return list(dict.fromkeys(patterns))


def _next_id(skill_name: str, existing_ids: set[str]) -> str:
    """Generate the next sequential ID for a skill."""
    prefix = skill_name.replace("-", "_")
    idx = 1
    while True:
        candidate = f"{prefix}_{idx:03d}"
        if candidate not in existing_ids:
            return candidate
        idx += 1


def _read_clipboard() -> str:
    """Read text from system clipboard."""
    import subprocess
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True, text=True, check=True,
            )
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("Error: Could not read clipboard (tried pbpaste and xclip)")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Add a test case to a skill's ground_truth.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "skill_name",
        help="Name of the skill (e.g., databricks-model-serving)",
    )
    parser.add_argument(
        "--prompt", "-p",
        default=None,
        help="The user prompt for the test case",
    )
    parser.add_argument(
        "--response", "-r",
        default=None,
        help="The expected response text (inline)",
    )
    parser.add_argument(
        "--response-file",
        type=Path,
        default=None,
        help="Path to a file containing the expected response",
    )
    parser.add_argument(
        "--facts", "-f",
        nargs="*",
        default=None,
        help="Expected facts that must appear in the response",
    )
    parser.add_argument(
        "--patterns",
        nargs="*",
        default=None,
        help="Expected patterns (regex) that must match in the response",
    )
    parser.add_argument(
        "--category", "-c",
        default="happy_path",
        help="Test case category (default: happy_path)",
    )
    parser.add_argument(
        "--from-clipboard",
        action="store_true",
        help="Read prompt and response from clipboard (separated by ---)",
    )
    parser.add_argument(
        "--id",
        default=None,
        help="Override the auto-generated test case ID",
    )

    args = parser.parse_args()

    import yaml
    from skill_test.dataset import get_dataset_source, YAMLDatasetSource

    # Validate skill exists
    skill_dir = Path(".test/skills") / args.skill_name
    gt_path = skill_dir / "ground_truth.yaml"

    if not skill_dir.exists():
        print(f"Error: skill directory not found: {skill_dir}")
        print("Available skills:")
        for d in sorted(Path(".test/skills").iterdir()):
            if d.is_dir() and not d.name.startswith("_"):
                print(f"  {d.name}")
        sys.exit(1)

    # Load existing records
    existing_ids = set()
    if gt_path.exists():
        try:
            source = YAMLDatasetSource(gt_path)
            existing = source.load()
            existing_ids = {r.id for r in existing}
        except Exception:
            pass

    # Get prompt
    prompt = args.prompt
    response = args.response

    if args.from_clipboard:
        clipboard = _read_clipboard()
        if "---" in clipboard:
            parts = clipboard.split("---", 1)
            prompt = parts[0].strip()
            response = parts[1].strip()
        else:
            prompt = clipboard.strip()
            print("Clipboard content set as prompt (no --- separator found for response)")

    if args.response_file:
        response = args.response_file.read_text()

    if not prompt:
        print("Enter the user prompt (Ctrl+D to finish):")
        prompt = sys.stdin.read().strip()

    if not prompt:
        print("Error: prompt is required")
        sys.exit(1)

    if not response:
        print("Enter the expected response (Ctrl+D to finish):")
        response = sys.stdin.read().strip()

    # Generate ID
    test_id = args.id or _next_id(args.skill_name, existing_ids)

    # Auto-extract patterns and facts
    auto_patterns = _auto_extract_patterns(response) if response else []
    auto_facts = args.facts or []
    user_patterns = args.patterns or []

    # Merge auto and user patterns
    all_patterns = list(dict.fromkeys(user_patterns + auto_patterns))

    # Detect language
    language = _detect_language(response) if response else None

    # Build test case
    test_case = {
        "id": test_id,
        "inputs": {"prompt": prompt},
        "metadata": {
            "category": args.category,
            "source": "manual",
        },
    }

    if response:
        test_case["outputs"] = {"response": response}
        if language:
            test_case["metadata"]["language"] = language

    expectations = {}
    if auto_facts:
        expectations["expected_facts"] = auto_facts
    if all_patterns:
        expectations["expected_patterns"] = all_patterns
    if expectations:
        test_case["expectations"] = expectations

    # Show summary
    print(f"\n--- Test Case Preview ---")
    print(f"ID: {test_id}")
    print(f"Skill: {args.skill_name}")
    print(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    if response:
        print(f"Response: {len(response)} chars")
    if all_patterns:
        print(f"Patterns: {all_patterns}")
    if auto_facts:
        print(f"Facts: {auto_facts}")
    print(f"Category: {args.category}")

    # Confirm
    if sys.stdin.isatty():
        confirm = input("\nAppend to ground_truth.yaml? [Y/n] ").strip().lower()
        if confirm and confirm != "y":
            print("Aborted.")
            sys.exit(0)

    # Save
    if gt_path.exists():
        with open(gt_path) as f:
            data = yaml.safe_load(f) or {"test_cases": []}
    else:
        gt_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"test_cases": []}

    data["test_cases"].append(test_case)

    with open(gt_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"Added test case '{test_id}' to {gt_path}")


if __name__ == "__main__":
    main()
