"""Binary assertion layer for SkillBench-style evaluation.

Wraps pattern and fact checks into binary pass/fail assertions,
mirroring SkillBench's pytest-style binary approach. No fuzzy keyword
scoring -- each assertion either passes or fails.
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class AssertionResult:
    """Result of a single binary assertion."""

    name: str
    passed: bool
    rationale: str
    assertion_type: str  # "pattern" | "fact"


def _run_pattern_assertions(response: str, expected_patterns: list) -> list[AssertionResult]:
    """Run pattern assertions against a response.

    Each pattern spec can be a plain regex string or a dict with
    ``pattern``, ``min_count``, ``max_count``, ``description`` keys.
    """
    results = []
    for pattern_spec in expected_patterns:
        if isinstance(pattern_spec, str):
            pattern = pattern_spec
            min_count = 1
            max_count = None
            description = pattern[:40]
        else:
            pattern = pattern_spec["pattern"]
            min_count = pattern_spec.get("min_count", 1)
            max_count = pattern_spec.get("max_count", None)
            description = pattern_spec.get("description", pattern[:40])

        matches = len(re.findall(pattern, response, re.IGNORECASE))

        if max_count is not None:
            passed = min_count <= matches <= max_count
            rationale = f"Found {matches} matches (need {min_count}-{max_count})"
        else:
            passed = matches >= min_count
            rationale = f"Found {matches} matches (need >={min_count})"

        results.append(AssertionResult(
            name=f"pattern_{description}",
            passed=passed,
            rationale=rationale,
            assertion_type="pattern",
        ))
    return results


def _run_fact_assertions(response: str, expected_facts: list[str]) -> list[AssertionResult]:
    """Run fact assertions against a response.

    Exact substring match (case-insensitive). No fuzzy keyword overlap.
    """
    response_lower = response.lower()
    results = []
    for fact in expected_facts:
        found = fact.lower() in response_lower
        results.append(AssertionResult(
            name=f"fact_{fact[:40]}",
            passed=found,
            rationale=f"{'Found' if found else 'Missing'}: {fact}",
            assertion_type="fact",
        ))
    return results


def run_all_assertions(response: str, expectations: dict[str, Any]) -> list[AssertionResult]:
    """Run all pattern + fact assertions, return binary pass/fail per assertion.

    Args:
        response: The text to check assertions against.
        expectations: Dict with optional ``expected_patterns`` and ``expected_facts`` keys.

    Returns:
        List of AssertionResult with binary pass/fail for each assertion.
    """
    results: list[AssertionResult] = []

    patterns = expectations.get("expected_patterns", [])
    if patterns:
        results.extend(_run_pattern_assertions(response, patterns))

    facts = expectations.get("expected_facts", [])
    if facts:
        results.extend(_run_fact_assertions(response, facts))

    return results


def _classify_assertion(
    with_result: AssertionResult,
    without_result: AssertionResult,
) -> str:
    """Classify a single assertion by comparing with-skill vs without-skill.

    Returns one of:
        POSITIVE   — fails without skill, passes with  (skill is helping)
        REGRESSION — passes without skill, fails with  (skill is confusing the agent)
        NEEDS_SKILL — fails both with and without       (skill must add this content)
        NEUTRAL    — same result either way             (agent already knows this)
    """
    if with_result.passed and not without_result.passed:
        return "POSITIVE"
    elif not with_result.passed and without_result.passed:
        return "REGRESSION"
    elif not with_result.passed and not without_result.passed:
        return "NEEDS_SKILL"
    else:
        return "NEUTRAL"


def _extract_content(result: AssertionResult) -> str:
    """Extract the actual expected content from an assertion result.

    For facts, strips the ``Missing: `` / ``Found: `` prefix to get the raw
    fact text.  For patterns, uses the description embedded in the assertion
    name (strips the ``pattern_`` prefix).
    """
    if result.assertion_type == "fact":
        for prefix in ("Missing: ", "Found: "):
            if result.rationale.startswith(prefix):
                return result.rationale[len(prefix):]
        return result.rationale
    else:
        # Pattern: name is "pattern_{description}", rationale is match count
        return result.name.removeprefix("pattern_")


def summarize_failures(
    with_results: list[AssertionResult],
    without_results: list[AssertionResult],
) -> dict[str, str]:
    """Build GEPA-friendly diagnostic strings from assertion results.

    Collects only NEEDS_SKILL and REGRESSION assertions (skips NEUTRAL/POSITIVE)
    and produces structured output that maps to GEPA's standard diagnostic keys.

    Only non-empty keys are included in the returned dict so that GEPA does not
    render empty ``## Header`` sections that waste tokens and confuse the
    reflection LM.

    Returns:
        Dict with a subset of: ``Error``, ``Regressions``.
        ``Error`` carries compact NEEDS_SKILL/REGRESSION tokens that downstream
        consumers (``_review_skillbench``, ``build_skillbench_background``) parse.
        ``Regressions`` is a concise NL summary only present when regressions exist.
    """
    needs_skill: list[tuple[AssertionResult, AssertionResult]] = []
    regressions: list[tuple[AssertionResult, AssertionResult]] = []

    for w, wo in zip(with_results, without_results):
        label = _classify_assertion(w, wo)
        if label == "NEEDS_SKILL":
            needs_skill.append((w, wo))
        elif label == "REGRESSION":
            regressions.append((w, wo))

    result: dict[str, str] = {}

    # Error: compact assertion labels (NEEDS_SKILL/REGRESSION tokens preserved)
    error_lines: list[str] = []
    for w, _ in needs_skill:
        content = _extract_content(w)
        error_lines.append(f"NEEDS_SKILL: {w.assertion_type} — '{content}'")
    for w, _ in regressions:
        content = _extract_content(w)
        error_lines.append(f"REGRESSION: {w.assertion_type} — '{content}'")
    if error_lines:
        result["Error"] = "\n".join(error_lines)

    # Regressions: concise NL (only when non-empty)
    if regressions:
        lines: list[str] = []
        for i, (w, wo) in enumerate(regressions, 1):
            content = _extract_content(w)
            lines.append(f"{i}. '{content}' — passes without skill, fails with it")
        result["Regressions"] = "\n".join(lines)

    return result
