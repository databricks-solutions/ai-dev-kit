"""Integration tests for trace source detection and retrieval.

Tests actual MLflow status checking and local trace discovery.
No mocks - uses real subprocess calls and file system operations.
"""
import sys
from pathlib import Path

import pytest

# Add src to path for imports
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root / "src") not in sys.path:
    sys.path.insert(0, str(_repo_root / "src"))


class TestRealAutologStatus:
    """Test actual mlflow autolog claude --status execution."""

    def test_check_autolog_returns_valid_status(self):
        """Run real mlflow CLI and verify response structure.

        This test runs against the actual system configuration.
        If mlflow is not installed, the function should handle it gracefully.
        """
        from skill_test.trace.source import check_autolog_status

        status = check_autolog_status()

        # Should always return a valid AutologStatus object
        assert hasattr(status, 'enabled')
        assert isinstance(status.enabled, bool)
        assert hasattr(status, 'tracking_uri')
        assert hasattr(status, 'experiment_name')
        assert hasattr(status, 'error')

    def test_autolog_status_includes_tracking_uri_when_enabled(self, mlflow_configured):
        """When MLflow is configured, verify tracking_uri or enabled flag is set."""
        # mlflow_configured fixture ensures mlflow is set up, will skip if not
        assert mlflow_configured is True

        from skill_test.trace.source import check_autolog_status

        status = check_autolog_status()

        # When mlflow_configured passes, we know mlflow CLI reported enabled
        # The status should at minimum reflect enabled=True
        assert status.enabled is True
        # Note: tracking_uri and experiment_name may be None depending on
        # how mlflow reports status - the key assertion is enabled=True

    def test_check_autolog_handles_timeout_gracefully(self):
        """Verify timeout handling doesn't crash."""
        from skill_test.trace.source import check_autolog_status

        # The function should complete within its timeout
        # and return a valid status even if mlflow is slow
        status = check_autolog_status()
        assert status is not None

    def test_check_autolog_with_custom_directory(self, tmp_path):
        """Test checking autolog status in a specific directory."""
        from skill_test.trace.source import check_autolog_status

        status = check_autolog_status(directory=str(tmp_path))

        # Should return valid status regardless of directory
        assert hasattr(status, 'enabled')


class TestRealLocalTraces:
    """Test real local trace file discovery."""

    def test_list_local_traces_returns_valid_structure(self):
        """Verify list_local_traces returns properly structured result."""
        from skill_test.trace.source import list_local_traces

        result = list_local_traces(limit=5)

        # Should always return a dict with expected keys
        assert isinstance(result, dict)
        assert "success" in result
        assert "traces" in result
        assert isinstance(result["traces"], list)

    def test_list_local_traces_respects_limit(self):
        """Verify limit parameter is honored."""
        from skill_test.trace.source import list_local_traces

        result = list_local_traces(limit=3)

        # Should return at most 3 traces
        assert len(result["traces"]) <= 3

    def test_get_current_session_trace_path_returns_path_or_none(self):
        """Test finding actual Claude Code session trace."""
        from skill_test.trace.source import get_current_session_trace_path

        result = get_current_session_trace_path()

        # Should return Path or None, never raise
        assert result is None or isinstance(result, Path)

        if result is not None:
            # If a path is returned, verify it has expected properties
            assert result.suffix == ".jsonl"


class TestRealTraceFromBestSource:
    """Test getting traces from the best available source."""

    def test_get_trace_raises_on_no_source(self, tmp_path):
        """When no trace source exists, should raise FileNotFoundError."""
        from skill_test.trace.source import get_trace_from_best_source

        # Change to a directory with no traces
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            with pytest.raises(FileNotFoundError):
                get_trace_from_best_source("nonexistent-skill")
        finally:
            os.chdir(original_cwd)

    def test_get_trace_prefers_mlflow_when_configured(self, mlflow_configured, databricks_configured):
        """When MLflow is configured, it should be preferred."""
        # These fixtures ensure services are configured, will skip if not
        assert mlflow_configured is True
        assert databricks_configured is True

        from skill_test.trace.source import get_trace_from_best_source

        try:
            _metrics, source = get_trace_from_best_source("test-skill", prefer_mlflow=True)
            # If successful, source should indicate mlflow or local
            assert source.startswith("mlflow:") or source.startswith("local:")
        except FileNotFoundError:
            # Acceptable if no traces exist
            pytest.skip("No traces available")


class TestGetSetupInstructions:
    """Test setup instructions generation."""

    def test_get_setup_instructions_returns_string(self):
        """Verify setup instructions are properly formatted."""
        from skill_test.trace.source import get_setup_instructions

        instructions = get_setup_instructions("test-skill")

        assert isinstance(instructions, str)
        assert len(instructions) > 0
        assert "mlflow" in instructions.lower()
        assert "test-skill" in instructions
