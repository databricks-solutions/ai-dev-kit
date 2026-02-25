"""Skill routing scorer - evaluates Claude Code's skill selection."""

from mlflow.genai.scorers import scorer
from mlflow.entities import Feedback
from typing import Dict, Any, Set

# Skill trigger patterns (extracted from SKILL.md description fields)
SKILL_TRIGGERS = {
    "databricks-spark-declarative-pipelines": [
        "streaming table",
        "dlt",
        "delta live",
        "lakeflow",
        "sdp",
        "ldp",
        "medallion",
        "bronze",
        "silver",
        "gold",
        "cdc",
        "change data capture",
        "scd",
        "auto loader",
    ],
    # APX = FastAPI + React full-stack. "fastapi react" triggers APX specifically;
    # bare "fastapi" triggers python skill. A prompt mentioning both (e.g. "FastAPI React app")
    # will correctly match both skills, letting the router pick the best fit.
    "databricks-app-apx": [
        "databricks app",
        "apx",
        "full-stack app",
        "fastapi react",
        "react frontend",
    ],
    "databricks-app-python": [
        "python app",
        "streamlit",
        "dash",
        "flask",
        "gradio",
        "fastapi",
        "reflex",
        "dashboard app",
        "data app",
    ],
    "databricks-asset-bundles": ["dabs", "databricks asset bundle", "deploy", "bundle.yaml"],
    "databricks-python-sdk": [
        "python sdk",
        "databricks-sdk",
        "workspaceclient",
        "databricks connect",
        "rest api",
    ],
    "databricks-jobs": ["job", "workflow", "task", "schedule", "trigger"],
    "databricks-synthetic-data-generation": [
        "synthetic data",
        "fake data",
        "generate data",
        "mock data",
        "faker",
    ],
    "databricks-mlflow-evaluation": [
        "mlflow eval",
        "evaluate agent",
        "scorer",
        "genai.evaluate",
        "llm judge",
    ],
    "databricks-agent-bricks": [
        "agent brick",
        "knowledge assistant",
        "genie",
        "multi-agent",
        "supervisor",
    ],
    "databricks-lakebase-provisioned": ["lakebase", "postgresql", "postgres"],
    "databricks-model-serving": ["model serving", "serving endpoint", "inference endpoint"],
}


def detect_skills_from_prompt(prompt: str) -> Set[str]:
    """Detect which skills a prompt should trigger."""
    prompt_lower = prompt.lower()
    detected = set()

    for skill, triggers in SKILL_TRIGGERS.items():
        for trigger in triggers:
            if trigger in prompt_lower:
                detected.add(skill)
                break

    return detected


@scorer
def skill_routing_accuracy(inputs: Dict[str, Any], expectations: Dict[str, Any]) -> Feedback:
    """
    Score skill routing accuracy.

    Compares detected skills from prompt against expected skills.
    Handles both single-skill and multi-skill scenarios.
    """
    prompt = inputs.get("prompt", "").lower()
    expected_skills = set(expectations.get("expected_skills", []))
    is_multi_skill = expectations.get("is_multi_skill", False)

    detected_skills = detect_skills_from_prompt(prompt)

    # Both empty = correct (no skill should match)
    if not expected_skills and not detected_skills:
        return Feedback(
            name="routing_accuracy",
            value="yes",
            rationale="Correctly identified no skill match",
        )

    # Expected none but got some
    if not expected_skills:
        return Feedback(
            name="routing_accuracy",
            value="no",
            rationale=f"Expected no skills but detected: {detected_skills}",
        )

    # Expected some but got none
    if not detected_skills:
        return Feedback(
            name="routing_accuracy",
            value="no",
            rationale=f"Expected {expected_skills} but no skills detected",
        )

    # Check overlap
    if is_multi_skill:
        # For multi-skill: all expected skills should be detected
        missing = expected_skills - detected_skills
        if not missing:
            return Feedback(
                name="routing_accuracy",
                value="yes",
                rationale=f"All expected skills detected: {detected_skills}",
            )
        else:
            return Feedback(
                name="routing_accuracy",
                value="no",
                rationale=f"Missing skills: {missing}. Detected: {detected_skills}",
            )
    else:
        # For single-skill: expected should be subset of detected
        if expected_skills <= detected_skills:
            return Feedback(
                name="routing_accuracy",
                value="yes",
                rationale=f"Expected skill(s) detected. Expected: {expected_skills}, Got: {detected_skills}",
            )
        else:
            return Feedback(
                name="routing_accuracy",
                value="no",
                rationale=f"Expected: {expected_skills}, Detected: {detected_skills}",
            )


@scorer
def routing_precision(inputs: Dict[str, Any], expectations: Dict[str, Any]) -> Feedback:
    """Measure precision - avoid false positives (extra skills)."""
    prompt = inputs.get("prompt", "")
    expected_skills = set(expectations.get("expected_skills", []))
    detected_skills = detect_skills_from_prompt(prompt)

    if not detected_skills:
        return Feedback(
            name="routing_precision",
            value=1.0,
            rationale="No skills detected (no false positives possible)",
        )

    correct = expected_skills & detected_skills
    precision = len(correct) / len(detected_skills)

    return Feedback(
        name="routing_precision",
        value=precision,
        rationale=f"Precision: {len(correct)}/{len(detected_skills)}",
    )


@scorer
def routing_recall(inputs: Dict[str, Any], expectations: Dict[str, Any]) -> Feedback:
    """Measure recall - avoid false negatives (missing skills)."""
    prompt = inputs.get("prompt", "")
    expected_skills = set(expectations.get("expected_skills", []))

    if not expected_skills:
        return Feedback(
            name="routing_recall",
            value=1.0,
            rationale="No expected skills (recall not applicable)",
        )

    detected_skills = detect_skills_from_prompt(prompt)
    correct = expected_skills & detected_skills
    recall = len(correct) / len(expected_skills)

    return Feedback(
        name="routing_recall",
        value=recall,
        rationale=f"Recall: {len(correct)}/{len(expected_skills)}",
    )
