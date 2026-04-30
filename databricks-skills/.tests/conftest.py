"""
Pytest fixtures for databricks-skills integration tests.

These fixtures set up test resources in Databricks for testing the Python scripts
in databricks-skills that use databricks-tools-core functionality.

Requires a valid Databricks connection (via env vars or ~/.databrickscfg).
"""

import logging
import os
from pathlib import Path

import pytest
from databricks.sdk import WorkspaceClient

# Load .env.test file if it exists
_env_file = Path(__file__).parent.parent.parent / "databricks-tools-core" / ".env.test"
if _env_file.exists():
    from dotenv import load_dotenv

    load_dotenv(_env_file)
    logging.getLogger(__name__).info(f"Loaded environment from {_env_file}")

logger = logging.getLogger(__name__)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring Databricks"
    )


@pytest.fixture(scope="session")
def workspace_client() -> WorkspaceClient:
    """
    Create a WorkspaceClient for the test session.

    Uses standard Databricks authentication:
    1. DATABRICKS_HOST + DATABRICKS_TOKEN env vars
    2. ~/.databrickscfg profile
    """
    try:
        client = WorkspaceClient()
        # Verify connection works
        client.current_user.me()
        logger.info(f"Connected to Databricks: {client.config.host}")
        return client
    except Exception as e:
        pytest.skip(f"Could not connect to Databricks: {e}")


@pytest.fixture(scope="session")
def warehouse_id(workspace_client: WorkspaceClient) -> str:
    """
    Get a running SQL warehouse for tests.

    Prefers shared endpoints, falls back to any running warehouse.
    """
    from databricks.sdk.service.sql import State

    warehouses = list(workspace_client.warehouses.list())

    # Priority: running shared endpoint
    for w in warehouses:
        if w.state == State.RUNNING and "shared" in (w.name or "").lower():
            logger.info(f"Using warehouse: {w.name} ({w.id})")
            return w.id

    # Fallback: any running warehouse
    for w in warehouses:
        if w.state == State.RUNNING:
            logger.info(f"Using warehouse: {w.name} ({w.id})")
            return w.id

    # No running warehouse found
    pytest.skip("No running SQL warehouse available for tests")
