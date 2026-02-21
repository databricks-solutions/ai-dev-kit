"""GEPA-powered skill optimization for the skill-test framework.

Public API:
    optimize_skill()        - End-to-end optimize a SKILL.md
    create_skill_adapter()  - Create a GEPA adapter for a skill
    OptimizationResult      - Dataclass with optimization results
    PRESETS                 - GEPA config presets (quick, standard, thorough)
"""

from .runner import optimize_skill, OptimizationResult
from .evaluator import create_skill_adapter, SkillAdapter
from .config import PRESETS
from .review import review_optimization, apply_optimization

__all__ = [
    "optimize_skill",
    "OptimizationResult",
    "create_skill_adapter",
    "SkillAdapter",
    "PRESETS",
    "review_optimization",
    "apply_optimization",
]
