"""
MLflow Traces

Functions for searching, inspecting, tagging, and assessing MLflow traces
via the Databricks REST API.
"""

import logging
from typing import Any, Dict, List, Optional

from ..auth import get_workspace_client

logger = logging.getLogger(__name__)

_TRACES_API = "/api/2.0/mlflow/traces"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_trace_summary(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a concise summary from a search-result trace dict."""
    tags = {}
    for t in trace.get("tags", []):
        tags[t["key"]] = t["value"]

    metadata = {}
    for m in trace.get("request_metadata", []):
        metadata[m["key"]] = m["value"]

    return {
        "trace_id": trace.get("request_id"),
        "experiment_id": trace.get("experiment_id"),
        "timestamp_ms": trace.get("timestamp_ms"),
        "execution_time_ms": trace.get("execution_time_ms"),
        "status": trace.get("status"),
        "tags": tags,
        "metadata": metadata,
    }


def _extract_trace_detail(resp: Dict[str, Any]) -> Dict[str, Any]:
    """Extract full trace detail from a GET response."""
    trace = resp.get("trace", {})
    info = trace.get("trace_info", {})
    data = trace.get("trace_data", {})

    # Tags and metadata can be plain dicts or lists of {key, value}
    raw_tags = info.get("tags", {})
    if isinstance(raw_tags, dict):
        tags = raw_tags
    else:
        tags = {t.get("key", ""): t.get("value", "") for t in raw_tags if isinstance(t, dict)}

    raw_metadata = info.get("trace_metadata", {})
    if isinstance(raw_metadata, dict):
        metadata = raw_metadata
    else:
        metadata = {m.get("key", ""): m.get("value", "") for m in raw_metadata if isinstance(m, dict)}

    assessments = []
    for a in info.get("assessments", []):
        assessments.append({
            "assessment_id": a.get("assessment_id"),
            "assessment_name": a.get("assessment_name"),
            "source": a.get("source"),
            "feedback": a.get("feedback"),
            "expectation": a.get("expectation"),
            "rationale": a.get("rationale"),
            "create_time": a.get("create_time"),
        })

    spans = []
    for s in data.get("spans", []):
        spans.append({
            "span_id": s.get("span_id"),
            "name": s.get("name"),
            "parent_span_id": s.get("parent_id"),
            "start_time_ns": s.get("start_time_unix_nano"),
            "end_time_ns": s.get("end_time_unix_nano"),
            "status": s.get("status"),
            "attributes": s.get("attributes", {}),
        })

    return {
        "trace_id": info.get("trace_id"),
        "experiment_id": info.get("trace_location", {}).get("mlflow_experiment", {}).get("experiment_id"),
        "state": info.get("state"),
        "request_time": info.get("request_time"),
        "execution_duration": info.get("execution_duration"),
        "request_preview": info.get("request_preview"),
        "response_preview": info.get("response_preview"),
        "tags": tags,
        "metadata": metadata,
        "assessments": assessments,
        "spans": spans,
        "span_count": len(spans),
    }


# ---------------------------------------------------------------------------
# Search & Get
# ---------------------------------------------------------------------------


def search_traces(
    experiment_ids: List[str],
    filter_string: Optional[str] = None,
    max_results: int = 50,
    order_by: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Search MLflow traces across one or more experiments.

    Args:
        experiment_ids: List of experiment IDs to search within
        filter_string: Filter expression (e.g. "status = 'OK'",
            "timestamp_ms > 1700000000000")
        max_results: Maximum traces to return (default: 50)
        order_by: Sort fields (e.g. ["timestamp_ms DESC"])

    Returns:
        Dictionary with:
        - traces: List of trace summary dicts with trace_id, status,
          execution_time_ms, tags, metadata
        - count: Number of traces returned
    """
    client = get_workspace_client()

    query: Dict[str, Any] = {
        "experiment_ids": experiment_ids,
        "max_results": max_results,
    }
    if filter_string:
        query["filter"] = filter_string
    if order_by:
        query["order_by"] = order_by

    try:
        resp = client.api_client.do("GET", _TRACES_API, query=query)
    except Exception as e:
        raise Exception(f"Failed to search traces: {e}")

    traces = [_extract_trace_summary(t) for t in resp.get("traces", [])]
    return {"traces": traces, "count": len(traces)}


def get_trace(trace_id: str) -> Dict[str, Any]:
    """
    Get full details for an MLflow trace including spans and assessments.

    Args:
        trace_id: The trace ID (e.g. "tr-abc123...")

    Returns:
        Dictionary with trace details:
        - trace_id: Unique trace ID
        - experiment_id: Parent experiment
        - state: OK, ERROR, IN_PROGRESS
        - request_time: When the trace started
        - execution_duration: Duration string (e.g. "16.357s")
        - request_preview: Truncated request content
        - response_preview: Truncated response content
        - tags: Dict of trace tags
        - metadata: Dict of trace metadata (token usage, size, etc.)
        - assessments: List of assessment dicts
        - spans: List of span dicts with name, status, timing
        - span_count: Number of spans
    """
    client = get_workspace_client()

    try:
        resp = client.api_client.do("GET", f"{_TRACES_API}/{trace_id}")
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg or "404" in error_msg or "not found" in error_msg.lower():
            return {"error": f"Trace '{trace_id}' not found", "status": "NOT_FOUND"}
        raise Exception(f"Failed to get trace '{trace_id}': {e}")

    if not resp.get("trace"):
        return {"error": f"Trace '{trace_id}' not found", "status": "NOT_FOUND"}

    return _extract_trace_detail(resp)


# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------


def set_trace_tag(
    trace_id: str,
    key: str,
    value: str,
) -> Dict[str, Any]:
    """
    Set a tag on an MLflow trace.

    Tags are key-value metadata. Setting an existing key overwrites the value.

    Args:
        trace_id: The trace ID
        key: Tag key
        value: Tag value

    Returns:
        Dictionary with:
        - trace_id: The trace ID
        - key: Tag key
        - value: Tag value
        - status: "set"
    """
    client = get_workspace_client()

    try:
        client.api_client.do("PATCH", f"{_TRACES_API}/{trace_id}/tags", body={"key": key, "value": value})
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg or "not found" in error_msg.lower():
            return {"error": f"Trace '{trace_id}' not found", "status": "NOT_FOUND"}
        raise Exception(f"Failed to set tag on trace '{trace_id}': {e}")

    return {"trace_id": trace_id, "key": key, "value": value, "status": "set"}


def delete_trace_tag(
    trace_id: str,
    key: str,
) -> Dict[str, Any]:
    """
    Delete a tag from an MLflow trace.

    Args:
        trace_id: The trace ID
        key: Tag key to remove

    Returns:
        Dictionary with:
        - trace_id: The trace ID
        - key: Tag key removed
        - status: "deleted"
    """
    client = get_workspace_client()

    try:
        client.api_client.do("DELETE", f"{_TRACES_API}/{trace_id}/tags", body={"key": key})
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg or "not found" in error_msg.lower():
            return {"error": f"Trace '{trace_id}' not found", "status": "NOT_FOUND"}
        raise Exception(f"Failed to delete tag from trace '{trace_id}': {e}")

    return {"trace_id": trace_id, "key": key, "status": "deleted"}


# ---------------------------------------------------------------------------
# Assessments (Feedback & Expectations)
# ---------------------------------------------------------------------------


def log_assessment(
    trace_id: str,
    assessment_name: str,
    value: str,
    assessment_type: str = "feedback",
    source_type: str = "HUMAN",
    source_id: str = "databricks-ai-dev-kit",
    rationale: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Log a feedback or expectation assessment on an MLflow trace.

    Args:
        trace_id: The trace ID
        assessment_name: Name of the assessment (e.g. "quality",
            "expected_response", "correctness")
        value: Assessment value (string). For feedback: "yes", "no",
            "good", "bad", or any string. For expectations: the expected
            answer or behavior.
        assessment_type: "feedback" (default) or "expectation"
        source_type: "HUMAN" (default) or "LLM_JUDGE"
        source_id: Identifier for the source (default: "databricks-ai-dev-kit")
        rationale: Optional explanation for the assessment

    Returns:
        Dictionary with:
        - assessment_id: Unique assessment ID
        - trace_id: The trace ID
        - assessment_name: Name
        - status: "created"
    """
    client = get_workspace_client()

    assessment: Dict[str, Any] = {
        "assessment_name": assessment_name,
        "source": {"source_type": source_type, "source_id": source_id},
        assessment_type: {"value": value},
    }
    if rationale:
        assessment["rationale"] = rationale

    try:
        resp = client.api_client.do(
            "POST",
            f"{_TRACES_API}/{trace_id}/assessments",
            body={"assessment": assessment},
        )
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg or "not found" in error_msg.lower():
            return {"error": f"Trace '{trace_id}' not found", "status": "NOT_FOUND"}
        raise Exception(f"Failed to log assessment on trace '{trace_id}': {e}")

    result = resp.get("assessment", {})
    return {
        "assessment_id": result.get("assessment_id"),
        "trace_id": trace_id,
        "assessment_name": assessment_name,
        "status": "created",
    }


def delete_assessment(
    trace_id: str,
    assessment_id: str,
) -> Dict[str, Any]:
    """
    Delete an assessment from an MLflow trace.

    Args:
        trace_id: The trace ID
        assessment_id: The assessment ID to delete

    Returns:
        Dictionary with:
        - trace_id: The trace ID
        - assessment_id: The deleted assessment ID
        - status: "deleted"
    """
    client = get_workspace_client()

    try:
        client.api_client.do("DELETE", f"{_TRACES_API}/{trace_id}/assessments/{assessment_id}")
    except Exception as e:
        error_msg = str(e)
        if "RESOURCE_DOES_NOT_EXIST" in error_msg or "not found" in error_msg.lower():
            return {"error": f"Assessment '{assessment_id}' not found", "status": "NOT_FOUND"}
        raise Exception(f"Failed to delete assessment: {e}")

    return {"trace_id": trace_id, "assessment_id": assessment_id, "status": "deleted"}
