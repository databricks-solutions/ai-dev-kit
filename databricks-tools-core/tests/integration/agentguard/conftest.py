"""
Fixtures for AgentGuard integration tests.

Extends the root conftest.py fixtures (workspace_client, test_catalog,
test_schema, warehouse_id, test_tables) with AgentGuard-specific fixtures
for session lifecycle, middleware, and audit ledger testing.

Requires a live Databricks workspace with a running SQL warehouse.
"""

import logging
import os
from typing import Generator

import pytest

from databricks_tools_core.agentguard.context import clear_active_session
from databricks_tools_core.agentguard.models import AgentGuardMode, AgentGuardSession
from databricks_tools_core.agentguard.policy import PolicyEngine
from databricks_tools_core.agentguard.session import start_session, stop_session

logger = logging.getLogger(__name__)

# Audit ledger test catalog/schema — isolated from the main "agentguard" catalog
LEDGER_TEST_CATALOG = os.environ.get("TEST_CATALOG", "ai_dev_kit_test")
LEDGER_TEST_SCHEMA = "agentguard_test"


@pytest.fixture(autouse=True)
def _clean_session():
    """Ensure no stale session leaks between tests."""
    clear_active_session()
    yield
    clear_active_session()


@pytest.fixture
def policy_engine() -> PolicyEngine:
    return PolicyEngine()


@pytest.fixture
def monitor_session() -> Generator[AgentGuardSession, None, None]:
    """Start a monitor-only AgentGuard session, stop it after the test."""
    session = start_session(
        mode=AgentGuardMode.MONITOR_ONLY,
        description="integration-test-monitor",
        agent_id="test-agent",
        user_id="test-user",
    )
    yield session
    try:
        stop_session()
    except Exception:
        clear_active_session()


@pytest.fixture
def enforce_session() -> Generator[AgentGuardSession, None, None]:
    """Start an enforce-mode AgentGuard session, stop it after the test."""
    session = start_session(
        mode=AgentGuardMode.ENFORCE,
        description="integration-test-enforce",
        agent_id="test-agent",
        user_id="test-user",
    )
    yield session
    try:
        stop_session()
    except Exception:
        clear_active_session()


@pytest.fixture(scope="module")
def ledger_schema(workspace_client, warehouse_id):
    """Create and clean up the audit ledger test schema.

    Uses the test catalog from the root conftest and creates a dedicated
    schema for ledger tests so we don't pollute production data.
    """
    from databricks_tools_core.sql.sql import execute_sql

    full_schema = f"{LEDGER_TEST_CATALOG}.{LEDGER_TEST_SCHEMA}"

    # Ensure catalog exists
    execute_sql(
        f"CREATE CATALOG IF NOT EXISTS {LEDGER_TEST_CATALOG}",
        warehouse_id=warehouse_id,
    )

    # Clean slate
    try:
        execute_sql(
            f"DROP SCHEMA IF EXISTS {full_schema} CASCADE",
            warehouse_id=warehouse_id,
        )
    except Exception as e:
        logger.debug("Schema cleanup on setup failed (may not exist): %s", e)

    execute_sql(
        f"CREATE SCHEMA IF NOT EXISTS {full_schema}",
        warehouse_id=warehouse_id,
    )

    logger.info("Created ledger test schema: %s", full_schema)

    yield {
        "catalog": LEDGER_TEST_CATALOG,
        "schema": LEDGER_TEST_SCHEMA,
        "full_schema": full_schema,
    }

    # Cleanup after all tests in this module
    # NOTE: Commented out so you can inspect the table after test runs.
    #       Re-enable when done investigating.
    # try:
    #     execute_sql(
    #         f"DROP SCHEMA IF EXISTS {full_schema} CASCADE",
    #         warehouse_id=warehouse_id,
    #     )
    #     logger.info("Cleaned up ledger test schema: %s", full_schema)
    # except Exception as e:
    #     logger.warning("Failed to clean up ledger schema: %s", e)
