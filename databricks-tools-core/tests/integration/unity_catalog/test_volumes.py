"""
Integration tests for Unity Catalog - Volume operations.

Tests:
- list_volumes
- get_volume
- create_volume
- update_volume
- delete_volume
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    list_volumes,
    get_volume,
    create_volume,
    update_volume,
    delete_volume,
)

logger = logging.getLogger(__name__)

UC_TEST_PREFIX = "uc_test"


@pytest.mark.integration
class TestListVolumes:
    """Tests for listing volumes."""

    def test_list_volumes(self, test_catalog: str, uc_test_schema: str):
        """Should list volumes in schema (may be empty)."""
        volumes = list_volumes(
            catalog_name=test_catalog,
            schema_name=uc_test_schema,
        )

        logger.info(f"Found {len(volumes)} volumes in {test_catalog}.{uc_test_schema}")
        assert isinstance(volumes, list)


@pytest.mark.integration
class TestVolumeCRUD:
    """Tests for volume create, get, update, delete lifecycle."""

    def test_create_managed_volume(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
        cleanup_volumes,
    ):
        """Should create a managed volume."""
        vol_name = f"{UC_TEST_PREFIX}_vol_{unique_name}"
        full_name = f"{test_catalog}.{uc_test_schema}.{vol_name}"

        logger.info(f"Creating managed volume: {full_name}")
        vol = create_volume(
            catalog_name=test_catalog,
            schema_name=uc_test_schema,
            name=vol_name,
            volume_type="MANAGED",
            comment="Test managed volume",
        )
        cleanup_volumes(full_name)

        assert vol.name == vol_name
        logger.info(f"Volume created: {vol.full_name}")

    def test_get_volume(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
        cleanup_volumes,
    ):
        """Should get volume details."""
        vol_name = f"{UC_TEST_PREFIX}_vol_{unique_name}"
        full_name = f"{test_catalog}.{uc_test_schema}.{vol_name}"

        create_volume(
            catalog_name=test_catalog,
            schema_name=uc_test_schema,
            name=vol_name,
            comment="Get test volume",
        )
        cleanup_volumes(full_name)

        fetched = get_volume(full_name)

        logger.info(f"Got volume: {fetched.full_name} (type: {fetched.volume_type})")
        assert fetched.name == vol_name
        assert fetched.catalog_name == test_catalog
        assert fetched.schema_name == uc_test_schema

    def test_update_volume_comment(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
        cleanup_volumes,
    ):
        """Should update volume comment."""
        vol_name = f"{UC_TEST_PREFIX}_vol_{unique_name}"
        full_name = f"{test_catalog}.{uc_test_schema}.{vol_name}"

        create_volume(
            catalog_name=test_catalog,
            schema_name=uc_test_schema,
            name=vol_name,
            comment="Original",
        )
        cleanup_volumes(full_name)

        updated = update_volume(
            full_volume_name=full_name,
            comment="Updated comment",
        )

        logger.info(f"Updated volume comment: {updated.comment}")
        assert updated.comment == "Updated comment"

    def test_update_volume_no_fields_raises(self):
        """Should raise ValueError when no update fields provided."""
        with pytest.raises(ValueError) as exc_info:
            update_volume(full_volume_name="cat.sch.vol")

        assert "at least one field" in str(exc_info.value).lower()

    def test_create_external_volume_without_location_raises(
        self,
        test_catalog: str,
        uc_test_schema: str,
    ):
        """Should raise ValueError for EXTERNAL volume without storage_location."""
        with pytest.raises(ValueError) as exc_info:
            create_volume(
                catalog_name=test_catalog,
                schema_name=uc_test_schema,
                name="bad_external",
                volume_type="EXTERNAL",
            )

        assert "storage_location" in str(exc_info.value).lower()

    def test_delete_volume(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
    ):
        """Should delete a volume."""
        vol_name = f"{UC_TEST_PREFIX}_vol_del_{unique_name}"
        full_name = f"{test_catalog}.{uc_test_schema}.{vol_name}"

        create_volume(
            catalog_name=test_catalog,
            schema_name=uc_test_schema,
            name=vol_name,
        )

        logger.info(f"Deleting volume: {full_name}")
        delete_volume(full_name)
        logger.info(f"Volume deleted: {full_name}")

        # Verify deletion
        with pytest.raises(Exception):
            get_volume(full_name)

    def test_list_volumes_after_create(
        self,
        test_catalog: str,
        uc_test_schema: str,
        unique_name: str,
        cleanup_volumes,
    ):
        """Should list volumes and include newly created one."""
        vol_name = f"{UC_TEST_PREFIX}_vol_list_{unique_name}"
        full_name = f"{test_catalog}.{uc_test_schema}.{vol_name}"

        create_volume(
            catalog_name=test_catalog,
            schema_name=uc_test_schema,
            name=vol_name,
        )
        cleanup_volumes(full_name)

        volumes = list_volumes(
            catalog_name=test_catalog,
            schema_name=uc_test_schema,
        )
        volume_names = [v.name for v in volumes]

        logger.info(f"Volumes in schema: {volume_names}")
        assert vol_name in volume_names
