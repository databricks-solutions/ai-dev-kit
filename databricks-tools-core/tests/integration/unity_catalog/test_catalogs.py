"""
Integration tests for Unity Catalog - Catalog operations.

Tests:
- list_catalogs
- get_catalog
- create_catalog
- update_catalog
- delete_catalog
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    list_catalogs,
    get_catalog,
    create_catalog,
    update_catalog,
    delete_catalog,
)

logger = logging.getLogger(__name__)

TEST_CATALOG_PREFIX = "uc_test_catalog"


@pytest.mark.integration
class TestListCatalogs:
    """Tests for listing catalogs."""

    def test_list_catalogs(self):
        """Should list catalogs in the metastore."""
        catalogs = list_catalogs()

        logger.info(f"Found {len(catalogs)} catalogs")
        for cat in catalogs[:5]:
            logger.info(f"  - {cat.name}")

        assert isinstance(catalogs, list)
        assert len(catalogs) > 0, "Should have at least one catalog"

    def test_list_catalogs_contains_main(self):
        """Should contain the main catalog."""
        catalogs = list_catalogs()
        catalog_names = [c.name for c in catalogs]

        # Most workspaces have a 'main' catalog
        assert any(name in catalog_names for name in ["main", "hive_metastore"]), (
            f"Expected 'main' or 'hive_metastore' in catalogs: {catalog_names[:10]}"
        )


@pytest.mark.integration
class TestGetCatalog:
    """Tests for getting catalog details."""

    def test_get_catalog(self, test_catalog: str):
        """Should get catalog details by name."""
        catalog = get_catalog(test_catalog)

        logger.info(f"Got catalog: {catalog.name} (owner: {catalog.owner})")

        assert catalog.name == test_catalog
        assert catalog.owner is not None

    def test_get_catalog_not_found(self):
        """Should raise error for non-existent catalog."""
        with pytest.raises(Exception) as exc_info:
            get_catalog("nonexistent_catalog_xyz_12345")

        error_msg = str(exc_info.value).lower()
        logger.info(f"Expected error: {exc_info.value}")
        assert "not found" in error_msg or "does not exist" in error_msg


@pytest.mark.integration
class TestCatalogCRUD:
    """Tests for catalog create, update, delete lifecycle."""

    def test_create_and_delete_catalog(self, unique_name: str):
        """Should create and delete a catalog."""
        catalog_name = f"{TEST_CATALOG_PREFIX}_{unique_name}"

        try:
            # Create
            logger.info(f"Creating catalog: {catalog_name}")
            catalog = create_catalog(
                name=catalog_name,
                comment="Integration test catalog",
            )

            assert catalog.name == catalog_name
            assert catalog.comment == "Integration test catalog"
            logger.info(f"Catalog created: {catalog.name}")

            # Verify via get
            fetched = get_catalog(catalog_name)
            assert fetched.name == catalog_name

        finally:
            # Cleanup
            try:
                logger.info(f"Deleting catalog: {catalog_name}")
                delete_catalog(catalog_name, force=True)
                logger.info(f"Catalog deleted: {catalog_name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup catalog: {e}")

    def test_update_catalog_comment(self, unique_name: str):
        """Should update catalog comment."""
        catalog_name = f"{TEST_CATALOG_PREFIX}_{unique_name}"

        try:
            # Create
            create_catalog(name=catalog_name, comment="Original comment")

            # Update comment
            logger.info(f"Updating catalog comment: {catalog_name}")
            updated = update_catalog(
                catalog_name=catalog_name,
                comment="Updated comment",
            )

            assert updated.comment == "Updated comment"
            logger.info(f"Catalog comment updated: {updated.comment}")

        finally:
            try:
                delete_catalog(catalog_name, force=True)
            except Exception as e:
                logger.warning(f"Failed to cleanup catalog: {e}")

    def test_update_catalog_no_fields_raises(self, test_catalog: str):
        """Should raise ValueError when no fields provided."""
        with pytest.raises(ValueError) as exc_info:
            update_catalog(catalog_name=test_catalog)

        assert "at least one field" in str(exc_info.value).lower()

    def test_delete_catalog_not_found(self):
        """Should raise error when deleting non-existent catalog."""
        with pytest.raises(Exception):
            delete_catalog("nonexistent_catalog_xyz_12345")
