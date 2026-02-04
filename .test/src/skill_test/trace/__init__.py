"""Trace capture and analysis for Claude Code sessions."""

from .models import (
    ToolCall,
    TokenUsage,
    FileOperation,
    TraceMetrics,
    TranscriptEntry,
)
from .parser import (
    parse_transcript,
    parse_transcript_file,
    parse_and_compute_metrics,
    compute_metrics,
)
from .mlflow_integration import (
    get_trace_from_mlflow,
    get_trace_by_id,
    get_trace_metrics,
    list_trace_runs,
    get_latest_trace_run,
)
from .source import (
    AutologStatus,
    check_autolog_status,
    get_current_session_trace_path,
    get_trace_from_best_source,
    list_local_traces,
    get_setup_instructions,
)

__all__ = [
    # Models
    "ToolCall",
    "TokenUsage",
    "FileOperation",
    "TraceMetrics",
    "TranscriptEntry",
    # Parser
    "parse_transcript",
    "parse_transcript_file",
    "parse_and_compute_metrics",
    "compute_metrics",
    # MLflow integration
    "get_trace_from_mlflow",
    "get_trace_by_id",
    "get_trace_metrics",
    "list_trace_runs",
    "get_latest_trace_run",
    # Source detection
    "AutologStatus",
    "check_autolog_status",
    "get_current_session_trace_path",
    "get_trace_from_best_source",
    "list_local_traces",
    "get_setup_instructions",
]
