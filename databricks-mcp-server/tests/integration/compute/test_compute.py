"""
Integration tests for compute MCP tools.

Tests:
- execute_code: serverless and cluster execution
- list_compute: clusters, node_types, spark_versions
- manage_cluster: create, modify, start, terminate, delete
"""

import logging
import time

import pytest

from databricks_mcp_server.tools.compute import execute_code, list_compute, manage_cluster
from tests.test_config import TEST_RESOURCE_PREFIX

logger = logging.getLogger(__name__)

# Deterministic name for tests (enables safe cleanup/restart)
CLUSTER_NAME = f"{TEST_RESOURCE_PREFIX}cluster_lifecycle"


@pytest.mark.integration
class TestListCompute:
    """Tests for list_compute tool."""

    @pytest.mark.slow
    def test_list_clusters(self):
        """Should list all clusters (slow - iterates all clusters)."""
        result = list_compute(resource="clusters")

        logger.info(f"List clusters result: {result}")

        assert "error" not in result, f"List failed: {result}"
        assert "clusters" in result
        assert isinstance(result["clusters"], list)

    def test_list_node_types(self):
        """Should list available node types."""
        result = list_compute(resource="node_types")

        logger.info(f"List node types result: {result}")

        assert "error" not in result, f"List failed: {result}"
        assert "node_types" in result
        assert isinstance(result["node_types"], list)
        assert len(result["node_types"]) > 0

    def test_list_spark_versions(self):
        """Should list available Spark versions."""
        result = list_compute(resource="spark_versions")

        logger.info(f"List spark versions result: {result}")

        assert "error" not in result, f"List failed: {result}"
        assert "spark_versions" in result
        assert isinstance(result["spark_versions"], list)
        assert len(result["spark_versions"]) > 0

    def test_invalid_resource(self):
        """Should return error for invalid resource type."""
        result = list_compute(resource="invalid_resource")

        assert "error" in result


@pytest.mark.integration
class TestExecuteCode:
    """Tests for execute_code tool.

    Consolidated into fewer tests to minimize serverless cold start overhead (~30s each).
    """

    def test_execute_serverless_comprehensive(self):
        """Test Python, SQL via spark.sql, and error handling in one serverless run.

        This consolidates multiple scenarios into one test to avoid repeated cold starts.
        Tests: print output, spark.sql execution, try/except error handling.
        """
        # Comprehensive notebook that tests multiple scenarios
        code = '''
# Test 1: Basic Python output
print("TEST1: Hello from MCP test")
result_value = 42
print(f"TEST1: Result value is {result_value}")

# Test 2: SQL via spark.sql
df = spark.sql("SELECT 42 as answer, 'hello' as greeting")
print(f"TEST2: SQL row count = {df.count()}")
row = df.first()
print(f"TEST2: answer={row.answer}, greeting={row.greeting}")

# Test 3: Error handling (try invalid code in try/except)
error_caught = False
try:
    exec("this is not valid python!!!")
except SyntaxError as e:
    error_caught = True
    print(f"TEST3: Caught expected SyntaxError: {type(e).__name__}")

if not error_caught:
    raise Exception("TEST3 FAILED: SyntaxError was not caught")

print("ALL TESTS PASSED")
dbutils.notebook.exit("success")
'''
        result = execute_code(
            code=code,
            compute_type="serverless",
            timeout=180,
        )

        logger.info(f"Comprehensive execute result: {result}")

        assert not result.get("error"), f"Execute failed: {result}"
        assert result.get("success", False), f"Execution should succeed: {result}"

        # Serverless notebooks return dbutils.notebook.exit() value as result
        # Print statements go to logs which may not be captured in result
        output = str(result.get("output", "")) + str(result.get("result", ""))

        # If we got "success" it means all internal tests passed (including SQL and error handling)
        # The notebook only exits with "success" if all tests pass
        assert "success" in output.lower(), \
            f"Notebook should exit with success (all internal tests passed): {output}"


@pytest.mark.integration
class TestManageCluster:
    """Tests for manage_cluster tool (read-only operations)."""

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = manage_cluster(action="invalid_action")

        assert "error" in result


@pytest.mark.integration
class TestClusterLifecycle:
    """End-to-end test for complete cluster lifecycle.

    Consolidated into a single test: create -> list -> start -> terminate -> delete.
    This is much faster than separate tests that each create their own cluster.
    """

    def test_full_cluster_lifecycle(self, workspace_client):
        """Test complete cluster lifecycle: create, list, start, terminate, delete."""
        cluster_id = None
        test_start = time.time()

        def log_time(msg):
            elapsed = time.time() - test_start
            print(f"[{elapsed:.1f}s] {msg}", flush=True)

        try:
            # Step 1: Create cluster
            log_time("Step 1: Creating cluster...")
            t0 = time.time()
            create_result = manage_cluster(
                action="create",
                name=CLUSTER_NAME,
                num_workers=0,  # Single-node for cost savings
                autotermination_minutes=10,
            )
            log_time(f"Create took {time.time()-t0:.1f}s - Result: {create_result}")
            assert create_result.get("cluster_id"), f"Create failed: {create_result}"
            cluster_id = create_result["cluster_id"]

            # Step 2: Get cluster to verify it exists (test both APIs)
            log_time("Step 2a: Verifying cluster via manage_cluster(get)...")
            t0 = time.time()
            status = manage_cluster(action="get", cluster_id=cluster_id)
            log_time(f"Get took {time.time()-t0:.1f}s - Status: {status.get('state')}")
            assert "error" not in status, f"Get cluster failed: {status}"
            assert status.get("cluster_name") == CLUSTER_NAME, f"Name mismatch: {status}"

            log_time("Step 2b: Verifying cluster via list_compute(cluster_id)...")
            t0 = time.time()
            status2 = list_compute(resource="clusters", cluster_id=cluster_id)
            log_time(f"list_compute took {time.time()-t0:.1f}s - Status: {status2.get('state')}")
            assert "error" not in status2, f"list_compute failed: {status2}"

            # Step 3: Start the cluster
            log_time("Step 3: Starting cluster...")
            t0 = time.time()
            start_result = manage_cluster(action="start", cluster_id=cluster_id)
            log_time(f"Start took {time.time()-t0:.1f}s - Result: {start_result}")
            # Start may fail if cluster is already starting/running, that's ok
            if "error" in str(start_result).lower() and "already" not in str(start_result).lower():
                assert False, f"Start failed unexpectedly: {start_result}"

            # Wait for cluster to start processing the request
            log_time("Waiting 10s after start request...")
            time.sleep(10)

            # Check state (should be PENDING, RUNNING, or STARTING)
            t0 = time.time()
            status = manage_cluster(action="get", cluster_id=cluster_id)
            log_time(f"State check took {time.time()-t0:.1f}s - State: {status.get('state')}")

            # Step 4: Terminate the cluster
            log_time("Step 4: Terminating cluster...")
            t0 = time.time()
            terminate_result = manage_cluster(action="terminate", cluster_id=cluster_id)
            log_time(f"Terminate took {time.time()-t0:.1f}s - Result: {terminate_result}")
            assert "error" not in str(terminate_result).lower() or terminate_result.get("success"), \
                f"Terminate failed: {terminate_result}"

            # Wait for termination to process
            log_time("Waiting 10s after terminate request...")
            time.sleep(10)

            # Poll for TERMINATED state (max 60s)
            max_wait = 60
            waited = 0
            while waited < max_wait:
                t0 = time.time()
                status = manage_cluster(action="get", cluster_id=cluster_id)
                state = status.get("state")
                log_time(f"Poll took {time.time()-t0:.1f}s - State after {waited}s: {state}")
                if state == "TERMINATED":
                    break
                time.sleep(10)
                waited += 10

            # Step 5: Delete the cluster (permanent)
            log_time("Step 5: Deleting cluster...")
            t0 = time.time()
            delete_result = manage_cluster(action="delete", cluster_id=cluster_id)
            log_time(f"Delete took {time.time()-t0:.1f}s - Result: {delete_result}")
            assert "error" not in str(delete_result).lower() or delete_result.get("success"), \
                f"Delete failed: {delete_result}"

            # Wait for deletion
            time.sleep(5)

            # Verify cluster is gone or marked as deleted
            t0 = time.time()
            final_status = manage_cluster(action="get", cluster_id=cluster_id)
            log_time(f"Final check took {time.time()-t0:.1f}s - Status: {final_status}")

            is_deleted = (
                final_status.get("exists") is False or
                final_status.get("state") in ("DELETED", "TERMINATED")
            )
            assert is_deleted, f"Cluster should be deleted: {final_status}"

            log_time("Full cluster lifecycle test PASSED!")
            cluster_id = None  # Clear so finally block doesn't try to clean up

        finally:
            # Cleanup if test failed partway through
            if cluster_id:
                log_time(f"Cleanup: attempting to delete cluster {cluster_id}")
                try:
                    manage_cluster(action="terminate", cluster_id=cluster_id)
                    time.sleep(5)
                    manage_cluster(action="delete", cluster_id=cluster_id)
                except Exception as e:
                    logger.warning(f"Cleanup failed: {e}")
