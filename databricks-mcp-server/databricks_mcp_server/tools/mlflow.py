"""MLflow tools - Manage experiments and runs.

Consolidated into 2 tools:
- manage_mlflow_experiment: create, get, list, search, set_tag, delete
- manage_mlflow_run: get, search, get_metric_history, list_artifacts
"""

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
)

from ..manifest import register_deleter, track_resource, remove_resource
from ..server import mcp


# Register deleter for experiment cleanup
def _delete_experiment_resource(resource_id: str) -> None:
    _delete_experiment(experiment_id=resource_id)


register_deleter("mlflow_experiment", _delete_experiment_resource)


# ============================================================================
# Tool 1: manage_mlflow_experiment
# ============================================================================


@mcp.tool(timeout=60)
def manage_mlflow_experiment(
    action: str,
    # For get/set_tag/delete:
    experiment_id: Optional[str] = None,
    # For get/create:
    name: Optional[str] = None,
    # For create:
    experiment_kind: Optional[str] = None,
    artifact_location: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    # For set_tag:
    key: Optional[str] = None,
    value: Optional[str] = None,
    # For list/search:
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
    view_type: str = "ACTIVE_ONLY",
) -> Dict[str, Any]:
    """Manage MLflow experiments: create, get, list, search, set_tag, delete.

    Actions:
    - create: New experiment. Requires name. Optional: experiment_kind ("genai" or "ml"), tags.
      experiment_kind controls UI type: "genai" = GenAI apps & agents, "ml" = Machine learning.
      Returns: {experiment_id, name, status}.
    - get: Get experiment. Requires experiment_id OR name. Returns: experiment details with tags.
    - list: List experiments. Optional: max_results (default 50), view_type (ACTIVE_ONLY/DELETED_ONLY/ALL).
    - search: Search experiments. Optional: filter_string (e.g. "name LIKE '%churn%'"), order_by, max_results.
    - set_tag: Set tag on experiment. Requires experiment_id, key, value.
    - delete: Soft-delete experiment (can be restored). Requires experiment_id.

    See databricks-mlflow skill for experiment paths, filter syntax, and patterns."""
    act = action.lower()

    if act == "create":
        if not name:
            return {"error": "create requires: name"}
        merged_tags = {**get_default_tags(), **(tags or {})}
        result = _create_experiment(
            name=name, experiment_kind=experiment_kind, artifact_location=artifact_location, tags=merged_tags
        )
        if result.get("status") == "created":
            try:
                track_resource(resource_type="mlflow_experiment", name=name, resource_id=result["experiment_id"])
            except Exception:
                pass
        return result

    elif act == "get":
        if not experiment_id and not name:
            return {"error": "get requires: experiment_id or name"}
        return _get_experiment(experiment_id=experiment_id, name=name)

    elif act == "list":
        return _list_experiments(max_results=max_results, view_type=view_type)

    elif act == "search":
        return _search_experiments(
            filter_string=filter_string, max_results=max_results, order_by=order_by, view_type=view_type
        )

    elif act == "set_tag":
        if not experiment_id or not key or not value:
            return {"error": "set_tag requires: experiment_id, key, value"}
        return _set_experiment_tag(experiment_id=experiment_id, key=key, value=value)

    elif act == "delete":
        if not experiment_id:
            return {"error": "delete requires: experiment_id"}
        result = _delete_experiment(experiment_id=experiment_id)
        if result.get("status") == "deleted":
            try:
                remove_resource(resource_type="mlflow_experiment", resource_id=experiment_id)
            except Exception:
                pass
        return result

    else:
        return {"error": f"Invalid action '{action}'. Valid: create, get, list, search, set_tag, delete"}


# ============================================================================
# Tool 2: manage_mlflow_run
# ============================================================================


@mcp.tool(timeout=30)
def manage_mlflow_run(
    action: str,
    # For get/get_metric_history/list_artifacts:
    run_id: Optional[str] = None,
    # For search:
    experiment_ids: Optional[List[str]] = None,
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
    view_type: str = "ACTIVE_ONLY",
    # For get_metric_history:
    metric_key: Optional[str] = None,
    # For list_artifacts:
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage MLflow runs: get, search, get_metric_history, list_artifacts.

    Actions:
    - get: Get run details (metrics, params, tags, status). Requires run_id.
    - search: Search runs. Requires experiment_ids. Optional: filter_string
      (e.g. "metrics.accuracy > 0.9 AND status = 'FINISHED'"), order_by, max_results.
    - get_metric_history: Get metric over training steps. Requires run_id, metric_key.
    - list_artifacts: List run artifacts (models, plots). Requires run_id. Optional: path.

    See databricks-mlflow skill for filter syntax and metric logging patterns."""
    act = action.lower()

    if act == "get":
        if not run_id:
            return {"error": "get requires: run_id"}
        return _get_run(run_id=run_id)

    elif act == "search":
        if not experiment_ids:
            return {"error": "search requires: experiment_ids"}
        return _search_runs(
            experiment_ids=experiment_ids,
            filter_string=filter_string,
            max_results=max_results,
            order_by=order_by,
            view_type=view_type,
        )

    elif act == "get_metric_history":
        if not run_id or not metric_key:
            return {"error": "get_metric_history requires: run_id, metric_key"}
        return _get_run_metrics_history(run_id=run_id, metric_key=metric_key, max_results=max_results)

    elif act == "list_artifacts":
        if not run_id:
            return {"error": "list_artifacts requires: run_id"}
        return _list_run_artifacts(run_id=run_id, path=path)

    else:
        return {"error": f"Invalid action '{action}'. Valid: get, search, get_metric_history, list_artifacts"}
