#!/usr/bin/env python3
"""Generate test cases from user requirements for skill optimization.

Converts natural-language requirements into ground_truth.yaml test cases
with binary assertions (patterns + facts) and guidelines for LLM judge
evaluation.

Usage:
    # From a requirements file (one requirement per line)
    uv run python .test/scripts/generate_examples.py databricks-metric-views \
      --requirements requirements.txt

    # Inline requirements (repeatable)
    uv run python .test/scripts/generate_examples.py databricks-metric-views \
      --requirement "Must explain MEASURE() wrapping for all measure references" \
      --requirement "Should show error handling when SELECT * is used on metric views"

    # Interactive mode (prompts for requirements)
    uv run python .test/scripts/generate_examples.py databricks-metric-views --interactive

    # Auto-append to ground_truth.yaml (skip manual review)
    uv run python .test/scripts/generate_examples.py databricks-metric-views \
      --requirement "Must explain MEASURE() wrapping" --trust

    # With a second LLM pass to tighten assertions
    uv run python .test/scripts/generate_examples.py databricks-metric-views \
      --requirement "Must explain MEASURE() wrapping" --refine
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import setup_path

setup_path()


def _find_skill_md(skill_name: str) -> str:
    """Load SKILL.md content for the given skill."""
    from skill_test.optimize.evaluator import _find_skill_md as find_md
    path = find_md(skill_name)
    if path is None:
        raise FileNotFoundError(f"Could not find SKILL.md for '{skill_name}'")
    return path.read_text()


def _load_existing_ids(skill_name: str) -> set[str]:
    """Load existing test case IDs from ground_truth.yaml."""
    import yaml
    gt_path = Path(".test/skills") / skill_name / "ground_truth.yaml"
    if not gt_path.exists():
        return set()
    with open(gt_path) as f:
        data = yaml.safe_load(f) or {}
    return {tc["id"] for tc in data.get("test_cases", []) if "id" in tc}


def generate_examples_from_requirements(
    skill_name: str,
    requirements: list[str],
    skill_md: str,
    gen_model: str,
    count_per_requirement: int = 3,
) -> list[dict]:
    """Generate test cases from requirements using an LLM.

    For each requirement, generates ``count_per_requirement`` test cases
    grounded in the SKILL.md content.

    Returns:
        List of test case dicts in ground_truth.yaml format.
    """
    import litellm

    existing_ids = _load_existing_ids(skill_name)
    all_examples: list[dict] = []

    for req_idx, requirement in enumerate(requirements):
        print(f"\n  Generating for requirement {req_idx + 1}/{len(requirements)}:")
        print(f"    {requirement[:100]}")

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert test case generator for Databricks skills. "
                    "Given a SKILL.md document and a user requirement, generate "
                    f"{count_per_requirement} realistic test cases that evaluate "
                    "whether the skill satisfies the requirement.\n\n"
                    "Each test case must include:\n"
                    "- A realistic user prompt\n"
                    "- A reference response grounded in SKILL.md\n"
                    "- Binary assertions: expected_patterns (regex) and expected_facts (substring)\n"
                    "- Guidelines derived from the requirement (for LLM judge evaluation)\n"
                    "- Category and difficulty metadata\n\n"
                    "Return a JSON array of test cases. Each test case:\n"
                    "{\n"
                    '  "prompt": "user question",\n'
                    '  "response": "reference answer grounded in SKILL.md",\n'
                    '  "expected_patterns": [{"pattern": "regex", "min_count": 1, "description": "what it checks"}],\n'
                    '  "expected_facts": ["substring that must appear"],\n'
                    '  "guidelines": ["evaluation guideline from the requirement"],\n'
                    '  "category": "happy_path|edge_case|error_handling",\n'
                    '  "difficulty": "easy|medium|hard"\n'
                    "}\n\n"
                    "Important:\n"
                    "- Patterns should be regex that work with re.findall(pattern, response, re.IGNORECASE)\n"
                    "- Facts should be exact substrings (case-insensitive) from the response\n"
                    "- Guidelines should be evaluable by an LLM judge looking at the response\n"
                    "- Ground everything in SKILL.md — don't invent APIs or syntax"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"## SKILL.md for '{skill_name}':\n\n"
                    f"{skill_md[:8000]}\n\n"
                    f"## Requirement:\n{requirement}\n\n"
                    f"## Existing test case IDs (avoid duplicates):\n"
                    f"{', '.join(sorted(existing_ids)[:20]) or 'None'}\n\n"
                    f"Generate {count_per_requirement} test cases as a JSON array."
                ),
            },
        ]

        try:
            resp = litellm.completion(
                model=gen_model,
                messages=messages,
                temperature=0.7,
            )
            content = resp.choices[0].message.content or ""

            # Extract JSON array from response
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if not json_match:
                print(f"    Warning: no JSON array found in response")
                continue

            cases = json.loads(json_match.group())
            if not isinstance(cases, list):
                print(f"    Warning: expected JSON array, got {type(cases)}")
                continue

            for case_idx, case in enumerate(cases):
                test_id = f"{skill_name}_gen_{req_idx:02d}_{case_idx:02d}"
                # Avoid collisions with existing IDs
                while test_id in existing_ids:
                    test_id += "_x"
                existing_ids.add(test_id)

                example = {
                    "id": test_id,
                    "inputs": {"prompt": case.get("prompt", "")},
                    "outputs": {
                        "response": case.get("response", ""),
                        "execution_success": True,
                    },
                    "expectations": {},
                    "metadata": {
                        "category": case.get("category", "happy_path"),
                        "difficulty": case.get("difficulty", "medium"),
                        "source": "generated_from_requirement",
                        "requirement": requirement[:200],
                    },
                }

                if case.get("expected_patterns"):
                    example["expectations"]["expected_patterns"] = case["expected_patterns"]
                if case.get("expected_facts"):
                    example["expectations"]["expected_facts"] = case["expected_facts"]
                if case.get("guidelines"):
                    example["expectations"]["guidelines"] = case["guidelines"]

                all_examples.append(example)

            print(f"    Generated {len(cases)} test case(s)")

        except Exception as e:
            print(f"    Error generating for requirement: {e}")

    return all_examples


def refine_examples(examples: list[dict], gen_model: str) -> list[dict]:
    """Second LLM pass to validate and tighten assertions."""
    import litellm

    for ex in examples:
        prompt_text = ex["inputs"]["prompt"][:200]
        response_text = ex["outputs"]["response"][:1000]
        patterns = ex["expectations"].get("expected_patterns", [])
        facts = ex["expectations"].get("expected_facts", [])
        guidelines = ex["expectations"].get("guidelines", [])

        messages = [
            {
                "role": "system",
                "content": (
                    "You are reviewing auto-generated test expectations. "
                    "Validate that patterns actually match the response, "
                    "facts are actually present as substrings, and guidelines "
                    "are clear and evaluable. Tighten or fix as needed. "
                    "Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Prompt: {prompt_text}\n\n"
                    f"Response: {response_text}\n\n"
                    f"Patterns: {json.dumps(patterns)}\n"
                    f"Facts: {json.dumps(facts)}\n"
                    f"Guidelines: {json.dumps(guidelines)}\n\n"
                    "Return a JSON object with:\n"
                    '- "expected_patterns": refined list\n'
                    '- "expected_facts": refined list (must be exact substrings of response)\n'
                    '- "guidelines": refined list\n'
                    "Remove any patterns/facts that don't actually match the response."
                ),
            },
        ]

        try:
            resp = litellm.completion(model=gen_model, messages=messages, temperature=0)
            content = resp.choices[0].message.content or ""
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                refined = json.loads(json_match.group())
                if "expected_patterns" in refined:
                    ex["expectations"]["expected_patterns"] = refined["expected_patterns"]
                if "expected_facts" in refined:
                    ex["expectations"]["expected_facts"] = refined["expected_facts"]
                if "guidelines" in refined:
                    ex["expectations"]["guidelines"] = refined["guidelines"]
        except Exception as e:
            print(f"    Warning: refinement failed for {ex['id']}: {e}")

    return examples


def save_candidates(examples: list[dict], skill_name: str) -> Path:
    """Save generated examples to candidates.yaml for review."""
    import yaml

    output_path = Path(".test/skills") / skill_name / "candidates.yaml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {"test_cases": examples}
    with open(output_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nSaved {len(examples)} examples to {output_path}")
    print(f"Review and then append to ground_truth.yaml, or re-run with --trust")
    return output_path


def append_to_ground_truth(examples: list[dict], skill_name: str) -> None:
    """Append generated examples to ground_truth.yaml."""
    import yaml

    gt_path = Path(".test/skills") / skill_name / "ground_truth.yaml"
    gt_path.parent.mkdir(parents=True, exist_ok=True)

    if gt_path.exists():
        with open(gt_path) as f:
            data = yaml.safe_load(f) or {"test_cases": []}
    else:
        data = {"test_cases": []}

    existing_ids = {tc["id"] for tc in data.get("test_cases", []) if "id" in tc}
    new_examples = [ex for ex in examples if ex["id"] not in existing_ids]

    if not new_examples:
        print("No new examples to add (all IDs already exist).")
        return

    data["test_cases"].extend(new_examples)

    with open(gt_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"\nAppended {len(new_examples)} examples to {gt_path}")


def run_generation(
    skill_name: str,
    requirements: list[str],
    gen_model: str,
    trust: bool = False,
    refine: bool = False,
    count_per_requirement: int = 3,
) -> list[dict]:
    """Run the full generation pipeline. Called by optimize.py --generate-from.

    Returns:
        List of generated test case dicts.
    """
    skill_md = _find_skill_md(skill_name)
    print(f"Generating test cases for '{skill_name}' from {len(requirements)} requirement(s)")

    examples = generate_examples_from_requirements(
        skill_name=skill_name,
        requirements=requirements,
        skill_md=skill_md,
        gen_model=gen_model,
        count_per_requirement=count_per_requirement,
    )

    if not examples:
        print("No examples generated.")
        return []

    if refine:
        print("\nRefining assertions with LLM...")
        examples = refine_examples(examples, gen_model)

    if trust:
        append_to_ground_truth(examples, skill_name)
    else:
        save_candidates(examples, skill_name)

    return examples


def main():
    parser = argparse.ArgumentParser(
        description="Generate test cases from requirements for skill optimization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "skill_name",
        help="Name of the skill (e.g., databricks-metric-views)",
    )
    parser.add_argument(
        "--requirements",
        type=str,
        default=None,
        metavar="FILE",
        help="Path to a requirements file (one requirement per line)",
    )
    parser.add_argument(
        "--requirement",
        action="append",
        default=None,
        dest="inline_requirements",
        help="Inline requirement (repeatable)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively enter requirements",
    )
    parser.add_argument(
        "--gen-model",
        default=None,
        help="LLM model for generation (default: GEPA_GEN_LM env or Sonnet)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=3,
        help="Number of test cases per requirement (default: 3)",
    )
    parser.add_argument(
        "--trust",
        action="store_true",
        help="Auto-append to ground_truth.yaml instead of writing candidates.yaml",
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Second LLM pass to validate and tighten assertions",
    )

    args = parser.parse_args()

    # Collect requirements from all sources
    requirements: list[str] = []

    if args.requirements:
        req_path = Path(args.requirements)
        if not req_path.exists():
            print(f"Error: requirements file not found: {req_path}")
            sys.exit(1)
        requirements.extend(
            line.strip() for line in req_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    if args.inline_requirements:
        requirements.extend(args.inline_requirements)

    if args.interactive:
        print("Enter requirements (one per line, empty line to finish):")
        while True:
            line = input("  > ").strip()
            if not line:
                break
            requirements.append(line)

    if not requirements:
        parser.error("Provide requirements via --requirements, --requirement, or --interactive")

    # Resolve gen_model
    gen_model = args.gen_model
    if gen_model is None:
        from skill_test.optimize.config import DEFAULT_GEN_LM
        gen_model = DEFAULT_GEN_LM

    run_generation(
        skill_name=args.skill_name,
        requirements=requirements,
        gen_model=gen_model,
        trust=args.trust,
        refine=args.refine,
        count_per_requirement=args.count,
    )


if __name__ == "__main__":
    main()
