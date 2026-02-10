"""
Integration tests for Lakebase Unity Catalog registration.

Tests:
- create_lakebase_catalog
- get_lakebase_catalog
- delete_lakebase_catalog

Requires a running Lakebase instance.
"""

import logging

import pytest

from databricks_tools_core.lakebase import (
    create_lakebase_catalog,
    delete_lakebase_catalog,
    get_lakebase_catalog,
)

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestCreateCatalog:
    """Tests for registering a Lakebase instance as a UC catalog."""

    def test_create_catalog(
        self, lakebase_instance_name: str, unique_name, cleanup_catalogs
    ):
        """Should register a Lakebase instance as a UC catalog."""
        catalog_name = f"lb_test_cat_{unique_name}"
        cleanup_catalogs(catalog_name)

        try:
            result = create_lakebase_catalog(
                name=catalog_name,
                instance_name=lakebase_instance_name,
                database_name="databricks_postgres",
                create_database_if_not_exists=True,
            )
        except Exception as e:
            if "CREATE CATALOG" in str(e) or "permission" in str(e).lower():
                pytest.skip("User lacks CREATE CATALOG permission on this metastore")
            raise

        logger.info(f"Create catalog result: {result}")

        assert result["name"] == catalog_name
        assert result["instance_name"] == lakebase_instance_name
        assert result["status"] in ("created", "ALREADY_EXISTS")

    def test_create_duplicate_catalog(
        self, lakebase_instance_name: str, unique_name, cleanup_catalogs
    ):
        """Should return ALREADY_EXISTS for duplicate catalog."""
        catalog_name = f"lb_test_cat_dup_{unique_name}"
        cleanup_catalogs(catalog_name)

        # Create first
        try:
            create_lakebase_catalog(
                name=catalog_name,
                instance_name=lakebase_instance_name,
                database_name="databricks_postgres",
                create_database_if_not_exists=True,
            )
        except Exception as e:
            if "CREATE CATALOG" in str(e) or "permission" in str(e).lower():
                pytest.skip("User lacks CREATE CATALOG permission on this metastore")
            raise

        # Create again
        result = create_lakebase_catalog(
            name=catalog_name,
            instance_name=lakebase_instance_name,
        )

        assert result["status"] == "ALREADY_EXISTS"


@pytest.mark.integration
class TestGetCatalog:
    """Tests for getting Lakebase catalog details."""

    def test_get_catalog(
        self, lakebase_instance_name: str, unique_name, cleanup_catalogs
    ):
        """Should return catalog details."""
        catalog_name = f"lb_test_cat_get_{unique_name}"
        cleanup_catalogs(catalog_name)

        # Create
        try:
            create_lakebase_catalog(
                name=catalog_name,
                instance_name=lakebase_instance_name,
                database_name="databricks_postgres",
                create_database_if_not_exists=True,
            )
        except Exception as e:
            if "CREATE CATALOG" in str(e) or "permission" in str(e).lower():
                pytest.skip("User lacks CREATE CATALOG permission on this metastore")
            raise

        # Get
        result = get_lakebase_catalog(catalog_name)

        logger.info(f"Get catalog result: {result}")

        assert result["name"] == catalog_name
        assert result.get("instance_name") == lakebase_instance_name

    def test_get_catalog_not_found(self):
        """Should return NOT_FOUND for non-existent catalog."""
        result = get_lakebase_catalog("nonexistent_lb_catalog_99999")

        assert result["status"] == "NOT_FOUND"
        assert "error" in result


@pytest.mark.integration
class TestDeleteCatalog:
    """Tests for deleting Lakebase catalogs."""

    def test_delete_catalog(
        self, lakebase_instance_name: str, unique_name, cleanup_catalogs
    ):
        """Should delete a Lakebase catalog."""
        catalog_name = f"lb_test_cat_del_{unique_name}"
        # Don't register for cleanup since we're testing delete

        # Create
        try:
            create_lakebase_catalog(
                name=catalog_name,
                instance_name=lakebase_instance_name,
                database_name="databricks_postgres",
                create_database_if_not_exists=True,
            )
        except Exception as e:
            if "CREATE CATALOG" in str(e) or "permission" in str(e).lower():
                pytest.skip("User lacks CREATE CATALOG permission on this metastore")
            raise

        # Delete
        result = delete_lakebase_catalog(catalog_name)

        logger.info(f"Delete catalog result: {result}")

        assert result["name"] == catalog_name
        assert result["status"] == "deleted"

        # Verify it's gone
        verify = get_lakebase_catalog(catalog_name)
        assert verify["status"] == "NOT_FOUND"

    def test_delete_catalog_not_found(self):
        """Should return NOT_FOUND for non-existent catalog."""
        result = delete_lakebase_catalog("nonexistent_lb_catalog_99999")

        assert result["status"] == "NOT_FOUND"
        assert "error" in result
