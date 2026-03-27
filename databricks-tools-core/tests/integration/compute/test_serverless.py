"""
Integration tests for serverless compute execution (run_code_on_serverless).

Tests serverless Python/SQL execution, ephemeral vs persistent modes,
workspace_path, error handling, and input validation.
"""

import logging
import pytest

from databricks_tools_core.compute import (
    run_code_on_serverless,
    ServerlessRunResult,
)
from databricks_tools_core.auth import get_workspace_client, get_current_username

logger = logging.getLogger(__name__)


@pytest.mark.integration
class TestServerlessInputValidation:
    """Tests for input validation (no cluster/serverless needed)."""

    def test_empty_code(self):
        """Should reject empty code without submitting a run."""
        result = run_code_on_serverless(code="")
        assert not result.success
        assert result.state == "INVALID_INPUT"
        assert "empty" in result.error.lower()

    def test_whitespace_only_code(self):
        """Should reject whitespace-only code."""
        result = run_code_on_serverless(code="   \n\n  ")
        assert not result.success
        assert result.state == "INVALID_INPUT"

    def test_unsupported_language(self):
        """Should reject unsupported languages."""
        result = run_code_on_serverless(code="println('hi')", language="scala")
        assert not result.success
        assert result.state == "INVALID_INPUT"
        assert "scala" in result.error.lower()

    def test_result_is_serverless_run_result(self):
        """Should return ServerlessRunResult type even on validation errors."""
        result = run_code_on_serverless(code="", language="python")
        assert isinstance(result, ServerlessRunResult)

    def test_to_dict(self):
        """Should serialize to dict properly."""
        result = run_code_on_serverless(code="")
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "success" in d
        assert "output" in d
        assert "error" in d
        assert "run_id" in d
        assert "state" in d


@pytest.mark.integration
class TestServerlessPythonExecution:
    """Tests for Python code execution on serverless compute."""

    def test_simple_python_dbutils_exit(self):
        """Should capture output from dbutils.notebook.exit()."""
        code = 'dbutils.notebook.exit("hello from serverless")'
        result = run_code_on_serverless(code=code, language="python")

        logger.info(f"Result: success={result.success}, output={result.output}, "
                     f"duration={result.duration_seconds}s")

        assert result.success, f"Execution failed: {result.error}"
        assert "hello from serverless" in result.output
        assert result.run_id is not None
        assert result.run_url is not None
        assert result.duration_seconds is not None
        assert result.state == "SUCCESS"

    def test_python_computation(self):
        """Should execute computation and return result via dbutils.notebook.exit()."""
        code = """
import math
result = sum(math.factorial(i) for i in range(10))
dbutils.notebook.exit(str(result))
"""
        result = run_code_on_serverless(code=code, language="python")

        assert result.success, f"Execution failed: {result.error}"
        assert "409114" in result.output  # sum of 0! through 9!

    def test_python_error_handling(self):
        """Should capture Python errors with traceback."""
        code = """
x = 1 / 0
"""
        result = run_code_on_serverless(code=code, language="python")

        logger.info(f"Error result: success={result.success}, error={result.error[:200] if result.error else None}")

        assert not result.success
        assert result.error is not None
        assert "ZeroDivisionError" in result.error
        assert result.state == "FAILED"

    def test_python_with_spark(self):
        """Should have access to Spark on serverless."""
        code = """
df = spark.range(10)
count = df.count()
dbutils.notebook.exit(str(count))
"""
        result = run_code_on_serverless(code=code, language="python")

        assert result.success, f"Execution failed: {result.error}"
        assert "10" in result.output

    def test_custom_run_name(self):
        """Should accept custom run name."""
        result = run_code_on_serverless(
            code='dbutils.notebook.exit("named run")',
            run_name="test_custom_name_integration",
        )

        assert result.success, f"Execution failed: {result.error}"
        assert "named run" in result.output


@pytest.mark.integration
class TestServerlessSQLExecution:
    """Tests for SQL execution on serverless compute."""

    def test_sql_ddl(self):
        """Should execute SQL DDL statements."""
        code = """
CREATE DATABASE IF NOT EXISTS ai_dev_kit_serverless_test;
"""
        result = run_code_on_serverless(code=code, language="sql")

        logger.info(f"SQL DDL result: success={result.success}, state={result.state}")

        assert result.success, f"SQL DDL failed: {result.error}"


@pytest.mark.integration
class TestServerlessEphemeralMode:
    """Tests for ephemeral mode (default - temp notebook cleaned up)."""

    def test_ephemeral_no_workspace_path_in_result(self):
        """Ephemeral mode should not include workspace_path in result."""
        result = run_code_on_serverless(
            code='dbutils.notebook.exit("ephemeral")',
        )

        assert result.success, f"Execution failed: {result.error}"
        assert result.workspace_path is None

    def test_ephemeral_to_dict_no_workspace_path(self):
        """Ephemeral mode should not include workspace_path in dict."""
        result = run_code_on_serverless(
            code='dbutils.notebook.exit("ephemeral dict")',
        )

        assert result.success, f"Execution failed: {result.error}"
        d = result.to_dict()
        assert "workspace_path" not in d


@pytest.mark.integration
class TestServerlessPersistentMode:
    """Tests for persistent mode (workspace_path provided, notebook saved)."""

    @pytest.fixture(autouse=True)
    def _setup_cleanup(self):
        """Track workspace paths for cleanup after each test."""
        self._paths_to_cleanup = []
        yield
        # Cleanup persisted notebooks
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

    def test_persistent_saves_notebook(self):
        """Persistent mode should save notebook at workspace_path."""
        username = get_current_username()
        ws_path = f"/Workspace/Users/{username}/.ai_dev_kit_test/persistent_test"
        self._paths_to_cleanup.append(ws_path)

        result = run_code_on_serverless(
            code='dbutils.notebook.exit("persisted!")',
            workspace_path=ws_path,
        )

        logger.info(f"Persistent result: success={result.success}, "
                     f"workspace_path={result.workspace_path}")

        assert result.success, f"Execution failed: {result.error}"
        assert result.workspace_path == ws_path
        assert "persisted!" in result.output

        # Verify notebook exists in workspace
        w = get_workspace_client()
        status = w.workspace.get_status(ws_path)
        assert status is not None

    def test_persistent_to_dict_includes_workspace_path(self):
        """Persistent mode should include workspace_path in dict."""
        username = get_current_username()
        ws_path = f"/Workspace/Users/{username}/.ai_dev_kit_test/persistent_dict_test"
        self._paths_to_cleanup.append(ws_path)

        result = run_code_on_serverless(
            code='dbutils.notebook.exit("dict test")',
            workspace_path=ws_path,
        )

        assert result.success, f"Execution failed: {result.error}"
        d = result.to_dict()
        assert d["workspace_path"] == ws_path
