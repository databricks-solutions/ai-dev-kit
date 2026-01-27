"""Tests for CLI commands module."""
import pytest
import shutil
from pathlib import Path

from skill_test.cli import CLIContext, interactive, run, regression, init
from skill_test.grp import (
    DatabricksExecutionConfig,
    extract_code_blocks,
    execute_code_blocks,
)
from skill_test.fixtures import TestFixtureConfig


@pytest.fixture
def temp_skills_dir(tmp_path):
    """Create a temporary skills directory for testing."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    return skills_dir


@pytest.fixture
def ctx(temp_skills_dir):
    """Create a CLI context for testing."""
    return CLIContext(base_path=temp_skills_dir)


class TestInit:
    """Tests for the init command."""

    def test_init_creates_skill_directory(self, ctx, temp_skills_dir):
        """Test that init creates the skill directory and files."""
        result = init("test-skill", ctx)

        assert result["success"] is True
        assert result["skill_name"] == "test-skill"
        assert (temp_skills_dir / "test-skill").exists()
        assert (temp_skills_dir / "test-skill" / "ground_truth.yaml").exists()
        assert (temp_skills_dir / "test-skill" / "candidates.yaml").exists()
        assert (temp_skills_dir / "test-skill" / "manifest.yaml").exists()

    def test_init_fails_if_exists(self, ctx, temp_skills_dir):
        """Test that init fails if skill already exists."""
        # Create skill first
        init("test-skill", ctx)

        # Try to create again
        result = init("test-skill", ctx)
        assert result["success"] is False
        assert "already has test definitions" in result["error"]


class TestRun:
    """Tests for the run command."""

    def test_run_returns_error_for_missing_skill(self, ctx):
        """Test that run returns error for missing skill."""
        result = run("nonexistent-skill", ctx)

        assert result["success"] is False
        assert "No ground_truth.yaml found" in result["error"]

    def test_run_evaluates_skill(self, ctx):
        """Test that run evaluates a skill's ground truth."""
        # Create skill
        init("test-skill", ctx)

        # Run evaluation
        result = run("test-skill", ctx)

        assert result["success"] is True
        assert result["skill_name"] == "test-skill"
        assert result["total"] == 1
        assert result["passed"] == 1


class TestInteractive:
    """Tests for the interactive command."""

    def test_interactive_passes_valid_sql(self, ctx):
        """Test that valid SQL passes and is auto-approved."""
        init("test-skill", ctx)

        result = interactive(
            skill_name="test-skill",
            prompt="Create a SELECT query",
            response="```sql\nSELECT * FROM users;\n```",
            ctx=ctx,
            auto_approve_on_success=True
        )

        assert result.success is True
        assert result.execution_mode == "local"
        assert result.total_blocks == 1
        assert result.passed_blocks == 1
        assert result.auto_approved is True
        assert result.saved_to == "ground_truth.yaml"

    def test_interactive_fails_invalid_python(self, ctx):
        """Test that invalid Python fails and goes to candidates."""
        init("test-skill", ctx)

        result = interactive(
            skill_name="test-skill",
            prompt="Create a function",
            response="```python\ndef broken(\n```",
            ctx=ctx,
            auto_approve_on_success=True
        )

        assert result.success is True  # Process succeeded
        assert result.total_blocks == 1
        assert result.passed_blocks == 0
        assert result.auto_approved is False
        assert result.saved_to == "candidates.yaml"

    def test_interactive_handles_multiple_blocks(self, ctx):
        """Test that multiple code blocks are all executed."""
        init("test-skill", ctx)

        response = """
```python
x = 1 + 1
```

```sql
SELECT * FROM table1;
```

```python
def add(a, b):
    return a + b
```
"""
        result = interactive(
            skill_name="test-skill",
            prompt="Create some code",
            response=response,
            ctx=ctx,
            auto_approve_on_success=True
        )

        assert result.total_blocks == 3
        assert result.passed_blocks == 3
        assert result.auto_approved is True


class TestCodeBlockExtraction:
    """Tests for code block extraction and execution."""

    def test_extract_code_blocks(self):
        """Test code block extraction from markdown."""
        response = """
```python
print("hello")
```

```sql
SELECT 1;
```
"""
        blocks = extract_code_blocks(response)
        assert len(blocks) == 2
        assert blocks[0].language == "python"
        assert blocks[1].language == "sql"

    def test_execute_code_blocks_valid(self):
        """Test execution of valid code blocks."""
        response = """
```python
def add(a, b):
    return a + b
```

```sql
SELECT id, name FROM users WHERE active = true;
```
"""
        total, passed, details = execute_code_blocks(response)
        assert total == 2
        assert passed == 2

    def test_execute_code_blocks_invalid_python(self):
        """Test execution of invalid Python."""
        response = "```python\ndef broken(\n```"
        total, passed, details = execute_code_blocks(response)
        assert total == 1
        assert passed == 0
        assert "Syntax error" in details[0]["error"]


class TestDatabricksExecutionConfig:
    """Tests for DatabricksExecutionConfig."""

    def test_default_serverless(self):
        """Test that serverless is the default."""
        config = DatabricksExecutionConfig()
        assert config.use_serverless is True
        assert config.cluster_id is None

    def test_custom_config(self):
        """Test custom configuration."""
        config = DatabricksExecutionConfig(
            cluster_id="my-cluster",
            use_serverless=False,
            catalog="my_catalog",
            schema="my_schema"
        )
        assert config.cluster_id == "my-cluster"
        assert config.use_serverless is False
        assert config.catalog == "my_catalog"
        assert config.schema == "my_schema"


class TestTestFixtureConfig:
    """Tests for TestFixtureConfig."""

    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            "catalog": "test_catalog",
            "schema": "test_schema",
            "volume": "test_volume",
            "files": [
                {"local_path": "a.json", "volume_path": "raw/a.json"}
            ],
            "tables": [
                {"name": "test_table", "ddl": "CREATE TABLE test_table (id INT)"}
            ],
            "cleanup_after": False
        }
        config = TestFixtureConfig.from_dict(data)

        assert config.catalog == "test_catalog"
        assert config.schema == "test_schema"
        assert config.volume == "test_volume"
        assert len(config.files) == 1
        assert len(config.tables) == 1
        assert config.cleanup_after is False

    def test_defaults(self):
        """Test default values."""
        config = TestFixtureConfig()
        assert config.catalog == "skill_test"
        assert config.cleanup_after is True


class TestCLIContext:
    """Tests for CLIContext."""

    def test_has_databricks_tools_false(self):
        """Test that has_databricks_tools returns False without MCP tools."""
        ctx = CLIContext()
        assert ctx.has_databricks_tools() is False

    def test_has_databricks_tools_true(self):
        """Test that has_databricks_tools returns True with MCP tools."""
        ctx = CLIContext(
            mcp_execute_command=lambda **kwargs: {},
        )
        assert ctx.has_databricks_tools() is True
