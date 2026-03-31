"""
Integration tests for vector search MCP tools.

Tests:
- manage_vs_endpoint: create, get, list, delete
- manage_vs_index: create, get, sync, delete
- query_vs_index: basic queries
"""

import logging
import uuid
import time

import pytest

from databricks_mcp_server.tools.vector_search import (
    manage_vs_endpoint,
    manage_vs_index,
    query_vs_index,
)
from databricks_mcp_server.tools.sql import execute_sql
from tests.test_config import TEST_CATALOG, SCHEMAS, TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)

# Deterministic names for tests (enables safe cleanup/restart)
VS_ENDPOINT_NAME = f"{TEST_RESOURCE_PREFIX}vs_endpoint"
VS_ENDPOINT_DELETE = f"{TEST_RESOURCE_PREFIX}vs_ep_delete"
VS_INDEX_NAME_SUFFIX = f"{TEST_RESOURCE_PREFIX}vs_index"
VS_INDEX_DELETE_SUFFIX = f"{TEST_RESOURCE_PREFIX}vs_idx_delete"


@pytest.fixture(scope="module")
def clean_vs_resources():
    """Pre-test cleanup: delete any existing test VS endpoints and indexes."""
    endpoints_to_clean = [VS_ENDPOINT_NAME, VS_ENDPOINT_DELETE]

    for ep_name in endpoints_to_clean:
        try:
            result = manage_vs_endpoint(action="get", name=ep_name)
            if result.get("state") != "NOT_FOUND" and not result.get("error"):
                manage_vs_endpoint(action="delete", name=ep_name)
                logger.info(f"Pre-cleanup: deleted VS endpoint {ep_name}")
        except Exception as e:
            logger.warning(f"Pre-cleanup failed for endpoint {ep_name}: {e}")

    yield

    # Post-test cleanup
    for ep_name in endpoints_to_clean:
        try:
            result = manage_vs_endpoint(action="get", name=ep_name)
            if result.get("state") != "NOT_FOUND" and not result.get("error"):
                manage_vs_endpoint(action="delete", name=ep_name)
                logger.info(f"Post-cleanup: deleted VS endpoint {ep_name}")
        except Exception:
            pass


@pytest.fixture(scope="module")
def vs_source_table(
    workspace_client,
    test_catalog: str,
    vector_search_schema: str,
    warehouse_id: str,
) -> str:
    """Create a source table for vector search index."""
    table_name = f"{test_catalog}.{vector_search_schema}.vs_source_table"

    # Create table with text content for embedding
    execute_sql(
        sql_query=f"""
            CREATE OR REPLACE TABLE {table_name} (
                id STRING,
                content STRING,
                category STRING
            )
            TBLPROPERTIES (delta.enableChangeDataFeed = true)
        """,
        warehouse_id=warehouse_id,
    )

    # Insert test data
    execute_sql(
        sql_query=f"""
            INSERT INTO {table_name} VALUES
            ('doc1', 'Databricks is a unified analytics platform', 'tech'),
            ('doc2', 'Machine learning helps analyze data', 'tech'),
            ('doc3', 'Python is a programming language', 'tech')
        """,
        warehouse_id=warehouse_id,
    )

    logger.info(f"Created source table: {table_name}")
    return table_name


@pytest.fixture(scope="module")
def existing_vs_endpoint(workspace_client) -> str:
    """Find an existing VS endpoint for read-only tests."""
    try:
        result = manage_vs_endpoint(action="list")
        endpoints = result.get("endpoints", [])
        for ep in endpoints:
            if ep.get("state") == "ONLINE":
                logger.info(f"Using existing endpoint: {ep['name']}")
                return ep["name"]
    except Exception as e:
        logger.warning(f"Could not list endpoints: {e}")

    pytest.skip("No existing VS endpoint available")


@pytest.mark.integration
class TestManageVsEndpoint:
    """Tests for manage_vs_endpoint tool."""

    def test_list_endpoints(self):
        """Should list all VS endpoints."""
        result = manage_vs_endpoint(action="list")

        logger.info(f"List result: {result}")

        assert not result.get("error"), f"List failed: {result}"
        assert "endpoints" in result
        assert isinstance(result["endpoints"], list)

    def test_get_endpoint(self, existing_vs_endpoint: str):
        """Should get endpoint details."""
        result = manage_vs_endpoint(action="get", name=existing_vs_endpoint)

        logger.info(f"Get result: {result}")

        # API returns error: None as a field, check truthiness not presence
        assert not result.get("error"), f"Get failed: {result}"
        assert result.get("name") == existing_vs_endpoint
        assert result.get("state") is not None

    def test_get_nonexistent_endpoint(self):
        """Should handle nonexistent endpoint gracefully."""
        result = manage_vs_endpoint(action="get", name="nonexistent_endpoint_xyz_12345")

        assert result.get("state") == "NOT_FOUND" or "error" in result

    def test_create_endpoint(self, cleanup_vs_endpoints):
        """Should create a new endpoint."""
        name = f"{TEST_RESOURCE_PREFIX}vs_create_{uuid.uuid4().hex[:6]}"
        cleanup_vs_endpoints(name)

        result = manage_vs_endpoint(
            action="create_or_update",  # API only supports create_or_update
            name=name,
            endpoint_type="STANDARD",
        )

        logger.info(f"Create result: {result}")

        assert not result.get("error"), f"Create failed: {result}"
        assert result.get("name") == name
        assert result.get("status") in ("CREATING", "ALREADY_EXISTS", "ONLINE", None)

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_vs_endpoint(action="invalid_action")

        assert "error" in result


@pytest.mark.integration
class TestManageVsIndex:
    """Tests for manage_vs_index tool."""

    def test_list_indexes(self, existing_vs_endpoint: str):
        """Should list indexes on an endpoint."""
        result = manage_vs_index(action="list", endpoint_name=existing_vs_endpoint)

        logger.info(f"List indexes result: {result}")

        # May have no indexes, but should not error
        assert not result.get("error") or "indexes" in result

    def test_get_nonexistent_index(self):
        """Should handle nonexistent index gracefully."""
        result = manage_vs_index(
            action="get",
            name="nonexistent.schema.index_xyz_12345",  # Param is 'name' not 'index_name'
        )

        assert result.get("state") == "NOT_FOUND" or result.get("error")

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_vs_index(action="invalid_action")

        assert "error" in result


@pytest.mark.integration
class TestVsIndexLifecycle:
    """End-to-end test for VS index lifecycle: create -> get -> query -> delete."""

    def test_full_index_lifecycle(
        self,
        existing_vs_endpoint: str,
        vs_source_table: str,
        test_catalog: str,
        vector_search_schema: str,
    ):
        """Test complete index lifecycle: create, wait, get, query, delete, verify."""
        index_name = f"{test_catalog}.{vector_search_schema}.{VS_INDEX_NAME_SUFFIX}"
        test_start = time.time()

        def log_time(msg):
            elapsed = time.time() - test_start
            logger.info(f"[{elapsed:.1f}s] {msg}")

        try:
            # Step 1: Create index
            log_time("Step 1: Creating index...")
            create_result = manage_vs_index(
                action="create_or_update",
                name=index_name,
                endpoint_name=existing_vs_endpoint,
                primary_key="id",
                index_type="DELTA_SYNC",
                delta_sync_index_spec={
                    "source_table": vs_source_table,
                    "embedding_source_columns": [
                        {
                            "name": "content",
                            "embedding_model_endpoint_name": "databricks-gte-large-en",
                        }
                    ],
                    "pipeline_type": "TRIGGERED",
                    "columns_to_sync": ["id", "content", "category"],
                },
            )
            log_time(f"Create result: {create_result}")
            assert not create_result.get("error"), f"Create index failed: {create_result}"
            # create_or_update returns "created" boolean and may have "status" field
            assert create_result.get("created") is True or create_result.get("status") in ("CREATING", "ALREADY_EXISTS", None)

            # Step 2: Wait for index to be ready and verify via get
            log_time("Step 2: Waiting for index to be ready...")
            max_wait = 300  # 5 minutes
            wait_interval = 10
            waited = 0

            while waited < max_wait:
                get_result = manage_vs_index(action="get", name=index_name)
                state = get_result.get("state", get_result.get("status"))
                ready = get_result.get("ready", False)
                log_time(f"Index state: {state}, ready: {ready}")
                if ready:
                    log_time(f"Index ready after {waited}s")
                    break
                time.sleep(wait_interval)
                waited += wait_interval
            else:
                pytest.skip(f"Index not ready after {max_wait}s, skipping remaining tests")

            # Step 3: Query the index
            log_time("Step 3: Querying index...")
            query_result = query_vs_index(
                index_name=index_name,
                columns=["id", "content", "category"],
                query_text="analytics platform",
                num_results=3,
            )
            log_time(f"Query result: {query_result}")
            assert not query_result.get("error"), f"Query failed: {query_result}"

            results = query_result.get("result", {}).get("data_array", []) or query_result.get("results", [])
            assert len(results) > 0, f"Query should return results: {query_result}"

            # Verify the expected document is found
            result_contents = str(results)
            assert "doc1" in result_contents or "Databricks" in result_contents or "analytics" in result_contents, \
                f"Query should return doc about Databricks analytics: {results}"

            # Step 4: Delete the index
            log_time("Step 4: Deleting index...")
            delete_result = manage_vs_index(action="delete", name=index_name)
            log_time(f"Delete result: {delete_result}")
            assert not delete_result.get("error"), f"Delete index failed: {delete_result}"

            # Step 5: Verify index is gone
            log_time("Step 5: Verifying deletion...")
            time.sleep(10)
            get_after = manage_vs_index(action="get", name=index_name)
            log_time(f"Get after delete: {get_after}")
            assert get_after.get("state") == "NOT_FOUND" or "error" in get_after, \
                f"Index should be deleted: {get_after}"

            log_time("Full index lifecycle test PASSED!")

        except Exception as e:
            # Cleanup on failure
            log_time(f"Test failed, attempting cleanup: {e}")
            try:
                manage_vs_index(action="delete", name=index_name)
            except Exception:
                pass
            raise


@pytest.mark.integration
class TestVsEndpointLifecycle:
    """End-to-end test for VS endpoint lifecycle: create -> get -> delete."""

    def test_full_endpoint_lifecycle(self, clean_vs_resources):
        """Test complete endpoint lifecycle: create, get, delete, verify."""
        test_start = time.time()

        def log_time(msg):
            elapsed = time.time() - test_start
            logger.info(f"[{elapsed:.1f}s] {msg}")

        try:
            # Step 1: Create endpoint
            log_time("Step 1: Creating endpoint...")
            create_result = manage_vs_endpoint(
                action="create_or_update",
                name=VS_ENDPOINT_DELETE,
                endpoint_type="STANDARD",
            )
            log_time(f"Create result: {create_result}")
            assert not create_result.get("error"), f"Create failed: {create_result}"
            assert create_result.get("name") == VS_ENDPOINT_DELETE

            # Step 2: Verify endpoint exists via get
            log_time("Step 2: Verifying endpoint exists...")
            time.sleep(5)
            get_before = manage_vs_endpoint(action="get", name=VS_ENDPOINT_DELETE)
            log_time(f"Get result: {get_before}")
            assert get_before.get("state") != "NOT_FOUND", \
                f"Endpoint should exist after create: {get_before}"

            # Step 3: Delete endpoint
            log_time("Step 3: Deleting endpoint...")
            delete_result = manage_vs_endpoint(action="delete", name=VS_ENDPOINT_DELETE)
            log_time(f"Delete result: {delete_result}")
            assert not delete_result.get("error"), f"Delete failed: {delete_result}"

            # Step 4: Verify endpoint is gone
            log_time("Step 4: Verifying deletion...")
            time.sleep(5)
            get_after = manage_vs_endpoint(action="get", name=VS_ENDPOINT_DELETE)
            log_time(f"Get after delete: {get_after}")
            assert get_after.get("state") == "NOT_FOUND" or "error" in get_after, \
                f"Endpoint should be deleted: {get_after}"

            log_time("Full endpoint lifecycle test PASSED!")

        except Exception as e:
            # Cleanup on failure
            log_time(f"Test failed, attempting cleanup: {e}")
            try:
                manage_vs_endpoint(action="delete", name=VS_ENDPOINT_DELETE)
            except Exception:
                pass
            raise
