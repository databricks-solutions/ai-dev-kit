"""
Integration tests for Vector Search index operations.

Tests:
- create_vs_index
- get_vs_index
- list_vs_indexes
- delete_vs_index
- sync_vs_index
"""

import json
import logging
import uuid

import pytest

from databricks_tools_core.vector_search import (
    create_vs_index,
    delete_vs_index,
    get_vs_index,
    list_vs_indexes,
    sync_vs_index,
)

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 8


@pytest.mark.integration
class TestCreateIndex:
    """Tests for creating indexes."""

    def test_create_direct_access_index(self, vs_endpoint_name: str, test_catalog, test_schema, cleanup_indexes):
        """Should create a Direct Access index."""
        suffix = uuid.uuid4().hex[:8]
        index_name = f"{test_catalog}.{test_schema}.vs_idx_create_{suffix}"
        cleanup_indexes(index_name)

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
                "schema_json": json.dumps(
                    {
                        "id": "int",
                        "text": "string",
                        "embedding": "array<float>",
                    }
                ),
            },
        )

        logger.info(f"Create index result: {result}")

        assert result["name"] == index_name
        assert result["endpoint_name"] == vs_endpoint_name
        assert result["index_type"] == "DIRECT_ACCESS"
        assert result["status"] in ("CREATING", "ALREADY_EXISTS")

    def test_create_duplicate_index(self, vs_endpoint_name: str, vs_direct_index_name: str):
        """Should return ALREADY_EXISTS for duplicate index."""
        result = create_vs_index(
            name=vs_direct_index_name,
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
                "schema_json": json.dumps(
                    {
                        "id": "int",
                        "text": "string",
                        "embedding": "array<float>",
                    }
                ),
            },
        )

        assert result["status"] == "ALREADY_EXISTS"


@pytest.mark.integration
class TestGetIndex:
    """Tests for getting index details."""

    def test_get_index(self, vs_direct_index_name: str):
        """Should return details for an existing index."""
        result = get_vs_index(vs_direct_index_name)

        logger.info(f"Index details: {result}")

        assert result["name"] == vs_direct_index_name
        assert result.get("index_type") == "DIRECT_ACCESS"
        assert result.get("primary_key") == "id"
        assert result.get("state") == "ONLINE"

    def test_get_index_not_found(self, test_catalog, test_schema):
        """Should return NOT_FOUND for non-existent index."""
        result = get_vs_index(f"{test_catalog}.{test_schema}.nonexistent_idx_99999")

        assert result["state"] == "NOT_FOUND"
        assert "error" in result


@pytest.mark.integration
class TestListIndexes:
    """Tests for listing indexes."""

    def test_list_indexes(self, vs_endpoint_name: str, vs_direct_index_name: str):
        """Should list indexes on the endpoint including our test index."""
        indexes = list_vs_indexes(vs_endpoint_name)

        logger.info(f"Found {len(indexes)} indexes on {vs_endpoint_name}")

        assert isinstance(indexes, list)
        assert len(indexes) > 0

        names = [idx["name"] for idx in indexes]
        assert vs_direct_index_name in names, f"Test index '{vs_direct_index_name}' not in: {names}"


@pytest.mark.integration
class TestSyncIndex:
    """Tests for syncing indexes."""

    def test_sync_direct_access_index(self, vs_direct_index_name: str):
        """Sync on Direct Access index should raise (not a Delta Sync index)."""
        # Direct Access indexes don't support sync - expect an error
        with pytest.raises(Exception):
            sync_vs_index(vs_direct_index_name)


@pytest.mark.integration
class TestDeleteIndex:
    """Tests for deleting indexes."""

    def test_delete_index_not_found(self, test_catalog, test_schema):
        """Should return NOT_FOUND when deleting non-existent index."""
        result = delete_vs_index(f"{test_catalog}.{test_schema}.nonexistent_idx_99999")

        assert result["status"] == "NOT_FOUND"
        assert "error" in result
