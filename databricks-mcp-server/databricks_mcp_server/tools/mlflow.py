"""MLflow tools - Manage experiments, runs, metrics, artifacts, and model registry."""

from typing import Any, Dict, List, Optional

from databricks_tools_core.identity import get_default_tags
from databricks_tools_core.mlflow import (
    get_experiment as _get_experiment,
    list_experiments as _list_experiments,
    search_experiments as _search_experiments,
    create_experiment as _create_experiment,
    set_experiment_tag as _set_experiment_tag,
    delete_experiment as _delete_experiment,
    get_run as _get_run,
    search_runs as _search_runs,
    get_run_metrics_history as _get_run_metrics_history,
    list_run_artifacts as _list_run_artifacts,
    get_registered_model as _get_registered_model,
    list_registered_models as _list_registered_models,
    search_registered_models as _search_registered_models,
    get_model_version as _get_model_version,
    list_model_versions as _list_model_versions,
    get_model_version_by_alias as _get_model_version_by_alias,
    set_model_alias as _set_model_alias,
    delete_model_alias as _delete_model_alias,
)

from ..manifest import register_deleter, track_resource, remove_resource
from ..server import mcp


# Register deleter for experiment cleanup
def _delete_experiment_resource(resource_id: str) -> None:
    _delete_experiment(experiment_id=resource_id)


register_deleter("mlflow_experiment", _delete_experiment_resource)


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


@mcp.tool(timeout=30)
def get_mlflow_experiment(
    experiment_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get an MLflow experiment by ID or name.

    Use this to inspect experiment details, check lifecycle stage,
    or look up an experiment before searching its runs.

    Args:
        experiment_id: Experiment ID (numeric string, e.g. "123456789")
        name: Full experiment path (e.g. "/Users/user@example.com/my-experiment").
            Provide exactly one of experiment_id or name.

    Returns:
        Dictionary with experiment details:
        - experiment_id: Unique ID
        - name: Full experiment path
        - lifecycle_stage: "active" or "deleted"
        - tags: Dict of experiment tags
        - creation_time: Creation timestamp (ms)

    Example:
        >>> get_mlflow_experiment(experiment_id="123456789")
        {"experiment_id": "123456789", "name": "/Users/...", "lifecycle_stage": "active"}
    """
    return _get_experiment(experiment_id=experiment_id, name=name)


@mcp.tool(timeout=30)
def list_mlflow_experiments(
    max_results: int = 50,
    view_type: str = "ACTIVE_ONLY",
) -> Dict[str, Any]:
    """
    List MLflow experiments in the workspace.

    Use this to discover experiments, browse recent work, or find
    experiments by lifecycle stage.

    Args:
        max_results: Maximum experiments to return (default: 50)
        view_type: Filter by lifecycle. One of:
            "ACTIVE_ONLY" (default), "DELETED_ONLY", "ALL"

    Returns:
        Dictionary with:
        - experiments: List of experiment dicts
        - count: Number returned

    Example:
        >>> list_mlflow_experiments(max_results=10)
        {"experiments": [...], "count": 10}
    """
    return _list_experiments(max_results=max_results, view_type=view_type)


@mcp.tool(timeout=30)
def search_mlflow_experiments(
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
    view_type: str = "ACTIVE_ONLY",
) -> Dict[str, Any]:
    """
    Search MLflow experiments with filters.

    Use this to find experiments by name pattern, tags, or other attributes.

    Args:
        filter_string: Filter expression. Examples:
            - "name LIKE '%my-project%'"
            - "tags.team = 'ml-eng'"
            - "tags.`mlflow.experimentType` = 'MLFLOW_EXPERIMENT'"
        max_results: Maximum experiments to return (default: 50)
        order_by: Sort fields (e.g. ["last_update_time DESC"])
        view_type: "ACTIVE_ONLY" (default), "DELETED_ONLY", or "ALL"

    Returns:
        Dictionary with:
        - experiments: List of matching experiment dicts
        - count: Number returned

    Example:
        >>> search_mlflow_experiments(filter_string="name LIKE '%churn%'")
        {"experiments": [...], "count": 3}
    """
    return _search_experiments(
        filter_string=filter_string,
        max_results=max_results,
        order_by=order_by,
        view_type=view_type,
    )


@mcp.tool(timeout=60)
def create_mlflow_experiment(
    name: str,
    experiment_kind: Optional[str] = None,
    artifact_location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Create a new MLflow experiment.

    Use this to set up a new experiment for organizing runs.
    Experiment names must be unique in the workspace.

    Args:
        name: Experiment name/path (e.g. "/Users/user@example.com/my-experiment")
        experiment_kind: Controls experiment type in the UI:
            - "genai" — GenAI apps & agents (tracing, LLM evaluation)
            - "ml" — Machine learning (traditional ML training)
            - None — no kind set (default)
        artifact_location: Optional custom artifact storage location
        tags: Optional dict of tags (e.g. {"team": "ml-eng"})

    Returns:
        Dictionary with:
        - experiment_id: ID of the created experiment
        - name: Experiment name
        - status: "created" or "already_exists"

    Example:
        >>> create_mlflow_experiment("/Users/me/my-agent", experiment_kind="genai")
        {"experiment_id": "123", "name": "/Users/me/my-agent", "status": "created"}
    """
    merged_tags = {**get_default_tags(), **(tags or {})}

    result = _create_experiment(
        name=name, experiment_kind=experiment_kind, artifact_location=artifact_location, tags=merged_tags
    )

    if result.get("status") == "created":
        try:
            track_resource(
                resource_type="mlflow_experiment",
                name=name,
                resource_id=result["experiment_id"],
            )
        except Exception:
            pass

    return result


@mcp.tool(timeout=30)
def set_mlflow_experiment_tag(
    experiment_id: str,
    key: str,
    value: str,
) -> Dict[str, Any]:
    """
    Set a tag on an MLflow experiment.

    Use this to add metadata, change the experiment kind, or label
    experiments for organization. Setting an existing key overwrites it.

    Args:
        experiment_id: Experiment ID (numeric string)
        key: Tag key (e.g. "team", "mlflow.experimentKind")
        value: Tag value

    Returns:
        Dictionary with:
        - experiment_id, key, value, status: "set"

    Example:
        >>> set_mlflow_experiment_tag("123", "mlflow.experimentKind", "genai_development")
        {"experiment_id": "123", "key": "mlflow.experimentKind", "value": "genai_development", "status": "set"}
    """
    return _set_experiment_tag(experiment_id=experiment_id, key=key, value=value)


@mcp.tool(timeout=30)
def delete_mlflow_experiment(experiment_id: str) -> Dict[str, Any]:
    """
    Delete (soft-delete) an MLflow experiment.

    The experiment moves to "deleted" lifecycle stage. It can be restored
    from the MLflow UI or API. All runs within it are also soft-deleted.

    Args:
        experiment_id: ID of the experiment to delete

    Returns:
        Dictionary with:
        - experiment_id: The deleted experiment ID
        - status: "deleted" or "not_found"

    Example:
        >>> delete_mlflow_experiment("123456789")
        {"experiment_id": "123456789", "status": "deleted"}
    """
    result = _delete_experiment(experiment_id=experiment_id)

    if result.get("status") == "deleted":
        try:
            remove_resource(resource_type="mlflow_experiment", resource_id=experiment_id)
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@mcp.tool(timeout=30)
def get_mlflow_run(run_id: str) -> Dict[str, Any]:
    """
    Get details for an MLflow run.

    Use this to inspect a specific run's metrics, parameters, tags,
    and status. Returns the latest value for each metric.

    Args:
        run_id: The run ID (UUID string)

    Returns:
        Dictionary with:
        - run_id: Unique run ID
        - run_name: Display name
        - experiment_id: Parent experiment ID
        - status: RUNNING, FINISHED, FAILED, KILLED
        - metrics: Dict of latest metric values
        - params: Dict of logged parameters
        - tags: Dict of run tags

    Example:
        >>> get_mlflow_run("abc123def456")
        {"run_id": "abc123...", "status": "FINISHED", "metrics": {"accuracy": 0.95}}
    """
    return _get_run(run_id=run_id)


@mcp.tool(timeout=30)
def search_mlflow_runs(
    experiment_ids: List[str],
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
    view_type: str = "ACTIVE_ONLY",
) -> Dict[str, Any]:
    """
    Search MLflow runs across one or more experiments.

    Use this to find runs by metrics, parameters, status, or tags.

    Args:
        experiment_ids: List of experiment IDs to search within
        filter_string: Filter expression. Examples:
            - "metrics.accuracy > 0.9"
            - "params.model_type = 'xgboost'"
            - "status = 'FINISHED'"
            - "tags.mlflow.runName LIKE '%best%'"
        max_results: Maximum runs to return (default: 50)
        order_by: Sort fields (e.g. ["metrics.accuracy DESC", "start_time DESC"])
        view_type: "ACTIVE_ONLY" (default), "DELETED_ONLY", or "ALL"

    Returns:
        Dictionary with:
        - runs: List of run dicts with metrics, params, tags
        - count: Number returned

    Example:
        >>> search_mlflow_runs(["123"], filter_string="metrics.accuracy > 0.9", order_by=["metrics.accuracy DESC"])
        {"runs": [...], "count": 5}
    """
    return _search_runs(
        experiment_ids=experiment_ids,
        filter_string=filter_string,
        max_results=max_results,
        order_by=order_by,
        view_type=view_type,
    )


@mcp.tool(timeout=30)
def get_mlflow_metric_history(
    run_id: str,
    metric_key: str,
    max_results: int = 100,
) -> Dict[str, Any]:
    """
    Get the history of a specific metric for a run.

    Use this to see how a metric changed over training steps — useful
    for analyzing convergence, detecting overfitting, etc.

    Args:
        run_id: The run ID
        metric_key: Name of the metric (e.g. "loss", "accuracy", "val_f1_score")
        max_results: Maximum data points to return (default: 100)

    Returns:
        Dictionary with:
        - run_id: The run ID
        - metric_key: The metric name
        - history: List of dicts with value, timestamp, step
        - count: Number of data points

    Example:
        >>> get_mlflow_metric_history("abc123", "loss")
        {"run_id": "abc123", "metric_key": "loss", "history": [{"value": 0.5, "step": 0}, ...]}
    """
    return _get_run_metrics_history(run_id=run_id, metric_key=metric_key, max_results=max_results)


@mcp.tool(timeout=30)
def list_mlflow_run_artifacts(
    run_id: str,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List artifacts stored for an MLflow run.

    Use this to discover what files (models, plots, configs) were
    logged during a run.

    Args:
        run_id: The run ID
        path: Optional relative path within the artifact directory.
            Omit to list root artifacts.

    Returns:
        Dictionary with:
        - run_id: The run ID
        - artifacts: List of dicts with path, is_dir, file_size
        - count: Number of artifacts

    Example:
        >>> list_mlflow_run_artifacts("abc123")
        {"run_id": "abc123", "artifacts": [{"path": "model", "is_dir": true}, ...], "count": 5}
    """
    return _list_run_artifacts(run_id=run_id, path=path)


# ---------------------------------------------------------------------------
# Registered Models (Unity Catalog)
# ---------------------------------------------------------------------------


@mcp.tool(timeout=30)
def get_mlflow_model(
    full_name: str,
    include_aliases: bool = True,
) -> Dict[str, Any]:
    """
    Get a registered model from Unity Catalog.

    Use this to inspect model details, owner, aliases, and description.

    Args:
        full_name: Three-level name (catalog.schema.model)
        include_aliases: Include alias information (default: True)

    Returns:
        Dictionary with model details:
        - full_name: Three-level name
        - name: Model name
        - catalog_name/schema_name: Namespace
        - comment: Description
        - owner: Owner principal
        - aliases: List of {alias_name, version_number}

    Example:
        >>> get_mlflow_model("main.ml.churn_model")
        {"full_name": "main.ml.churn_model", "owner": "user@example.com", "aliases": [...]}
    """
    return _get_registered_model(full_name=full_name, include_aliases=include_aliases)


@mcp.tool(timeout=30)
def list_mlflow_models(
    catalog_name: Optional[str] = None,
    schema_name: Optional[str] = None,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    List registered models in Unity Catalog.

    Use this to discover models, optionally filtered by catalog and schema.

    Args:
        catalog_name: Filter by catalog (optional)
        schema_name: Filter by schema (requires catalog_name)
        max_results: Maximum models to return (default: 50)

    Returns:
        Dictionary with:
        - models: List of model dicts
        - count: Number returned

    Example:
        >>> list_mlflow_models(catalog_name="main", schema_name="ml")
        {"models": [...], "count": 5}
    """
    return _list_registered_models(catalog_name=catalog_name, schema_name=schema_name, max_results=max_results)


@mcp.tool(timeout=30)
def search_mlflow_models(
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Search models in the legacy workspace model registry.

    For Unity Catalog models, use list_mlflow_models with catalog/schema filters.
    This searches the workspace-level (non-UC) registry.

    Args:
        filter_string: Filter expression (e.g. "name LIKE '%churn%'")
        max_results: Maximum models to return (default: 50)
        order_by: Sort fields (e.g. ["name ASC"])

    Returns:
        Dictionary with:
        - models: List with name, description, tags, latest_versions
        - count: Number returned

    Example:
        >>> search_mlflow_models(filter_string="name LIKE '%churn%'")
        {"models": [...], "count": 2}
    """
    return _search_registered_models(filter_string=filter_string, max_results=max_results, order_by=order_by)


# ---------------------------------------------------------------------------
# Model Versions (Unity Catalog)
# ---------------------------------------------------------------------------


@mcp.tool(timeout=30)
def get_mlflow_model_version(
    full_name: str,
    version: int,
) -> Dict[str, Any]:
    """
    Get a specific model version from Unity Catalog.

    Use this to inspect a version's source, run_id, status, and aliases.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        version: Version number

    Returns:
        Dictionary with version details:
        - full_name, version, status (READY, PENDING_REGISTRATION, etc.)
        - source: Artifact location
        - run_id: MLflow run that produced this version
        - aliases: List of alias dicts

    Example:
        >>> get_mlflow_model_version("main.ml.churn_model", version=3)
        {"full_name": "main.ml.churn_model", "version": 3, "status": "READY", ...}
    """
    return _get_model_version(full_name=full_name, version=version)


@mcp.tool(timeout=30)
def list_mlflow_model_versions(
    full_name: str,
    max_results: int = 50,
) -> Dict[str, Any]:
    """
    List all versions of a registered model in Unity Catalog.

    Use this to see version history, find the latest version, or
    compare versions by their run_id.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        max_results: Maximum versions to return (default: 50)

    Returns:
        Dictionary with:
        - full_name: The model name
        - versions: List of version dicts
        - count: Number returned

    Example:
        >>> list_mlflow_model_versions("main.ml.churn_model")
        {"full_name": "...", "versions": [{"version": 3, "status": "READY"}, ...], "count": 3}
    """
    return _list_model_versions(full_name=full_name, max_results=max_results)


@mcp.tool(timeout=30)
def get_mlflow_model_version_by_alias(
    full_name: str,
    alias: str,
) -> Dict[str, Any]:
    """
    Get a model version by its alias (e.g. "champion", "challenger").

    Use this to resolve which version an alias points to.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        alias: Alias name (e.g. "champion", "production")

    Returns:
        Dictionary with version details (same as get_mlflow_model_version)

    Example:
        >>> get_mlflow_model_version_by_alias("main.ml.churn_model", "champion")
        {"full_name": "...", "version": 5, "status": "READY", ...}
    """
    return _get_model_version_by_alias(full_name=full_name, alias=alias)


@mcp.tool(timeout=30)
def set_mlflow_model_alias(
    full_name: str,
    alias: str,
    version_num: int,
) -> Dict[str, Any]:
    """
    Set an alias on a model version (e.g. "champion", "challenger").

    Aliases provide mutable references to specific versions. If the
    alias already exists, it is reassigned to the new version.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        alias: Alias name to set
        version_num: Version number to point the alias to

    Returns:
        Dictionary with:
        - full_name, alias, version_num, status: "set"

    Example:
        >>> set_mlflow_model_alias("main.ml.churn_model", "champion", 5)
        {"full_name": "...", "alias": "champion", "version_num": 5, "status": "set"}
    """
    return _set_model_alias(full_name=full_name, alias=alias, version_num=version_num)


@mcp.tool(timeout=30)
def delete_mlflow_model_alias(
    full_name: str,
    alias: str,
) -> Dict[str, Any]:
    """
    Remove an alias from a registered model.

    Args:
        full_name: Three-level model name (catalog.schema.model)
        alias: Alias name to remove

    Returns:
        Dictionary with:
        - full_name, alias, status: "deleted" or "NOT_FOUND"

    Example:
        >>> delete_mlflow_model_alias("main.ml.churn_model", "old-alias")
        {"full_name": "...", "alias": "old-alias", "status": "deleted"}
    """
    return _delete_model_alias(full_name=full_name, alias=alias)
