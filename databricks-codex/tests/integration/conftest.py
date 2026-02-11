"""Integration test fixtures.

These tests require:
- Codex CLI installed and authenticated
- Databricks connection configured
"""

import logging
import os

import pytest

logger = logging.getLogger(__name__)


def pytest_configure(config):
    """Register integration markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require Codex + Databricks)"
    )


@pytest.fixture(scope="session")
def codex_installed():
    """Verify Codex CLI is installed."""
    import subprocess

    try:
        result = subprocess.run(
            ["codex", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            pytest.skip("Codex CLI not working properly")
        logger.info(f"Codex CLI version: {result.stdout.strip()}")
        return True
    except FileNotFoundError:
        pytest.skip("Codex CLI not installed")
    except subprocess.TimeoutExpired:
        pytest.skip("Codex CLI timed out")


@pytest.fixture(scope="session")
def codex_authenticated(codex_installed):
    """Verify Codex is authenticated."""
    from databricks_codex.auth import check_codex_auth

    status = check_codex_auth()
    if not status.is_authenticated:
        pytest.skip(f"Codex not authenticated: {status.error}")
    return status


@pytest.fixture(scope="session")
def databricks_connected():
    """Verify Databricks connection."""
    # Check environment variables first
    host = os.environ.get("DATABRICKS_HOST")
    token = os.environ.get("DATABRICKS_TOKEN")

    if host and token:
        logger.info(f"Databricks configured via environment: {host}")
        return {"host": host, "token": token}

    # Try SDK
    try:
        from databricks.sdk import WorkspaceClient

        client = WorkspaceClient()
        user = client.current_user.me()
        logger.info(f"Databricks connected as: {user.user_name}")
        return {"host": client.config.host, "client": client}
    except ImportError:
        pytest.skip("databricks-sdk not installed")
    except Exception as e:
        pytest.skip(f"Databricks not configured: {e}")


@pytest.fixture(scope="session")
def executor(codex_authenticated, databricks_connected):
    """Create executor with both Codex and Databricks configured."""
    from databricks_codex.executor import CodexExecutor

    return CodexExecutor()


@pytest.fixture(scope="function")
def cleanup_operations(executor):
    """Cleanup operations created during tests."""
    created_ops = []

    def register(op_id: str):
        created_ops.append(op_id)

    yield register

    for op_id in created_ops:
        try:
            executor.clear_operation(op_id)
            logger.info(f"Cleaned up operation: {op_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup operation {op_id}: {e}")
