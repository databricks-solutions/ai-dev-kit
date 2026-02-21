"""Databricks Codex Integration - Python SDK for OpenAI Codex CLI with Databricks.

This package provides programmatic access to Codex CLI capabilities with
Databricks authentication and tool integration.
"""

from databricks_codex.models import (
    CodexToolCategory,
    TransportType,
    SandboxMode,
    ExecutionStatus,
    CodexAuthMethod,
    ExecutionResult,
    CodexExecOptions,
    CodexResponse,
    MCPToolInfo,
)
from databricks_codex.config import (
    MCPServerConfig,
    CodexConfig,
    CodexConfigManager,
)
from databricks_codex.auth import (
    CodexAuthStatus,
    check_codex_auth,
    login_codex,
    logout_codex,
    get_combined_auth_context,
)
from databricks_codex.executor import CodexExecutor
from databricks_codex.mcp_client import CodexMCPClient, MCPClientConfig
from databricks_codex.session import CodexSession, SessionManager

__version__ = "0.1.0"

__all__ = [
    # Models
    "CodexToolCategory",
    "TransportType",
    "SandboxMode",
    "ExecutionStatus",
    "CodexAuthMethod",
    "ExecutionResult",
    "CodexExecOptions",
    "CodexResponse",
    "MCPToolInfo",
    # Config
    "MCPServerConfig",
    "CodexConfig",
    "CodexConfigManager",
    # Auth
    "CodexAuthStatus",
    "check_codex_auth",
    "login_codex",
    "logout_codex",
    "get_combined_auth_context",
    # Executor
    "CodexExecutor",
    # MCP Client
    "CodexMCPClient",
    "MCPClientConfig",
    # Session
    "CodexSession",
    "SessionManager",
]
