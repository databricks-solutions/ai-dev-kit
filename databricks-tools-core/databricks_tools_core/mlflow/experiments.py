"""
MLflow Experiments and Runs

Functions for managing MLflow experiments, runs, metrics, and artifacts
via the Databricks SDK.
"""

import logging
from typing import Any, Dict, List, Optional

from databricks.sdk.errors import NotFound, ResourceDoesNotExist
from databricks.sdk.service.ml import ViewType

from ..auth import get_workspace_client

_VIEW_TYPE_MAP = {
    "ACTIVE_ONLY": ViewType.ACTIVE_ONLY,
    "DELETED_ONLY": ViewType.DELETED_ONLY,
    "ALL": ViewType.ALL,
}

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _experiment_to_dict(exp) -> Dict[str, Any]:
    """Convert an Experiment SDK object to a user-friendly dict."""
    return {
        "experiment_id": exp.experiment_id,
        "name": exp.name,
        "artifact_location": exp.artifact_location,
        "lifecycle_stage": exp.lifecycle_stage,
        "last_update_time": exp.last_update_time,
        "creation_time": exp.creation_time,
        "tags": {t.key: t.value for t in (exp.tags or [])},
    }


def _run_to_dict(run) -> Dict[str, Any]:
    """Convert a Run SDK object to a user-friendly dict."""
    info = run.info or run
    data = run.data

    status = getattr(info, "status", None)
    if status is not None and hasattr(status, "value"):
        status = status.value

    result: Dict[str, Any] = {
        "run_id": getattr(info, "run_id", None),
        "run_name": getattr(info, "run_name", None),
        "experiment_id": getattr(info, "experiment_id", None),
        "status": status,
        "start_time": getattr(info, "start_time", None),
        "end_time": getattr(info, "end_time", None),
        "artifact_uri": getattr(info, "artifact_uri", None),
        "lifecycle_stage": getattr(info, "lifecycle_stage", None),
        "user_id": getattr(info, "user_id", None),
    }

    if data:
        result["metrics"] = {m.key: m.value for m in (data.metrics or [])}
        result["params"] = {p.key: p.value for p in (data.params or [])}
        result["tags"] = {t.key: t.value for t in (data.tags or [])}

    return result


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


def get_experiment(
    experiment_id: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get an MLflow experiment by ID or name.

    Exactly one of experiment_id or name must be provided.

    Args:
        experiment_id: Experiment ID (numeric string, e.g. "123456789")
        name: Full experiment name (e.g. "/Users/user@example.com/my-experiment")

    Returns:
        Dictionary with experiment details:
        - experiment_id: Unique experiment ID
        - name: Full experiment path/name
        - artifact_location: Storage location for artifacts
        - lifecycle_stage: "active" or "deleted"
        - last_update_time: Last modification timestamp (ms)
        - creation_time: Creation timestamp (ms)
        - tags: Dict of experiment tags
    """
    if not experiment_id and not name:
        raise ValueError("Must provide either experiment_id or name")

    client = get_workspace_client()

    try:
        if experiment_id:
            resp = client.experiments.get_experiment(experiment_id=experiment_id)
            exp = resp.experiment
        else:
            resp = client.experiments.get_by_name(experiment_name=name)
            exp = resp.experiment
    except (ResourceDoesNotExist, NotFound):
        identifier = experiment_id or name
        return {"error": f"Experiment '{identifier}' not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to get experiment: {e}")

    if exp is None:
        identifier = experiment_id or name
        return {"error": f"Experiment '{identifier}' not found", "status": "NOT_FOUND"}

    return _experiment_to_dict(exp)


def list_experiments(
    max_results: int = 50,
    view_type: str = "ACTIVE_ONLY",
) -> Dict[str, Any]:
    """
    List MLflow experiments in the workspace.

    Args:
        max_results: Maximum experiments to return (default: 50)
        view_type: Filter by lifecycle stage. One of:
            "ACTIVE_ONLY" (default), "DELETED_ONLY", "ALL"

    Returns:
        Dictionary with:
        - experiments: List of experiment dicts
        - count: Number of experiments returned
    """
    client = get_workspace_client()

    try:
        experiments_iter = client.experiments.list_experiments(
            max_results=max_results,
            view_type=_VIEW_TYPE_MAP.get(view_type, ViewType.ACTIVE_ONLY),
        )
        experiments = []
        for exp in experiments_iter:
            experiments.append(_experiment_to_dict(exp))
            if len(experiments) >= max_results:
                break
    except Exception as e:
        raise Exception(f"Failed to list experiments: {e}")

    return {"experiments": experiments, "count": len(experiments)}


def search_experiments(
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
    view_type: str = "ACTIVE_ONLY",
) -> Dict[str, Any]:
    """
    Search MLflow experiments with filters.

    Args:
        filter_string: Filter expression (e.g. "name LIKE '%my-project%'",
            "tags.team = 'ml-eng'")
        max_results: Maximum experiments to return (default: 50)
        order_by: Sort order (e.g. ["last_update_time DESC"])
        view_type: "ACTIVE_ONLY" (default), "DELETED_ONLY", or "ALL"

    Returns:
        Dictionary with:
        - experiments: List of matching experiment dicts
        - count: Number of experiments returned
    """
    client = get_workspace_client()

    try:
        experiments_iter = client.experiments.search_experiments(
            filter=filter_string,
            max_results=max_results,
            order_by=order_by,
            view_type=_VIEW_TYPE_MAP.get(view_type, ViewType.ACTIVE_ONLY),
        )
        experiments = []
        for exp in experiments_iter:
            experiments.append(_experiment_to_dict(exp))
            if len(experiments) >= max_results:
                break
    except Exception as e:
        raise Exception(f"Failed to search experiments: {e}")

    return {"experiments": experiments, "count": len(experiments)}


def create_experiment(
    name: str,
    experiment_kind: Optional[str] = None,
    artifact_location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Create a new MLflow experiment.

    Args:
        name: Experiment name (e.g. "/Users/user@example.com/my-experiment")
        experiment_kind: Experiment type in the UI. One of:
            - "genai" — shows as "GenAI apps & agents" (for agents, LLM apps)
            - "ml" — shows as "Machine learning" (for traditional ML)
            - None — no kind set (default)
        artifact_location: Optional custom artifact storage location
        tags: Optional dict of tags to set on the experiment

    Returns:
        Dictionary with:
        - experiment_id: ID of the created experiment
        - name: Experiment name
        - status: "created"
    """
    from databricks.sdk.service.ml import ExperimentTag

    _KIND_MAP = {
        "genai": "genai_development",
        "ml": "custom_model_development",
    }

    client = get_workspace_client()

    all_tags = dict(tags or {})
    if experiment_kind:
        kind_value = _KIND_MAP.get(experiment_kind, experiment_kind)
        all_tags["mlflow.experimentKind"] = kind_value

    tag_list = [ExperimentTag(key=k, value=v) for k, v in all_tags.items()] if all_tags else None

    try:
        resp = client.experiments.create_experiment(
            name=name,
            artifact_location=artifact_location,
            tags=tag_list,
        )
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_ALREADY_EXISTS" in error_msg:
            return {
                "error": f"Experiment '{name}' already exists",
                "status": "ALREADY_EXISTS",
            }
        raise Exception(f"Failed to create experiment '{name}': {e}")

    return {
        "experiment_id": resp.experiment_id,
        "name": name,
        "status": "created",
    }


def set_experiment_tag(
    experiment_id: str,
    key: str,
    value: str,
) -> Dict[str, Any]:
    """
    Set a tag on an MLflow experiment.

    Tags are key-value metadata. Setting an existing key overwrites the value.

    Args:
        experiment_id: Experiment ID
        key: Tag key (e.g. "team", "mlflow.experimentKind")
        value: Tag value

    Returns:
        Dictionary with:
        - experiment_id: The experiment ID
        - key: Tag key
        - value: Tag value
        - status: "set"
    """
    client = get_workspace_client()

    try:
        client.experiments.set_experiment_tag(
            experiment_id=experiment_id,
            key=key,
            value=value,
        )
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Experiment '{experiment_id}' not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to set tag on experiment '{experiment_id}': {e}")

    return {
        "experiment_id": experiment_id,
        "key": key,
        "value": value,
        "status": "set",
    }


def delete_experiment(experiment_id: str) -> Dict[str, Any]:
    """
    Delete (soft-delete) an MLflow experiment.

    The experiment moves to "deleted" lifecycle stage and can be restored.

    Args:
        experiment_id: ID of the experiment to delete

    Returns:
        Dictionary with:
        - experiment_id: The deleted experiment ID
        - status: "deleted" or "not_found"
    """
    client = get_workspace_client()

    try:
        client.experiments.delete_experiment(experiment_id=experiment_id)
    except (ResourceDoesNotExist, NotFound):
        return {
            "experiment_id": experiment_id,
            "status": "NOT_FOUND",
            "message": f"Experiment '{experiment_id}' not found",
        }
    except Exception as e:
        raise Exception(f"Failed to delete experiment '{experiment_id}': {e}")

    return {
        "experiment_id": experiment_id,
        "status": "deleted",
        "message": f"Experiment '{experiment_id}' deleted (soft-delete, can be restored)",
    }


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def get_run(run_id: str) -> Dict[str, Any]:
    """
    Get details for an MLflow run.

    Args:
        run_id: The run ID (UUID string)

    Returns:
        Dictionary with run details:
        - run_id: Unique run ID
        - run_name: Display name
        - experiment_id: Parent experiment ID
        - status: RUNNING, FINISHED, FAILED, KILLED
        - start_time: Start timestamp (ms)
        - end_time: End timestamp (ms)
        - artifact_uri: URI for run artifacts
        - lifecycle_stage: "active" or "deleted"
        - metrics: Dict of latest metric values
        - params: Dict of logged parameters
        - tags: Dict of run tags
    """
    client = get_workspace_client()

    try:
        resp = client.experiments.get_run(run_id=run_id)
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Run '{run_id}' not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to get run '{run_id}': {e}")

    return _run_to_dict(resp.run)


def search_runs(
    experiment_ids: List[str],
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
    view_type: str = "ACTIVE_ONLY",
) -> Dict[str, Any]:
    """
    Search MLflow runs across one or more experiments.

    Args:
        experiment_ids: List of experiment IDs to search within
        filter_string: Filter expression (e.g. "metrics.accuracy > 0.9",
            "params.model_type = 'xgboost'", "status = 'FINISHED'")
        max_results: Maximum runs to return (default: 50)
        order_by: Sort order (e.g. ["metrics.accuracy DESC", "start_time DESC"])
        view_type: "ACTIVE_ONLY" (default), "DELETED_ONLY", or "ALL"

    Returns:
        Dictionary with:
        - runs: List of run dicts with metrics, params, tags
        - count: Number of runs returned
    """
    client = get_workspace_client()

    try:
        runs_iter = client.experiments.search_runs(
            experiment_ids=experiment_ids,
            filter=filter_string,
            max_results=max_results,
            order_by=order_by,
            run_view_type=_VIEW_TYPE_MAP.get(view_type, ViewType.ACTIVE_ONLY),  # SDK expects ViewType enum
        )
        runs = []
        for run in runs_iter:
            runs.append(_run_to_dict(run))
            if len(runs) >= max_results:
                break
    except Exception as e:
        raise Exception(f"Failed to search runs: {e}")

    return {"runs": runs, "count": len(runs)}


def get_run_metrics_history(
    run_id: str,
    metric_key: str,
    max_results: int = 100,
) -> Dict[str, Any]:
    """
    Get the history of a specific metric for a run.

    Useful for viewing how a metric changed over training steps.

    Args:
        run_id: The run ID
        metric_key: Name of the metric (e.g. "loss", "accuracy")
        max_results: Maximum data points to return (default: 100)

    Returns:
        Dictionary with:
        - run_id: The run ID
        - metric_key: The metric name
        - history: List of dicts with value, timestamp, step
        - count: Number of data points
    """
    client = get_workspace_client()

    try:
        metrics_iter = client.experiments.get_history(
            run_id=run_id,
            metric_key=metric_key,
            max_results=max_results,
        )
        history = []
        for m in metrics_iter:
            history.append(
                {
                    "value": m.value,
                    "timestamp": m.timestamp,
                    "step": m.step,
                }
            )
            if len(history) >= max_results:
                break
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Run '{run_id}' not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to get metric history: {e}")

    return {
        "run_id": run_id,
        "metric_key": metric_key,
        "history": history,
        "count": len(history),
    }


def list_run_artifacts(
    run_id: str,
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    List artifacts stored for an MLflow run.

    Args:
        run_id: The run ID
        path: Optional relative path within the artifact directory.
            Omit to list root artifacts.

    Returns:
        Dictionary with:
        - run_id: The run ID
        - path: The listed path
        - artifacts: List of dicts with path, is_dir, file_size
        - count: Number of artifacts
    """
    client = get_workspace_client()

    try:
        artifacts_iter = client.experiments.list_artifacts(
            run_id=run_id,
            path=path,
        )
        artifacts = []
        for f in artifacts_iter:
            artifacts.append(
                {
                    "path": f.path,
                    "is_dir": f.is_dir,
                    "file_size": f.file_size,
                }
            )
    except (ResourceDoesNotExist, NotFound):
        return {"error": f"Run '{run_id}' not found", "status": "NOT_FOUND"}
    except Exception as e:
        raise Exception(f"Failed to list artifacts: {e}")

    return {
        "run_id": run_id,
        "path": path or "/",
        "artifacts": artifacts,
        "count": len(artifacts),
    }
