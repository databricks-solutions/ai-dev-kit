"""gskill pipeline: wraps GEPA optimize for customer repository skill generation.

Configures GEPA with Databricks-appropriate defaults, generates an optimized
SKILL.md, and outputs it in the standard format.
"""

import re
from pathlib import Path
from typing import Any

import gepa
from gepa import GEPAAdapter, EvaluationBatch

from ..config import get_preset


class _GSkillAdapter(GEPAAdapter):
    """Minimal adapter for gskill that scores SKILL.md structural quality."""

    SKILL_KEY = "skill_md"

    def evaluate(
        self,
        batch: list[dict[str, Any]],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch:
        """Score candidate skill based on structural quality metrics."""
        import ast

        candidate_text = candidate.get(self.SKILL_KEY, "")
        trajectories = []

        for data_inst in batch:
            score = 0.0
            parts = 0

            # Has markdown headers
            if re.search(r"^#{1,3}\s+", candidate_text, re.MULTILINE):
                score += 1.0
                parts += 1

            # Has code blocks
            code_blocks = re.findall(r"```(\w+)\n(.*?)```", candidate_text, re.DOTALL)
            if code_blocks:
                score += 1.0
                parts += 1

                # Python blocks parse
                py_blocks = [b for lang, b in code_blocks if lang == "python"]
                if py_blocks:
                    valid = sum(1 for b in py_blocks if _parses(b))
                    score += valid / len(py_blocks)
                    parts += 1

            # Reasonable length (not too short, not too long)
            word_count = len(candidate_text.split())
            if 200 <= word_count <= 5000:
                score += 1.0
                parts += 1

            final = score / parts if parts > 0 else 0.0

            trajectories.append({
                "data": data_inst,
                "full_assistant_response": candidate_text[:200],
                "score": final,
            })

        return EvaluationBatch(trajectories=trajectories)

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch,
        components_to_update: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        reflective_data: dict[str, list[dict[str, Any]]] = {}
        for component in components_to_update:
            examples = []
            for traj in eval_batch.trajectories:
                if traj.get("score", 1.0) < 0.8:
                    examples.append({
                        "input": traj.get("data", {}).get("input", ""),
                        "current_text": candidate.get(component, ""),
                        "feedback": "Skill structural quality is below threshold.",
                        "score": traj.get("score", 0.0),
                    })
            reflective_data[component] = examples
        return reflective_data


def _parses(code: str) -> bool:
    """Check if Python code parses without syntax errors."""
    import ast
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def run_gskill(
    repo_path: str | Path,
    skill_name: str | None = None,
    output_dir: str | Path | None = None,
    preset: str = "standard",
    context_files: list[str] | None = None,
) -> dict[str, Any]:
    """Generate an optimized skill for a customer repository using GEPA.

    Scans the repo for Databricks patterns, generates a SKILL.md optimized
    for Claude Code consumption, and outputs to .claude/skills/<name>/SKILL.md.

    Args:
        repo_path: Path to the customer's repository
        skill_name: Name for the generated skill (auto-detected if None)
        output_dir: Override output directory
        preset: GEPA optimization preset
        context_files: Additional files to provide as context

    Returns:
        Dict with generated skill path, quality score, and metadata
    """
    repo_path = Path(repo_path).resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    preset_config = get_preset(preset)

    if skill_name is None:
        skill_name = repo_path.name

    # Gather repo context
    repo_context = _scan_repo(repo_path, context_files)

    # Build seed candidate
    seed_content = (
        f"# {skill_name}\n\n"
        "## Overview\n\n"
        f"Patterns and best practices for the {skill_name} project.\n\n"
        + repo_context
    )

    seed_candidate = {_GSkillAdapter.SKILL_KEY: seed_content}

    # Build a synthetic trainset from the repo
    trainset = [
        {
            "input": f"Help me understand the patterns in {skill_name}",
            "additional_context": {},
            "answer": "",
        },
        {
            "input": f"Show me code examples from {skill_name}",
            "additional_context": {},
            "answer": "",
        },
    ]

    adapter = _GSkillAdapter()

    # Run GEPA
    result = gepa.optimize(
        seed_candidate=seed_candidate,
        trainset=trainset,
        adapter=adapter,
        **preset_config.to_kwargs(),
    )

    generated_content = result.best_candidate.get(_GSkillAdapter.SKILL_KEY, seed_content)

    # Write output
    if output_dir is None:
        output_dir = repo_path / ".claude" / "skills" / skill_name
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    skill_path = output_dir / "SKILL.md"
    skill_path.write_text(generated_content)

    return {
        "skill_name": skill_name,
        "skill_path": str(skill_path),
        "content_length": len(generated_content),
        "repo_path": str(repo_path),
        "preset": preset,
    }


def _scan_repo(repo_path: Path, context_files: list[str] | None = None) -> str:
    """Scan repository for Databricks-relevant patterns and build context."""
    context_parts = []

    # Read explicitly provided context files
    if context_files:
        for f in context_files:
            p = Path(f) if Path(f).is_absolute() else repo_path / f
            if p.exists():
                content = p.read_text()[:5000]  # Cap at 5K per file
                context_parts.append(f"### {p.name}\n\n```\n{content}\n```\n")

    # Auto-scan for README
    readme = repo_path / "README.md"
    if readme.exists() and not context_files:
        context_parts.append(f"### README\n\n{readme.read_text()[:3000]}\n")

    return "\n".join(context_parts) if context_parts else ""
