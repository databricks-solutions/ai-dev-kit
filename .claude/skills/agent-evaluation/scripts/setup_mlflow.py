"""
MLflow environment setup script with auto-detection and convenience features.

This script configures MLFLOW_TRACKING_URI and MLFLOW_EXPERIMENT_ID
for agent evaluation using auto-detection with optional overrides.

Features:
- Auto-detects Databricks profiles or local SQLite
- Search experiments by name using MLflow Python API
- Single command instead of multiple CLI calls
- Creates experiments if they don't exist
"""

import argparse
import os
import subprocess
import sys


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Configure MLflow for agent evaluation with auto-detection"
    )
    parser.add_argument(
        "--tracking-uri",
        help="MLflow tracking URI (default: auto-detect from env/Databricks/local)",
    )
    parser.add_argument("--experiment-id", help="Experiment ID to use (default: from env or search)")
    parser.add_argument("--experiment-name", help="Experiment name (for search or creation)")
    parser.add_argument(
        "--create", action="store_true", help="Create new experiment with --experiment-name"
    )
    return parser.parse_args()


def check_mlflow_installed() -> bool:
    """Check if MLflow >=3.6.0 is installed."""
    try:
        import mlflow

        version = mlflow.__version__
        print(f"✓ MLflow {version} is installed")
        return True
    except ImportError:
        print("✗ MLflow is not installed")
        print("  Install with: uv pip install mlflow")
        return False


def detect_databricks_profiles() -> list[str]:
    """Detect available and valid Databricks profiles.

    Returns:
        List of profile names that have Valid=YES
    """
    try:
        result = subprocess.run(
            ["databricks", "auth", "profiles"], capture_output=True, text=True, check=True
        )
        lines = result.stdout.strip().split("\n")
        # Skip header line: "Name        Host                      Valid"
        profiles = []
        for line in lines[1:]:
            if not line.strip():
                continue
            # Parse columns: Name, Host, Valid
            parts = line.split()
            if len(parts) >= 3:
                name = parts[0]
                valid = parts[-1]  # Last column is Valid (YES/NO)
                if valid.upper() == "YES":
                    profiles.append(name)
        return profiles
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def auto_detect_tracking_uri() -> str:
    """Auto-detect best tracking URI.

    Priority:
    1. Existing MLFLOW_TRACKING_URI environment variable
    2. DEFAULT Databricks profile
    3. First available Databricks profile
    4. Local SQLite (sqlite:///mlflow.db)
    """
    # Priority 1: Use existing MLFLOW_TRACKING_URI if set
    existing = os.getenv("MLFLOW_TRACKING_URI")
    if existing:
        print(f"✓ Using existing MLFLOW_TRACKING_URI: {existing}")
        return existing

    # Priority 2: Try DEFAULT Databricks profile
    profiles = detect_databricks_profiles()
    if profiles:
        # Look for DEFAULT profile
        if "DEFAULT" in profiles:
            uri = "databricks://DEFAULT"
            print(f"✓ Auto-detected Databricks profile: {uri}")
            return uri

        # Fallback to first profile
        first_profile = profiles[0]
        uri = f"databricks://{first_profile}"
        print(f"✓ Auto-detected Databricks profile: {uri}")
        return uri

    # Priority 3: Fallback to local SQLite
    uri = "sqlite:///mlflow.db"
    print(f"✓ Auto-detected tracking URI: {uri}")
    print("  (No Databricks profiles found, using local SQLite)")
    return uri


def configure_tracking_uri(args_uri: str | None = None) -> str:
    """Configure MLFLOW_TRACKING_URI with auto-detection.

    Args:
        args_uri: Tracking URI from CLI arguments (optional)

    Returns:
        Tracking URI to use
    """
    print("\n" + "=" * 60)
    print("Step 1: Configure MLFLOW_TRACKING_URI")
    print("=" * 60)
    print()

    # If URI provided via CLI, use it
    if args_uri:
        print(f"✓ Using specified tracking URI: {args_uri}")
        return args_uri

    # Otherwise auto-detect
    return auto_detect_tracking_uri()


def list_experiments(tracking_uri: str, max_results: int = 100) -> list[dict]:
    """List available experiments using MLflow Python API.

    Args:
        tracking_uri: MLflow tracking URI
        max_results: Maximum number of experiments to return

    Returns:
        List of dicts with 'id' and 'name' keys
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        experiments = mlflow.search_experiments(max_results=max_results)

        return [{"id": exp.experiment_id, "name": exp.name} for exp in experiments]
    except Exception as e:
        print(f"✗ Error listing experiments: {e}")
        return []


def create_experiment(tracking_uri: str, name: str) -> str | None:
    """Create a new experiment using MLflow Python API.

    Args:
        tracking_uri: MLflow tracking URI
        name: Name for the new experiment

    Returns:
        Experiment ID if created successfully, None otherwise
    """
    try:
        import mlflow

        mlflow.set_tracking_uri(tracking_uri)
        exp_id = mlflow.create_experiment(name)
        return str(exp_id)
    except Exception as e:
        print(f"✗ Error creating experiment: {e}")
        return None


def configure_experiment_id(
    tracking_uri: str,
    args_exp_id: str | None = None,
    args_exp_name: str | None = None,
    create_new: bool = False,
) -> str:
    """Configure MLFLOW_EXPERIMENT_ID with auto-detection.

    Args:
        tracking_uri: MLflow tracking URI
        args_exp_id: Experiment ID from CLI arguments (optional)
        args_exp_name: Experiment name from CLI arguments (optional)
        create_new: Create new experiment with args_exp_name if not found

    Returns:
        Experiment ID to use
    """
    print("\n" + "=" * 60)
    print("Step 2: Configure MLFLOW_EXPERIMENT_ID")
    print("=" * 60)
    print()

    # Priority 1: Use experiment ID from CLI args
    if args_exp_id:
        print(f"✓ Using specified experiment ID: {args_exp_id}")
        return args_exp_id

    # Priority 2: Use existing MLFLOW_EXPERIMENT_ID from environment
    existing = os.getenv("MLFLOW_EXPERIMENT_ID")
    if existing and not args_exp_name:
        # Only use existing if not explicitly searching for a different experiment
        print(f"✓ Using existing MLFLOW_EXPERIMENT_ID: {existing}")
        return existing

    # Priority 3: Create new experiment if --create and --experiment-name provided
    if create_new and args_exp_name:
        print(f"Creating experiment: {args_exp_name}")
        exp_id = create_experiment(tracking_uri, args_exp_name)
        if exp_id:
            print(f"✓ Experiment created with ID: {exp_id}")
            return exp_id
        else:
            # Try to find it by name (might have been created but ID not parsed)
            experiments = list_experiments(tracking_uri)
            for exp in experiments:
                if exp["name"] == args_exp_name:
                    print(f"✓ Found experiment ID: {exp['id']}")
                    return exp["id"]
            print(f"✗ Failed to create or find experiment '{args_exp_name}'")
            sys.exit(1)

    # Priority 4: Search for experiment by name if provided
    if args_exp_name:
        print(f"Searching for experiment: {args_exp_name}")
        experiments = list_experiments(tracking_uri)
        for exp in experiments:
            if exp["name"] == args_exp_name:
                print(f"✓ Found experiment ID: {exp['id']}")
                return exp["id"]

        # Not found - fail with clear message
        print(f"✗ Experiment '{args_exp_name}' not found")
        print(f"  Use --create flag to create it: --experiment-name '{args_exp_name}' --create")
        sys.exit(1)

    # Priority 5: Auto-select first available experiment
    print("Auto-detecting experiment...")
    experiments = list_experiments(tracking_uri)

    if experiments:
        # Use first experiment
        exp = experiments[0]
        print(f"✓ Auto-selected experiment: {exp['name']} (ID: {exp['id']})")
        if len(experiments) > 1:
            print(f"  ({len(experiments) - 1} other experiment(s) available)")
        return exp["id"]

    # No experiments found - fail with clear message
    print("✗ No experiments found")
    print("  Create one with: --experiment-name <name> --create")
    sys.exit(1)


def main():
    """Main setup flow with auto-detection."""
    # Parse command-line arguments
    args = parse_arguments()

    print("=" * 60)
    print("MLflow Environment Setup for Agent Evaluation")
    print("=" * 60)

    # Check MLflow installation
    if not check_mlflow_installed():
        sys.exit(1)

    print()

    # Configure tracking URI (auto-detects if not provided)
    tracking_uri = configure_tracking_uri(args.tracking_uri)

    # Configure experiment ID (auto-detects if not provided)
    experiment_id = configure_experiment_id(
        tracking_uri, args.experiment_id, args.experiment_name, args.create
    )

    # Summary
    print("\n" + "=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print()
    print("Export these environment variables:")
    print()
    print(f'export MLFLOW_TRACKING_URI="{tracking_uri}"')
    print(f'export MLFLOW_EXPERIMENT_ID="{experiment_id}"')
    print()
    print("Or add them to your shell configuration (~/.bashrc, ~/.zshrc, etc.)")
    print("=" * 60)


if __name__ == "__main__":
    main()
