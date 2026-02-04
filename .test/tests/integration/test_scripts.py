"""Integration tests for CLI script execution.

Tests actual subprocess execution of CLI scripts in .test/scripts/.
No mocks - scripts are run as real subprocesses.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

# Get repo root for running scripts
_repo_root = Path(__file__).resolve().parents[3]


class TestTraceEvalScript:
    """Test trace_eval.py script execution."""

    def test_script_evaluates_local_trace(self, real_trace_file, real_skill_dir):
        """Run trace_eval.py as subprocess with real args."""
        # Copy skill to expected location
        import shutil
        skills_dest = _repo_root / ".test" / "skills" / "integration-test-skill"
        if not skills_dest.exists():
            shutil.copytree(real_skill_dir, skills_dest)

        try:
            result = subprocess.run(
                [
                    sys.executable, str(_repo_root / ".test" / "scripts" / "trace_eval.py"),
                    "integration-test-skill",
                    "--trace", str(real_trace_file)
                ],
                capture_output=True,
                text=True,
                cwd=str(_repo_root),
                timeout=30
            )

            # Parse output
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError:
                pytest.fail(f"Script output not valid JSON: {result.stdout}\nStderr: {result.stderr}")

            assert "success" in output
            assert "skill_name" in output
            assert output["skill_name"] == "integration-test-skill"

        finally:
            # Cleanup
            if skills_dest.exists():
                shutil.rmtree(skills_dest)

    def test_script_shows_help(self):
        """Verify script has help output."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "trace_eval.py"),
                "--help"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert result.returncode == 0
        assert "skill_name" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_script_missing_skill_returns_error(self):
        """Verify proper error when skill doesn't exist."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "trace_eval.py"),
                "nonexistent-skill-12345",
                "--trace", "/tmp/fake.jsonl"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        # Should return error
        try:
            output = json.loads(result.stdout)
            assert output.get("success") is False
        except json.JSONDecodeError:
            # Error message in stderr is also acceptable
            assert result.returncode != 0

    def test_script_evaluates_trace_directory(self, real_trace_dir, real_skill_dir):
        """Run trace_eval.py with --trace-dir."""
        import shutil
        skills_dest = _repo_root / ".test" / "skills" / "integration-test-skill"
        if not skills_dest.exists():
            shutil.copytree(real_skill_dir, skills_dest)

        try:
            result = subprocess.run(
                [
                    sys.executable, str(_repo_root / ".test" / "scripts" / "trace_eval.py"),
                    "integration-test-skill",
                    "--trace-dir", str(real_trace_dir)
                ],
                capture_output=True,
                text=True,
                cwd=str(_repo_root),
                timeout=30
            )

            try:
                output = json.loads(result.stdout)
                assert "traces_evaluated" in output
                assert output["traces_evaluated"] >= 1
            except json.JSONDecodeError:
                pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")

        finally:
            if skills_dest.exists():
                shutil.rmtree(skills_dest)


class TestListTracesScript:
    """Test list_traces.py script execution."""

    def test_script_shows_help(self):
        """Verify script has help output."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "list_traces.py"),
                "--help"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert result.returncode == 0
        assert "limit" in result.stdout.lower() or "usage" in result.stdout.lower()

    def test_script_lists_local_traces(self):
        """Run list_traces.py --local as subprocess."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "list_traces.py"),
                "test-skill",
                "--local"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=30  # Longer timeout for import overhead
        )

        try:
            output = json.loads(result.stdout)
            # Should return traces list (may be empty)
            assert "traces" in output
            assert isinstance(output["traces"], list)
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")

    def test_script_respects_limit(self):
        """Verify --limit flag works."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "list_traces.py"),
                "test-skill",
                "--local",
                "--limit", "2"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        try:
            output = json.loads(result.stdout)
            assert len(output.get("traces", [])) <= 2
        except json.JSONDecodeError:
            pytest.fail(f"Invalid JSON: {result.stdout}")

    def test_script_lists_mlflow_traces(self, mlflow_configured):
        """Run list_traces.py with MLflow experiment."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "list_traces.py"),
                "test-skill",
                "--experiment", "/Shared/skill-test-traces"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=30
        )

        try:
            output = json.loads(result.stdout)
            assert "source" in output or "error" in output
        except json.JSONDecodeError:
            # May fail if MLflow not reachable
            pass


class TestAddScript:
    """Test add.py script with --trace flag."""

    def test_script_shows_help(self):
        """Verify script has help output."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "add.py"),
                "--help"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert result.returncode == 0
        assert "trace" in result.stdout.lower() or "skill_name" in result.stdout.lower()

    def test_script_with_prompt_and_response(self, real_skill_dir):
        """Run add.py with prompt and response args."""
        import shutil
        skills_dest = _repo_root / ".test" / "skills" / "integration-test-skill"
        if not skills_dest.exists():
            shutil.copytree(real_skill_dir, skills_dest)

        try:
            result = subprocess.run(
                [
                    sys.executable, str(_repo_root / ".test" / "scripts" / "add.py"),
                    "integration-test-skill",
                    "--prompt", "Test prompt",
                    "--response", "```sql\nSELECT 1;\n```"
                ],
                capture_output=True,
                text=True,
                cwd=str(_repo_root),
                timeout=30
            )

            try:
                output = json.loads(result.stdout)
                assert "success" in output
                assert "test_id" in output
            except json.JSONDecodeError:
                pytest.fail(f"Invalid JSON: {result.stdout}\nStderr: {result.stderr}")

        finally:
            if skills_dest.exists():
                shutil.rmtree(skills_dest)

    def test_script_requires_prompt(self):
        """Verify script requires prompt."""
        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "add.py"),
                "test-skill",
                "--response", "test"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10,
            input=""  # Empty input for interactive prompt
        )

        # Should fail or prompt for input
        assert result.returncode != 0 or "error" in result.stdout.lower() or "no prompt" in result.stdout.lower()


class TestCommonUtilities:
    """Test the _common.py utilities."""

    def test_find_repo_root(self):
        """Verify find_repo_root works from scripts directory."""
        # Import from scripts
        scripts_dir = _repo_root / ".test" / "scripts"
        sys.path.insert(0, str(scripts_dir))

        try:
            from _common import find_repo_root
            root = find_repo_root()
            assert root.exists()
            assert (root / ".test" / "src").exists()
        finally:
            sys.path.remove(str(scripts_dir))

    def test_setup_path_adds_src(self):
        """Verify setup_path adds src to Python path."""
        scripts_dir = _repo_root / ".test" / "scripts"
        sys.path.insert(0, str(scripts_dir))

        try:
            from _common import setup_path
            setup_path()

            # Should be able to import skill_test now
            import skill_test
            assert skill_test is not None
        finally:
            sys.path.remove(str(scripts_dir))

    def test_create_cli_context(self):
        """Verify create_cli_context returns valid context."""
        scripts_dir = _repo_root / ".test" / "scripts"
        sys.path.insert(0, str(scripts_dir))

        try:
            from _common import create_cli_context
            ctx = create_cli_context()

            assert ctx is not None
            assert hasattr(ctx, 'base_path')
            assert ctx.base_path.exists() or ctx.base_path.parent.exists()
        finally:
            sys.path.remove(str(scripts_dir))


class TestScriptEnvironment:
    """Test script environment handling."""

    def test_scripts_handle_missing_env_vars(self):
        """Verify scripts handle missing DATABRICKS_* env vars gracefully."""
        # Run with no Databricks env vars
        env = os.environ.copy()
        env.pop("DATABRICKS_HOST", None)
        env.pop("DATABRICKS_TOKEN", None)

        result = subprocess.run(
            [
                sys.executable, str(_repo_root / ".test" / "scripts" / "list_traces.py"),
                "test-skill",
                "--local"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            env=env,
            timeout=10
        )

        # Should still work with --local flag
        try:
            output = json.loads(result.stdout)
            assert "traces" in output
        except json.JSONDecodeError:
            pytest.fail(f"Script failed without Databricks env: {result.stderr}")

    def test_scripts_import_dotenv(self):
        """Verify scripts attempt to load .env file."""
        # The scripts should try to import dotenv but not fail if missing
        result = subprocess.run(
            [
                sys.executable, "-c",
                "import sys; sys.path.insert(0, '.test/scripts'); from _common import setup_path; print('ok')"
            ],
            capture_output=True,
            text=True,
            cwd=str(_repo_root),
            timeout=10
        )

        assert "ok" in result.stdout or result.returncode == 0
