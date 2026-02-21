"""Tests for configuration management."""

import pytest
from pathlib import Path

from databricks_codex.config import (
    CodexConfigManager,
    CodexConfig,
    MCPServerConfig,
)


class TestMCPServerConfig:
    """Tests for MCPServerConfig model."""

    def test_minimal_config(self):
        """Test minimal server config."""
        config = MCPServerConfig(command="python")

        assert config.command == "python"
        assert config.args == []
        assert config.env == {}

    def test_full_config(self):
        """Test full server config."""
        config = MCPServerConfig(
            command="/usr/bin/python3",
            args=["-m", "databricks_mcp_server"],
            env={"KEY": "value"},
        )

        assert config.command == "/usr/bin/python3"
        assert config.args == ["-m", "databricks_mcp_server"]
        assert config.env == {"KEY": "value"}


class TestCodexConfig:
    """Tests for CodexConfig model."""

    def test_empty_config(self):
        """Test empty configuration."""
        config = CodexConfig()

        assert config.mcp_servers == {}

    def test_config_with_servers(self):
        """Test configuration with MCP servers."""
        config = CodexConfig(
            mcp_servers={
                "databricks": MCPServerConfig(command="python"),
                "other": MCPServerConfig(command="node"),
            }
        )

        assert len(config.mcp_servers) == 2
        assert "databricks" in config.mcp_servers
        assert "other" in config.mcp_servers


class TestCodexConfigManager:
    """Tests for CodexConfigManager."""

    def test_read_nonexistent_returns_empty(self, mock_config_manager):
        """Reading non-existent config returns empty config."""
        config = mock_config_manager.read()

        assert isinstance(config, CodexConfig)
        assert len(config.mcp_servers) == 0

    def test_write_and_read_roundtrip(self, mock_config_manager, sample_config):
        """Config can be written and read back."""
        mock_config_manager.write(sample_config)

        read_config = mock_config_manager.read()

        assert "databricks" in read_config.mcp_servers
        assert read_config.mcp_servers["databricks"].command == "/usr/bin/python"
        assert read_config.mcp_servers["databricks"].args == ["-m", "databricks_mcp_server"]

    def test_write_empty_config(self, mock_config_manager):
        """Writing empty config creates valid file."""
        config = CodexConfig()
        mock_config_manager.write(config)

        read_config = mock_config_manager.read()
        assert read_config.mcp_servers == {}

    def test_configure_databricks_mcp(self, mock_config_manager):
        """Configure Databricks MCP server."""
        mock_config_manager.configure_databricks_mcp(
            profile="PROD",
            python_path="/custom/python",
            mcp_entry="/custom/run_server.py",
        )

        config = mock_config_manager.read()

        assert "databricks" in config.mcp_servers
        assert config.mcp_servers["databricks"].command == "/custom/python"
        assert config.mcp_servers["databricks"].args == ["/custom/run_server.py"]
        assert config.mcp_servers["databricks"].env.get("DATABRICKS_CONFIG_PROFILE") == "PROD"

    def test_configure_databricks_mcp_default_profile(self, mock_config_manager):
        """Configure with DEFAULT profile doesn't add env var."""
        mock_config_manager.configure_databricks_mcp(
            profile="DEFAULT",
            python_path="/python",
            mcp_entry="/server.py",
        )

        config = mock_config_manager.read()

        # DEFAULT profile shouldn't add env var
        assert "DATABRICKS_CONFIG_PROFILE" not in config.mcp_servers["databricks"].env

    def test_remove_databricks_mcp(self, mock_config_manager, sample_config):
        """Remove Databricks MCP configuration."""
        mock_config_manager.write(sample_config)

        removed = mock_config_manager.remove_databricks_mcp()
        assert removed is True

        config = mock_config_manager.read()
        assert "databricks" not in config.mcp_servers

    def test_remove_databricks_mcp_not_exists(self, mock_config_manager):
        """Remove returns False if not configured."""
        removed = mock_config_manager.remove_databricks_mcp()
        assert removed is False

    def test_has_databricks_mcp(self, mock_config_manager, sample_config):
        """Check if Databricks MCP is configured."""
        assert mock_config_manager.has_databricks_mcp() is False

        mock_config_manager.write(sample_config)

        assert mock_config_manager.has_databricks_mcp() is True

    def test_get_databricks_mcp_config(self, mock_config_manager, sample_config):
        """Get Databricks MCP configuration."""
        assert mock_config_manager.get_databricks_mcp_config() is None

        mock_config_manager.write(sample_config)

        config = mock_config_manager.get_databricks_mcp_config()
        assert config is not None
        assert config.command == "/usr/bin/python"

    def test_atomic_write_creates_directory(self, temp_config_dir):
        """Write creates parent directory if needed."""
        nested_path = temp_config_dir / "nested" / "deep" / "config.toml"
        manager = CodexConfigManager(config_path=nested_path)

        config = CodexConfig(
            mcp_servers={"test": MCPServerConfig(command="test")}
        )
        manager.write(config)

        assert nested_path.exists()

    def test_scope_global(self):
        """Test global scope path."""
        manager = CodexConfigManager(scope="global")
        assert manager.config_path == Path.home() / ".codex" / "config.toml"

    def test_scope_project(self):
        """Test project scope path."""
        manager = CodexConfigManager(scope="project")
        assert manager.config_path == Path(".codex") / "config.toml"

    def test_custom_path_overrides_scope(self, temp_config_dir):
        """Custom path overrides scope setting."""
        custom_path = temp_config_dir / "custom.toml"
        manager = CodexConfigManager(config_path=custom_path, scope="global")

        assert manager.config_path == custom_path

    def test_multiple_servers(self, mock_config_manager):
        """Config can have multiple MCP servers."""
        config = CodexConfig(
            mcp_servers={
                "databricks": MCPServerConfig(command="python", args=["-m", "db"]),
                "github": MCPServerConfig(command="node", args=["gh-server.js"]),
                "slack": MCPServerConfig(command="python", args=["-m", "slack"]),
            }
        )

        mock_config_manager.write(config)
        read_config = mock_config_manager.read()

        assert len(read_config.mcp_servers) == 3
        assert "databricks" in read_config.mcp_servers
        assert "github" in read_config.mcp_servers
        assert "slack" in read_config.mcp_servers
