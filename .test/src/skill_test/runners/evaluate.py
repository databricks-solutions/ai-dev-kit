"""Main evaluation runner with MLflow integration."""

from pathlib import Path
from typing import Optional, Dict, Any, List
import yaml
import mlflow
from mlflow.genai.scorers import Safety

from ..config import SkillTestConfig
from ..dataset import get_dataset_source
from ..scorers.universal import (
    python_syntax,
    sql_syntax,
    pattern_adherence,
    no_hallucinated_apis,
    expected_facts_present,
)
from ..scorers.routing import skill_routing_accuracy, routing_precision, routing_recall
from ..scorers.dynamic import guidelines_from_expectations, create_guidelines_scorer


def setup_mlflow(config: SkillTestConfig) -> None:
    """Configure MLflow from environment variables."""
    mlflow.set_tracking_uri(config.mlflow.tracking_uri)
    mlflow.set_experiment(config.mlflow.experiment_name)


def load_scorer_config(
    skill_name: str, base_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Load scorer configuration from skill manifest.

    Args:
        skill_name: Name of the skill
        base_path: Base path to skills directory (defaults to standard location)

    Returns:
        Scorer configuration dict from manifest, or empty dict if not found
    """
    if base_path is None:
        # Default to the standard skills directory relative to this file
        base_path = Path(__file__).parent.parent.parent / "skills"

    manifest_path = base_path / skill_name / "manifest.yaml"
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f) or {}

        # Support both new flat format and existing nested format
        if "scorers" in manifest:
            return manifest["scorers"]
        elif "evaluation" in manifest and "scorers" in manifest["evaluation"]:
            # Legacy format: convert to new format
            eval_scorers = manifest["evaluation"]["scorers"]
            return {
                "enabled": eval_scorers.get("tier1", [])
                + eval_scorers.get("tier2", []),
                "llm_scorers": eval_scorers.get("tier3", []),
            }

    return {}


def build_scorers(scorer_config: Dict[str, Any]) -> List:
    """Build scorer list from configuration.

    Args:
        scorer_config: Scorer configuration from manifest

    Returns:
        List of configured scorer instances
    """
    # Map of available deterministic scorers
    SCORER_MAP = {
        "python_syntax": python_syntax,
        "sql_syntax": sql_syntax,
        "pattern_adherence": pattern_adherence,
        "no_hallucinated_apis": no_hallucinated_apis,
        "expected_facts_present": expected_facts_present,
        # Routing scorers
        "skill_routing_accuracy": skill_routing_accuracy,
        "routing_precision": routing_precision,
        "routing_recall": routing_recall,
    }

    scorers = []

    # Add enabled deterministic scorers
    for name in scorer_config.get("enabled", []):
        if name in SCORER_MAP:
            scorers.append(SCORER_MAP[name])

    # Add LLM scorers
    for name in scorer_config.get("llm_scorers", []):
        if name == "Safety":
            scorers.append(Safety())
        elif name == "guidelines_from_expectations":
            scorers.append(guidelines_from_expectations)
        elif name == "Guidelines":
            # Use default guidelines from manifest, or fallback defaults
            default_guidelines = scorer_config.get(
                "default_guidelines",
                [
                    "Response must address the user's request completely",
                    "Code examples must follow documented best practices",
                    "Response must use modern APIs (not deprecated ones)",
                ],
            )
            scorers.append(
                create_guidelines_scorer(default_guidelines, "skill_quality")
            )
        elif name.startswith("Guidelines:"):
            # Custom named guidelines: "Guidelines:my_name"
            custom_name = name.split(":", 1)[1]
            default_guidelines = scorer_config.get("default_guidelines", [])
            if default_guidelines:
                scorers.append(
                    create_guidelines_scorer(default_guidelines, custom_name)
                )

    return scorers


def get_default_scorers() -> List:
    """Get the default scorer list when no manifest config exists.

    Returns:
        List of default scorers (deterministic + LLM-based)
    """
    return [
        python_syntax,
        sql_syntax,
        pattern_adherence,
        no_hallucinated_apis,
        expected_facts_present,
        Safety(),
        guidelines_from_expectations,  # Dynamic: uses expectations.guidelines from each test
    ]


def evaluate_skill(
    skill_name: str,
    config: Optional[SkillTestConfig] = None,
    run_name: Optional[str] = None,
    filter_category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Evaluate a skill using pre-computed outputs (Pattern 2).

    Args:
        skill_name: Name of skill to evaluate
        config: Configuration (uses defaults if None)
        run_name: MLflow run name
        filter_category: Filter test cases by category

    Returns:
        Evaluation results dict with metrics and run_id
    """
    if config is None:
        config = SkillTestConfig()

    setup_mlflow(config)

    # Load ground truth
    dataset_source = get_dataset_source(skill_name)
    records = dataset_source.load()

    # Filter if requested
    if filter_category:
        records = [
            r
            for r in records
            if r.metadata and r.metadata.get("category") == filter_category
        ]

    # Convert to MLflow format (Pattern 2: pre-computed outputs)
    eval_data = [r.to_eval_dict() for r in records]

    # Load scorer configuration from manifest
    scorer_config = load_scorer_config(skill_name)

    # Build scorer list from config, or use defaults
    if scorer_config:
        scorers = build_scorers(scorer_config)
    else:
        scorers = get_default_scorers()

    # Run evaluation
    with mlflow.start_run(run_name=run_name or f"{skill_name}_eval"):
        mlflow.set_tags(
            {
                "skill_name": skill_name,
                "test_count": len(eval_data),
                "filter_category": filter_category or "all",
            }
        )

        # No predict_fn - using pre-computed outputs
        results = mlflow.genai.evaluate(data=eval_data, scorers=scorers)

        return {
            "run_id": mlflow.active_run().info.run_id,
            "metrics": results.metrics,
            "skill_name": skill_name,
            "test_count": len(eval_data),
        }


def evaluate_routing(
    config: Optional[SkillTestConfig] = None, run_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Evaluate skill routing accuracy.

    Tests Claude Code's ability to route prompts to correct skills.
    """
    if config is None:
        config = SkillTestConfig()

    setup_mlflow(config)

    # Load routing test cases
    dataset_source = get_dataset_source("_routing")
    records = dataset_source.load()

    # Convert to MLflow format
    eval_data = [
        {
            "inputs": {"prompt": r.inputs.get("prompt", "")},
            "expectations": r.expectations or {},
        }
        for r in records
    ]

    # Routing-specific scorers
    scorers = [skill_routing_accuracy, routing_precision, routing_recall]

    with mlflow.start_run(run_name=run_name or "routing_eval"):
        mlflow.set_tags({"evaluation_type": "routing", "test_count": len(eval_data)})

        results = mlflow.genai.evaluate(data=eval_data, scorers=scorers)

        return {
            "run_id": mlflow.active_run().info.run_id,
            "metrics": results.metrics,
            "evaluation_type": "routing",
            "test_count": len(eval_data),
        }
