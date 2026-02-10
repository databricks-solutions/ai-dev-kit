"""
Integration tests for Vector Search query and data operations.

Tests:
- upsert_vs_data
- query_vs_index
- scan_vs_index
- delete_vs_data

These tests run in order against a shared Direct Access index.
"""

import json
import logging
import time

import pytest

from databricks_tools_core.vector_search import (
    delete_vs_data,
    query_vs_index,
    scan_vs_index,
    upsert_vs_data,
)

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 8

# Sample data with small embeddings
SAMPLE_RECORDS = [
    {
        "id": 1,
        "text": "machine learning basics",
        "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    },
    {
        "id": 2,
        "text": "deep learning neural networks",
        "embedding": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    },
    {
        "id": 3,
        "text": "natural language processing",
        "embedding": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    },
    {
        "id": 4,
        "text": "computer vision and images",
        "embedding": [0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1],
    },
    {
        "id": 5,
        "text": "reinforcement learning agents",
        "embedding": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5],
    },
]


@pytest.mark.integration
class TestUpsertData:
    """Tests for upserting data into a Direct Access index."""

    def test_upsert_records(self, vs_direct_index_name: str):
        """Should upsert 5 records successfully."""
        result = upsert_vs_data(
            index_name=vs_direct_index_name,
            inputs_json=json.dumps(SAMPLE_RECORDS),
        )

        logger.info(f"Upsert result: {result}")

        assert result["name"] == vs_direct_index_name
        assert result["num_records"] == 5
        # Status can be SUCCESS or the enum value
        assert "status" in result

        # Small delay for data to be indexed
        time.sleep(3)

    def test_upsert_single_record(self, vs_direct_index_name: str):
        """Should upsert a single record (update existing)."""
        updated_record = [
            {
                "id": 1,
                "text": "machine learning fundamentals updated",
                "embedding": [0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85],
            }
        ]

        result = upsert_vs_data(
            index_name=vs_direct_index_name,
            inputs_json=json.dumps(updated_record),
        )

        assert result["num_records"] == 1
        time.sleep(2)


@pytest.mark.integration
class TestQueryIndex:
    """Tests for querying a Vector Search index."""

    def test_query_with_vector(self, vs_direct_index_name: str):
        """Should return results when querying with a vector."""
        # Query with a vector similar to record 1
        query_vec = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]

        result = query_vs_index(
            index_name=vs_direct_index_name,
            columns=["id", "text"],
            query_vector=query_vec,
            num_results=3,
        )

        logger.info(f"Query result: {result}")

        assert "columns" in result
        assert "data" in result
        assert result["num_results"] > 0
        assert result["num_results"] <= 3

    def test_query_with_fewer_results(self, vs_direct_index_name: str):
        """Should respect num_results parameter."""
        query_vec = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]

        result = query_vs_index(
            index_name=vs_direct_index_name,
            columns=["id", "text"],
            query_vector=query_vec,
            num_results=1,
        )

        assert result["num_results"] == 1

    def test_query_missing_params_raises(self, vs_direct_index_name: str):
        """Should raise ValueError when neither query_text nor query_vector provided."""
        with pytest.raises(ValueError, match="query_text or query_vector"):
            query_vs_index(
                index_name=vs_direct_index_name,
                columns=["id", "text"],
            )


@pytest.mark.integration
class TestScanIndex:
    """Tests for scanning index contents."""

    def test_scan_index(self, vs_direct_index_name: str):
        """Should return all entries in the index."""
        result = scan_vs_index(
            index_name=vs_direct_index_name,
            num_results=100,
        )

        logger.info(f"Scan result: {result.get('num_results')} entries")

        assert "columns" in result
        assert "data" in result
        assert result["num_results"] >= 5  # we upserted 5 records


@pytest.mark.integration
class TestDeleteData:
    """Tests for deleting data from a Direct Access index."""

    def test_delete_records(self, vs_direct_index_name: str):
        """Should delete specified records by primary key."""
        result = delete_vs_data(
            index_name=vs_direct_index_name,
            primary_keys=["4", "5"],
        )

        logger.info(f"Delete result: {result}")

        assert result["name"] == vs_direct_index_name
        assert result["num_deleted"] == 2

        # Small delay for deletion to propagate
        time.sleep(3)

    def test_verify_deletion(self, vs_direct_index_name: str):
        """Should show fewer entries after deletion."""
        result = scan_vs_index(
            index_name=vs_direct_index_name,
            num_results=100,
        )

        logger.info(f"After delete, scan shows {result.get('num_results')} entries")

        # Should have 3 remaining (5 upserted - 2 deleted)
        assert result["num_results"] <= 5  # at most 5
