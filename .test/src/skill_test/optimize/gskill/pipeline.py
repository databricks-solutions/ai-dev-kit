"""gskill pipeline: generate optimized skills for customer repositories.

Uses optimize_anything to produce SKILL.md files from repository context.
"""

import ast
import re
from pathlib import Path
from typing import Any

from gepa.optimize_anything import optimize_anything, GEPAConfig, EngineConfig, ReflectionConfig
import gepa.optimize_anything as oa

from ..config import get_preset


def run_gskill(
    repo_path: str | Path,
    skill_name: str | None = None,
    output_dir: str | Path | None = None,
    preset: str = "standard",
    context_files: list[str] | None = None,
) -> dict[str, Any]:
    """Generate an optimized skill for a customer repository.

    Args:
        repo_path: Path to the customer's repository
        skill_name: Name for the generated skill (auto-detected if None)
        output_dir: Override output directory
        preset: GEPA optimization preset
        context_files: Additional files to provide as context

    Returns:
        Dict with generated skill path and metadata
    """
    repo_path = Path(repo_path).resolve()
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository not found: {repo_path}")

    config = get_preset(preset)

    if skill_name is None:
        skill_name = repo_path.name

    repo_context = _scan_repo(repo_path, context_files)

    seed_content = (
        f"# {skill_name}\n\n"
        "## Overview\n\n"
        f"Patterns and best practices for the {skill_name} project.\n\n"
        + repo_context
    )

    def evaluate(candidate: str, example: dict) -> tuple[float, dict]:
        """Score structural quality of generated skill."""
        score = 0.0
        parts = 0

        if re.search(r"^#{1,3}\s+", candidate, re.MULTILINE):
            score += 1.0
            parts += 1

        code_blocks = re.findall(r"```(\w+)\n(.*?)```", candidate, re.DOTALL)
        if code_blocks:
            score += 1.0
            parts += 1
            py_blocks = [b for lang, b in code_blocks if lang == "python"]
            if py_blocks:
                valid = sum(1 for b in py_blocks if _parses(b))
                score += valid / len(py_blocks)
                parts += 1

        word_count = len(candidate.split())
        if 200 <= word_count <= 5000:
            score += 1.0
            parts += 1

        final = score / parts if parts > 0 else 0.0
        oa.log(f"Structure score: {final:.2f}, words: {word_count}")

        return final, {"structure_score": final, "word_count": word_count}

    trainset = [
        {"input": f"Help me understand patterns in {skill_name}", "additional_context": {}, "answer": ""},
        {"input": f"Show code examples from {skill_name}", "additional_context": {}, "answer": ""},
    ]

    result = optimize_anything(
        seed_candidate=seed_content,
        evaluator=evaluate,
        dataset=trainset,
        objective=f"Generate a SKILL.md that teaches an AI coding agent the patterns in {skill_name}.",
        background=(
            "SKILL.md files teach AI agents (Claude Code) repository-specific patterns. "
            "Focus on Databricks patterns: Unity Catalog, MLflow, Spark, Delta Lake, etc. "
            "Be CONCISE and ACTION-ORIENTED. Lead with code examples."
        ),
        config=config,
    )

    generated_content = result.best_candidate
    if isinstance(generated_content, dict):
        generated_content = list(generated_content.values())[0]

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


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False


def _scan_repo(repo_path: Path, context_files: list[str] | None = None) -> str:
    context_parts = []
    if context_files:
        for f in context_files:
            p = Path(f) if Path(f).is_absolute() else repo_path / f
            if p.exists():
                content = p.read_text()[:5000]
                context_parts.append(f"### {p.name}\n\n```\n{content}\n```\n")

    readme = repo_path / "README.md"
    if readme.exists() and not context_files:
        context_parts.append(f"### README\n\n{readme.read_text()[:3000]}\n")

    return "\n".join(context_parts) if context_parts else ""
