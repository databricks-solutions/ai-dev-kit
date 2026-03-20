"""SKILL.md parsing for evaluation criteria (mirrors PR #21725 Skill/SkillSet naming).

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
# Data model (matches Skill dataclass from PR #21725)
# ---------------------------------------------------------------------------


@dataclass
class Skill:
    """Parsed evaluation criteria skill.

    Mirrors the ``Skill`` dataclass from MLflow PR #21725::

        name, description, path, metadata, body, references, applies_to
    """

    name: str
    description: str
    path: Path
    metadata: dict[str, Any]
    body: str
    references: dict[str, str]  # {relative_path: content}
    applies_to: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Container (matches SkillSet from PR #21725)
# ---------------------------------------------------------------------------


class SkillSet:
    """Container for evaluation criteria skills.

    Parses SKILL.md files eagerly at creation time.  Provides prompt generation
    for judge instruction injection and lookup-by-name for tool invocation.
    """

    def __init__(self, paths: list[str | Path]):
        self.skills: list[Skill] = []
        for p in paths:
            try:
                self.skills.append(self._load_skill(p))
            except Exception as exc:
                logger.warning("Failed to load eval criteria from %s: %s", p, exc)
        self._by_name: dict[str, Skill] = {s.name: s for s in self.skills}

    # -- public API --

    def get_skill(self, name: str) -> Skill | None:
        return self._by_name.get(name)

    def filter_by_modules(self, tool_modules: list[str]) -> "SkillSet":
        """Return subset of criteria matching *tool_modules*.

        Criteria with empty ``applies_to`` are always included (general-purpose).
        """
        filtered = [s for s in self.skills if not s.applies_to or any(m in s.applies_to for m in tool_modules)]
        result = SkillSet.__new__(SkillSet)
        result.skills = filtered
        result._by_name = {s.name: s for s in filtered}
        return result

    @property
    def names(self) -> list[str]:
        return [s.name for s in self.skills]

    def to_prompt_inline(self) -> str:
        """Full body + references for instruction injection (current use).

        Inlines every skill's body and reference files into a single prompt
        block suitable for prepending to judge instructions.
        """
        if not self.skills:
            return ""
        sections: list[str] = ["# Evaluation Criteria\n"]
        for skill in self.skills:
            sections.append(f"## {skill.name}\n")
            sections.append(skill.body.strip())
            for ref_path, ref_content in skill.references.items():
                sections.append(f"\n### Reference: {ref_path}\n")
                sections.append(ref_content.strip())
            sections.append("")
        return "\n".join(sections)

    def to_prompt_summary(self) -> str:
        """Name + description only (future tool-based use).

        Generates a compact summary block listing available criteria so that
        an agentic judge can decide which to load via tools.
        """
        if not self.skills:
            return ""
        lines = ["## Available Evaluation Criteria", ""]
        for s in self.skills:
            lines.append(f"- **{s.name}**: {s.description}")
        lines.append("")
        lines.append(
            "Use the read_skill tool to load relevant criteria. "
            "Use read_skill_file for detailed rubrics within a skill."
        )
        return "\n".join(lines)

    # -- loading --

    @staticmethod
    def _load_skill(path: str | Path) -> Skill:
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

        return Skill(
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
) -> SkillSet:
    """Auto-discover all eval-criteria skill folders in *criteria_dir*."""
    base = Path(criteria_dir)
    if not base.is_dir():
        logger.debug("Eval criteria directory not found: %s", base)
        return SkillSet([])
    paths = sorted(d for d in base.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
    if paths:
        logger.info(
            "Discovered %d eval criteria: %s",
            len(paths),
            ", ".join(p.name for p in paths),
        )
    return SkillSet(paths)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
