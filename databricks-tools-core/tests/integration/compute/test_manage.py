"""
Integration tests for compute management functions.

Tests create_cluster, modify_cluster, terminate_cluster, delete_cluster,
list_node_types, list_spark_versions, create_sql_warehouse, modify_sql_warehouse,
and delete_sql_warehouse.

Requires a valid Databricks connection (e.g. DATABRICKS_CONFIG_PROFILE=E2-Demo).
"""

import logging
import time
import pytest

from databricks_tools_core.compute import (
    create_cluster,
    modify_cluster,
    terminate_cluster,
    delete_cluster,
    list_node_types,
    list_spark_versions,
    create_sql_warehouse,
    modify_sql_warehouse,
    delete_sql_warehouse,
    get_cluster_status,
)
from databricks_tools_core.auth import get_workspace_client

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def managed_cluster():
    """Create a test cluster and clean it up after all tests.

    Yields the cluster_id. The cluster is permanently deleted after the
    test module completes.
    """
    result = create_cluster(
        name="ai-dev-kit-test-manage",
        num_workers=0,
        autotermination_minutes=10,
    )

    assert result["cluster_id"] is not None
    cluster_id = result["cluster_id"]

    logger.info(f"Created test cluster: {cluster_id}")

    yield cluster_id

    # Cleanup: permanently delete
    try:
        delete_cluster(cluster_id)
        logger.info(f"Cleaned up test cluster: {cluster_id}")
    except Exception as e:
        logger.warning(f"Failed to cleanup test cluster {cluster_id}: {e}")


@pytest.fixture(scope="module")
def managed_warehouse():
    """Create a test SQL warehouse and clean it up after all tests.

    Yields the warehouse_id. The warehouse is permanently deleted after the
    test module completes.
    """
    result = create_sql_warehouse(
        name="ai-dev-kit-test-manage",
        size="2X-Small",
        auto_stop_mins=10,
        enable_serverless=True,
    )

    assert result["warehouse_id"] is not None
    warehouse_id = result["warehouse_id"]

    logger.info(f"Created test warehouse: {warehouse_id}")

    yield warehouse_id

    # Cleanup: permanently delete
    try:
        delete_sql_warehouse(warehouse_id)
        logger.info(f"Cleaned up test warehouse: {warehouse_id}")
    except Exception as e:
        logger.warning(f"Failed to cleanup test warehouse {warehouse_id}: {e}")


@pytest.mark.integration
class TestListNodeTypes:
    """Tests for list_node_types function."""

    def test_list_node_types(self):
        """Should return a non-empty list of node types."""
        node_types = list_node_types()

        print(f"\n=== List Node Types ===")
        print(f"Found {len(node_types)} node types")
        for nt in node_types[:5]:
            print(f"  - {nt['node_type_id']} ({nt['memory_mb']}MB, {nt['num_cores']} cores)")

        assert isinstance(node_types, list)
        assert len(node_types) > 0
        assert "node_type_id" in node_types[0]
        assert "memory_mb" in node_types[0]

    def test_node_type_has_expected_fields(self):
        """Each node type should have expected fields."""
        node_types = list_node_types()
        nt = node_types[0]

        assert "node_type_id" in nt
        assert "memory_mb" in nt
        assert "num_gpus" in nt
        assert "description" in nt


@pytest.mark.integration
class TestListSparkVersions:
    """Tests for list_spark_versions function."""

    def test_list_spark_versions(self):
        """Should return a non-empty list of spark versions."""
        versions = list_spark_versions()

        print(f"\n=== List Spark Versions ===")
        print(f"Found {len(versions)} versions")
        for v in versions[:5]:
            print(f"  - {v['key']}: {v['name']}")

        assert isinstance(versions, list)
        assert len(versions) > 0
        assert "key" in versions[0]
        assert "name" in versions[0]

    def test_has_lts_versions(self):
        """Should include at least one LTS version."""
        versions = list_spark_versions()
        lts = [v for v in versions if "LTS" in (v["name"] or "")]
        assert len(lts) > 0, "No LTS versions found"


@pytest.mark.integration
class TestCreateCluster:
    """Tests for create_cluster function."""

    def test_create_cluster_returns_expected_fields(self, managed_cluster):
        """managed_cluster fixture validates create_cluster returns cluster_id.

        This test just verifies the cluster exists.
        """
        status = get_cluster_status(managed_cluster)

        print(f"\n=== Created Cluster Status ===")
        print(f"Cluster ID: {status['cluster_id']}")
        print(f"Name: {status['cluster_name']}")
        print(f"State: {status['state']}")

        assert status["cluster_id"] == managed_cluster
        assert status["cluster_name"] == "ai-dev-kit-test-manage"


@pytest.mark.integration
class TestTerminateCluster:
    """Tests for terminate_cluster function."""

    def test_terminate_cluster(self, managed_cluster):
        """Should terminate the cluster (reversible)."""
        result = terminate_cluster(managed_cluster)

        print(f"\n=== Terminate Cluster ===")
        print(f"Result: {result}")

        assert result["cluster_id"] == managed_cluster
        assert result["state"] in ("TERMINATING", "TERMINATED")
        assert "reversible" in result["message"].lower() or "terminated" in result["message"].lower()


@pytest.mark.integration
class TestModifyCluster:
    """Tests for modify_cluster function.

    Runs after TestTerminateCluster so the cluster is in a stable (TERMINATED/TERMINATING)
    state — the edit API rejects edits on PENDING clusters.
    """

    def _wait_for_terminated(self, cluster_id, timeout=120):
        """Wait until cluster reaches TERMINATED state."""
        import time
        start = time.time()
        while time.time() - start < timeout:
            status = get_cluster_status(cluster_id)
            if status["state"] == "TERMINATED":
                return
            time.sleep(5)
        pytest.fail(f"Cluster did not terminate within {timeout}s")

    def test_modify_cluster_name(self, managed_cluster):
        """Should modify cluster name."""
        self._wait_for_terminated(managed_cluster)

        result = modify_cluster(
            cluster_id=managed_cluster,
            name="ai-dev-kit-test-manage-renamed",
        )

        print(f"\n=== Modify Cluster ===")
        print(f"Result: {result}")

        assert result["cluster_id"] == managed_cluster
        assert result["cluster_name"] == "ai-dev-kit-test-manage-renamed"
        assert "updated" in result["message"].lower()

        # Rename back for other tests
        modify_cluster(
            cluster_id=managed_cluster,
            name="ai-dev-kit-test-manage",
        )


@pytest.mark.integration
class TestCreateSqlWarehouse:
    """Tests for create_sql_warehouse function."""

    def test_create_warehouse_returns_expected_fields(self, managed_warehouse):
        """managed_warehouse fixture validates create returns warehouse_id."""
        w = get_workspace_client()
        wh = w.warehouses.get(managed_warehouse)

        print(f"\n=== Created Warehouse ===")
        print(f"Warehouse ID: {wh.id}")
        print(f"Name: {wh.name}")
        print(f"State: {wh.state}")

        assert wh.id == managed_warehouse
        assert wh.name == "ai-dev-kit-test-manage"


@pytest.mark.integration
class TestModifySqlWarehouse:
    """Tests for modify_sql_warehouse function."""

    def test_modify_warehouse_name(self, managed_warehouse):
        """Should modify warehouse name."""
        result = modify_sql_warehouse(
            warehouse_id=managed_warehouse,
            name="ai-dev-kit-test-manage-renamed",
        )

        print(f"\n=== Modify Warehouse ===")
        print(f"Result: {result}")

        assert result["warehouse_id"] == managed_warehouse
        assert result["name"] == "ai-dev-kit-test-manage-renamed"
        assert "updated" in result["message"].lower()

        # Rename back
        modify_sql_warehouse(
            warehouse_id=managed_warehouse,
            name="ai-dev-kit-test-manage",
        )


@pytest.mark.integration
class TestDeleteCluster:
    """Tests for delete_cluster function."""

    def test_delete_cluster_warning_message(self):
        """Should include a permanent deletion warning in the response."""
        # Create a throwaway cluster for deletion test
        result = create_cluster(
            name="ai-dev-kit-test-delete",
            num_workers=0,
            autotermination_minutes=10,
        )
        cluster_id = result["cluster_id"]

        try:
            delete_result = delete_cluster(cluster_id)

            print(f"\n=== Delete Cluster ===")
            print(f"Result: {delete_result}")

            assert delete_result["cluster_id"] == cluster_id
            assert delete_result["state"] == "DELETED"
            assert "permanent" in delete_result["message"].lower()
            assert "warning" in delete_result["message"].lower()
        except Exception:
            # Best-effort cleanup if delete fails
            try:
                delete_cluster(cluster_id)
            except Exception:
                pass
            raise


@pytest.mark.integration
class TestDeleteSqlWarehouse:
    """Tests for delete_sql_warehouse function."""

    def test_delete_warehouse_warning_message(self):
        """Should include a permanent deletion warning in the response."""
        # Create a throwaway warehouse for deletion test
        result = create_sql_warehouse(
            name="ai-dev-kit-test-delete",
            size="2X-Small",
            auto_stop_mins=10,
        )
        warehouse_id = result["warehouse_id"]

        try:
            delete_result = delete_sql_warehouse(warehouse_id)

            print(f"\n=== Delete Warehouse ===")
            print(f"Result: {delete_result}")

            assert delete_result["warehouse_id"] == warehouse_id
            assert delete_result["state"] == "DELETED"
            assert "permanent" in delete_result["message"].lower()
            assert "warning" in delete_result["message"].lower()
        except Exception:
            try:
                delete_sql_warehouse(warehouse_id)
            except Exception:
                pass
            raise
