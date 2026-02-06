"""Configuration for skill-test framework."""
import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class QualityGate:
    """A single quality gate threshold."""
    metric: str
    threshold: float
    comparison: str = ">="  # >=, >, ==, <, <=


@dataclass
class QualityGates:
    """Quality thresholds that must pass for evaluation success."""
    gates: list[QualityGate] = field(default_factory=lambda: [
        QualityGate("syntax_valid/score/mean", 1.0),        # 100% - all code must parse
        QualityGate("pattern_adherence/score/mean", 0.90),  # 90% - follow patterns
        QualityGate("no_hallucinated_apis/score/mean", 1.0),# 100% - no fake APIs
        QualityGate("execution_success/score/mean", 0.80),  # 80% - code runs
        QualityGate("routing_accuracy/score/mean", 0.90),   # 90% - correct routing
    ])


@dataclass
class DatabricksAuthConfig:
    """Databricks authentication configuration.

    Uses OAuth via config profile by default. The profile should be configured
    in ~/.databrickscfg with OAuth credentials.
    """
    config_profile: str = field(
        default_factory=lambda: os.getenv("DATABRICKS_CONFIG_PROFILE", "DEFAULT")
    )

    def apply(self) -> None:
        """Apply auth config by setting environment variables for MLflow.

        Reads the Databricks config profile and sets DATABRICKS_HOST
        so MLflow can authenticate properly. Does NOT overwrite if
        DATABRICKS_HOST is already set (e.g., from .env file).
        """
        os.environ["DATABRICKS_CONFIG_PROFILE"] = self.config_profile

        # Only set DATABRICKS_HOST if not already set (respect .env)
        if os.getenv("DATABRICKS_HOST"):
            return

        # Set DATABRICKS_HOST from profile for MLflow
        try:
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient(profile=self.config_profile)
            os.environ["DATABRICKS_HOST"] = w.config.host
        except Exception:
            # Fallback: try to read from databrickscfg directly
            import configparser
            from pathlib import Path

            cfg_path = Path.home() / ".databrickscfg"
            if cfg_path.exists():
                config = configparser.ConfigParser()
                config.read(cfg_path)
                if self.config_profile in config:
                    host = config[self.config_profile].get("host")
                    if host:
                        os.environ["DATABRICKS_HOST"] = host


@dataclass
class MLflowConfig:
    """MLflow configuration from environment variables.

    If DATABRICKS_CONFIG_PROFILE is set, uses databricks://<profile> as tracking URI.
    This ensures MLflow uses the correct workspace from the profile.
    """
    tracking_uri: str = field(default_factory=lambda: _get_mlflow_tracking_uri())
    experiment_name: str = field(
        default_factory=lambda: os.getenv(
            "MLFLOW_EXPERIMENT_NAME",
            "/Shared/skill-tests"
        )
    )


def _get_mlflow_tracking_uri() -> str:
    """Determine MLflow tracking URI, respecting DATABRICKS_CONFIG_PROFILE."""
    # If explicit tracking URI is set, use it
    if os.getenv("MLFLOW_TRACKING_URI"):
        return os.getenv("MLFLOW_TRACKING_URI")

    # If profile is set, use databricks://<profile> to ensure correct workspace
    profile = os.getenv("DATABRICKS_CONFIG_PROFILE")
    if profile:
        return f"databricks://{profile}"

    # Default to databricks (uses DEFAULT profile)
    return "databricks"


@dataclass
class DatabricksExecutionSettings:
    """Settings for Databricks code execution.

    By default, uses serverless compute. Only specify cluster_id if you
    explicitly need a specific cluster.
    """
    # Compute settings
    cluster_id: str | None = None  # Only set if user explicitly specifies
    warehouse_id: str | None = None  # Auto-detected if None
    use_serverless: bool = True  # Default to serverless compute

    # Catalog/schema context
    catalog: str = field(
        default_factory=lambda: os.getenv("SKILL_TEST_CATALOG", "main")
    )
    schema: str = field(
        default_factory=lambda: os.getenv("SKILL_TEST_SCHEMA", "skill_test")
    )

    # Execution settings
    timeout: int = 120  # seconds
    preserve_context: bool = True  # Reuse context across code blocks


@dataclass
class SkillTestConfig:
    """Main configuration for skill-test framework."""
    auth: DatabricksAuthConfig = field(default_factory=DatabricksAuthConfig)
    quality_gates: QualityGates = field(default_factory=QualityGates)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)
    databricks: DatabricksExecutionSettings = field(default_factory=DatabricksExecutionSettings)

    def __post_init__(self):
        """Apply auth configuration on initialization."""
        self.auth.apply()

    # Paths
    skills_root: str = ".claude/skills"
    test_definitions_path: str = ".test/skills"

    # GRP settings
    grp_timeout_seconds: int = 30
    grp_max_retries: int = 3
    human_review_required: bool = True  # Always True for ground truth

    # Interactive settings
    auto_approve_on_success: bool = True  # Auto-save to ground_truth if all blocks pass
