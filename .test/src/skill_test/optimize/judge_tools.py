"""Custom judge tools for adaptive evaluation criteria loading.

Implements ``ReadSkillTool`` and ``ReadSkillReferenceTool`` from the MLflow
#21255 design spec, registered in MLflow's global ``JudgeToolRegistry`` so
they are available to any trace-based judge.

Key difference from spec: tools accept ``trace: Trace`` (required by the
``JudgeTool`` interface) but use the internal ``EvalCriteriaSet`` for skill
lookup.  When the native ``make_judge(skills=[...])`` API lands, replace
this module with MLflow's built-in skill tools which route via type
annotation.

Registry invocation flow::

    registry.invoke(tool_call, trace)
      → json.loads(tool_call.function.arguments)
      → tool.invoke(trace, **parsed_args)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from mlflow.entities.trace import Trace
from mlflow.genai.judges.tools.base import JudgeTool
from mlflow.genai.judges.tools.registry import register_judge_tool
from mlflow.types.llm import FunctionToolDefinition, ParamProperty, ToolDefinition, ToolParamsSchema

from .eval_criteria import EvalCriteriaSet

logger = logging.getLogger(__name__)


class ReadEvalCriteriaTool(JudgeTool):
    """Read the full body of an evaluation-criteria skill.

    The judge calls this tool when a criteria's description matches the
    trace it is evaluating.
    """

    def __init__(self, criteria_set: EvalCriteriaSet):
        self._criteria_set = criteria_set

    @property
    def name(self) -> str:
        return "read_eval_criteria"

    def get_definition(self) -> ToolDefinition:
        available = self._criteria_set.names
        return ToolDefinition(
            function=FunctionToolDefinition(
                name="read_eval_criteria",
                description=(
                    "Read the full content of an evaluation criteria skill to get domain-specific "
                    "rubrics, scoring rules, and reference material.  Use this when a criteria's "
                    f"description matches the trace content.  Available criteria: {available}"
                ),
                parameters=ToolParamsSchema(
                    properties={
                        "skill_name": ParamProperty(
                            type="string", description="Name of the evaluation criteria to read"
                        ),
                    },
                ),
            ),
        )

    def invoke(self, trace: Trace, skill_name: str) -> str:
        skill = self._criteria_set.get_skill(skill_name)
        if not skill:
            available = self._criteria_set.names
            return f"Error: No criteria named '{skill_name}'. Available: {available}"
        return skill.body


class ReadEvalReferenceTool(JudgeTool):
    """Read a reference document from a criteria's ``references/`` directory.

    Used for detailed rubrics, edge cases, and scoring examples.
    """

    def __init__(self, criteria_set: EvalCriteriaSet):
        self._criteria_set = criteria_set

    @property
    def name(self) -> str:
        return "read_eval_reference"

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            function=FunctionToolDefinition(
                name="read_eval_reference",
                description=(
                    "Read a reference document from an evaluation criteria skill for detailed "
                    "rubrics, edge cases, or scoring examples."
                ),
                parameters=ToolParamsSchema(
                    properties={
                        "skill_name": ParamProperty(type="string", description="Name of the evaluation criteria"),
                        "file_path": ParamProperty(
                            type="string",
                            description="Relative path within the skill (e.g., 'references/RUBRIC.md')",
                        ),
                    },
                ),
            ),
        )

    def invoke(self, trace: Trace, skill_name: str, file_path: str) -> str:
        skill = self._criteria_set.get_skill(skill_name)
        if not skill:
            available = self._criteria_set.names
            return f"Error: No criteria named '{skill_name}'. Available: {available}"
        normalized = os.path.normpath(file_path)
        if normalized.startswith("..") or os.path.isabs(normalized):
            return f"Error: Invalid file path '{file_path}'. Must be relative."
        if normalized not in skill.references:
            return f"Error: File '{file_path}' not found in '{skill_name}'"
        return skill.references[normalized]


_registered = False


def register_eval_tools(criteria_set: EvalCriteriaSet) -> None:
    """Register eval-criteria tools in MLflow's global ``JudgeToolRegistry``.

    Safe to call multiple times — tools are registered only once per process.
    """
    global _registered
    if _registered:
        return
    if not criteria_set.skills:
        logger.debug("No eval criteria loaded; skipping tool registration")
        return
    register_judge_tool(ReadEvalCriteriaTool(criteria_set))
    register_judge_tool(ReadEvalReferenceTool(criteria_set))
    _registered = True
    logger.info("Registered eval criteria judge tools (%d criteria available)", len(criteria_set.skills))
