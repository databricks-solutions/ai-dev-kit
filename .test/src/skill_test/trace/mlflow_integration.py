"""MLflow integration for Claude Code trace analysis.

Provides functions to fetch and analyze traces from MLflow experiments
logged via `mlflow autolog claude`.

Environment Variables:
    DATABRICKS_CONFIG_PROFILE: Databricks CLI profile to use (e.g., "aws-apps")
    MLFLOW_TRACKING_URI: MLflow tracking URI (default: "databricks")
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import TraceMetrics, ToolCall, FileOperation
from .parser import parse_and_compute_metrics


def _configure_mlflow(tracking_uri: str = "databricks") -> None:
    """Configure MLflow with proper authentication.

    Uses DATABRICKS_CONFIG_PROFILE environment variable to configure
    the Databricks SDK client, which MLflow uses for authentication.
    """
    import mlflow

    # Explicitly configure Databricks SDK if profile is set
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if profile:
        try:
            from databricks.sdk import WorkspaceClient

            # Initialize WorkspaceClient with profile to configure auth
            w = WorkspaceClient(profile=profile)
            # Set host from the configured profile if not already set
            if not os.environ.get("DATABRICKS_HOST"):
                os.environ["DATABRICKS_HOST"] = w.config.host
        except ImportError:
            pass  # databricks-sdk not installed, fall back to default

    # Set tracking URI
    mlflow.set_tracking_uri(tracking_uri)


def get_trace_from_mlflow(
    run_id: str,
    tracking_uri: str = "databricks",
) -> TraceMetrics:
    """Extract TraceMetrics from an MLflow run.

    Fetches trace data from an MLflow run that was logged via
    `mlflow autolog claude`. The trace is stored as a JSONL artifact.

    Args:
        run_id: MLflow run ID containing the trace
        tracking_uri: MLflow tracking URI (default: "databricks")

    Returns:
        TraceMetrics computed from the trace

    Raises:
        ImportError: If mlflow is not installed
        FileNotFoundError: If trace artifact not found in run
        ValueError: If run_id is invalid or run not found
    """
    try:
        import mlflow
    except ImportError as e:
        raise ImportError(
            "mlflow is required for MLflow integration. Install with: pip install mlflow[databricks]"
        ) from e

    _configure_mlflow(tracking_uri)

    try:
        run = mlflow.get_run(run_id)
    except Exception as e:
        raise ValueError(f"Failed to get MLflow run '{run_id}': {e}") from e

    # Download trace artifact
    # MLflow autolog claude stores traces as trace.jsonl or session.jsonl
    artifact_names = ["trace.jsonl", "session.jsonl", "transcript.jsonl"]

    artifact_path = None
    for name in artifact_names:
        try:
            artifact_path = mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path=name)
            break
        except Exception:
            continue

    if artifact_path is None:
        raise FileNotFoundError(f"No trace artifact found in run '{run_id}'. Looked for: {artifact_names}")

    return parse_and_compute_metrics(artifact_path)


def get_trace_from_mlflow_traces(
    run_id: str,
    tracking_uri: str = "databricks",
) -> TraceMetrics:
    """Extract TraceMetrics from MLflow Traces API.

    Alternative method that uses the MLflow Traces API instead of
    downloading JSONL artifacts. This is useful when traces are logged
    via mlflow.tracing rather than autolog claude.

    Args:
        run_id: MLflow run ID containing the trace
        tracking_uri: MLflow tracking URI (default: "databricks")

    Returns:
        TraceMetrics computed from the trace data

    Raises:
        ImportError: If mlflow is not installed
        ValueError: If no traces found for the run
    """
    try:
        import mlflow
    except ImportError as e:
        raise ImportError(
            "mlflow is required for MLflow integration. Install with: pip install mlflow[databricks]"
        ) from e

    _configure_mlflow(tracking_uri)

    # Search for traces associated with this run
    try:
        traces = mlflow.search_traces(
            experiment_ids=[mlflow.get_run(run_id).info.experiment_id],
            filter_string=f"run_id = '{run_id}'",
            max_results=1,
        )
    except Exception as e:
        raise ValueError(f"Failed to search traces for run '{run_id}': {e}") from e

    if traces.empty:
        raise ValueError(f"No traces found for run '{run_id}'")

    # Extract metrics from trace data
    trace_data = traces.iloc[0]
    return _parse_mlflow_trace_row(trace_data, run_id)


def _parse_mlflow_trace_row(trace_row: Any, run_id: str) -> TraceMetrics:
    """Parse an MLflow trace row into TraceMetrics.

    Args:
        trace_row: Row from mlflow.search_traces() DataFrame
        run_id: The run ID for session identification

    Returns:
        TraceMetrics with available data
    """
    metrics = TraceMetrics(session_id=run_id)

    # Extract timestamps if available
    if hasattr(trace_row, "timestamp_ms"):
        metrics.start_time = datetime.fromtimestamp(trace_row.timestamp_ms / 1000)

    # Extract token usage from trace attributes/metrics
    if hasattr(trace_row, "attributes"):
        attrs = trace_row.attributes or {}
        # Token metrics may be stored in various formats
        metrics.total_input_tokens = attrs.get("total_input_tokens", 0)
        metrics.total_output_tokens = attrs.get("total_output_tokens", 0)

    # Extract spans (tool calls) if available
    if hasattr(trace_row, "spans"):
        spans = trace_row.spans or []
        tool_calls = []
        tool_counts: dict[str, int] = {}

        for span in spans:
            if isinstance(span, dict):
                span_name = span.get("name", "unknown")
                # Check if this is a tool call span
                if span.get("span_type") == "TOOL" or "tool" in span_name.lower():
                    tc = ToolCall(
                        id=span.get("span_id", ""),
                        name=span_name,
                        input=span.get("inputs", {}),
                        timestamp=None,
                        result=str(span.get("outputs", "")),
                    )
                    tool_calls.append(tc)
                    tool_counts[span_name] = tool_counts.get(span_name, 0) + 1

        metrics.tool_calls = tool_calls
        metrics.tool_counts = tool_counts
        metrics.total_tool_calls = len(tool_calls)

    return metrics


def list_trace_runs(
    experiment_name: str,
    tracking_uri: str = "databricks",
    limit: int = 10,
    filter_string: str | None = None,
) -> list[dict[str, Any]]:
    """List recent trace runs from an MLflow experiment.

    Args:
        experiment_name: Full experiment path (e.g., "/Users/user@example.com/traces")
        tracking_uri: MLflow tracking URI (default: "databricks")
        limit: Maximum number of runs to return (default: 10)
        filter_string: Optional MLflow search filter string

    Returns:
        List of run info dicts with keys: run_id, start_time, status, tags

    Raises:
        ImportError: If mlflow is not installed
        ValueError: If experiment not found
    """
    try:
        import mlflow
    except ImportError as e:
        raise ImportError(
            "mlflow is required for MLflow integration. Install with: pip install mlflow[databricks]"
        ) from e

    _configure_mlflow(tracking_uri)

    try:
        runs = mlflow.search_runs(
            experiment_names=[experiment_name],
            filter_string=filter_string,
            max_results=limit,
            order_by=["start_time DESC"],
        )
    except Exception as e:
        raise ValueError(f"Failed to search runs in experiment '{experiment_name}': {e}") from e

    if runs.empty:
        return []

    result = []
    for _, row in runs.iterrows():
        run_info = {
            "run_id": row["run_id"],
            "start_time": row["start_time"],
            "status": row.get("status", "UNKNOWN"),
            "end_time": row.get("end_time"),
        }

        # Extract relevant tags
        for col in runs.columns:
            if col.startswith("tags."):
                tag_name = col.replace("tags.", "")
                if row[col] is not None:
                    run_info.setdefault("tags", {})[tag_name] = row[col]

        result.append(run_info)

    return result


def get_latest_trace_run(
    experiment_name: str,
    tracking_uri: str = "databricks",
) -> str | None:
    """Get the most recent trace run_id from an MLflow experiment.

    Args:
        experiment_name: Full experiment path
        tracking_uri: MLflow tracking URI (default: "databricks")

    Returns:
        Run ID of the most recent run, or None if no runs found
    """
    runs = list_trace_runs(
        experiment_name=experiment_name,
        tracking_uri=tracking_uri,
        limit=1,
    )

    if runs:
        return runs[0]["run_id"]
    return None


def get_trace_by_id(
    trace_id: str,
    tracking_uri: str = "databricks",
) -> TraceMetrics:
    """Fetch trace directly by trace ID using mlflow.get_trace().

    This is different from get_trace_from_mlflow() which takes a run_id.
    Trace IDs look like "tr-d416fccdab46e2dea6bad1d0bd8aaaa8".

    Args:
        trace_id: MLflow trace ID (e.g., "tr-...")
        tracking_uri: MLflow tracking URI (default: "databricks")

    Returns:
        TraceMetrics computed from the trace

    Raises:
        ImportError: If mlflow is not installed
        ValueError: If trace not found
    """
    try:
        import mlflow
    except ImportError as e:
        raise ImportError(
            "mlflow is required for MLflow integration. Install with: pip install mlflow[databricks]"
        ) from e

    _configure_mlflow(tracking_uri)

    trace = mlflow.get_trace(trace_id)
    if trace is None:
        raise ValueError(f"Trace not found: {trace_id}")

    return _parse_mlflow_trace(trace)


def _parse_mlflow_trace(trace: Any) -> TraceMetrics:
    """Parse an MLflow Trace object into TraceMetrics.

    Args:
        trace: MLflow Trace object from mlflow.get_trace()

    Returns:
        TraceMetrics with available data
    """
    from datetime import datetime, timedelta

    # Get trace info
    trace_info = trace.info
    metrics = TraceMetrics(session_id=trace_info.request_id)

    # Extract timestamps
    if trace_info.timestamp_ms:
        metrics.start_time = datetime.fromtimestamp(trace_info.timestamp_ms / 1000)
        # Compute end_time from start_time + execution_time for duration_seconds property
        if trace_info.execution_time_ms:
            metrics.end_time = metrics.start_time + timedelta(milliseconds=trace_info.execution_time_ms)

    # Extract token usage from trace attributes if available
    if hasattr(trace_info, "request_metadata") and trace_info.request_metadata:
        metadata = trace_info.request_metadata
        if isinstance(metadata, dict):
            metrics.total_input_tokens = int(metadata.get("total_input_tokens", 0))
            metrics.total_output_tokens = int(metadata.get("total_output_tokens", 0))

    # Parse spans (tool calls, LLM calls, etc.)
    tool_calls = []
    tool_counts: dict[str, int] = {}

    if trace.data and hasattr(trace.data, "spans"):
        for span in trace.data.spans:
            span_name = span.name if hasattr(span, "name") else "unknown"
            span_type = span.span_type if hasattr(span, "span_type") else None

            # Check if this is a tool call span
            if span_type == "TOOL" or "tool" in span_name.lower():
                tc = ToolCall(
                    id=span.span_id if hasattr(span, "span_id") else "",
                    name=span_name,
                    input=span.inputs if hasattr(span, "inputs") else {},
                    timestamp=None,
                    result=str(span.outputs) if hasattr(span, "outputs") else "",
                )
                tool_calls.append(tc)
                tool_counts[span_name] = tool_counts.get(span_name, 0) + 1

    metrics.tool_calls = tool_calls
    metrics.tool_counts = tool_counts
    metrics.total_tool_calls = len(tool_calls)

    return metrics


def get_trace_metrics(
    source: str | Path,
    tracking_uri: str = "databricks",
) -> TraceMetrics:
    """Get TraceMetrics from either a local file or MLflow run.

    Convenience function that auto-detects the source type.

    Args:
        source: Either a local file path or MLflow run ID
        tracking_uri: MLflow tracking URI (used if source is a run ID)

    Returns:
        TraceMetrics computed from the trace

    Raises:
        FileNotFoundError: If local file not found
        ValueError: If MLflow run not found
    """
    # Check if source looks like a file path
    if isinstance(source, Path) or (
        isinstance(source, str)
        and (source.endswith(".jsonl") or source.startswith("/") or source.startswith("~") or source.startswith("."))
    ):
        path = Path(source).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Trace file not found: {path}")
        return parse_and_compute_metrics(path)

    # Assume it's an MLflow run ID
    return get_trace_from_mlflow(source, tracking_uri)
