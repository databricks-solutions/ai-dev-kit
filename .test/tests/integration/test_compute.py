"""Integration tests for compute.py CLI script.

Tests actual subprocess execution of the compute CLI script.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

# Get repo root for running scripts
_repo_root = Path(__file__).resolve().parents[3]
_compute_script = _repo_root / "databricks-skills" / "databricks-execution-compute" / "scripts" / "compute.py"


class TestComputeScriptHelp:
    """Test compute.py help and basic CLI structure."""

    def test_script_shows_help(self):
        """Verify script has help output."""
        result = subprocess.run(
            [sys.executable, str(_compute_script), "--help"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert result.returncode == 0
        assert "execute-code" in result.stdout
        assert "list-compute" in result.stdout
        assert "manage-cluster" in result.stdout

    def test_execute_code_help(self):
        """Verify execute-code subcommand help."""
        result = subprocess.run(
            [sys.executable, str(_compute_script), "execute-code", "--help"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert result.returncode == 0
        assert "--code" in result.stdout
        assert "--compute-type" in result.stdout

    def test_list_compute_help(self):
        """Verify list-compute subcommand help."""
        result = subprocess.run(
            [sys.executable, str(_compute_script), "list-compute", "--help"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert result.returncode == 0
        assert "--resource" in result.stdout

    def test_manage_cluster_help(self):
        """Verify manage-cluster subcommand help."""
        result = subprocess.run(
            [sys.executable, str(_compute_script), "manage-cluster", "--help"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert result.returncode == 0
        assert "--action" in result.stdout


@pytest.mark.integration
class TestListCompute:
    """Tests for list-compute command."""

    def test_list_clusters(self):
        """Should list all clusters."""
        result = subprocess.run(
            [sys.executable, str(_compute_script), "list-compute", "--resource", "clusters"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=60
        )

        try:
            output = json.loads(result.stdout)
            assert "clusters" in output
            assert isinstance(output["clusters"], list)
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")

    def test_list_node_types(self):
        """Should list available node types."""
        result = subprocess.run(
            [sys.executable, str(_compute_script), "list-compute", "--resource", "node_types"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=60
        )

        try:
            output = json.loads(result.stdout)
            assert "node_types" in output
            assert isinstance(output["node_types"], list)
            assert len(output["node_types"]) > 0
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")

    def test_list_spark_versions(self):
        """Should list available Spark versions."""
        result = subprocess.run(
            [sys.executable, str(_compute_script), "list-compute", "--resource", "spark_versions"],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=60
        )

        try:
            output = json.loads(result.stdout)
            assert "spark_versions" in output
            assert isinstance(output["spark_versions"], list)
            assert len(output["spark_versions"]) > 0
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")


@pytest.mark.integration
class TestExecuteCode:
    """Tests for execute-code command."""

    def test_execute_serverless_simple(self):
        """Test simple Python execution on serverless."""
        code = 'print("Hello from compute test"); dbutils.notebook.exit("success")'

        result = subprocess.run(
            [
                sys.executable, str(_compute_script),
                "execute-code",
                "--code", code,
                "--compute-type", "serverless",
                "--timeout", "180"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=300  # 5 min for cold start
        )

        try:
            output = json.loads(result.stdout)
            assert output.get("success", False), f"Execution failed: {output}"
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")

    def test_execute_requires_code_or_file(self):
        """Should return error when neither code nor file provided."""
        result = subprocess.run(
            [
                sys.executable, str(_compute_script),
                "execute-code",
                "--compute-type", "serverless"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=30
        )

        try:
            output = json.loads(result.stdout)
            assert output.get("success") is False
            assert "error" in output
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")


@pytest.mark.integration
class TestManageCluster:
    """Tests for manage-cluster command (read-only operations)."""

    def test_invalid_action(self):
        """Should return error for invalid action."""
        result = subprocess.run(
            [
                sys.executable, str(_compute_script),
                "manage-cluster",
                "--action", "invalid_action"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=30
        )

        # argparse will fail with invalid choice
        assert result.returncode != 0 or "error" in result.stdout.lower()

    def test_get_requires_cluster_id(self):
        """Should return error when cluster_id not provided for get."""
        result = subprocess.run(
            [
                sys.executable, str(_compute_script),
                "manage-cluster",
                "--action", "get"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=30
        )

        try:
            output = json.loads(result.stdout)
            assert output.get("success") is False
            assert "error" in output
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")

    def test_create_requires_name(self):
        """Should return error when name not provided for create."""
        result = subprocess.run(
            [
                sys.executable, str(_compute_script),
                "manage-cluster",
                "--action", "create"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=30
        )

        try:
            output = json.loads(result.stdout)
            assert output.get("success") is False
            assert "error" in output
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")
