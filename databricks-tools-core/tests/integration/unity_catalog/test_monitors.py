"""
Integration tests for Unity Catalog - Quality Monitor operations.

Tests:
- create_monitor
- get_monitor
- run_monitor_refresh
- list_monitor_refreshes
- delete_monitor

Note: Quality monitors require Lakehouse Monitoring to be enabled.
Tests skip if the feature is not available.
"""

import logging
import pytest

from databricks_tools_core.unity_catalog import (
    create_monitor,
    get_monitor,
    list_monitor_refreshes,
)

logger = logging.getLogger(__name__)

UC_TEST_PREFIX = "uc_test"


@pytest.mark.integration
@pytest.mark.slow
class TestMonitorCRUD:
    """Tests for monitor create, get, refresh, delete lifecycle."""

    def test_create_and_delete_monitor(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        warehouse_id: str,
        cleanup_monitors,
    ):
        """Should create and delete a quality monitor."""
        output_schema = f"{test_catalog}.{uc_test_schema}"

        try:
            logger.info(f"Creating monitor on: {uc_test_table}")
            monitor = create_monitor(
                table_name=uc_test_table,
                output_schema_name=output_schema,
            )
            cleanup_monitors(uc_test_table)

            assert monitor is not None
            logger.info(f"Monitor created: {monitor}")

            # Get monitor
            fetched = get_monitor(uc_test_table)
            assert fetched is not None
            logger.info(f"Monitor fetched: {fetched}")

        except Exception as e:
            if (
                "FEATURE_NOT_ENABLED" in str(e).upper()
                or "not enabled" in str(e).lower()
                or "NOT_FOUND" in str(e).upper()
            ):
                pytest.skip(f"Quality monitors not available: {e}")
            raise

    def test_list_monitor_refreshes(
        self,
        test_catalog: str,
        uc_test_schema: str,
        uc_test_table: str,
        warehouse_id: str,
        cleanup_monitors,
    ):
        """Should list refresh history for a monitor."""
        output_schema = f"{test_catalog}.{uc_test_schema}"

        try:
            # Create monitor
            create_monitor(
                table_name=uc_test_table,
                output_schema_name=output_schema,
            )
            cleanup_monitors(uc_test_table)

            # List refreshes (may be empty if no refresh has run)
            refreshes = list_monitor_refreshes(uc_test_table)
            assert isinstance(refreshes, list)
            logger.info(f"Monitor refreshes: {len(refreshes)}")

        except Exception as e:
            if (
                "FEATURE_NOT_ENABLED" in str(e).upper()
                or "not enabled" in str(e).lower()
                or "NOT_FOUND" in str(e).upper()
            ):
                pytest.skip(f"Quality monitors not available: {e}")
            raise

    def test_get_nonexistent_monitor(self):
        """Should raise error for table without monitor."""
        try:
            with pytest.raises(Exception):
                get_monitor("nonexistent_catalog.nonexistent_schema.nonexistent_table")
        except Exception as e:
            if "FEATURE_NOT_ENABLED" in str(e).upper():
                pytest.skip("Quality monitors not available")
            raise
