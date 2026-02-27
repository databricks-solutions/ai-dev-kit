"""
Pytest fixtures for Unity Catalog integration tests.

Provides fixtures for:
- UC test schema (dedicated for UC tests to avoid conflicts)
- Test tables for tag/security/grant tests
- Cleanup helpers for catalogs, volumes, shares, recipients, monitors
"""

import logging
import uuid
import pytest

from databricks_tools_core.auth import get_workspace_client
from databricks_tools_core.sql import execute_sql

logger = logging.getLogger(__name__)

# Dedicated UC test schema (separate from root conftest test_schema)
UC_TEST_SCHEMA = "uc_test_schema"
UC_TEST_PREFIX = "uc_test"


@pytest.fixture(scope="module")
def uc_test_schema(test_catalog: str, warehouse_id: str) -> str:
    """
    Create a dedicated schema for UC integration tests.

    Drops and recreates to ensure clean state.
    Yields the schema name.
    """
    full_schema_name = f"{test_catalog}.{UC_TEST_SCHEMA}"

    # Drop if exists
    try:
        logger.info(f"Dropping existing UC test schema: {full_schema_name}")
        w = get_workspace_client()
        w.schemas.delete(full_schema_name, force=True)
    except Exception as e:
        logger.debug(f"Schema drop failed (may not exist): {e}")

    # Create fresh
    logger.info(f"Creating UC test schema: {full_schema_name}")
    try:
        w = get_workspace_client()
        w.schemas.create(name=UC_TEST_SCHEMA, catalog_name=test_catalog)
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info(f"Schema already exists, reusing: {full_schema_name}")
        else:
            raise

    yield UC_TEST_SCHEMA

    # Cleanup
    try:
        logger.info(f"Cleaning up UC test schema: {full_schema_name}")
        w = get_workspace_client()
        w.schemas.delete(full_schema_name, force=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup UC test schema: {e}")


@pytest.fixture(scope="module")
def uc_test_table(
    test_catalog: str,
    uc_test_schema: str,
    warehouse_id: str,
) -> str:
    """
    Create a test table for UC operations (tags, grants, security policies).

    Returns the full table name.
    """
    table_name = f"{UC_TEST_PREFIX}_employees"
    full_name = f"{test_catalog}.{uc_test_schema}.{table_name}"

    logger.info(f"Creating UC test table: {full_name}")
    execute_sql(
        sql_query=f"""
            CREATE OR REPLACE TABLE {full_name} (
                employee_id BIGINT,
                name STRING,
                email STRING,
                department STRING,
                salary DOUBLE,
                hire_date DATE,
                is_active BOOLEAN
            )
        """,
        warehouse_id=warehouse_id,
    )

    execute_sql(
        sql_query=f"""
            INSERT INTO {full_name} VALUES
            (1, 'Alice Smith', 'alice@company.com', 'Engineering', 120000.00, '2022-01-15', true),
            (2, 'Bob Johnson', 'bob@company.com', 'Marketing', 95000.00, '2022-03-20', true),
            (3, 'Charlie Brown', 'charlie@company.com', 'Engineering', 110000.00, '2022-06-10', false),
            (4, 'Diana Ross', 'diana@company.com', 'Finance', 105000.00, '2023-01-05', true),
            (5, 'Eve Wilson', 'eve@company.com', 'Engineering', 130000.00, '2023-04-12', true)
        """,
        warehouse_id=warehouse_id,
    )

    logger.info(f"UC test table created: {full_name}")
    yield full_name

    # Cleanup handled by schema drop


@pytest.fixture(scope="function")
def unique_name() -> str:
    """Generate a unique name suffix for test resources."""
    return str(uuid.uuid4())[:8]


@pytest.fixture(scope="function")
def cleanup_volumes():
    """
    Track and cleanup volumes created during tests.

    Usage:
        def test_create_volume(cleanup_volumes):
            vol = create_volume(...)
            cleanup_volumes(full_volume_name)
    """
    from databricks_tools_core.unity_catalog import delete_volume

    volumes_to_cleanup = []

    def register(full_volume_name: str):
        if full_volume_name not in volumes_to_cleanup:
            volumes_to_cleanup.append(full_volume_name)
            logger.info(f"Registered volume for cleanup: {full_volume_name}")

    yield register

    for vol_name in volumes_to_cleanup:
        try:
            logger.info(f"Cleaning up volume: {vol_name}")
            delete_volume(vol_name)
        except Exception as e:
            logger.warning(f"Failed to cleanup volume {vol_name}: {e}")


@pytest.fixture(scope="function")
def cleanup_shares():
    """Track and cleanup shares created during tests."""
    from databricks_tools_core.unity_catalog import delete_share

    shares_to_cleanup = []

    def register(share_name: str):
        if share_name not in shares_to_cleanup:
            shares_to_cleanup.append(share_name)
            logger.info(f"Registered share for cleanup: {share_name}")

    yield register

    for name in shares_to_cleanup:
        try:
            logger.info(f"Cleaning up share: {name}")
            delete_share(name)
        except Exception as e:
            logger.warning(f"Failed to cleanup share {name}: {e}")


@pytest.fixture(scope="function")
def cleanup_recipients():
    """Track and cleanup recipients created during tests."""
    from databricks_tools_core.unity_catalog import delete_recipient

    recipients_to_cleanup = []

    def register(recipient_name: str):
        if recipient_name not in recipients_to_cleanup:
            recipients_to_cleanup.append(recipient_name)
            logger.info(f"Registered recipient for cleanup: {recipient_name}")

    yield register

    for name in recipients_to_cleanup:
        try:
            logger.info(f"Cleaning up recipient: {name}")
            delete_recipient(name)
        except Exception as e:
            logger.warning(f"Failed to cleanup recipient {name}: {e}")


@pytest.fixture(scope="function")
def cleanup_monitors():
    """Track and cleanup monitors created during tests."""
    from databricks_tools_core.unity_catalog import delete_monitor

    monitors_to_cleanup = []

    def register(table_name: str):
        if table_name not in monitors_to_cleanup:
            monitors_to_cleanup.append(table_name)
            logger.info(f"Registered monitor for cleanup: {table_name}")

    yield register

    for tbl in monitors_to_cleanup:
        try:
            logger.info(f"Cleaning up monitor on: {tbl}")
            delete_monitor(tbl)
        except Exception as e:
            logger.warning(f"Failed to cleanup monitor {tbl}: {e}")


@pytest.fixture(scope="function")
def cleanup_functions():
    """Track and cleanup UC functions created during tests."""
    from databricks_tools_core.unity_catalog import delete_function

    functions_to_cleanup = []

    def register(full_function_name: str):
        if full_function_name not in functions_to_cleanup:
            functions_to_cleanup.append(full_function_name)
            logger.info(f"Registered function for cleanup: {full_function_name}")

    yield register

    for fn_name in functions_to_cleanup:
        try:
            logger.info(f"Cleaning up function: {fn_name}")
            delete_function(fn_name, force=True)
        except Exception as e:
            logger.warning(f"Failed to cleanup function {fn_name}: {e}")


@pytest.fixture(scope="function")
def cleanup_policies():
    """
    Track and cleanup FGAC policies created during tests.

    Usage:
        def test_create_policy(cleanup_policies):
            create_fgac_policy(...)
            cleanup_policies((policy_name, securable_type, securable_fullname))
    """
    from databricks_tools_core.auth import get_workspace_client

    policies_to_cleanup = []

    def register(policy_tuple: tuple):
        """Register a policy for cleanup. Tuple: (name, securable_type, securable_fullname)."""
        if policy_tuple not in policies_to_cleanup:
            policies_to_cleanup.append(policy_tuple)
            logger.info(f"Registered policy for cleanup: {policy_tuple[0]}")

    yield register

    # Use SDK directly to bypass approval token guardrails during cleanup
    w = get_workspace_client()
    for name, stype, sfullname in policies_to_cleanup:
        try:
            logger.info(f"Cleaning up policy: {name}")
            w.policies.delete_policy(
                on_securable_type=stype,
                on_securable_fullname=sfullname,
                name=name,
            )
        except Exception as e:
            logger.warning(f"Failed to cleanup policy {name}: {e}")
