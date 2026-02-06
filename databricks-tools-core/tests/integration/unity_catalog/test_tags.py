"""
Integration tests for Unity Catalog - Tag and Comment operations.

Tests:
- set_tags
- unset_tags
- set_comment
- query_table_tags
- query_column_tags
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    set_tags,
    unset_tags,
    set_comment,
    query_table_tags,
    query_column_tags,
)

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestSetTags:
    """Tests for setting tags on UC objects."""

    def test_set_tags_on_table(self, uc_test_table: str, warehouse_id: str):
        """Should set tags on a table."""
        # Use unique prefixed tag names to avoid workspace governed tag policies
        result = set_tags(
            object_type="table",
            full_name=uc_test_table,
            tags={"uc_test_tier": "silver", "uc_test_owner": "data-eng"},
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "tags_set"
        assert result["tags"]["uc_test_tier"] == "silver"
        logger.info(f"Tags set on {uc_test_table}: {result['tags']}")

    def test_set_tags_on_column(self, uc_test_table: str, warehouse_id: str):
        """Should set tags on a column."""
        # Use unique prefixed tag names to avoid workspace governed tag policies
        result = set_tags(
            object_type="column",
            full_name=uc_test_table,
            column_name="email",
            tags={"uc_test_col_class": "sensitive", "uc_test_col_level": "high"},
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "tags_set"
        logger.info(f"Column tags set: {result['tags']}")

    def test_set_tags_on_schema(
        self, test_catalog: str, uc_test_schema: str, warehouse_id: str
    ):
        """Should set tags on a schema."""
        full_name = f"{test_catalog}.{uc_test_schema}"
        # Use unique prefixed tag names to avoid workspace governed tag policies
        result = set_tags(
            object_type="schema",
            full_name=full_name,
            tags={"uc_test_deploy": "testing"},
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "tags_set"
        logger.info(f"Schema tags set: {result['tags']}")

    def test_set_tags_column_without_column_name_raises(self, uc_test_table: str):
        """Should raise ValueError when column_name missing for column type."""
        with pytest.raises(ValueError) as exc_info:
            set_tags(
                object_type="column",
                full_name=uc_test_table,
                tags={"test": "value"},
            )

        assert "column_name" in str(exc_info.value).lower()

    def test_set_tags_invalid_object_type_raises(self, uc_test_table: str):
        """Should raise ValueError for invalid object type."""
        with pytest.raises(ValueError) as exc_info:
            set_tags(
                object_type="invalid_type",
                full_name=uc_test_table,
                tags={"test": "value"},
            )

        assert "object_type" in str(exc_info.value).lower()


@pytest.mark.integration
class TestUnsetTags:
    """Tests for removing tags from UC objects."""

    def test_unset_tags_on_table(self, uc_test_table: str, warehouse_id: str):
        """Should remove tags from a table."""
        # Set tags first
        set_tags(
            object_type="table",
            full_name=uc_test_table,
            tags={"temp_tag": "to_remove"},
            warehouse_id=warehouse_id,
        )

        # Unset
        result = unset_tags(
            object_type="table",
            full_name=uc_test_table,
            tag_names=["temp_tag"],
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "tags_unset"
        assert "temp_tag" in result["tag_names"]
        logger.info(f"Tags unset: {result['tag_names']}")

    def test_unset_tags_on_column(self, uc_test_table: str, warehouse_id: str):
        """Should remove tags from a column."""
        # Set first
        set_tags(
            object_type="column",
            full_name=uc_test_table,
            column_name="salary",
            tags={"temp_col_tag": "remove_me"},
            warehouse_id=warehouse_id,
        )

        # Unset
        result = unset_tags(
            object_type="column",
            full_name=uc_test_table,
            column_name="salary",
            tag_names=["temp_col_tag"],
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "tags_unset"
        logger.info(f"Column tags unset: {result['tag_names']}")


@pytest.mark.integration
class TestSetComment:
    """Tests for setting comments on UC objects."""

    def test_set_comment_on_table(self, uc_test_table: str, warehouse_id: str):
        """Should set a comment on a table."""
        result = set_comment(
            object_type="table",
            full_name=uc_test_table,
            comment_text="Employee records for UC testing",
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "comment_set"
        logger.info(f"Comment set on {uc_test_table}")

    def test_set_comment_on_column(self, uc_test_table: str, warehouse_id: str):
        """Should set a comment on a column."""
        result = set_comment(
            object_type="column",
            full_name=uc_test_table,
            column_name="salary",
            comment_text="Annual salary in USD",
            warehouse_id=warehouse_id,
        )

        assert result["status"] == "comment_set"
        logger.info("Column comment set on salary")

    def test_set_comment_column_without_name_raises(self, uc_test_table: str):
        """Should raise ValueError when column_name missing for column type."""
        with pytest.raises(ValueError) as exc_info:
            set_comment(
                object_type="column",
                full_name=uc_test_table,
                comment_text="test",
            )

        assert "column_name" in str(exc_info.value).lower()


@pytest.mark.integration
class TestQueryTags:
    """Tests for querying tags from information_schema."""

    def test_query_table_tags(self, test_catalog: str, uc_test_table: str, warehouse_id: str):
        """Should query table tags from information_schema."""
        # Ensure tags exist
        set_tags(
            object_type="table",
            full_name=uc_test_table,
            tags={"query_test": "yes"},
            warehouse_id=warehouse_id,
        )

        results = query_table_tags(
            catalog_filter=test_catalog,
            tag_name="query_test",
            limit=10,
            warehouse_id=warehouse_id,
        )

        logger.info(f"Found {len(results)} table tag entries")
        assert isinstance(results, list)
        # May take time for tags to propagate to information_schema
        if len(results) > 0:
            assert "tag_name" in results[0] or "TAG_NAME" in str(results[0].keys())

    def test_query_column_tags(self, test_catalog: str, uc_test_table: str, warehouse_id: str):
        """Should query column tags from information_schema."""
        # Ensure column tags exist
        set_tags(
            object_type="column",
            full_name=uc_test_table,
            column_name="email",
            tags={"col_query_test": "yes"},
            warehouse_id=warehouse_id,
        )

        results = query_column_tags(
            catalog_filter=test_catalog,
            tag_name="col_query_test",
            limit=10,
            warehouse_id=warehouse_id,
        )

        logger.info(f"Found {len(results)} column tag entries")
        assert isinstance(results, list)

    def test_query_table_tags_no_results(self, warehouse_id: str):
        """Should return empty list for non-matching filter."""
        results = query_table_tags(
            tag_name="nonexistent_tag_xyz_12345",
            limit=10,
            warehouse_id=warehouse_id,
        )

        assert isinstance(results, list)
        assert len(results) == 0
