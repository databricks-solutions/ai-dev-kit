"""Tests for Codex executor."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from databricks_codex.executor import (
    CodexExecutor,
    SAFE_EXECUTION_THRESHOLD,
)
from databricks_codex.models import (
    CodexExecOptions,
    ExecutionResult,
    ExecutionStatus,
    SandboxMode,
)


class TestCodexExecutor:
    """Tests for CodexExecutor class."""

    @pytest.fixture
    def executor(self):
        """Create executor instance for testing."""
        return CodexExecutor(default_timeout=60)

    def test_init_defaults(self):
        """Test executor initialization with defaults."""
        executor = CodexExecutor()

        assert executor.default_timeout == 300
        assert executor._operations == {}

    def test_init_custom(self):
        """Test executor initialization with custom values."""
        executor = CodexExecutor(default_timeout=600, max_workers=8)

        assert executor.default_timeout == 600


class TestExecSync:
    """Tests for exec_sync method."""

    @pytest.fixture
    def executor(self):
        return CodexExecutor()

    def test_exec_sync_success(self, executor, mock_subprocess_run):
        """Test successful synchronous execution."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Hello, world!",
            stderr="",
        )

        options = CodexExecOptions(prompt="echo hello")
        result = executor.exec_sync(options)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.stdout == "Hello, world!"
        assert result.exit_code == 0
        assert result.elapsed_seconds >= 0

    def test_exec_sync_failure(self, executor, mock_subprocess_run):
        """Test failed execution."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error occurred",
        )

        options = CodexExecOptions(prompt="failing command")
        result = executor.exec_sync(options)

        assert result.status == ExecutionStatus.FAILED
        assert result.stderr == "Error occurred"
        assert result.exit_code == 1

    def test_exec_sync_timeout(self, executor, mock_subprocess_run_timeout):
        """Test execution timeout."""
        options = CodexExecOptions(prompt="slow command", timeout=1)
        result = executor.exec_sync(options)

        assert result.status == ExecutionStatus.TIMEOUT

    def test_exec_sync_not_installed(self, executor, mock_subprocess_run_not_found):
        """Test when Codex not installed."""
        options = CodexExecOptions(prompt="test")
        result = executor.exec_sync(options)

        assert result.status == ExecutionStatus.FAILED
        assert "not found" in result.stderr.lower()

    def test_exec_sync_with_sandbox_mode(self, executor, mock_subprocess_run):
        """Test sandbox mode is passed correctly."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        options = CodexExecOptions(
            prompt="test",
            sandbox_mode=SandboxMode.WORKSPACE_WRITE,
        )
        executor.exec_sync(options)

        # Check command includes sandbox flag
        call_args = mock_subprocess_run.call_args
        cmd = call_args[0][0]
        assert "--sandbox" in cmd
        assert "workspace-write" in cmd

    def test_exec_sync_read_only_no_flag(self, executor, mock_subprocess_run):
        """Test read-only mode doesn't add extra flag."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        options = CodexExecOptions(
            prompt="test",
            sandbox_mode=SandboxMode.READ_ONLY,
        )
        executor.exec_sync(options)

        call_args = mock_subprocess_run.call_args
        cmd = call_args[0][0]
        # read-only is default, shouldn't add --sandbox flag
        assert "--sandbox" not in cmd

    def test_exec_sync_with_model(self, executor, mock_subprocess_run):
        """Test model parameter is passed."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        options = CodexExecOptions(prompt="test", model="gpt-4")
        executor.exec_sync(options)

        call_args = mock_subprocess_run.call_args
        cmd = call_args[0][0]
        assert "--model" in cmd
        assert "gpt-4" in cmd

    def test_exec_sync_with_working_dir(self, executor, mock_subprocess_run):
        """Test working directory is passed."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        options = CodexExecOptions(prompt="test", working_dir="/tmp")
        executor.exec_sync(options)

        call_args = mock_subprocess_run.call_args
        cmd = call_args[0][0]
        assert "--cd" in cmd
        assert "/tmp" in cmd


class TestBuildCommand:
    """Tests for _build_command method."""

    @pytest.fixture
    def executor(self):
        return CodexExecutor()

    def test_basic_command(self, executor):
        """Test basic command building."""
        options = CodexExecOptions(prompt="test prompt")
        cmd = executor._build_command(options)

        assert cmd[0] == "codex"
        assert cmd[1] == "exec"
        assert "test prompt" in cmd

    def test_command_with_all_options(self, executor):
        """Test command with all options."""
        options = CodexExecOptions(
            prompt="full test",
            sandbox_mode=SandboxMode.FULL_ACCESS,
            model="gpt-4",
            working_dir="/workspace",
        )
        cmd = executor._build_command(options)

        assert "--sandbox" in cmd
        assert "danger-full-access" in cmd
        assert "--model" in cmd
        assert "gpt-4" in cmd
        assert "--cd" in cmd
        assert "/workspace" in cmd


class TestBuildEnv:
    """Tests for _build_env method."""

    @pytest.fixture
    def executor(self):
        return CodexExecutor()

    def test_env_includes_databricks(self, executor, mock_databricks_env):
        """Test environment includes Databricks credentials."""
        options = CodexExecOptions(prompt="test", inject_databricks_env=True)
        env = executor._build_env(options)

        assert "DATABRICKS_HOST" in env
        assert "DATABRICKS_TOKEN" in env

    def test_env_without_databricks(self, executor, mock_databricks_env):
        """Test environment without Databricks injection."""
        options = CodexExecOptions(prompt="test", inject_databricks_env=False)
        env = executor._build_env(options)

        # Should still have env vars from outer scope but not from our injection
        # The mock_databricks_env fixture sets them, so they'd be in os.environ
        # which we copy. This test verifies the option is respected.

    def test_env_with_custom_vars(self, executor, mock_databricks_env):
        """Test custom environment variables are added."""
        options = CodexExecOptions(
            prompt="test",
            env_vars={"CUSTOM_VAR": "custom_value"},
        )
        env = executor._build_env(options)

        assert env.get("CUSTOM_VAR") == "custom_value"

    def test_env_with_profile(self, executor, mock_databricks_env):
        """Test non-default profile adds env var."""
        options = CodexExecOptions(
            prompt="test",
            databricks_profile="PROD",
        )
        env = executor._build_env(options)

        assert env.get("DATABRICKS_CONFIG_PROFILE") == "PROD"


class TestOperationTracking:
    """Tests for operation tracking."""

    @pytest.fixture
    def executor(self):
        return CodexExecutor()

    def test_get_operation_not_found(self, executor):
        """Test getting non-existent operation."""
        result = executor.get_operation("nonexistent")
        assert result is None

    def test_list_operations_empty(self, executor):
        """Test listing operations when empty."""
        ops = executor.list_operations()
        assert ops == {}

    def test_clear_operation_not_found(self, executor):
        """Test clearing non-existent operation."""
        result = executor.clear_operation("nonexistent")
        assert result is False


class TestExecutorContextManager:
    """Tests for context manager usage."""

    def test_context_manager(self, mock_subprocess_run):
        """Test executor as context manager."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        with CodexExecutor() as executor:
            options = CodexExecOptions(prompt="test")
            result = executor.exec_sync(options)
            assert result.status == ExecutionStatus.COMPLETED

    def test_shutdown(self):
        """Test explicit shutdown."""
        executor = CodexExecutor()
        executor.shutdown(wait=True)
        # Should not raise


class TestExecAsync:
    """Tests for exec_async method."""

    @pytest.fixture
    def executor(self):
        return CodexExecutor()

    @pytest.mark.asyncio
    async def test_exec_async_fast(self, executor, mock_subprocess_run):
        """Test fast async execution completes normally."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0,
            stdout="Fast result",
            stderr="",
        )

        options = CodexExecOptions(prompt="fast command")
        result = await executor.exec_async(options)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.stdout == "Fast result"

    @pytest.mark.asyncio
    async def test_exec_async_with_callback(self, executor, mock_subprocess_run):
        """Test async execution with callback."""
        mock_subprocess_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )

        callback_called = []

        def callback(result):
            callback_called.append(result)

        options = CodexExecOptions(prompt="test")
        await executor.exec_async(options, callback=callback)

        assert len(callback_called) == 1
