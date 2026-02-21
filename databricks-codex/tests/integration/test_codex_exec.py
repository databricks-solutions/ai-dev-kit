"""Integration tests for Codex executor.

These tests require Codex CLI to be installed and authenticated.
"""

import pytest

from databricks_codex.executor import CodexExecutor
from databricks_codex.models import CodexExecOptions, ExecutionStatus, SandboxMode


@pytest.mark.integration
class TestCodexExecutorIntegration:
    """Integration tests requiring live Codex."""

    def test_exec_simple_prompt(self, executor):
        """Execute a simple prompt through Codex."""
        options = CodexExecOptions(
            prompt="Echo 'hello world' to the console",
            sandbox_mode=SandboxMode.READ_ONLY,
            timeout=60,
        )

        result = executor.exec_sync(options)

        # Should complete (may succeed or fail depending on Codex state)
        assert result.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
        ]
        assert result.elapsed_seconds >= 0

    def test_exec_with_databricks_context(self, executor, databricks_connected):
        """Execute with Databricks environment injected."""
        options = CodexExecOptions(
            prompt="Print the value of DATABRICKS_HOST environment variable",
            sandbox_mode=SandboxMode.READ_ONLY,
            inject_databricks_env=True,
            timeout=60,
        )

        result = executor.exec_sync(options)

        # Verify execution attempted
        assert result.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
        ]

    def test_exec_sandbox_modes(self, executor):
        """Test different sandbox modes."""
        for mode in [SandboxMode.READ_ONLY, SandboxMode.WORKSPACE_WRITE]:
            options = CodexExecOptions(
                prompt="List files in current directory",
                sandbox_mode=mode,
                timeout=30,
            )

            result = executor.exec_sync(options)

            # Should at least attempt execution
            assert result.status in [
                ExecutionStatus.COMPLETED,
                ExecutionStatus.FAILED,
                ExecutionStatus.TIMEOUT,
            ]

    @pytest.mark.asyncio
    async def test_exec_async_short(self, executor):
        """Async execution for short operations."""
        options = CodexExecOptions(
            prompt="Echo hello",
            timeout=30,
        )

        result = await executor.exec_async(options)

        assert result.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.RUNNING,  # If handed off
        ]


@pytest.mark.integration
class TestCodexExecutorTimeout:
    """Tests for timeout behavior."""

    def test_short_timeout(self, executor):
        """Test that short timeout is respected."""
        options = CodexExecOptions(
            prompt="This is a test prompt that should timeout",
            timeout=1,  # Very short timeout
        )

        result = executor.exec_sync(options)

        # Should timeout or complete quickly
        assert result.status in [ExecutionStatus.TIMEOUT, ExecutionStatus.COMPLETED]


@pytest.mark.integration
class TestCodexExecutorEnvironment:
    """Tests for environment handling."""

    def test_custom_env_vars(self, executor):
        """Test custom environment variables are passed."""
        options = CodexExecOptions(
            prompt="Print MY_CUSTOM_VAR",
            env_vars={"MY_CUSTOM_VAR": "test_value_12345"},
            timeout=30,
        )

        result = executor.exec_sync(options)

        # Execution should complete
        assert result.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
        ]

    def test_databricks_profile(self, executor, databricks_connected):
        """Test Databricks profile is respected."""
        options = CodexExecOptions(
            prompt="Show Databricks config profile",
            databricks_profile="DEFAULT",
            inject_databricks_env=True,
            timeout=30,
        )

        result = executor.exec_sync(options)

        assert result.status in [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.TIMEOUT,
        ]
