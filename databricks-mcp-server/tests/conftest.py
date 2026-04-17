"""
Pytest fixtures for databricks-mcp-server integration tests.

Uses centralized configuration from test_config.py.
Each test module gets its own schema to enable parallel execution.
"""

import logging
import os
from pathlib import Path
from typing import Generator, Callable

import pytest
from databricks.sdk import WorkspaceClient

from .test_config import TEST_CATALOG, SCHEMAS, TEST_RESOURCE_PREFIX, get_full_schema_name

# Load .env.test file if it exists
_env_file = Path(__file__).parent.parent / ".env.test"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)
    logging.getLogger(__name__).info(f"Loaded environment from {_env_file}")

logger = logging.getLogger(__name__)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test requiring Databricks")
    config.addinivalue_line("markers", "slow: mark test as slow (may take a while to run)")


# =============================================================================
# Core Fixtures (Session-scoped)
# =============================================================================

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
def current_user(workspace_client: WorkspaceClient) -> str:
    """Get current user's email/username."""
    return workspace_client.current_user.me().user_name


@pytest.fixture(scope="session")
def test_catalog(workspace_client: WorkspaceClient, warehouse_id: str) -> str:
    """
    Ensure test catalog exists and current user has permissions.

    Returns the catalog name.
    """
    try:
        workspace_client.catalogs.get(TEST_CATALOG)
        logger.info(f"Using existing catalog: {TEST_CATALOG}")
    except Exception:
        logger.info(f"Creating catalog: {TEST_CATALOG}")
        workspace_client.catalogs.create(name=TEST_CATALOG)

    # Grant ALL_PRIVILEGES on the catalog to the current user using SQL
    current_user = workspace_client.current_user.me().user_name
    try:
        # Use backticks to escape the email address (contains @)
        grant_sql = f"GRANT ALL PRIVILEGES ON CATALOG `{TEST_CATALOG}` TO `{current_user}`"
        workspace_client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=grant_sql,
            wait_timeout="30s",
        )
        logger.info(f"Granted ALL_PRIVILEGES on {TEST_CATALOG} to {current_user}")
    except Exception as e:
        logger.warning(f"Could not grant permissions on catalog (may already have them): {e}")

    return TEST_CATALOG


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


# =============================================================================
# Schema Fixtures (Module-scoped, per test module)
# =============================================================================

def _create_test_schema(
    workspace_client: WorkspaceClient,
    test_catalog: str,
    schema_name: str,
) -> Generator[str, None, None]:
    """Helper to create and cleanup a test schema."""
    full_schema_name = f"{test_catalog}.{schema_name}"

    # Drop schema if exists (cascade to remove all objects)
    try:
        logger.info(f"Dropping existing schema: {full_schema_name}")
        workspace_client.schemas.delete(full_schema_name, force=True)
    except Exception as e:
        logger.debug(f"Schema delete failed (may not exist): {e}")

    # Create fresh schema
    logger.info(f"Creating schema: {full_schema_name}")
    try:
        workspace_client.schemas.create(
            name=schema_name,
            catalog_name=test_catalog,
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info(f"Schema already exists, reusing: {full_schema_name}")
        else:
            raise

    yield schema_name

    # Cleanup after tests
    try:
        logger.info(f"Cleaning up schema: {full_schema_name}")
        workspace_client.schemas.delete(full_schema_name, force=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup schema: {e}")


@pytest.fixture(scope="module")
def sql_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for SQL tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["sql"])


@pytest.fixture(scope="module")
def pipelines_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for pipeline tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["pipelines"])


@pytest.fixture(scope="module")
def vector_search_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for vector search tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["vector_search"])


@pytest.fixture(scope="module")
def genie_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for Genie tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["genie"])


@pytest.fixture(scope="module")
def dashboards_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for dashboard tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["dashboards"])


@pytest.fixture(scope="module")
def jobs_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for jobs tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["jobs"])


@pytest.fixture(scope="module")
def volume_files_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for volume files tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["volume_files"])


@pytest.fixture(scope="module")
def compute_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for compute tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["compute"])


@pytest.fixture(scope="module")
def agent_bricks_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for agent bricks tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["agent_bricks"])


@pytest.fixture(scope="module")
def pdf_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for PDF tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["pdf"])


# =============================================================================
# Cleanup Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def cleanup_pipelines() -> Generator[Callable[[str], None], None, None]:
    """Register pipelines for cleanup after test."""
    from databricks_mcp_server.tools.pipelines import manage_pipeline

    pipelines_to_cleanup = []

    def register(pipeline_id: str):
        pipelines_to_cleanup.append(pipeline_id)

    yield register

    for pid in pipelines_to_cleanup:
        try:
            manage_pipeline(action="delete", pipeline_id=pid)
            logger.info(f"Cleaned up pipeline: {pid}")
        except Exception as e:
            logger.warning(f"Failed to cleanup pipeline {pid}: {e}")


@pytest.fixture(scope="function")
def cleanup_vs_endpoints() -> Generator[Callable[[str], None], None, None]:
    """Register vector search endpoints for cleanup after test."""
    from databricks_mcp_server.tools.vector_search import manage_vs_endpoint

    endpoints_to_cleanup = []

    def register(endpoint_name: str):
        endpoints_to_cleanup.append(endpoint_name)

    yield register

    for name in endpoints_to_cleanup:
        try:
            manage_vs_endpoint(action="delete", name=name)
            logger.info(f"Cleaned up VS endpoint: {name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup VS endpoint {name}: {e}")


@pytest.fixture(scope="function")
def cleanup_vs_indexes() -> Generator[Callable[[str], None], None, None]:
    """Register vector search indexes for cleanup after test."""
    from databricks_mcp_server.tools.vector_search import manage_vs_index

    indexes_to_cleanup = []

    def register(index_name: str):
        indexes_to_cleanup.append(index_name)

    yield register

    for name in indexes_to_cleanup:
        try:
            manage_vs_index(action="delete", index_name=name)
            logger.info(f"Cleaned up VS index: {name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup VS index {name}: {e}")


@pytest.fixture(scope="function")
def cleanup_jobs() -> Generator[Callable[[str], None], None, None]:
    """Register jobs for cleanup after test."""
    from databricks_mcp_server.tools.jobs import manage_jobs

    jobs_to_cleanup = []

    def register(job_id: str):
        jobs_to_cleanup.append(job_id)

    yield register

    for jid in jobs_to_cleanup:
        try:
            manage_jobs(action="delete", job_id=jid)
            logger.info(f"Cleaned up job: {jid}")
        except Exception as e:
            logger.warning(f"Failed to cleanup job {jid}: {e}")


@pytest.fixture(scope="function")
def cleanup_dashboards() -> Generator[Callable[[str], None], None, None]:
    """Register dashboards for cleanup after test."""
    from databricks_mcp_server.tools.aibi_dashboards import manage_dashboard

    dashboards_to_cleanup = []

    def register(dashboard_id: str):
        dashboards_to_cleanup.append(dashboard_id)

    yield register

    for did in dashboards_to_cleanup:
        try:
            manage_dashboard(action="delete", dashboard_id=did)
            logger.info(f"Cleaned up dashboard: {did}")
        except Exception as e:
            logger.warning(f"Failed to cleanup dashboard {did}: {e}")


@pytest.fixture(scope="function")
def cleanup_genie_spaces() -> Generator[Callable[[str], None], None, None]:
    """Register Genie spaces for cleanup after test."""
    from databricks_mcp_server.tools.genie import manage_genie

    spaces_to_cleanup = []

    def register(space_id: str):
        spaces_to_cleanup.append(space_id)

    yield register

    for sid in spaces_to_cleanup:
        try:
            manage_genie(action="delete", space_id=sid)
            logger.info(f"Cleaned up Genie space: {sid}")
        except Exception as e:
            logger.warning(f"Failed to cleanup Genie space {sid}: {e}")


@pytest.fixture(scope="function")
def cleanup_apps() -> Generator[Callable[[str], None], None, None]:
    """Register apps for cleanup after test."""
    from databricks_mcp_server.tools.apps import manage_app

    apps_to_cleanup = []

    def register(app_name: str):
        apps_to_cleanup.append(app_name)

    yield register

    for name in apps_to_cleanup:
        try:
            manage_app(action="delete", name=name)
            logger.info(f"Cleaned up app: {name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup app {name}: {e}")


@pytest.fixture(scope="function")
def cleanup_lakebase_instances() -> Generator[Callable[[str], None], None, None]:
    """Register Lakebase instances for cleanup after test."""
    from databricks_mcp_server.tools.lakebase import manage_lakebase_database

    instances_to_cleanup = []

    def register(name: str, db_type: str = "provisioned"):
        instances_to_cleanup.append((name, db_type))

    yield register

    for name, db_type in instances_to_cleanup:
        try:
            manage_lakebase_database(action="delete", name=name, type=db_type, force=True)
            logger.info(f"Cleaned up Lakebase {db_type} instance: {name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup Lakebase instance {name}: {e}")


@pytest.fixture(scope="function")
def cleanup_ka() -> Generator[Callable[[str], None], None, None]:
    """Register Knowledge Assistants for cleanup after test."""
    from databricks_mcp_server.tools.agent_bricks import manage_ka

    kas_to_cleanup = []

    def register(tile_id: str):
        kas_to_cleanup.append(tile_id)

    yield register

    for tile_id in kas_to_cleanup:
        try:
            manage_ka(action="delete", tile_id=tile_id)
            logger.info(f"Cleaned up KA: {tile_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup KA {tile_id}: {e}")


@pytest.fixture(scope="function")
def cleanup_mas() -> Generator[Callable[[str], None], None, None]:
    """Register Multi-Agent Supervisors for cleanup after test."""
    from databricks_mcp_server.tools.agent_bricks import manage_mas

    mas_to_cleanup = []

    def register(tile_id: str):
        mas_to_cleanup.append(tile_id)

    yield register

    for tile_id in mas_to_cleanup:
        try:
            manage_mas(action="delete", tile_id=tile_id)
            logger.info(f"Cleaned up MAS: {tile_id}")
        except Exception as e:
            logger.warning(f"Failed to cleanup MAS {tile_id}: {e}")


# =============================================================================
# Workspace Path Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def workspace_test_path(workspace_client: WorkspaceClient, current_user: str) -> Generator[str, None, None]:
    """Get a workspace path for test files and clean up after tests."""
    path = f"/Workspace/Users/{current_user}/ai_dev_kit_test/workspace_files/resources"

    # Delete if exists
    try:
        workspace_client.workspace.delete(path, recursive=True)
    except Exception:
        pass

    yield path

    # Cleanup after tests
    try:
        workspace_client.workspace.delete(path, recursive=True)
        logger.info(f"Cleaned up workspace path: {path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup workspace path: {e}")
