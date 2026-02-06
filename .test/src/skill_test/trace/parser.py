"""Parser for Claude Code transcript JSONL files.

Reads raw transcript files and extracts structured TraceMetrics.
"""

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .models import (
    FileOperation,
    TokenUsage,
    ToolCall,
    TraceMetrics,
    TranscriptEntry,
)


def parse_timestamp(ts: str | int | float | None) -> datetime | None:
    """Parse various timestamp formats to datetime.

    Args:
        ts: ISO-8601 string, Unix timestamp (seconds/ms), or None

    Returns:
        Parsed datetime or None
    """
    if ts is None:
        return None

    if isinstance(ts, str):
        try:
            # ISO-8601 format: "2026-01-13T18:47:29.913Z"
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None

    if isinstance(ts, (int, float)):
        # Unix timestamp - detect seconds vs milliseconds
        if ts < 1e10:
            return datetime.fromtimestamp(ts)
        elif ts < 1e13:
            return datetime.fromtimestamp(ts / 1000)
        else:
            return datetime.fromtimestamp(ts / 1e9)

    return None


def extract_tool_calls(content: list[dict[str, Any]]) -> list[ToolCall]:
    """Extract tool calls from message content array.

    Args:
        content: The message.content array from an assistant entry

    Returns:
        List of ToolCall objects
    """
    tool_calls = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "tool_use":
            tool_calls.append(
                ToolCall(
                    id=part.get("id", ""),
                    name=part.get("name", "unknown"),
                    input=part.get("input", {}),
                )
            )
    return tool_calls


def extract_file_operation(
    tool_use_result: dict[str, Any] | str | None, timestamp: datetime | None = None
) -> FileOperation | None:
    """Extract file operation from toolUseResult.

    Args:
        tool_use_result: The toolUseResult object from a tool result entry
        timestamp: Timestamp of the operation

    Returns:
        FileOperation or None if not a file operation
    """
    if not isinstance(tool_use_result, dict):
        return None

    op_type = tool_use_result.get("type")
    file_path = tool_use_result.get("filePath")

    if op_type and file_path:
        return FileOperation(
            type=op_type,
            file_path=file_path,
            content=tool_use_result.get("content"),
            timestamp=timestamp,
        )
    return None


def parse_entry(line: str) -> TranscriptEntry | None:
    """Parse a single JSONL line into a TranscriptEntry.

    Args:
        line: A single line from the transcript JSONL file

    Returns:
        TranscriptEntry or None if parsing fails
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    entry_type = data.get("type")
    if entry_type not in ("user", "assistant"):
        return None

    message = data.get("message", {})
    timestamp = parse_timestamp(data.get("timestamp"))

    entry = TranscriptEntry(
        uuid=data.get("uuid", ""),
        type=entry_type,
        timestamp=timestamp,
        message=message,
        parent_uuid=data.get("parentUuid"),
        session_id=data.get("sessionId"),
        cwd=data.get("cwd"),
    )

    # Parse assistant-specific fields
    if entry_type == "assistant":
        entry.model = message.get("model")

        usage_dict = message.get("usage", {})
        if usage_dict:
            entry.usage = TokenUsage.from_usage_dict(usage_dict)

        content = message.get("content", [])
        if isinstance(content, list):
            entry.tool_calls = extract_tool_calls(content)

    # Parse tool result fields
    if entry_type == "user":
        entry.tool_use_result = data.get("toolUseResult")
        entry.source_tool_assistant_uuid = data.get("sourceToolAssistantUUID")

    return entry


def parse_transcript(lines: list[str]) -> list[TranscriptEntry]:
    """Parse transcript JSONL lines into TranscriptEntry objects.

    Args:
        lines: List of JSONL lines from transcript file

    Returns:
        List of TranscriptEntry objects
    """
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        entry = parse_entry(line)
        if entry:
            entries.append(entry)
    return entries


def parse_transcript_file(path: str | Path) -> list[TranscriptEntry]:
    """Parse a transcript JSONL file.

    Args:
        path: Path to the transcript JSONL file

    Returns:
        List of TranscriptEntry objects
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Transcript file not found: {path}")

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    return parse_transcript(lines)


def link_tool_results(entries: list[TranscriptEntry]) -> None:
    """Link tool results back to their tool calls.

    Modifies entries in place to populate tool_call.result fields.

    Args:
        entries: List of TranscriptEntry objects
    """
    # Build mapping of tool_use_id to tool_call
    tool_calls_by_id: dict[str, ToolCall] = {}
    for entry in entries:
        for tc in entry.tool_calls:
            tool_calls_by_id[tc.id] = tc

    # Link results
    for entry in entries:
        if entry.type != "user":
            continue

        content = entry.message.get("content", [])
        if not isinstance(content, list):
            continue

        for part in content:
            if part.get("type") == "tool_result":
                tool_use_id = part.get("tool_use_id")
                result_content = part.get("content", "")

                # Handle list content (multi-part results)
                if isinstance(result_content, list):
                    result_content = "\n".join(
                        str(p.get("text", p)) if isinstance(p, dict) else str(p)
                        for p in result_content
                    )

                if tool_use_id and tool_use_id in tool_calls_by_id:
                    tc = tool_calls_by_id[tool_use_id]
                    tc.result = result_content
                    tc.timestamp = entry.timestamp
                    # Determine success based on result content
                    if result_content and isinstance(result_content, str):
                        tc.success = "error" not in result_content.lower()


def compute_metrics(entries: list[TranscriptEntry]) -> TraceMetrics:
    """Compute aggregated metrics from transcript entries.

    Args:
        entries: List of TranscriptEntry objects

    Returns:
        TraceMetrics with aggregated data
    """
    if not entries:
        return TraceMetrics(session_id="unknown")

    # Link tool results first
    link_tool_results(entries)

    # Get session info from first entry
    session_id = entries[0].session_id or "unknown"

    metrics = TraceMetrics(session_id=session_id)

    tool_counts: dict[str, int] = defaultdict(int)
    category_counts: dict[str, int] = defaultdict(int)
    all_tool_calls: list[ToolCall] = []
    file_operations: list[FileOperation] = []

    timestamps = []

    for entry in entries:
        if entry.timestamp:
            timestamps.append(entry.timestamp)

        if entry.type == "assistant":
            metrics.num_turns += 1

            # Set model (use first one seen)
            if not metrics.model and entry.model:
                metrics.model = entry.model

            # Aggregate tokens
            if entry.usage:
                metrics.total_input_tokens += entry.usage.input_tokens
                metrics.total_output_tokens += entry.usage.output_tokens
                metrics.total_cache_creation_tokens += (
                    entry.usage.cache_creation_input_tokens
                )
                metrics.total_cache_read_tokens += entry.usage.cache_read_input_tokens

            # Collect tool calls
            for tc in entry.tool_calls:
                all_tool_calls.append(tc)
                tool_counts[tc.name] += 1
                category_counts[tc.tool_category] += 1

        elif entry.type == "user":
            # Count user messages (excluding tool results)
            if not entry.tool_use_result:
                metrics.num_user_messages += 1

            # Extract file operations
            if entry.tool_use_result:
                file_op = extract_file_operation(
                    entry.tool_use_result, entry.timestamp
                )
                if file_op:
                    file_operations.append(file_op)
                    if file_op.is_write:
                        if file_op.type == "create":
                            metrics.files_created.append(file_op.file_path)
                        else:
                            metrics.files_modified.append(file_op.file_path)
                    elif file_op.is_read:
                        metrics.files_read.append(file_op.file_path)

    # Set timing
    if timestamps:
        metrics.start_time = min(timestamps)
        metrics.end_time = max(timestamps)

    # Set tool metrics
    metrics.total_tool_calls = len(all_tool_calls)
    metrics.tool_counts = dict(tool_counts)
    metrics.tool_category_counts = dict(category_counts)
    metrics.tool_calls = all_tool_calls
    metrics.file_operations = file_operations

    return metrics


def parse_and_compute_metrics(path: str | Path) -> TraceMetrics:
    """Parse a transcript file and compute metrics in one step.

    Args:
        path: Path to the transcript JSONL file

    Returns:
        TraceMetrics with aggregated data
    """
    entries = parse_transcript_file(path)
    return compute_metrics(entries)
