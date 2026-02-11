"""Data models for Databricks Codex integration.

Provides Enums, TypedDicts, and Pydantic models for type safety.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================


class CodexToolCategory(Enum):
    """Categories of Codex tools."""

    GENERATION = "generation"
    ANALYSIS = "analysis"
    REFACTORING = "refactoring"
    TESTING = "testing"
    DOCUMENTATION = "documentation"


class TransportType(Enum):
    """MCP transport types."""

    STDIO = "stdio"
    HTTP = "http"


class SandboxMode(Enum):
    """Codex sandbox modes for security."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "danger-full-access"


class ExecutionStatus(Enum):
    """Status of a Codex execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class CodexAuthMethod(Enum):
    """Codex authentication methods."""

    CHATGPT_OAUTH = "chatgpt"
    DEVICE_CODE = "device"
    API_KEY = "api_key"
    NONE = "none"


# ============================================================================
# TypedDicts (for loose typing)
# ============================================================================


class ToolResultDict(TypedDict, total=False):
    """Tool call result."""

    content: List[Dict[str, Any]]
    is_error: bool
    metadata: Dict[str, Any]


class SessionInfoDict(TypedDict, total=False):
    """Session information."""

    session_id: str
    created_at: str
    last_activity: str
    project_dir: str


class MCPServerDict(TypedDict, total=False):
    """MCP server configuration."""

    command: str
    args: List[str]
    env: Dict[str, str]
    url: str
    bearer_token_env_var: str


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass
class ExecutionResult:
    """Result from codex exec."""

    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    elapsed_seconds: float = 0.0
    operation_id: Optional[str] = None


@dataclass
class MCPToolInfo:
    """Information about an available MCP tool."""

    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Pydantic Models (for strict typing and validation)
# ============================================================================


class CodexExecOptions(BaseModel):
    """Options for codex exec command."""

    prompt: str = Field(..., description="The prompt to send to Codex")
    working_dir: Optional[str] = Field(None, description="Working directory for execution")
    sandbox_mode: SandboxMode = Field(
        default=SandboxMode.READ_ONLY, description="Sandbox security mode"
    )
    model: Optional[str] = Field(None, description="Model to use (e.g., gpt-4)")
    timeout: int = Field(default=300, description="Timeout in seconds")
    env_vars: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    databricks_profile: str = Field(default="DEFAULT", description="Databricks config profile")
    inject_databricks_env: bool = Field(
        default=True, description="Inject Databricks credentials into environment"
    )

    model_config = {"use_enum_values": False}


class CodexToolCall(BaseModel):
    """A tool call made through Codex."""

    id: str = Field(..., description="Unique tool call ID")
    name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    timestamp: datetime = Field(default_factory=datetime.now, description="Call timestamp")


class CodexResponse(BaseModel):
    """Response from a Codex operation."""

    success: bool = Field(..., description="Whether the operation succeeded")
    content: str = Field(default="", description="Response content")
    tool_calls: List[CodexToolCall] = Field(
        default_factory=list, description="Tool calls made during execution"
    )
    error: Optional[str] = Field(None, description="Error message if failed")
    elapsed_ms: int = Field(default=0, description="Execution time in milliseconds")


class DatabricksContext(BaseModel):
    """Databricks context for Codex operations."""

    host: Optional[str] = Field(None, description="Databricks workspace host")
    profile: str = Field(default="DEFAULT", description="Config profile name")
    catalog: Optional[str] = Field(None, description="Default catalog")
    schema_name: Optional[str] = Field(None, description="Default schema")
    warehouse_id: Optional[str] = Field(None, description="SQL warehouse ID")


class CodexIntegrationConfig(BaseModel):
    """Full integration configuration."""

    codex_path: str = Field(default="codex", description="Path to Codex CLI binary")
    databricks_context: DatabricksContext = Field(
        default_factory=DatabricksContext, description="Databricks context"
    )
    mcp_servers: Dict[str, MCPServerDict] = Field(
        default_factory=dict, description="MCP server configurations"
    )
    default_timeout: int = Field(default=300, description="Default timeout in seconds")
    sandbox_mode: str = Field(default="read-only", description="Default sandbox mode")
