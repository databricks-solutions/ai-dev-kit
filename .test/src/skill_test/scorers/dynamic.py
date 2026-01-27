"""Dynamic scorers that use test case expectations from YAML config."""
from mlflow.genai.scorers import scorer, Guidelines
from mlflow.entities import Feedback
from typing import Dict, Any, List


@scorer
def guidelines_from_expectations(
    inputs: Dict[str, Any],
    outputs: Dict[str, Any],
    expectations: Dict[str, Any]
) -> Feedback:
    """Dynamic Guidelines scorer that uses expectations.guidelines from YAML.

    This scorer reads guidelines from the test case's expectations section,
    allowing per-test customization of evaluation criteria.

    Args:
        inputs: The test inputs (e.g., prompt)
        outputs: The skill outputs (e.g., response)
        expectations: Test expectations including optional guidelines list

    Returns:
        Feedback from Guidelines judge, or skip if no guidelines defined
    """
    guidelines = expectations.get("guidelines", [])

    if not guidelines:
        return Feedback(
            name="guidelines",
            value="skip",
            rationale="No guidelines defined in expectations"
        )

    # Create a Guidelines instance with the test-specific guidelines
    judge = Guidelines(name="guidelines", guidelines=guidelines)

    # Call the judge - it returns Feedback
    return judge(inputs=inputs, outputs=outputs)


def create_guidelines_scorer(
    guidelines: List[str],
    name: str = "skill_quality"
) -> Guidelines:
    """Factory to create a Guidelines scorer with specific guidelines.

    Use this when you want to create a Guidelines scorer with fixed
    guidelines (e.g., from manifest default_guidelines).

    Args:
        guidelines: List of guideline strings
        name: Name for the scorer

    Returns:
        Configured Guidelines scorer instance
    """
    return Guidelines(name=name, guidelines=guidelines)
