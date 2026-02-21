"""Train/val dataset splitting for GEPA optimization.

Loads ground_truth.yaml test cases and splits them into train/val sets,
stratified by metadata.category when possible.

GEPA's DefaultDataInst format: {"input": str, "additional_context": dict[str, str], "answer": str}

We store our internal task representation alongside, and convert to GEPA format
when needed via to_gepa_instances().
"""

import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, TypedDict

from ..dataset import EvalRecord, get_dataset_source


class SkillTask(TypedDict, total=False):
    """Internal task representation (superset of GEPA DefaultDataInst)."""

    id: str
    input: str  # The prompt (maps to DefaultDataInst.input)
    answer: str  # Expected response (maps to DefaultDataInst.answer)
    additional_context: dict[str, str]  # Extra context (maps to DefaultDataInst.additional_context)
    expectations: dict[str, Any]  # Scorer expectations (not sent to GEPA directly)
    metadata: dict[str, Any]  # Category, difficulty, etc.


def _record_to_task(record: EvalRecord) -> SkillTask:
    """Convert an EvalRecord to our internal task format."""
    task: SkillTask = {
        "id": record.id,
        "input": record.inputs.get("prompt", ""),
        "additional_context": {},
        "answer": "",
        "metadata": record.metadata or {},
    }
    if record.outputs:
        task["answer"] = record.outputs.get("response", "")
    if record.expectations:
        task["expectations"] = record.expectations
        # Also encode expectations into additional_context for GEPA reflection
        task["additional_context"]["expectations"] = json.dumps(record.expectations)
    return task


def to_gepa_instances(tasks: list[SkillTask]) -> list[dict[str, Any]]:
    """Convert internal tasks to GEPA DefaultDataInst format.

    Returns list of {"input": str, "additional_context": dict[str,str], "answer": str}
    """
    return [
        {
            "input": t["input"],
            "additional_context": t.get("additional_context", {}),
            "answer": t.get("answer", ""),
        }
        for t in tasks
    ]


def create_gepa_datasets(
    skill_name: str,
    val_ratio: float = 0.2,
    base_path: Path | None = None,
    seed: int = 42,
) -> tuple[list[SkillTask], list[SkillTask] | None]:
    """Load ground_truth.yaml, stratify by metadata.category, split into train/val.

    For skills with <5 test cases: uses all as train, val=None (single-task mode).
    For skills with >=5 test cases: stratified train/val split (generalization mode).

    Args:
        skill_name: Name of the skill to load test cases for
        val_ratio: Fraction of test cases to hold out for validation
        base_path: Override base path for skills directory
        seed: Random seed for reproducible splits

    Returns:
        Tuple of (train_tasks, val_tasks). val_tasks is None if <5 test cases.
    """
    source = get_dataset_source(skill_name, base_path)
    records = source.load()

    if not records:
        return [], None

    tasks = [_record_to_task(r) for r in records]

    # Too few for a meaningful val split
    if len(tasks) < 5:
        return tasks, None

    # Stratify by category
    by_category: dict[str, list[SkillTask]] = defaultdict(list)
    for task in tasks:
        cat = task.get("metadata", {}).get("category", "_uncategorized")
        by_category[cat].append(task)

    rng = random.Random(seed)
    train: list[SkillTask] = []
    val: list[SkillTask] = []

    for cat, cat_tasks in by_category.items():
        rng.shuffle(cat_tasks)
        n_val = max(1, int(len(cat_tasks) * val_ratio))

        # Ensure at least 1 train sample per category
        if len(cat_tasks) - n_val < 1:
            n_val = len(cat_tasks) - 1

        if n_val <= 0:
            train.extend(cat_tasks)
        else:
            val.extend(cat_tasks[:n_val])
            train.extend(cat_tasks[n_val:])

    # If val ended up empty, fall back
    if not val:
        return tasks, None

    return train, val


def generate_bootstrap_tasks(skill_name: str, base_path: Path | None = None) -> list[SkillTask]:
    """Generate synthetic tasks from a SKILL.md when no ground_truth.yaml exists.

    Parses the SKILL.md for documented patterns and generates basic test prompts
    that exercise each pattern.

    Args:
        skill_name: Name of the skill
        base_path: Override base path for skills directory

    Returns:
        List of synthetic SkillTask dicts
    """
    if base_path is None:
        # Find repo root for path resolution
        from .evaluator import _find_repo_root

        repo_root = _find_repo_root()
        skill_md_candidates = [
            repo_root / ".claude" / "skills" / skill_name / "SKILL.md",
            repo_root / "databricks-skills" / skill_name / "SKILL.md",
        ]
    else:
        skill_md_candidates = [base_path.parent / skill_name / "SKILL.md"]

    skill_content = None
    for path in skill_md_candidates:
        if path.exists():
            skill_content = path.read_text()
            break

    if not skill_content:
        return []

    tasks: list[SkillTask] = []

    # Extract h2/h3 headers as topic areas
    headers = re.findall(r"^#{2,3}\s+(.+)$", skill_content, re.MULTILINE)

    for i, header in enumerate(headers):
        tasks.append(
            {
                "id": f"bootstrap_{i:03d}",
                "input": f"Using the {skill_name} skill, help me with: {header}",
                "additional_context": {},
                "answer": "",
                "metadata": {"category": "bootstrap", "source": "auto_generated"},
            }
        )

    # Extract code block language hints for targeted prompts
    code_langs = set(re.findall(r"```(\w+)\n", skill_content))
    for lang in code_langs:
        tasks.append(
            {
                "id": f"bootstrap_lang_{lang}",
                "input": f"Show me a {lang} example using {skill_name} patterns",
                "additional_context": {},
                "answer": "",
                "metadata": {"category": "bootstrap", "source": "auto_generated"},
            }
        )

    return tasks or [
        {
            "id": "bootstrap_general",
            "input": f"Explain the key patterns in {skill_name}",
            "additional_context": {},
            "answer": "",
            "metadata": {"category": "bootstrap", "source": "auto_generated"},
        }
    ]
