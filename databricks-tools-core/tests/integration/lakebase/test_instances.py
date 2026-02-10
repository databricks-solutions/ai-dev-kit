"""
Integration tests for Lakebase Provisioned instance operations.

Tests:
- create_lakebase_instance
- get_lakebase_instance
- list_lakebase_instances
- update_lakebase_instance
- delete_lakebase_instance
- generate_lakebase_credential
"""

import logging
import time

import pytest

from databricks_tools_core.lakebase import (
    create_lakebase_instance,
    delete_lakebase_instance,
    generate_lakebase_credential,
    get_lakebase_instance,
    list_lakebase_instances,
    update_lakebase_instance,
)

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestGetInstance:
    """Tests for getting instance details."""

    def test_get_instance_running(self, lakebase_instance_name: str):
        """Should return details for a running instance."""
        result = get_lakebase_instance(lakebase_instance_name)

        logger.info(f"Instance details: {result}")

        assert result["name"] == lakebase_instance_name
        assert "state" in result
        # Instance should be ready (state string varies by SDK)
        state = result["state"].upper()
        assert any(s in state for s in ("RUNNING", "AVAILABLE", "ACTIVE")), (
            f"Unexpected state: {result['state']}"
        )
        assert "capacity" in result

    def test_get_instance_not_found(self):
        """Should return NOT_FOUND for non-existent instance."""
        result = get_lakebase_instance("nonexistent-instance-xyz-99999")

        assert result["state"] == "NOT_FOUND"
        assert "error" in result


@pytest.mark.integration
class TestListInstances:
    """Tests for listing instances."""

    def test_list_instances(self, lakebase_instance_name: str):
        """Should list instances including the test instance."""
        instances = list_lakebase_instances()

        logger.info(f"Found {len(instances)} instances")

        assert isinstance(instances, list)
        assert len(instances) > 0

        names = [inst["name"] for inst in instances]
        assert lakebase_instance_name in names, (
            f"Test instance '{lakebase_instance_name}' not in: {names}"
        )


@pytest.mark.integration
class TestCreateInstance:
    """Tests for creating instances."""

    def test_create_instance(self, cleanup_instances, unique_name):
        """Should create a new instance."""
        name = f"lb-test-create-{unique_name}"
        cleanup_instances(name)

        result = create_lakebase_instance(
            name=name,
            capacity="CU_1",
            stopped=False,
        )

        logger.info(f"Create result: {result}")

        assert result["name"] == name
        assert result.get("capacity") == "CU_1"
        assert result["status"] in ("CREATING", "ALREADY_EXISTS")

    def test_create_duplicate_instance(self, lakebase_instance_name: str):
        """Should return ALREADY_EXISTS for duplicate instance."""
        result = create_lakebase_instance(
            name=lakebase_instance_name,
            capacity="CU_1",
        )

        assert result["status"] == "ALREADY_EXISTS"


@pytest.mark.integration
class TestUpdateInstance:
    """Tests for updating instances."""

    def test_update_instance_stop(self, lakebase_instance_name: str):
        """Should stop the session instance (it will be restarted by other tests)."""
        result = update_lakebase_instance(name=lakebase_instance_name, stopped=True)
        logger.info(f"Stop result: {result}")
        assert result["status"] == "UPDATED"
        assert result.get("stopped") is True

        # Give it a moment then restart
        time.sleep(5)

        # Start it back up
        result = update_lakebase_instance(name=lakebase_instance_name, stopped=False)
        logger.info(f"Start result: {result}")
        assert result["status"] == "UPDATED"
        assert result.get("stopped") is False


@pytest.mark.integration
class TestGenerateCredential:
    """Tests for generating database credentials."""

    def test_generate_credential(self, lakebase_instance_name: str):
        """Should generate an OAuth token for connecting."""
        result = generate_lakebase_credential(instance_names=[lakebase_instance_name])

        logger.info(f"Credential result keys: {list(result.keys())}")

        assert "token" in result, "Expected OAuth token in result"
        assert len(result["token"]) > 0
        assert result["instance_names"] == [lakebase_instance_name]
        assert "message" in result


@pytest.mark.integration
class TestDeleteInstance:
    """Tests for deleting instances."""

    def test_delete_instance_not_found(self):
        """Should return NOT_FOUND when deleting non-existent instance."""
        result = delete_lakebase_instance("nonexistent-instance-xyz-99999")

        assert result["status"] == "NOT_FOUND"
        assert "error" in result
