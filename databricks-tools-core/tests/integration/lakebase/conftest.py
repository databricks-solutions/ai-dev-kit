"""
Pytest fixtures for Lakebase Provisioned integration tests.

Provides session-scoped fixtures for:
- Lakebase instance (CU_1, created once, shared across all Lakebase tests)
- Source Delta table for synced table tests
- Cleanup helpers
"""

import logging
import time
import uuid

import pytest

logger = logging.getLogger(__name__)

# Unique suffix to avoid collisions across test runs
_RUN_ID = str(uuid.uuid4())[:8]

LB_INSTANCE_NAME = f"lb-test-{_RUN_ID}"
LB_CATALOG_PREFIX = "lb_test_cat"
LB_SYNCED_TABLE_PREFIX = "lb_test_sync"


def _wait_for_instance_running(name: str, timeout: int = 1200, poll: int = 20):
    """Poll instance until RUNNING or timeout."""
    from databricks_tools_core.lakebase import get_lakebase_instance

    deadline = time.time() + timeout
    while time.time() < deadline:
        inst = get_lakebase_instance(name)
        state = inst.get("state", "")
        stopped = inst.get("stopped")
        logger.info(f"Instance '{name}' state: {state}, stopped: {stopped}")

        # State varies by SDK version (e.g. "DatabaseInstanceState.RUNNING",
        # "DatabaseInstanceState.AVAILABLE")
        state_upper = state.upper()
        if any(s in state_upper for s in ("RUNNING", "AVAILABLE", "ACTIVE")):
            return inst
        if state == "NOT_FOUND":
            raise RuntimeError(f"Instance '{name}' not found")
        if "FAILED" in state.upper() or "ERROR" in state.upper():
            raise RuntimeError(f"Instance '{name}' in terminal state: {state}")
        time.sleep(poll)
    raise TimeoutError(f"Instance '{name}' not RUNNING within {timeout}s")


@pytest.fixture(scope="session")
def lakebase_instance_name():
    """
    Create a CU_1 Lakebase instance for the test session.

    Waits for RUNNING state before yielding.
    Deletes the instance after all tests complete.
    """
    from databricks_tools_core.lakebase import (
        create_lakebase_instance,
        delete_lakebase_instance,
        get_lakebase_instance,
    )

    name = LB_INSTANCE_NAME
    logger.info(f"Creating Lakebase instance: {name}")

    # Check if it already exists (from a previous failed run)
    existing = get_lakebase_instance(name)
    if existing.get("state") != "NOT_FOUND":
        logger.info(f"Instance '{name}' already exists (state: {existing.get('state')}), reusing")
        # If it's stopped, we still proceed - tests that need it running will handle it
    else:
        result = create_lakebase_instance(
            name=name,
            capacity="CU_1",
            stopped=False,
        )
        logger.info(f"Instance creation result: {result}")

    # Wait for RUNNING
    _wait_for_instance_running(name)
    logger.info(f"Instance '{name}' is RUNNING")

    yield name

    # Teardown
    logger.info(f"Deleting Lakebase instance: {name}")
    try:
        delete_lakebase_instance(name=name, force=False, purge=True)
        logger.info(f"Instance '{name}' deleted")
    except Exception as e:
        logger.warning(f"Failed to delete instance '{name}': {e}")


@pytest.fixture(scope="module")
def source_delta_table(test_catalog, test_schema, warehouse_id):
    """
    Create a small Delta table for synced table tests.

    Returns the fully qualified table name.
    """
    from databricks_tools_core.sql import execute_sql

    table_name = f"{test_catalog}.{test_schema}.lb_source_{_RUN_ID}"
    logger.info(f"Creating source Delta table: {table_name}")

    execute_sql(
        sql_query=f"""
            CREATE OR REPLACE TABLE {table_name} (
                id BIGINT,
                name STRING,
                email STRING,
                score DOUBLE
            )
        """,
        warehouse_id=warehouse_id,
    )

    execute_sql(
        sql_query=f"""
            INSERT INTO {table_name} VALUES
            (1, 'Alice', 'alice@test.com', 95.5),
            (2, 'Bob', 'bob@test.com', 87.3),
            (3, 'Charlie', 'charlie@test.com', 92.1)
        """,
        warehouse_id=warehouse_id,
    )

    logger.info(f"Source Delta table created: {table_name}")
    yield table_name

    # Cleanup handled by schema teardown


@pytest.fixture(scope="function")
def unique_name() -> str:
    """Generate a unique name suffix for test resources."""
    return str(uuid.uuid4())[:8]


@pytest.fixture(scope="function")
def cleanup_instances():
    """Track and cleanup Lakebase instances created during a test."""
    from databricks_tools_core.lakebase import delete_lakebase_instance

    instances_to_cleanup = []

    def register(name: str):
        if name not in instances_to_cleanup:
            instances_to_cleanup.append(name)
            logger.info(f"Registered instance for cleanup: {name}")

    yield register

    for inst_name in instances_to_cleanup:
        try:
            logger.info(f"Cleaning up instance: {inst_name}")
            delete_lakebase_instance(name=inst_name, force=False, purge=True)
        except Exception as e:
            logger.warning(f"Failed to cleanup instance {inst_name}: {e}")


@pytest.fixture(scope="function")
def cleanup_catalogs():
    """Track and cleanup Lakebase catalogs created during a test."""
    from databricks_tools_core.lakebase import delete_lakebase_catalog

    catalogs_to_cleanup = []

    def register(name: str):
        if name not in catalogs_to_cleanup:
            catalogs_to_cleanup.append(name)
            logger.info(f"Registered catalog for cleanup: {name}")

    yield register

    for cat_name in catalogs_to_cleanup:
        try:
            logger.info(f"Cleaning up Lakebase catalog: {cat_name}")
            delete_lakebase_catalog(cat_name)
        except Exception as e:
            logger.warning(f"Failed to cleanup catalog {cat_name}: {e}")


@pytest.fixture(scope="function")
def cleanup_synced_tables():
    """Track and cleanup synced tables created during a test."""
    from databricks_tools_core.lakebase import delete_synced_table

    tables_to_cleanup = []

    def register(table_name: str):
        if table_name not in tables_to_cleanup:
            tables_to_cleanup.append(table_name)
            logger.info(f"Registered synced table for cleanup: {table_name}")

    yield register

    for tbl_name in tables_to_cleanup:
        try:
            logger.info(f"Cleaning up synced table: {tbl_name}")
            delete_synced_table(tbl_name)
        except Exception as e:
            logger.warning(f"Failed to cleanup synced table {tbl_name}: {e}")
