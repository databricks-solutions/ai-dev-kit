"""MLflow tools - Manage experiments, runs, traces, and model registry.

Consolidated into 4 tools:
- manage_mlflow_experiment: create, get, list, search, set_tag, delete
- manage_mlflow_run: get, search, get_metric_history, list_artifacts
- manage_mlflow_model: get, list, search, get_version, list_versions, get_by_alias, set_alias, delete_alias
- manage_mlflow_trace: search, get, set_tag, delete_tag, log_assessment, delete_assessment
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
    get_registered_model as _get_registered_model,
    list_registered_models as _list_registered_models,
    search_registered_models as _search_registered_models,
    get_model_version as _get_model_version,
    list_model_versions as _list_model_versions,
    get_model_version_by_alias as _get_model_version_by_alias,
    set_model_alias as _set_model_alias,
    delete_model_alias as _delete_model_alias,
    search_traces as _search_traces,
    get_trace as _get_trace,
    set_trace_tag as _set_trace_tag,
    delete_trace_tag as _delete_trace_tag,
    log_assessment as _log_assessment,
    delete_assessment as _delete_assessment,
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


# ============================================================================
# Tool 3: manage_mlflow_model
# ============================================================================


@mcp.tool(timeout=30)
def manage_mlflow_model(
    action: str,
    # For get/get_version/list_versions/get_by_alias/set_alias/delete_alias:
    full_name: Optional[str] = None,
    # For get_version/set_alias:
    version: Optional[int] = None,
    # For get_by_alias/set_alias/delete_alias:
    alias: Optional[str] = None,
    # For list:
    catalog_name: Optional[str] = None,
    schema_name: Optional[str] = None,
    # For search (legacy):
    filter_string: Optional[str] = None,
    order_by: Optional[List[str]] = None,
    # For list/list_versions/search:
    max_results: int = 50,
) -> Dict[str, Any]:
    """Manage MLflow registered models and versions (Unity Catalog).

    Actions:
    - get: Get UC model details + aliases. Requires full_name (catalog.schema.model).
    - list: List UC models. Optional: catalog_name, schema_name, max_results.
    - search: Search legacy workspace registry. Optional: filter_string, order_by, max_results.
    - get_version: Get specific version. Requires full_name, version.
    - list_versions: List all versions. Requires full_name.
    - get_by_alias: Resolve alias to version. Requires full_name, alias.
    - set_alias: Point alias to version. Requires full_name, alias, version.
    - delete_alias: Remove alias. Requires full_name, alias.

    See databricks-mlflow skill for UC vs legacy models, alias workflows."""
    act = action.lower()

    if act == "get":
        if not full_name:
            return {"error": "get requires: full_name (catalog.schema.model)"}
        return _get_registered_model(full_name=full_name)

    elif act == "list":
        return _list_registered_models(catalog_name=catalog_name, schema_name=schema_name, max_results=max_results)

    elif act == "search":
        return _search_registered_models(filter_string=filter_string, max_results=max_results, order_by=order_by)

    elif act == "get_version":
        if not full_name or version is None:
            return {"error": "get_version requires: full_name, version"}
        return _get_model_version(full_name=full_name, version=version)

    elif act == "list_versions":
        if not full_name:
            return {"error": "list_versions requires: full_name"}
        return _list_model_versions(full_name=full_name, max_results=max_results)

    elif act == "get_by_alias":
        if not full_name or not alias:
            return {"error": "get_by_alias requires: full_name, alias"}
        return _get_model_version_by_alias(full_name=full_name, alias=alias)

    elif act == "set_alias":
        if not full_name or not alias or version is None:
            return {"error": "set_alias requires: full_name, alias, version"}
        return _set_model_alias(full_name=full_name, alias=alias, version_num=version)

    elif act == "delete_alias":
        if not full_name or not alias:
            return {"error": "delete_alias requires: full_name, alias"}
        return _delete_model_alias(full_name=full_name, alias=alias)

    else:
        return {
            "error": f"Invalid action '{action}'. Valid: get, list, search, get_version, list_versions, "
            "get_by_alias, set_alias, delete_alias"
        }


# ============================================================================
# Tool 4: manage_mlflow_trace
# ============================================================================


@mcp.tool(timeout=30)
def manage_mlflow_trace(
    action: str,
    # For get/set_tag/delete_tag/log_assessment/delete_assessment:
    trace_id: Optional[str] = None,
    # For search:
    experiment_ids: Optional[List[str]] = None,
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
    # For set_tag/delete_tag:
    key: Optional[str] = None,
    value: Optional[str] = None,
    # For log_assessment:
    assessment_name: Optional[str] = None,
    assessment_value: Optional[str] = None,
    assessment_type: str = "feedback",
    source_type: str = "HUMAN",
    rationale: Optional[str] = None,
    # For delete_assessment:
    assessment_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Manage MLflow traces: search, get, tag, and assess GenAI traces.

    Actions:
    - search: Search traces. Requires experiment_ids. Optional: filter_string
      (e.g. "status = 'OK'"), order_by, max_results.
    - get: Full trace detail with spans, metadata, assessments. Requires trace_id.
    - set_tag: Set tag on trace. Requires trace_id, key, value.
    - delete_tag: Remove tag. Requires trace_id, key.
    - log_assessment: Log feedback or expectation. Requires trace_id, assessment_name, assessment_value.
      assessment_type: "feedback" (default) or "expectation". source_type: "HUMAN" or "LLM_JUDGE".
    - delete_assessment: Remove assessment. Requires trace_id, assessment_id.

    See databricks-mlflow skill for trace structure, assessment types, token usage."""
    act = action.lower()

    if act == "search":
        if not experiment_ids:
            return {"error": "search requires: experiment_ids"}
        return _search_traces(
            experiment_ids=experiment_ids, filter_string=filter_string, max_results=max_results, order_by=order_by
        )

    elif act == "get":
        if not trace_id:
            return {"error": "get requires: trace_id"}
        return _get_trace(trace_id=trace_id)

    elif act == "set_tag":
        if not trace_id or not key or not value:
            return {"error": "set_tag requires: trace_id, key, value"}
        return _set_trace_tag(trace_id=trace_id, key=key, value=value)

    elif act == "delete_tag":
        if not trace_id or not key:
            return {"error": "delete_tag requires: trace_id, key"}
        return _delete_trace_tag(trace_id=trace_id, key=key)

    elif act == "log_assessment":
        if not trace_id or not assessment_name or not assessment_value:
            return {"error": "log_assessment requires: trace_id, assessment_name, assessment_value"}
        return _log_assessment(
            trace_id=trace_id,
            assessment_name=assessment_name,
            value=assessment_value,
            assessment_type=assessment_type,
            source_type=source_type,
            rationale=rationale,
        )

    elif act == "delete_assessment":
        if not trace_id or not assessment_id:
            return {"error": "delete_assessment requires: trace_id, assessment_id"}
        return _delete_assessment(trace_id=trace_id, assessment_id=assessment_id)

    else:
        return {
            "error": f"Invalid action '{action}'. Valid: search, get, set_tag, delete_tag, "
            "log_assessment, delete_assessment"
        }
