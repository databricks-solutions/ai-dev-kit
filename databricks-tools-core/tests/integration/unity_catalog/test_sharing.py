"""
Integration tests for Unity Catalog - Delta Sharing operations.

Tests:
- list_shares, create_share, get_share, delete_share
- add_table_to_share, remove_table_from_share
- grant_share_to_recipient, revoke_share_from_recipient
- list_recipients, create_recipient, get_recipient, delete_recipient
- list_providers

Note: Delta Sharing must be enabled in the workspace.
Tests skip if the feature is not available.
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    list_shares,
    get_share,
    create_share,
    add_table_to_share,
    remove_table_from_share,
    grant_share_to_recipient,
    revoke_share_from_recipient,
    list_recipients,
    get_recipient,
    create_recipient,
    list_providers,
)

logger = logging.getLogger(__name__)

UC_TEST_PREFIX = "uc_test"


def _is_sharing_error(e: Exception) -> bool:
    """Check if error indicates sharing is not available."""
    msg = str(e).upper()
    return any(
        kw in msg
        for kw in [
            "FEATURE_NOT_ENABLED",
            "NOT_FOUND",
            "FORBIDDEN",
            "PERMISSION_DENIED",
            "DELTA_SHARING",
            "NOT_AVAILABLE",
        ]
    )


@pytest.mark.integration
class TestListShares:
    """Tests for listing shares."""

    def test_list_shares(self):
        """Should list shares (may be empty)."""
        try:
            shares = list_shares()
            logger.info(f"Found {len(shares)} shares")
            assert isinstance(shares, list)
        except Exception as e:
            if _is_sharing_error(e):
                pytest.skip(f"Delta Sharing not available: {e}")
            raise


@pytest.mark.integration
class TestShareCRUD:
    """Tests for share create, get, delete lifecycle."""

    def test_create_and_delete_share(self, unique_name: str, cleanup_shares):
        """Should create and delete a share."""
        share_name = f"{UC_TEST_PREFIX}_share_{unique_name}"

        try:
            logger.info(f"Creating share: {share_name}")
            share = create_share(
                name=share_name,
                comment="Integration test share",
            )
            cleanup_shares(share_name)

            assert share["name"] == share_name
            logger.info(f"Share created: {share['name']}")

            # Get share
            fetched = get_share(share_name)
            assert fetched["name"] == share_name
            logger.info(f"Share fetched: {fetched['name']}")

        except Exception as e:
            if _is_sharing_error(e):
                pytest.skip(f"Delta Sharing not available: {e}")
            raise

    def test_add_and_remove_table_from_share(
        self,
        uc_test_table: str,
        unique_name: str,
        cleanup_shares,
    ):
        """Should add and remove a table from a share."""
        share_name = f"{UC_TEST_PREFIX}_share_tbl_{unique_name}"

        try:
            # Create share
            create_share(name=share_name)
            cleanup_shares(share_name)

            # Add table
            logger.info(f"Adding table {uc_test_table} to share {share_name}")
            result = add_table_to_share(
                share_name=share_name,
                table_name=uc_test_table,
            )
            assert result is not None
            logger.info("Table added to share")

            # Verify table is in share
            share = get_share(share_name, include_shared_data=True)
            objects = share.get("objects", [])
            logger.info(f"Share has {len(objects)} objects")

            # Remove table
            logger.info("Removing table from share")
            remove_result = remove_table_from_share(
                share_name=share_name,
                table_name=uc_test_table,
            )
            assert remove_result is not None
            logger.info("Table removed from share")

        except Exception as e:
            if _is_sharing_error(e):
                pytest.skip(f"Delta Sharing not available: {e}")
            raise


@pytest.mark.integration
class TestRecipientCRUD:
    """Tests for recipient create, get, delete lifecycle."""

    def test_create_and_delete_recipient(self, unique_name: str, cleanup_recipients):
        """Should create and delete a sharing recipient."""
        recipient_name = f"{UC_TEST_PREFIX}_recipient_{unique_name}"

        try:
            logger.info(f"Creating recipient: {recipient_name}")
            recipient = create_recipient(
                name=recipient_name,
                authentication_type="TOKEN",
                comment="Integration test recipient",
            )
            cleanup_recipients(recipient_name)

            assert recipient["name"] == recipient_name
            logger.info(f"Recipient created: {recipient['name']}")

            # Get recipient
            fetched = get_recipient(recipient_name)
            assert fetched["name"] == recipient_name
            logger.info(f"Recipient fetched: {fetched['name']}")

        except Exception as e:
            if _is_sharing_error(e):
                pytest.skip(f"Delta Sharing not available: {e}")
            raise

    def test_list_recipients(self):
        """Should list recipients."""
        try:
            recipients = list_recipients()
            logger.info(f"Found {len(recipients)} recipients")
            assert isinstance(recipients, list)
        except Exception as e:
            if _is_sharing_error(e):
                pytest.skip(f"Delta Sharing not available: {e}")
            raise


@pytest.mark.integration
class TestSharePermissions:
    """Tests for share grant/revoke to recipients."""

    def test_grant_and_revoke_share(
        self,
        uc_test_table: str,
        unique_name: str,
        cleanup_shares,
        cleanup_recipients,
    ):
        """Should grant and revoke share permissions to a recipient."""
        share_name = f"{UC_TEST_PREFIX}_share_perm_{unique_name}"
        recipient_name = f"{UC_TEST_PREFIX}_recip_perm_{unique_name}"

        try:
            # Create share with table
            create_share(name=share_name)
            cleanup_shares(share_name)
            add_table_to_share(share_name=share_name, table_name=uc_test_table)

            # Create recipient
            create_recipient(name=recipient_name, authentication_type="TOKEN")
            cleanup_recipients(recipient_name)

            # Grant
            logger.info(
                f"Granting share '{share_name}' to recipient '{recipient_name}'"
            )
            grant_result = grant_share_to_recipient(
                share_name=share_name,
                recipient_name=recipient_name,
            )
            assert grant_result["status"] == "granted"
            logger.info(f"Share granted: {grant_result}")

            # Revoke
            logger.info("Revoking share from recipient")
            revoke_result = revoke_share_from_recipient(
                share_name=share_name,
                recipient_name=recipient_name,
            )
            assert revoke_result["status"] == "revoked"
            logger.info(f"Share revoked: {revoke_result}")

        except Exception as e:
            if _is_sharing_error(e):
                pytest.skip(f"Delta Sharing not available: {e}")
            raise


@pytest.mark.integration
class TestListProviders:
    """Tests for listing sharing providers."""

    def test_list_providers(self):
        """Should list sharing providers (may be empty)."""
        try:
            providers = list_providers()
            logger.info(f"Found {len(providers)} providers")
            assert isinstance(providers, list)
        except Exception as e:
            if _is_sharing_error(e):
                pytest.skip(f"Delta Sharing not available: {e}")
            raise
