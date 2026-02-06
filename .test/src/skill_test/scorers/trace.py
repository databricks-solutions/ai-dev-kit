"""Trace-based scorers for evaluating Claude Code session behavior.

These scorers analyze TraceMetrics to verify:
- Tool usage patterns and limits
- Token budgets
- Required/banned tools
- File existence
"""

from typing import Any, Dict, List

from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

from ..trace.models import TraceMetrics


@scorer
def tool_count(
    trace: dict[str, Any],
    expectations: dict[str, Any],
) -> Feedback:
    """Check if tool usage is within specified limits.

    Expectations format:
        tool_limits:
            Bash: 5              # Max 5 Bash calls
            Read: 10             # Max 10 Read calls
            mcp__databricks__execute_sql: 3

    Args:
        trace: TraceMetrics.to_dict() output
        expectations: Dict with tool_limits

    Returns:
        Feedback with yes/no and violations list
    """
    limits = expectations.get("tool_limits", {})
    if not limits:
        return Feedback(
            name="tool_count",
            value="skip",
            rationale="No tool_limits defined in expectations",
        )

    tool_counts = trace.get("tools", {}).get("by_name", {})
    violations = []

    for tool_name, max_count in limits.items():
        actual = tool_counts.get(tool_name, 0)
        if actual > max_count:
            violations.append(f"{tool_name}: {actual} > {max_count}")

    if violations:
        return Feedback(
            name="tool_count",
            value="no",
            rationale=f"Tool limit violations: {'; '.join(violations)}",
        )

    return Feedback(
        name="tool_count",
        value="yes",
        rationale=f"All {len(limits)} tool limits satisfied",
    )


@scorer
def token_budget(
    trace: dict[str, Any],
    expectations: dict[str, Any],
) -> Feedback:
    """Check if token usage is within budget.

    Expectations format:
        token_budget:
            max_input: 50000
            max_output: 10000
            max_total: 60000

    Args:
        trace: TraceMetrics.to_dict() output
        expectations: Dict with token_budget

    Returns:
        Feedback with yes/no and usage details
    """
    budget = expectations.get("token_budget", {})
    if not budget:
        return Feedback(
            name="token_budget",
            value="skip",
            rationale="No token_budget defined in expectations",
        )

    tokens = trace.get("tokens", {})
    violations = []

    if "max_input" in budget:
        actual = tokens.get("input", 0)
        if actual > budget["max_input"]:
            violations.append(f"input: {actual:,} > {budget['max_input']:,}")

    if "max_output" in budget:
        actual = tokens.get("output", 0)
        if actual > budget["max_output"]:
            violations.append(f"output: {actual:,} > {budget['max_output']:,}")

    if "max_total" in budget:
        actual = tokens.get("total", 0)
        if actual > budget["max_total"]:
            violations.append(f"total: {actual:,} > {budget['max_total']:,}")

    if violations:
        return Feedback(
            name="token_budget",
            value="no",
            rationale=f"Token budget exceeded: {'; '.join(violations)}",
        )

    total = tokens.get("total", 0)
    return Feedback(
        name="token_budget",
        value="yes",
        rationale=f"Token usage ({total:,}) within budget",
    )


@scorer
def required_tools(
    trace: dict[str, Any],
    expectations: dict[str, Any],
) -> Feedback:
    """Check if required tools were used.

    Expectations format:
        required_tools:
            - Read
            - mcp__databricks__execute_sql

    Args:
        trace: TraceMetrics.to_dict() output
        expectations: Dict with required_tools list

    Returns:
        Feedback with yes/no and missing tools
    """
    required = expectations.get("required_tools", [])
    if not required:
        return Feedback(
            name="required_tools",
            value="skip",
            rationale="No required_tools defined in expectations",
        )

    tool_counts = trace.get("tools", {}).get("by_name", {})
    missing = [tool for tool in required if tool not in tool_counts]

    if missing:
        return Feedback(
            name="required_tools",
            value="no",
            rationale=f"Missing required tools: {missing}",
        )

    return Feedback(
        name="required_tools",
        value="yes",
        rationale=f"All {len(required)} required tools were used",
    )


@scorer
def banned_tools(
    trace: dict[str, Any],
    expectations: dict[str, Any],
) -> Feedback:
    """Check that banned tools were not used.

    Expectations format:
        banned_tools:
            - Write  # Prevent file creation
            - Bash   # Prevent shell commands

    Args:
        trace: TraceMetrics.to_dict() output
        expectations: Dict with banned_tools list

    Returns:
        Feedback with yes/no and violations
    """
    banned = expectations.get("banned_tools", [])
    if not banned:
        return Feedback(
            name="banned_tools",
            value="skip",
            rationale="No banned_tools defined in expectations",
        )

    tool_counts = trace.get("tools", {}).get("by_name", {})
    violations = [tool for tool in banned if tool in tool_counts]

    if violations:
        counts = {t: tool_counts[t] for t in violations}
        return Feedback(
            name="banned_tools",
            value="no",
            rationale=f"Banned tools used: {counts}",
        )

    return Feedback(
        name="banned_tools",
        value="yes",
        rationale=f"None of {len(banned)} banned tools were used",
    )


@scorer
def file_existence(
    trace: dict[str, Any],
    expectations: dict[str, Any],
) -> Feedback:
    """Check if expected files were created.

    Expectations format:
        expected_files:
            - "*.sql"           # Glob pattern
            - "bronze_*.py"     # Specific pattern
            - "/path/to/file"   # Exact path

    Args:
        trace: TraceMetrics.to_dict() output
        expectations: Dict with expected_files list

    Returns:
        Feedback with yes/no and missing files
    """
    import fnmatch

    expected = expectations.get("expected_files", [])
    if not expected:
        return Feedback(
            name="file_existence",
            value="skip",
            rationale="No expected_files defined in expectations",
        )

    files = trace.get("files", {})
    created = files.get("created", [])
    modified = files.get("modified", [])
    all_written = created + modified

    missing = []
    for pattern in expected:
        # Check if any written file matches the pattern
        matched = any(
            fnmatch.fnmatch(f, pattern) or pattern in f for f in all_written
        )
        if not matched:
            missing.append(pattern)

    if missing:
        return Feedback(
            name="file_existence",
            value="no",
            rationale=f"Missing expected files: {missing}",
        )

    return Feedback(
        name="file_existence",
        value="yes",
        rationale=f"All {len(expected)} expected file patterns matched",
    )


@scorer
def tool_sequence(
    trace: dict[str, Any],
    expectations: dict[str, Any],
) -> Feedback:
    """Check if tools were used in expected order.

    Expectations format:
        tool_sequence:
            - Read      # First: read existing code
            - Edit      # Then: modify it
            - Bash      # Finally: run tests

    Args:
        trace: TraceMetrics.to_dict() output
        expectations: Dict with tool_sequence list

    Returns:
        Feedback with yes/no and sequence analysis
    """
    expected_sequence = expectations.get("tool_sequence", [])
    if not expected_sequence:
        return Feedback(
            name="tool_sequence",
            value="skip",
            rationale="No tool_sequence defined in expectations",
        )

    # Get tool call order from trace
    # Note: This requires the full tool_calls list, not just counts
    # For now, we check that all tools appear and in relative order
    tool_counts = trace.get("tools", {}).get("by_name", {})

    # Check all required tools were used
    missing = [t for t in expected_sequence if t not in tool_counts]
    if missing:
        return Feedback(
            name="tool_sequence",
            value="no",
            rationale=f"Sequence tools not used: {missing}",
        )

    return Feedback(
        name="tool_sequence",
        value="yes",
        rationale=f"All {len(expected_sequence)} sequence tools were used",
    )


@scorer
def category_limits(
    trace: dict[str, Any],
    expectations: dict[str, Any],
) -> Feedback:
    """Check if tool category usage is within limits.

    Expectations format:
        category_limits:
            bash: 10           # Max 10 bash commands
            file_ops: 20       # Max 20 file operations
            mcp_databricks: 5  # Max 5 Databricks MCP calls

    Args:
        trace: TraceMetrics.to_dict() output
        expectations: Dict with category_limits

    Returns:
        Feedback with yes/no and violations
    """
    limits = expectations.get("category_limits", {})
    if not limits:
        return Feedback(
            name="category_limits",
            value="skip",
            rationale="No category_limits defined in expectations",
        )

    category_counts = trace.get("tools", {}).get("by_category", {})
    violations = []

    for category, max_count in limits.items():
        actual = category_counts.get(category, 0)
        if actual > max_count:
            violations.append(f"{category}: {actual} > {max_count}")

    if violations:
        return Feedback(
            name="category_limits",
            value="no",
            rationale=f"Category limit violations: {'; '.join(violations)}",
        )

    return Feedback(
        name="category_limits",
        value="yes",
        rationale=f"All {len(limits)} category limits satisfied",
    )


# Convenience function to get all trace scorers
def get_trace_scorers() -> list:
    """Get list of all trace-based scorers."""
    return [
        tool_count,
        token_budget,
        required_tools,
        banned_tools,
        file_existence,
        tool_sequence,
        category_limits,
    ]
