"""
Integration tests for compute execution functions.

Tests execute_databricks_command and run_python_file_on_databricks with a real cluster.
"""

import tempfile
import pytest
from pathlib import Path

from databricks_tools_core.compute import (
    execute_databricks_command,
    run_python_file_on_databricks,
    list_clusters,
    get_best_cluster,
    destroy_context,
    NoRunningClusterError,
)


@pytest.fixture(scope="module")
def shared_context():
    """
    Create a shared execution context for tests that need cluster execution.

    This speeds up tests by reusing the same context instead of creating
    a new one for each test (context creation takes ~5-10s).
    """
    # Get a running cluster
    cluster_id = get_best_cluster()
    if cluster_id is None:
        pytest.skip("No running cluster available")

    # Create context with first execution
    result = execute_databricks_command(
        code='print("Context initialized")',
        cluster_id=cluster_id,
        timeout=120,
    )

    if not result.success:
        pytest.fail(f"Failed to create shared context: {result.error}")

    yield {
        "cluster_id": result.cluster_id,
        "context_id": result.context_id,
    }

    # Cleanup
    try:
        destroy_context(result.cluster_id, result.context_id)
    except Exception:
        pass  # Ignore cleanup errors


@pytest.mark.integration
class TestListClusters:
    """Tests for list_clusters function."""

    def test_list_clusters_running_only(self):
        """Should list running clusters quickly."""
        clusters = list_clusters(include_terminated=False)

        print("\n=== List Running Clusters ===")
        print(f"Found {len(clusters)} running clusters:")
        for c in clusters[:5]:
            print(f"  - {c['cluster_name']} ({c['cluster_id']}) - {c['state']}")

        assert isinstance(clusters, list)
        # All should be running/pending states
        for c in clusters:
            assert c['state'] in ['RUNNING', 'PENDING', 'RESIZING', 'RESTARTING']

    def test_list_clusters_with_limit(self):
        """Should respect limit parameter."""
        clusters = list_clusters(limit=5)

        print("\n=== List Clusters (limit=5) ===")
        print(f"Found {len(clusters)} clusters")

        assert isinstance(clusters, list)
        assert len(clusters) <= 5


@pytest.mark.integration
class TestGetBestCluster:
    """Tests for get_best_cluster function."""

    def test_get_best_cluster(self):
        """Should return a running cluster ID or None."""
        cluster_id = get_best_cluster()

        print("\n=== Get Best Cluster ===")
        print(f"Best cluster ID: {cluster_id}")

        # Result can be None if no running clusters
        if cluster_id is not None:
            assert isinstance(cluster_id, str)
            assert len(cluster_id) > 0


@pytest.mark.integration
class TestExecuteDatabricksCommand:
    """Tests for execute_databricks_command function."""

    def test_simple_code_with_shared_context(self, shared_context):
        """Should execute simple code with shared context."""
        result = execute_databricks_command(
            code='print("Hello from shared context!")',
            cluster_id=shared_context["cluster_id"],
            context_id=shared_context["context_id"],
            timeout=120
        )

        print("\n=== Shared Context Execution ===")
        print(f"Success: {result.success}")
        print(f"Output: {result.output}")

        assert result.success, f"Execution failed: {result.error}"
        assert "Hello" in result.output
        assert result.context_id == shared_context["context_id"]

    def test_context_variable_persistence(self, shared_context):
        """Should persist variables across executions in same context."""
        # Set a variable
        result1 = execute_databricks_command(
            code='test_var = 42\nprint(f"Set test_var = {test_var}")',
            cluster_id=shared_context["cluster_id"],
            context_id=shared_context["context_id"],
            timeout=120
        )

        print("\n=== First Execution ===")
        print(f"Success: {result1.success}")

        assert result1.success, f"First execution failed: {result1.error}"

        # Read the variable back
        result2 = execute_databricks_command(
            code='print(f"test_var is still {test_var}")',
            cluster_id=shared_context["cluster_id"],
            context_id=shared_context["context_id"],
            timeout=120
        )

        print("\n=== Second Execution ===")
        print(f"Success: {result2.success}")
        print(f"Output: {result2.output}")

        assert result2.success, f"Second execution failed: {result2.error}"
        assert "test_var is still 42" in result2.output

    def test_sql_execution(self, shared_context):
        """Should execute SQL queries."""
        result = execute_databricks_command(
            code='SELECT 1 + 1 as result',
            cluster_id=shared_context["cluster_id"],
            language='sql',
            timeout=120,
        )

        print("\n=== SQL Execution ===")
        print(f"Success: {result.success}")
        print(f"Output: {result.output}")

        assert result.success, f"SQL execution failed: {result.error}"

    def test_destroy_context_on_completion(self):
        """Should destroy context when requested."""
        try:
            result = execute_databricks_command(
                code='print("Destroying context after this")',
                timeout=120,
                destroy_context_on_completion=True
            )

            print("\n=== Destroy Context On Completion ===")
            print(f"Success: {result.success}")
            print(f"Context Destroyed: {result.context_destroyed}")

            assert result.success, f"Execution failed: {result.error}"
            assert result.context_destroyed is True
            assert "destroyed" in result.message.lower()

        except NoRunningClusterError as e:
            pytest.skip(f"No running cluster available: {e}")


@pytest.mark.integration
class TestRunPythonFileOnDatabricks:
    """Tests for run_python_file_on_databricks function."""

    def test_simple_file_execution(self, shared_context):
        """Should execute a simple Python file."""
        code = 'print("Hello from file!")\nprint(2 + 2)'

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            result = run_python_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                timeout=120,
            )

            print("\n=== File Execution Result ===")
            print(f"Success: {result.success}")
            print(f"Output: {result.output}")

            assert result.success, f"Execution failed: {result.error}"
            assert "Hello from file!" in result.output

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_spark_code(self, shared_context):
        """Should execute Spark code."""
        code = """
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()
df = spark.range(5)
print(f"Row count: {df.count()}")
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            result = run_python_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                timeout=120,
            )

            print("\n=== Spark Execution Result ===")
            print(f"Success: {result.success}")
            print(f"Output: {result.output}")

            assert result.success, f"Spark execution failed: {result.error}"
            assert "Row count: 5" in result.output

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_error_handling(self, shared_context):
        """Should capture Python errors with details."""
        code = "x = 1 / 0  # This will raise ZeroDivisionError"

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            result = run_python_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                timeout=120,
            )

            print("\n=== Error Handling Result ===")
            print(f"Success: {result.success}")
            print(f"Error: {result.error[:200] if result.error else None}...")

            assert not result.success, "Should have failed with division by zero"
            assert result.error is not None
            assert "ZeroDivisionError" in result.error

        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_file_not_found(self):
        """Should handle missing file gracefully (no cluster needed)."""
        result = run_python_file_on_databricks(
            file_path="/nonexistent/path/to/file.py",
            timeout=120
        )

        print("\n=== File Not Found Result ===")
        print(f"Success: {result.success}")
        print(f"Error: {result.error}")

        assert not result.success
        assert "not found" in result.error.lower()
