"""Judge tools for MLflow's JudgeToolRegistry (matches PR #21725 naming).

Implements ``ReadSkillTool`` and ``ReadSkillFileTool``, registered in MLflow's
global ``JudgeToolRegistry`` so they are available to any trace-based judge.

These won't activate in current field-based judges (no agentic loop), but are
ready for future trace-based judges.

When the native ``make_judge(skills=[...])`` API lands in MLflow, replace this
module with MLflow's built-in skill tools.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mlflow.entities.trace import Trace
from mlflow.genai.judges.tools.base import JudgeTool
from mlflow.genai.judges.tools.registry import register_judge_tool
from mlflow.types.llm import (
    FunctionToolDefinition,
    ParamProperty,
    ToolDefinition,
    ToolParamsSchema,
)

from .eval_criteria import SkillSet

logger = logging.getLogger(__name__)


class ReadSkillTool(JudgeTool):
    """Read the full body of an evaluation-criteria skill.

    The judge calls this tool when a criteria's description matches the
    trace it is evaluating.
    """

    def __init__(self, skill_set: SkillSet):
        self._skill_set = skill_set

    @property
    def name(self) -> str:
        return "read_skill"

    def get_definition(self) -> ToolDefinition:
        available = self._skill_set.names
        return ToolDefinition(
            function=FunctionToolDefinition(
                name="read_skill",
                description=(
                    "Read the full content of an evaluation criteria skill to get "
                    "domain-specific rubrics, scoring rules, and reference material. "
                    "Use this when a criteria's description matches the trace content. "
                    f"Available criteria: {available}"
                ),
                parameters=ToolParamsSchema(
                    properties={
                        "skill_name": ParamProperty(
                            type="string",
                            description="Name of the evaluation criteria to read",
                        ),
                    },
                ),
            ),
        )

    def invoke(self, trace: Trace, skill_name: str) -> str:
        skill = self._skill_set.get_skill(skill_name)
        if not skill:
            available = self._skill_set.names
            return f"Error: No criteria named '{skill_name}'. Available: {available}"
        return skill.body


class ReadSkillFileTool(JudgeTool):
    """Read a reference document from a criteria's ``references/`` directory.

    Used for detailed rubrics, edge cases, and scoring examples.
    Path traversal protected: rejects absolute paths and ``..`` components.
    """

    def __init__(self, skill_set: SkillSet):
        self._skill_set = skill_set

    @property
    def name(self) -> str:
        return "read_skill_file"

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            function=FunctionToolDefinition(
                name="read_skill_file",
                description=(
                    "Read a reference document from an evaluation criteria skill "
                    "for detailed rubrics, edge cases, or scoring examples."
                ),
                parameters=ToolParamsSchema(
                    properties={
                        "skill_name": ParamProperty(
                            type="string",
                            description="Name of the evaluation criteria",
                        ),
                        "file_path": ParamProperty(
                            type="string",
                            description="Relative path within the skill (e.g., 'references/RUBRIC.md')",
                        ),
                    },
                ),
            ),
        )

    def invoke(self, trace: Trace, skill_name: str, file_path: str) -> str:
        skill = self._skill_set.get_skill(skill_name)
        if not skill:
            available = self._skill_set.names
            return f"Error: No criteria named '{skill_name}'. Available: {available}"
        normalized = os.path.normpath(file_path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            return f"Error: Invalid file path '{file_path}'. Must be relative."
        if normalized not in skill.references:
            return f"Error: File '{file_path}' not found in '{skill_name}'"
        return skill.references[normalized]


_registered = False


def register_skill_tools(skill_set: SkillSet) -> None:
    """Register skill tools in MLflow's global ``JudgeToolRegistry``.

    Safe to call multiple times -- tools are registered only once per process.
    """
    global _registered
    if _registered:
        return
    if not skill_set.skills:
        logger.debug("No eval criteria loaded; skipping tool registration")
        return
    register_judge_tool(ReadSkillTool(skill_set))
    register_judge_tool(ReadSkillFileTool(skill_set))
    _registered = True
    logger.info(
        "Registered skill judge tools (%d criteria available)",
        len(skill_set.skills),
    )
