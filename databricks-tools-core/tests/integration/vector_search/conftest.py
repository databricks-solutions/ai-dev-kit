"""
Pytest fixtures for Vector Search integration tests.

Provides session-scoped fixtures for:
- VS endpoint (created once, shared across all VS tests)
- Direct Access index (for query/upsert/scan tests)
- Cleanup helpers
"""

import json
import logging
import time
import uuid

import pytest

logger = logging.getLogger(__name__)

# Unique suffix to avoid collisions across test runs
_RUN_ID = str(uuid.uuid4())[:8]

VS_ENDPOINT_NAME = f"vs_test_ep_{_RUN_ID}"
VS_INDEX_NAME_TEMPLATE = "{catalog}.{schema}.vs_test_idx_{suffix}"
EMBEDDING_DIM = 8  # small dimension for fast tests

# Schema for Direct Access index
DA_SCHEMA = {
    "id": "int",
    "text": "string",
    "embedding": "array<float>",
}


def _wait_for_endpoint_online(name: str, timeout: int = 1200, poll: int = 15):
    """Poll endpoint until ONLINE or timeout."""
    from databricks_tools_core.vector_search import get_vs_endpoint

    deadline = time.time() + timeout
    while time.time() < deadline:
        ep = get_vs_endpoint(name)
        state = ep.get("state")
        logger.info(f"Endpoint '{name}' state: {state}")
        if state == "ONLINE":
            return ep
        if state in ("OFFLINE", "NOT_FOUND"):
            raise RuntimeError(f"Endpoint '{name}' in terminal state: {state}")
        time.sleep(poll)
    raise TimeoutError(f"Endpoint '{name}' not ONLINE within {timeout}s")


def _wait_for_index_online(index_name: str, timeout: int = 600, poll: int = 15):
    """Poll index until ONLINE or timeout.

    Handles transient InternalError from the VS service gracefully
    by treating them as 'still provisioning'.
    """
    from databricks_tools_core.vector_search import get_vs_index

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            idx = get_vs_index(index_name)
        except Exception as e:
            # Transient server errors during provisioning - keep retrying
            logger.warning(f"Transient error polling index '{index_name}': {e}")
            time.sleep(poll)
            continue
        state = idx.get("state")
        logger.info(f"Index '{index_name}' state: {state}")
        if state == "ONLINE":
            return idx
        if state == "NOT_FOUND":
            raise RuntimeError(f"Index '{index_name}' not found")
        time.sleep(poll)
    raise TimeoutError(f"Index '{index_name}' not ONLINE within {timeout}s")


@pytest.fixture(scope="session")
def vs_endpoint_name():
    """
    Create a Standard VS endpoint for the test session.

    Waits for ONLINE state before yielding.
    Deletes the endpoint after all tests complete.
    """
    from databricks_tools_core.vector_search import (
        create_vs_endpoint,
        delete_vs_endpoint,
        get_vs_endpoint,
    )

    name = VS_ENDPOINT_NAME
    logger.info(f"Creating VS endpoint: {name}")

    # Check if it already exists (from a previous failed run)
    existing = get_vs_endpoint(name)
    if existing.get("state") != "NOT_FOUND":
        logger.info(f"Endpoint '{name}' already exists, reusing")
    else:
        result = create_vs_endpoint(name=name, endpoint_type="STANDARD")
        logger.info(f"Endpoint creation result: {result}")

    # Wait for ONLINE
    _wait_for_endpoint_online(name)
    logger.info(f"Endpoint '{name}' is ONLINE")

    yield name

    # Teardown
    logger.info(f"Deleting VS endpoint: {name}")
    try:
        delete_vs_endpoint(name)
        logger.info(f"Endpoint '{name}' deleted")
    except Exception as e:
        logger.warning(f"Failed to delete endpoint '{name}': {e}")


@pytest.fixture(scope="module")
def vs_direct_index_name(vs_endpoint_name, test_catalog, test_schema):
    """
    Create a Direct Access index for query/data tests.

    Depends on test_catalog/test_schema to ensure the catalog exists.
    Uses a small embedding dimension for speed.
    Yields the fully qualified index name.
    """
    from databricks_tools_core.vector_search import (
        create_vs_index,
        delete_vs_index,
        get_vs_index,
    )

    suffix = str(uuid.uuid4())[:8]
    index_name = VS_INDEX_NAME_TEMPLATE.format(
        catalog=test_catalog, schema=test_schema, suffix=suffix
    )
    logger.info(f"Creating Direct Access index: {index_name}")

    # Check if it already exists
    existing = get_vs_index(index_name)
    if existing.get("state") != "NOT_FOUND":
        logger.info(f"Index '{index_name}' already exists, reusing")
    else:
        result = create_vs_index(
            name=index_name,
            endpoint_name=vs_endpoint_name,
            primary_key="id",
            index_type="DIRECT_ACCESS",
            direct_access_index_spec={
                "embedding_vector_columns": [
                    {
                        "name": "embedding",
                        "embedding_dimension": EMBEDDING_DIM,
                    }
                ],
                "schema_json": json.dumps(DA_SCHEMA),
            },
        )
        logger.info(f"Index creation result: {result}")

    # Wait for ONLINE
    _wait_for_index_online(index_name)
    logger.info(f"Index '{index_name}' is ONLINE")

    yield index_name

    # Teardown
    logger.info(f"Deleting Direct Access index: {index_name}")
    try:
        delete_vs_index(index_name)
        logger.info(f"Index '{index_name}' deleted")
    except Exception as e:
        logger.warning(f"Failed to delete index '{index_name}': {e}")


@pytest.fixture(scope="function")
def unique_suffix() -> str:
    """Generate a unique suffix for throwaway resources."""
    return str(uuid.uuid4())[:8]


@pytest.fixture(scope="function")
def cleanup_indexes():
    """Track and cleanup indexes created during a test."""
    from databricks_tools_core.vector_search import delete_vs_index

    indexes_to_cleanup = []

    def register(index_name: str):
        if index_name not in indexes_to_cleanup:
            indexes_to_cleanup.append(index_name)
            logger.info(f"Registered index for cleanup: {index_name}")

    yield register

    for idx_name in indexes_to_cleanup:
        try:
            logger.info(f"Cleaning up index: {idx_name}")
            delete_vs_index(idx_name)
        except Exception as e:
            logger.warning(f"Failed to cleanup index {idx_name}: {e}")


@pytest.fixture(scope="function")
def cleanup_endpoints():
    """Track and cleanup endpoints created during a test."""
    from databricks_tools_core.vector_search import delete_vs_endpoint

    endpoints_to_cleanup = []

    def register(name: str):
        if name not in endpoints_to_cleanup:
            endpoints_to_cleanup.append(name)
            logger.info(f"Registered endpoint for cleanup: {name}")

    yield register

    for ep_name in endpoints_to_cleanup:
        try:
            logger.info(f"Cleaning up endpoint: {ep_name}")
            delete_vs_endpoint(ep_name)
        except Exception as e:
            logger.warning(f"Failed to cleanup endpoint {ep_name}: {e}")
