"""Evaluation criteria packaged as Agent Skills (SKILL.md format).

Implements the Skill/SkillSet data model from MLflow #21255 design spec
(https://github.com/mlflow/mlflow/issues/21255#issuecomment-3997922398).

Each eval criteria is a folder with SKILL.md (YAML frontmatter + markdown body)
and optional ``references/`` directory with detailed rubrics.

The ``applies_to`` metadata field maps to ``manifest.yaml`` ``tool_modules``,
enabling adaptive criteria selection per skill domain.  When the native
``make_judge(skills=[...])`` API lands in MLflow, replace this module with
``from mlflow.genai.skills import SkillSet``.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model (matches Skill dataclass from spec)
# ---------------------------------------------------------------------------


@dataclass
class EvalCriteriaSkill:
    """Parsed evaluation criteria skill.

    Mirrors the ``Skill`` dataclass from the MLflow #21255 design spec::

        name, description, path, metadata, body, references
    """

    name: str
    description: str
    path: Path
    metadata: dict[str, Any]
    body: str
    references: dict[str, str]  # {relative_path: content}
    applies_to: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Container (matches SkillSet from spec)
# ---------------------------------------------------------------------------


class EvalCriteriaSet:
    """Container for evaluation criteria skills.

    Parses SKILL.md files eagerly at creation time.  Generates system-prompt
    blocks for judge injection and provides lookup-by-name for tool invocation.
    """

    def __init__(self, paths: list[str | Path]):
        self.skills: list[EvalCriteriaSkill] = []
        for p in paths:
            try:
                self.skills.append(self._load_skill(p))
            except Exception as exc:
                logger.warning("Failed to load eval criteria from %s: %s", p, exc)
        self._by_name: dict[str, EvalCriteriaSkill] = {s.name: s for s in self.skills}

    # -- public API --

    def to_prompt(self, model: str | None = None) -> str:
        """Generate available-criteria block for system-prompt injection.

        Per spec: XML for Claude models, Markdown for others.
        Only includes frontmatter (name + description) — ~50-100 tokens per skill.
        """
        if not self.skills:
            return ""
        if model and _is_claude_model(model):
            return self._to_xml()
        return self._to_markdown()

    def get_skill(self, name: str) -> EvalCriteriaSkill | None:
        return self._by_name.get(name)

    def filter_by_modules(self, tool_modules: list[str]) -> "EvalCriteriaSet":
        """Return subset of criteria matching *tool_modules*.

        Criteria with empty ``applies_to`` are always included (general-purpose).
        """
        filtered = [
            s
            for s in self.skills
            if not s.applies_to or any(m in s.applies_to for m in tool_modules)
        ]
        result = EvalCriteriaSet.__new__(EvalCriteriaSet)
        result.skills = filtered
        result._by_name = {s.name: s for s in filtered}
        return result

    @property
    def names(self) -> list[str]:
        return [s.name for s in self.skills]

    # -- prompt formatting --

    def _to_xml(self) -> str:
        """XML format for Claude models (per Agent Skills integration spec)."""
        lines = ["<available_skills>"]
        for s in self.skills:
            lines.append("  <skill>")
            lines.append(f"    <name>{s.name}</name>")
            lines.append(f"    <description>{s.description}</description>")
            lines.append("  </skill>")
        lines.append("</available_skills>")
        lines.append("")
        lines.append(
            "You have access to evaluation criteria skills that provide "
            "domain-specific rubrics. Use the read_eval_criteria tool to load "
            "a skill's full content when it is relevant to the trace you are "
            "evaluating. Use read_eval_reference to access detailed rubrics "
            "within a skill."
        )
        return "\n".join(lines)

    def _to_markdown(self) -> str:
        """Markdown format for OpenAI / Gemini / other models."""
        lines = ["## Available Evaluation Criteria", ""]
        for s in self.skills:
            lines.append(f"- **{s.name}**: {s.description}")
        lines.append("")
        lines.append(
            "Use the read_eval_criteria tool to load relevant criteria. "
            "Use read_eval_reference for detailed rubrics."
        )
        return "\n".join(lines)

    # -- loading --

    @staticmethod
    def _load_skill(path: str | Path) -> EvalCriteriaSkill:
        """Parse a SKILL.md file and eagerly load references."""
        path = Path(path).resolve()
        skill_md = path / "SKILL.md" if path.is_dir() else path
        skill_dir = skill_md.parent

        content = skill_md.read_text(encoding="utf-8")
        frontmatter, body = _parse_frontmatter(content)

        name = frontmatter.get("name", skill_dir.name)
        description = frontmatter.get("description", "")
        metadata = frontmatter.get("metadata", {})
        applies_to = metadata.get("applies_to", [])
        if isinstance(applies_to, str):
            applies_to = [applies_to]

        references = _load_references(skill_dir)

        return EvalCriteriaSkill(
            name=name,
            description=description,
            path=skill_dir,
            metadata=metadata,
            body=body,
            references=references,
            applies_to=applies_to,
        )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_eval_criteria(
    criteria_dir: str | Path = ".test/eval-criteria",
) -> EvalCriteriaSet:
    """Auto-discover all eval-criteria skill folders in *criteria_dir*."""
    base = Path(criteria_dir)
    if not base.is_dir():
        logger.debug("Eval criteria directory not found: %s", base)
        return EvalCriteriaSet([])
    paths = sorted(
        d for d in base.iterdir() if d.is_dir() and (d / "SKILL.md").exists()
    )
    if paths:
        logger.info(
            "Discovered %d eval criteria: %s",
            len(paths),
            ", ".join(p.name for p in paths),
        )
    return EvalCriteriaSet(paths)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_claude_model(model: str) -> bool:
    low = model.lower()
    return any(k in low for k in ("claude", "anthropic"))


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and markdown body from a SKILL.md file."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", content, re.DOTALL)
    if not match:
        return {}, content
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, match.group(2)


def _load_references(skill_dir: Path) -> dict[str, str]:
    """Eagerly load all text files from ``references/`` into memory."""
    refs_dir = skill_dir / "references"
    if not refs_dir.is_dir():
        return {}
    result: dict[str, str] = {}
    for f in sorted(refs_dir.rglob("*")):
        if f.is_file() and f.suffix in (".md", ".txt", ".yaml", ".json"):
            rel = str(f.relative_to(skill_dir))
            try:
                result[rel] = f.read_text(encoding="utf-8")
            except Exception:
                logger.warning("Could not read reference file: %s", f)
    return result
