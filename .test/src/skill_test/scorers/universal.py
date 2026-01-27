"""Tier 1 deterministic scorers - fast and reliable."""
from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback
import ast
import re
from typing import Dict, Any, List


@scorer
def python_syntax(outputs: Dict[str, Any]) -> Feedback:
    """Check if Python code blocks have valid syntax."""
    response = outputs.get("response", "")

    python_blocks = re.findall(r'```python\n(.*?)```', response, re.DOTALL)

    if not python_blocks:
        return Feedback(
            name="python_syntax",
            value="skip",
            rationale="No Python code blocks found"
        )

    errors = []
    for i, block in enumerate(python_blocks):
        try:
            ast.parse(block)
        except SyntaxError as e:
            errors.append(f"Block {i+1}: {e.msg} at line {e.lineno}")

    if errors:
        return Feedback(
            name="python_syntax",
            value="no",
            rationale=f"Syntax errors: {'; '.join(errors)}"
        )

    return Feedback(
        name="python_syntax",
        value="yes",
        rationale=f"All {len(python_blocks)} Python blocks parse successfully"
    )


@scorer
def sql_syntax(outputs: Dict[str, Any]) -> Feedback:
    """Basic SQL syntax validation (structural checks)."""
    response = outputs.get("response", "")

    sql_blocks = re.findall(r'```sql\n(.*?)```', response, re.DOTALL)

    if not sql_blocks:
        return Feedback(
            name="sql_syntax",
            value="skip",
            rationale="No SQL code blocks found"
        )

    errors = []
    for i, block in enumerate(sql_blocks):
        if not re.search(r'(SELECT|CREATE|INSERT|UPDATE|DELETE|WITH|MERGE)', block, re.I):
            errors.append(f"Block {i+1}: No recognizable SQL statement")
        if block.count('(') != block.count(')'):
            errors.append(f"Block {i+1}: Unbalanced parentheses")

    if errors:
        return Feedback(
            name="sql_syntax",
            value="no",
            rationale=f"SQL issues: {'; '.join(errors)}"
        )

    return Feedback(
        name="sql_syntax",
        value="yes",
        rationale=f"All {len(sql_blocks)} SQL blocks look valid"
    )


@scorer
def pattern_adherence(
    outputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> List[Feedback]:
    """Check for required patterns in response."""
    response = outputs.get("response", "")
    expected_patterns = expectations.get("expected_patterns", [])

    if not expected_patterns:
        return [Feedback(
            name="pattern_adherence",
            value="skip",
            rationale="No expected_patterns defined"
        )]

    feedbacks = []
    for pattern_spec in expected_patterns:
        if isinstance(pattern_spec, str):
            pattern = pattern_spec
            min_count = 1
            description = pattern[:30]
        else:
            pattern = pattern_spec["pattern"]
            min_count = pattern_spec.get("min_count", 1)
            description = pattern_spec.get("description", pattern[:30])

        matches = len(re.findall(pattern, response, re.IGNORECASE))
        passed = matches >= min_count

        feedbacks.append(Feedback(
            name=f"pattern_{description}",
            value="yes" if passed else "no",
            rationale=f"Found {matches} matches (need {min_count})"
        ))

    return feedbacks


@scorer
def no_hallucinated_apis(outputs: Dict[str, Any]) -> Feedback:
    """Check for common API hallucinations in Databricks context."""
    response = outputs.get("response", "")

    hallucinations = [
        (r'@dlt\.table', "Legacy @dlt.table - should use @dp.table"),
        (r'dlt\.read', "Legacy dlt.read - use spark.read or dp.read"),
        (r'PARTITION BY', "PARTITION BY deprecated - use CLUSTER BY"),
        (r'mlflow\.evaluate\(', "Old mlflow.evaluate - use mlflow.genai.evaluate"),
    ]

    found = []
    for pattern, description in hallucinations:
        if re.search(pattern, response):
            found.append(description)

    if found:
        return Feedback(
            name="no_hallucinated_apis",
            value="no",
            rationale=f"Issues: {'; '.join(found)}"
        )

    return Feedback(
        name="no_hallucinated_apis",
        value="yes",
        rationale="No common API hallucinations detected"
    )


@scorer
def expected_facts_present(
    outputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> Feedback:
    """Check if expected facts are mentioned in response."""
    response = outputs.get("response", "").lower()
    expected_facts = expectations.get("expected_facts", [])

    if not expected_facts:
        return Feedback(
            name="expected_facts",
            value="skip",
            rationale="No expected_facts defined"
        )

    missing = []
    for fact in expected_facts:
        if fact.lower() not in response:
            missing.append(fact)

    if missing:
        return Feedback(
            name="expected_facts",
            value="no",
            rationale=f"Missing facts: {missing}"
        )

    return Feedback(
        name="expected_facts",
        value="yes",
        rationale=f"All {len(expected_facts)} expected facts present"
    )
