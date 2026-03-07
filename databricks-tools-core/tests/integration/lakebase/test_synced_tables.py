"""
Integration tests for Lakebase synced table (reverse ETL) operations.

Tests:
- create_synced_table
- get_synced_table
- delete_synced_table

Requires a running Lakebase instance and a source Delta table.
"""

import logging
import time

import pytest

from databricks_tools_core.lakebase import (
    create_lakebase_catalog,
    create_synced_table,
    delete_synced_table,
    get_synced_table,
)

logger = logging.getLogger(__name__)


def _create_catalog_or_skip(catalog_name: str, instance_name: str):
    """Create a Lakebase catalog, skipping test if permissions are lacking."""
    try:
        create_lakebase_catalog(
            name=catalog_name,
            instance_name=instance_name,
            database_name="databricks_postgres",
            create_database_if_not_exists=True,
        )
    except Exception as e:
        err = str(e)
        if "CREATE CATALOG" in err or "permission" in err.lower() or "storage root" in err.lower():
            pytest.skip(f"Cannot create catalog on this metastore: {err[:120]}")
        raise


@pytest.mark.integration
class TestCreateSyncedTable:
    """Tests for creating synced tables."""

    def test_create_synced_table(
        self,
        lakebase_instance_name: str,
        source_delta_table: str,
        unique_name,
        cleanup_synced_tables,
        cleanup_catalogs,
    ):
        """Should create a synced table from a source Delta table."""
        catalog_name = f"lb_sync_cat_{unique_name}"
        cleanup_catalogs(catalog_name)

        _create_catalog_or_skip(catalog_name, lakebase_instance_name)
        time.sleep(5)

        target_table = f"{catalog_name}.public.synced_{unique_name}"
        cleanup_synced_tables(target_table)

        result = create_synced_table(
            instance_name=lakebase_instance_name,
            source_table_name=source_delta_table,
            target_table_name=target_table,
            primary_key_columns=["id"],
            scheduling_policy="TRIGGERED",
        )

        logger.info(f"Create synced table result: {result}")

        assert result["instance_name"] == lakebase_instance_name
        assert result["source_table_name"] == source_delta_table
        assert result["target_table_name"] == target_table
        assert result["status"] in ("CREATING", "ALREADY_EXISTS")


@pytest.mark.integration
class TestGetSyncedTable:
    """Tests for getting synced table details."""

    def test_get_synced_table(
        self,
        lakebase_instance_name: str,
        source_delta_table: str,
        unique_name,
        cleanup_synced_tables,
        cleanup_catalogs,
    ):
        """Should return synced table details."""
        catalog_name = f"lb_sync_cat_get_{unique_name}"
        cleanup_catalogs(catalog_name)

        _create_catalog_or_skip(catalog_name, lakebase_instance_name)
        time.sleep(5)

        target_table = f"{catalog_name}.public.synced_get_{unique_name}"
        cleanup_synced_tables(target_table)

        create_synced_table(
            instance_name=lakebase_instance_name,
            source_table_name=source_delta_table,
            target_table_name=target_table,
            primary_key_columns=["id"],
        )
        time.sleep(5)

        result = get_synced_table(target_table)

        logger.info(f"Get synced table result: {result}")

        assert result["table_name"] == target_table
        assert result.get("instance_name") == lakebase_instance_name
        assert result.get("source_table_name") == source_delta_table

    def test_get_synced_table_not_found(self):
        """Should return NOT_FOUND for non-existent synced table."""
        result = get_synced_table("nonexistent_cat.nonexistent_schema.nonexistent_table")

        assert result["status"] == "NOT_FOUND"
        assert "error" in result


@pytest.mark.integration
class TestDeleteSyncedTable:
    """Tests for deleting synced tables."""

    def test_delete_synced_table(
        self,
        lakebase_instance_name: str,
        source_delta_table: str,
        unique_name,
        cleanup_catalogs,
    ):
        """Should delete a synced table."""
        catalog_name = f"lb_sync_cat_del_{unique_name}"
        cleanup_catalogs(catalog_name)

        _create_catalog_or_skip(catalog_name, lakebase_instance_name)
        time.sleep(5)

        target_table = f"{catalog_name}.public.synced_del_{unique_name}"

        create_synced_table(
            instance_name=lakebase_instance_name,
            source_table_name=source_delta_table,
            target_table_name=target_table,
            primary_key_columns=["id"],
        )
        time.sleep(5)

        # Delete
        result = delete_synced_table(target_table)

        logger.info(f"Delete synced table result: {result}")

        assert result["table_name"] == target_table
        assert result["status"] == "deleted"

    def test_delete_synced_table_not_found(self):
        """Should return NOT_FOUND for non-existent synced table."""
        result = delete_synced_table("nonexistent_cat.nonexistent_schema.nonexistent_table")

        assert result["status"] == "NOT_FOUND"
        assert "error" in result
