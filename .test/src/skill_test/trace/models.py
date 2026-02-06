"""Data models for Claude Code transcript traces.

Based on actual transcript JSONL structure from Claude Code sessions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class TokenUsage:
    """Token usage from a single assistant turn.

    Matches the `message.usage` structure in transcript entries.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output)."""
        return self.input_tokens + self.output_tokens

    @property
    def cache_tokens(self) -> int:
        """Total cache-related tokens."""
        return self.cache_creation_input_tokens + self.cache_read_input_tokens

    @classmethod
    def from_usage_dict(cls, usage: dict[str, Any]) -> "TokenUsage":
        """Create from transcript usage dictionary."""
        return cls(
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_creation_input_tokens=usage.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=usage.get("cache_read_input_tokens", 0),
        )


@dataclass
class ToolCall:
    """A single tool call from the transcript.

    Extracted from `message.content[]` where `type == "tool_use"`.
    """

    id: str  # e.g., "toolu_01S7qwmk3nEirzyaDwPHESzo"
    name: str  # e.g., "Write", "Read", "Bash", "mcp__databricks__execute_sql"
    input: dict[str, Any]  # Tool parameters
    timestamp: datetime | None = None
    result: str | None = None  # Populated from tool_result entry
    success: bool | None = None  # Determined from result content

    @property
    def is_mcp_tool(self) -> bool:
        """Check if this is an MCP tool call."""
        return self.name.startswith("mcp__")

    @property
    def is_file_operation(self) -> bool:
        """Check if this is a file operation tool."""
        return self.name in ("Read", "Write", "Edit", "Glob", "Grep")

    @property
    def is_bash(self) -> bool:
        """Check if this is a Bash command."""
        return self.name == "Bash"

    @property
    def tool_category(self) -> str:
        """Categorize the tool for counting purposes."""
        if self.is_mcp_tool:
            # Extract MCP server name: mcp__databricks__execute_sql -> databricks
            parts = self.name.split("__")
            return f"mcp_{parts[1]}" if len(parts) >= 2 else "mcp_unknown"
        elif self.is_file_operation:
            return "file_ops"
        elif self.is_bash:
            return "bash"
        else:
            return "other"


@dataclass
class FileOperation:
    """A file operation extracted from toolUseResult.

    Extracted from the `toolUseResult` object in tool result entries.
    """

    type: str  # "create", "edit", "read", etc.
    file_path: str
    content: str | None = None
    timestamp: datetime | None = None

    @property
    def is_write(self) -> bool:
        """Check if this is a write operation (create or edit)."""
        return self.type in ("create", "edit", "write")

    @property
    def is_read(self) -> bool:
        """Check if this is a read operation."""
        return self.type == "read"


@dataclass
class TranscriptEntry:
    """A single entry from the transcript JSONL.

    Represents either a user message, assistant response, or tool result.
    """

    uuid: str
    type: str  # "user" or "assistant"
    timestamp: datetime
    message: dict[str, Any]
    parent_uuid: str | None = None
    session_id: str | None = None
    cwd: str | None = None

    # Populated for assistant entries
    model: str | None = None
    usage: TokenUsage | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    # Populated for tool result entries
    tool_use_result: dict[str, Any] | None = None
    source_tool_assistant_uuid: str | None = None


@dataclass
class TraceMetrics:
    """Aggregated metrics from a Claude Code session trace.

    This is the primary data structure for trace-based scoring.
    """

    session_id: str
    start_time: datetime | None = None
    end_time: datetime | None = None

    # Token metrics (aggregated across all turns)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_creation_tokens: int = 0
    total_cache_read_tokens: int = 0

    # Tool call metrics
    total_tool_calls: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)  # tool_name -> count
    tool_category_counts: dict[str, int] = field(
        default_factory=dict
    )  # category -> count

    # All tool calls for detailed analysis
    tool_calls: list[ToolCall] = field(default_factory=list)

    # File operations
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    file_operations: list[FileOperation] = field(default_factory=list)

    # Conversation metrics
    num_turns: int = 0  # Number of assistant responses
    num_user_messages: int = 0

    # Model info
    model: str | None = None

    @property
    def total_tokens(self) -> int:
        """Total tokens used in the session."""
        return self.total_input_tokens + self.total_output_tokens

    @property
    def duration_seconds(self) -> float | None:
        """Session duration in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    def get_tool_count(self, tool_name: str) -> int:
        """Get count for a specific tool."""
        return self.tool_counts.get(tool_name, 0)

    def get_category_count(self, category: str) -> int:
        """Get count for a tool category."""
        return self.tool_category_counts.get(category, 0)

    def has_tool(self, tool_name: str) -> bool:
        """Check if a tool was used."""
        return tool_name in self.tool_counts

    def get_mcp_calls(self) -> list[ToolCall]:
        """Get all MCP tool calls."""
        return [tc for tc in self.tool_calls if tc.is_mcp_tool]

    def get_bash_commands(self) -> list[ToolCall]:
        """Get all Bash tool calls."""
        return [tc for tc in self.tool_calls if tc.is_bash]

    def get_file_ops(self) -> list[ToolCall]:
        """Get all file operation tool calls."""
        return [tc for tc in self.tool_calls if tc.is_file_operation]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "tokens": {
                "total": self.total_tokens,
                "input": self.total_input_tokens,
                "output": self.total_output_tokens,
                "cache_creation": self.total_cache_creation_tokens,
                "cache_read": self.total_cache_read_tokens,
            },
            "tools": {
                "total_calls": self.total_tool_calls,
                "by_name": self.tool_counts,
                "by_category": self.tool_category_counts,
            },
            "files": {
                "created": self.files_created,
                "modified": self.files_modified,
                "read": self.files_read,
            },
            "conversation": {
                "turns": self.num_turns,
                "user_messages": self.num_user_messages,
            },
            "model": self.model,
        }
