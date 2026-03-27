"""
Integration tests for compute execution functions.

Tests execute_databricks_command, run_file_on_databricks (with language detection,
workspace_path persistence), and backwards-compatible run_python_file_on_databricks.
"""

import logging
import tempfile
import pytest
from pathlib import Path

from databricks_tools_core.compute import (
    execute_databricks_command,
    run_file_on_databricks,
    run_python_file_on_databricks,
    list_clusters,
    get_best_cluster,
    destroy_context,
    NoRunningClusterError,
    ExecutionResult,
)
from databricks_tools_core.auth import get_workspace_client, get_current_username

logger = logging.getLogger(__name__)


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
            assert c["state"] in ["RUNNING", "PENDING", "RESIZING", "RESTARTING"]

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
            timeout=120,
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
            timeout=120,
        )

        print("\n=== First Execution ===")
        print(f"Success: {result1.success}")

        assert result1.success, f"First execution failed: {result1.error}"

        # Read the variable back
        result2 = execute_databricks_command(
            code='print(f"test_var is still {test_var}")',
            cluster_id=shared_context["cluster_id"],
            context_id=shared_context["context_id"],
            timeout=120,
        )

        print("\n=== Second Execution ===")
        print(f"Success: {result2.success}")
        print(f"Output: {result2.output}")

        assert result2.success, f"Second execution failed: {result2.error}"
        assert "test_var is still 42" in result2.output

    def test_sql_execution(self, shared_context):
        """Should execute SQL queries."""
        result = execute_databricks_command(
            code="SELECT 1 + 1 as result",
            cluster_id=shared_context["cluster_id"],
            language="sql",
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
                destroy_context_on_completion=True,
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
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

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
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
        result = run_python_file_on_databricks(file_path="/nonexistent/path/to/file.py", timeout=120)

        print("\n=== File Not Found Result ===")
        print(f"Success: {result.success}")
        print(f"Error: {result.error}")

        assert not result.success
        assert "not found" in result.error.lower()


@pytest.mark.integration
class TestRunFileOnDatabricks:
    """Tests for run_file_on_databricks (renamed from run_python_file_on_databricks).

    Covers: language auto-detection, multi-language support, workspace_path persistence,
    backwards compatibility alias.
    """

    def test_backwards_compat_alias(self):
        """run_python_file_on_databricks should be an alias for run_file_on_databricks."""
        assert run_python_file_on_databricks is run_file_on_databricks

    def test_python_auto_detect(self, shared_context):
        """Should auto-detect Python from .py extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('print("auto-detected python")')
            temp_path = f.name

        try:
            result = run_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                timeout=120,
            )
            assert result.success, f"Execution failed: {result.error}"
            assert "auto-detected python" in result.output
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_sql_auto_detect(self, shared_context):
        """Should auto-detect SQL from .sql extension."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as f:
            f.write("SELECT 42 as answer")
            temp_path = f.name

        try:
            result = run_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                language=None,  # should auto-detect
                timeout=120,
            )

            logger.info(f"SQL auto-detect: success={result.success}, output={result.output}")

            assert result.success, f"SQL execution failed: {result.error}"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_explicit_language_override(self, shared_context):
        """Should use explicit language even if extension differs."""
        # File has .txt extension but we specify python
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write('print("explicit python")')
            temp_path = f.name

        try:
            result = run_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                language="python",
                timeout=120,
            )
            assert result.success, f"Execution failed: {result.error}"
            assert "explicit python" in result.output
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_empty_file(self):
        """Should reject empty files gracefully."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            result = run_file_on_databricks(file_path=temp_path, timeout=120)
            assert not result.success
            assert "empty" in result.error.lower()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_returns_execution_result(self, shared_context):
        """Should return ExecutionResult type."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('print("type check")')
            temp_path = f.name

        try:
            result = run_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                timeout=120,
            )
            assert isinstance(result, ExecutionResult)
            assert result.success
            d = result.to_dict()
            assert isinstance(d, dict)
            assert "success" in d
            assert "cluster_id" in d
            assert "context_id" in d
        finally:
            Path(temp_path).unlink(missing_ok=True)


@pytest.mark.integration
class TestRunFileWorkspacePath:
    """Tests for run_file_on_databricks with workspace_path (persistent mode)."""

    @pytest.fixture(autouse=True)
    def _setup_cleanup(self):
        """Track workspace paths for cleanup."""
        self._paths_to_cleanup = []
        yield
        try:
            w = get_workspace_client()
            for path in self._paths_to_cleanup:
                try:
                    w.workspace.delete(path=path, recursive=False)
                    logger.info(f"Cleaned up: {path}")
                except Exception:
                    pass
        except Exception:
            pass

    def test_workspace_path_uploads_notebook(self, shared_context):
        """Should upload file as notebook when workspace_path is provided."""
        username = get_current_username()
        ws_path = f"/Workspace/Users/{username}/.ai_dev_kit_test/file_persist_test"
        self._paths_to_cleanup.append(ws_path)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('print("persisted via run_file")')
            temp_path = f.name

        try:
            result = run_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                workspace_path=ws_path,
                timeout=120,
            )

            logger.info(f"Workspace path result: success={result.success}")

            assert result.success, f"Execution failed: {result.error}"
            assert "persisted via run_file" in result.output

            # Verify notebook exists in workspace
            w = get_workspace_client()
            status = w.workspace.get_status(ws_path)
            assert status is not None
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_workspace_path_none_no_upload(self, shared_context):
        """Without workspace_path, no notebook should be uploaded (ephemeral)."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('print("ephemeral file")')
            temp_path = f.name

        try:
            result = run_file_on_databricks(
                file_path=temp_path,
                cluster_id=shared_context["cluster_id"],
                context_id=shared_context["context_id"],
                timeout=120,
            )
            assert result.success, f"Execution failed: {result.error}"
            # No workspace_path on ExecutionResult — just verify execution worked
        finally:
            Path(temp_path).unlink(missing_ok=True)
