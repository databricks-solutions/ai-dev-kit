"""Tests for data models."""

import pytest
from datetime import datetime

from databricks_codex.models import (
    CodexToolCategory,
    TransportType,
    SandboxMode,
    ExecutionStatus,
    CodexAuthMethod,
    ExecutionResult,
    MCPToolInfo,
    CodexExecOptions,
    CodexToolCall,
    CodexResponse,
    DatabricksContext,
    CodexIntegrationConfig,
)


class TestEnums:
    """Tests for enum types."""

    def test_sandbox_mode_values(self):
        """Test SandboxMode enum values."""
        assert SandboxMode.READ_ONLY.value == "read-only"
        assert SandboxMode.WORKSPACE_WRITE.value == "workspace-write"
        assert SandboxMode.FULL_ACCESS.value == "danger-full-access"

    def test_execution_status_values(self):
        """Test ExecutionStatus enum values."""
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.RUNNING.value == "running"
        assert ExecutionStatus.COMPLETED.value == "completed"
        assert ExecutionStatus.FAILED.value == "failed"
        assert ExecutionStatus.TIMEOUT.value == "timeout"

    def test_auth_method_values(self):
        """Test CodexAuthMethod enum values."""
        assert CodexAuthMethod.CHATGPT_OAUTH.value == "chatgpt"
        assert CodexAuthMethod.DEVICE_CODE.value == "device"
        assert CodexAuthMethod.API_KEY.value == "api_key"
        assert CodexAuthMethod.NONE.value == "none"

    def test_transport_type_values(self):
        """Test TransportType enum values."""
        assert TransportType.STDIO.value == "stdio"
        assert TransportType.HTTP.value == "http"

    def test_tool_category_values(self):
        """Test CodexToolCategory enum values."""
        assert CodexToolCategory.GENERATION.value == "generation"
        assert CodexToolCategory.ANALYSIS.value == "analysis"


class TestDataclasses:
    """Tests for dataclass types."""

    def test_execution_result_defaults(self):
        """Test ExecutionResult default values."""
        result = ExecutionResult(status=ExecutionStatus.COMPLETED)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code is None
        assert result.elapsed_seconds == 0.0
        assert result.operation_id is None

    def test_execution_result_with_values(self):
        """Test ExecutionResult with custom values."""
        result = ExecutionResult(
            status=ExecutionStatus.FAILED,
            stdout="output",
            stderr="error",
            exit_code=1,
            elapsed_seconds=5.5,
            operation_id="abc123",
        )

        assert result.status == ExecutionStatus.FAILED
        assert result.stdout == "output"
        assert result.stderr == "error"
        assert result.exit_code == 1
        assert result.elapsed_seconds == 5.5
        assert result.operation_id == "abc123"

    def test_mcp_tool_info(self):
        """Test MCPToolInfo dataclass."""
        tool = MCPToolInfo(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object"},
        )

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.input_schema == {"type": "object"}

    def test_mcp_tool_info_defaults(self):
        """Test MCPToolInfo default values."""
        tool = MCPToolInfo(name="minimal", description="")

        assert tool.name == "minimal"
        assert tool.input_schema == {}


class TestPydanticModels:
    """Tests for Pydantic models."""

    def test_codex_exec_options_defaults(self):
        """Test CodexExecOptions default values."""
        options = CodexExecOptions(prompt="test prompt")

        assert options.prompt == "test prompt"
        assert options.working_dir is None
        assert options.sandbox_mode == SandboxMode.READ_ONLY
        assert options.model is None
        assert options.timeout == 300
        assert options.env_vars == {}
        assert options.databricks_profile == "DEFAULT"
        assert options.inject_databricks_env is True

    def test_codex_exec_options_custom(self):
        """Test CodexExecOptions with custom values."""
        options = CodexExecOptions(
            prompt="custom prompt",
            working_dir="/tmp",
            sandbox_mode=SandboxMode.WORKSPACE_WRITE,
            model="gpt-4",
            timeout=600,
            env_vars={"KEY": "value"},
            databricks_profile="PROD",
            inject_databricks_env=False,
        )

        assert options.prompt == "custom prompt"
        assert options.working_dir == "/tmp"
        assert options.sandbox_mode == SandboxMode.WORKSPACE_WRITE
        assert options.model == "gpt-4"
        assert options.timeout == 600
        assert options.env_vars == {"KEY": "value"}
        assert options.databricks_profile == "PROD"
        assert options.inject_databricks_env is False

    def test_codex_tool_call(self):
        """Test CodexToolCall model."""
        call = CodexToolCall(
            id="call_123",
            name="test_tool",
            arguments={"arg1": "value1"},
        )

        assert call.id == "call_123"
        assert call.name == "test_tool"
        assert call.arguments == {"arg1": "value1"}
        assert isinstance(call.timestamp, datetime)

    def test_codex_response_success(self):
        """Test CodexResponse for success."""
        response = CodexResponse(
            success=True,
            content="Result content",
            elapsed_ms=100,
        )

        assert response.success is True
        assert response.content == "Result content"
        assert response.tool_calls == []
        assert response.error is None
        assert response.elapsed_ms == 100

    def test_codex_response_failure(self):
        """Test CodexResponse for failure."""
        response = CodexResponse(
            success=False,
            error="Something went wrong",
        )

        assert response.success is False
        assert response.error == "Something went wrong"

    def test_databricks_context_defaults(self):
        """Test DatabricksContext default values."""
        ctx = DatabricksContext()

        assert ctx.host is None
        assert ctx.profile == "DEFAULT"
        assert ctx.catalog is None
        assert ctx.schema_name is None
        assert ctx.warehouse_id is None

    def test_codex_integration_config(self):
        """Test CodexIntegrationConfig model."""
        config = CodexIntegrationConfig(
            codex_path="/custom/codex",
            default_timeout=600,
            sandbox_mode="workspace-write",
        )

        assert config.codex_path == "/custom/codex"
        assert config.default_timeout == 600
        assert config.sandbox_mode == "workspace-write"
        assert isinstance(config.databricks_context, DatabricksContext)

    def test_model_serialization(self):
        """Test model serialization to dict."""
        options = CodexExecOptions(
            prompt="test",
            sandbox_mode=SandboxMode.READ_ONLY,
        )

        data = options.model_dump()
        assert data["prompt"] == "test"
        assert data["sandbox_mode"] == SandboxMode.READ_ONLY
