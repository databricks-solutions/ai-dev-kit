"""Shared test fixtures for databricks-codex tests."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from databricks_codex.config import CodexConfigManager, CodexConfig, MCPServerConfig
from databricks_codex.executor import CodexExecutor
from databricks_codex.auth import CodexAuthStatus
from databricks_codex.models import CodexAuthMethod, ExecutionStatus, ExecutionResult


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config_manager(temp_config_dir):
    """Config manager with temporary directory."""
    config_path = temp_config_dir / "config.toml"
    return CodexConfigManager(config_path=config_path)


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return CodexConfig(
        mcp_servers={
            "databricks": MCPServerConfig(
                command="/usr/bin/python",
                args=["-m", "databricks_mcp_server"],
                env={"DATABRICKS_CONFIG_PROFILE": "DEFAULT"},
            )
        }
    )


@pytest.fixture
def empty_config():
    """Empty configuration for testing."""
    return CodexConfig()


@pytest.fixture
def mock_executor():
    """Mock executor for unit tests."""
    executor = MagicMock(spec=CodexExecutor)
    executor.exec_sync = MagicMock(
        return_value=ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            stdout="Success",
            exit_code=0,
        )
    )
    executor.exec_async = AsyncMock(
        return_value=ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            stdout="Success",
            exit_code=0,
        )
    )
    return executor


@pytest.fixture
def mock_subprocess_run():
    """Mock subprocess.run for testing CLI calls."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_subprocess_run_not_found():
    """Mock subprocess.run that raises FileNotFoundError."""
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("codex not found")
        yield mock_run


@pytest.fixture
def mock_subprocess_run_timeout():
    """Mock subprocess.run that times out."""
    import subprocess
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="codex", timeout=30)
        yield mock_run


@pytest.fixture
def authenticated_status():
    """Mock authenticated status."""
    return CodexAuthStatus(
        method=CodexAuthMethod.CHATGPT_OAUTH,
        is_authenticated=True,
        username="test@example.com",
    )


@pytest.fixture
def unauthenticated_status():
    """Mock unauthenticated status."""
    return CodexAuthStatus(
        method=CodexAuthMethod.NONE,
        is_authenticated=False,
        error="Not logged in",
    )


@pytest.fixture
def mock_databricks_env():
    """Mock Databricks environment variables."""
    env_vars = {
        "DATABRICKS_HOST": "https://test.cloud.databricks.com",
        "DATABRICKS_TOKEN": "dapi_test_token",
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def clean_env():
    """Clean environment without Databricks variables."""
    env_to_remove = ["DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_CONFIG_PROFILE"]
    original_env = {k: os.environ.get(k) for k in env_to_remove}

    for key in env_to_remove:
        os.environ.pop(key, None)

    yield

    # Restore original environment
    for key, value in original_env.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
