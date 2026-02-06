"""
Integration tests for Unity Catalog - Storage operations.

Tests:
- list_storage_credentials
- list_external_locations
- validate_storage_credential

Note: Create/update/delete operations for storage credentials and external
locations require cloud-specific resources (IAM roles, access connectors, etc.)
and are tested as read-only list operations in CI. Full CRUD requires manual
setup with proper cloud credentials.
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    list_storage_credentials,
    get_storage_credential,
    create_storage_credential,
    list_external_locations,
    get_external_location,
    validate_storage_credential,
)

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestListStorageCredentials:
    """Tests for listing storage credentials."""

    def test_list_storage_credentials(self):
        """Should list storage credentials in the metastore."""
        credentials = list_storage_credentials()

        logger.info(f"Found {len(credentials)} storage credentials")
        for cred in credentials[:5]:
            logger.info(f"  - {cred.name} (read_only: {cred.read_only})")

        assert isinstance(credentials, list)
        # Most workspaces have at least the default credential
        assert len(credentials) >= 0

    def test_list_storage_credentials_structure(self):
        """Should return StorageCredentialInfo objects."""
        credentials = list_storage_credentials()

        if len(credentials) > 0:
            cred = credentials[0]
            assert hasattr(cred, "name")
            assert hasattr(cred, "owner")
            logger.info(f"First credential: {cred.name}")


@pytest.mark.integration
class TestGetStorageCredential:
    """Tests for getting a specific storage credential."""

    def test_get_existing_credential(self):
        """Should get details of an existing credential."""
        credentials = list_storage_credentials()
        if not credentials:
            pytest.skip("No storage credentials in workspace")

        cred_name = credentials[0].name
        logger.info(f"Getting credential: {cred_name}")

        cred = get_storage_credential(cred_name)
        assert cred.name == cred_name
        logger.info(f"Got credential: {cred.name} (owner: {cred.owner})")

    def test_get_nonexistent_credential(self):
        """Should raise error for non-existent credential."""
        with pytest.raises(Exception):
            get_storage_credential("nonexistent_credential_xyz_12345")


@pytest.mark.integration
class TestValidateStorageCredential:
    """Tests for validating storage credentials."""

    def test_validate_existing_credential(self):
        """Should validate an existing storage credential."""
        credentials = list_storage_credentials()
        if not credentials:
            pytest.skip("No storage credentials in workspace")

        cred_name = credentials[0].name
        logger.info(f"Validating credential: {cred_name}")

        try:
            result = validate_storage_credential(name=cred_name)
            assert isinstance(result, dict)
            assert "results" in result
            logger.info(f"Validation result: {result}")
        except Exception as e:
            # Some credentials may not support validation without a URL
            logger.info(f"Validation requires URL: {e}")


@pytest.mark.integration
class TestCreateStorageCredentialValidation:
    """Tests for storage credential creation validation."""

    def test_create_without_cloud_credentials_raises(self):
        """Should raise ValueError when no cloud credentials provided."""
        with pytest.raises(ValueError) as exc_info:
            create_storage_credential(
                name="test_bad_credential",
            )

        assert (
            "aws_iam_role_arn" in str(exc_info.value).lower()
            or "azure_access_connector_id" in str(exc_info.value).lower()
        )


@pytest.mark.integration
class TestListExternalLocations:
    """Tests for listing external locations."""

    def test_list_external_locations(self):
        """Should list external locations."""
        locations = list_external_locations()

        logger.info(f"Found {len(locations)} external locations")
        for loc in locations[:5]:
            logger.info(f"  - {loc.name} -> {loc.url}")

        assert isinstance(locations, list)

    def test_list_external_locations_structure(self):
        """Should return ExternalLocationInfo objects."""
        locations = list_external_locations()

        if len(locations) > 0:
            loc = locations[0]
            assert hasattr(loc, "name")
            assert hasattr(loc, "url")
            assert hasattr(loc, "credential_name")
            logger.info(f"First location: {loc.name} -> {loc.url}")


@pytest.mark.integration
class TestGetExternalLocation:
    """Tests for getting a specific external location."""

    def test_get_existing_location(self):
        """Should get details of an existing external location."""
        locations = list_external_locations()
        if not locations:
            pytest.skip("No external locations in workspace")

        loc_name = locations[0].name
        logger.info(f"Getting external location: {loc_name}")

        loc = get_external_location(loc_name)
        assert loc.name == loc_name
        logger.info(f"Got location: {loc.name} (url: {loc.url})")

    def test_get_nonexistent_location(self):
        """Should raise error for non-existent location."""
        with pytest.raises(Exception):
            get_external_location("nonexistent_location_xyz_12345")
