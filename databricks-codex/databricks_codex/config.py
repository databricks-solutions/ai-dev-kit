"""Configuration management for Codex integration.

Handles reading/writing ~/.codex/config.toml with Databricks MCP server configuration.
Supports profile management and environment variable handling.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Python 3.11+ has tomllib built-in
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None  # type: ignore

try:
    import tomli_w
except ImportError:
    tomli_w = None  # type: ignore


class MCPServerConfig(BaseModel):
    """MCP server entry in config.toml."""

    command: str = Field(..., description="Command to run the MCP server")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")


class CodexConfig(BaseModel):
    """Full Codex configuration model."""

    mcp_servers: Dict[str, MCPServerConfig] = Field(
        default_factory=dict, description="MCP server configurations"
    )


class CodexConfigManager:
    """Manage Codex configuration files.

    Supports both global (~/.codex/config.toml) and project-local
    (.codex/config.toml) configurations.

    Example:
        >>> manager = CodexConfigManager()
        >>> config = manager.read()
        >>> manager.configure_databricks_mcp(profile="PROD")
    """

    DEFAULT_GLOBAL_PATH = Path.home() / ".codex" / "config.toml"
    DEFAULT_LOCAL_PATH = Path(".codex") / "config.toml"

    def __init__(self, config_path: Optional[Path] = None, scope: str = "global"):
        """Initialize configuration manager.

        Args:
            config_path: Override path to config.toml
            scope: "global" or "project" (default: global)
        """
        if config_path:
            self.config_path = Path(config_path)
        elif scope == "project":
            self.config_path = self.DEFAULT_LOCAL_PATH
        else:
            self.config_path = self.DEFAULT_GLOBAL_PATH

    def read(self) -> CodexConfig:
        """Read and parse the configuration file.

        Returns:
            CodexConfig with parsed configuration
        """
        if tomllib is None:
            raise ImportError("tomli package required for Python < 3.11: pip install tomli")

        if not self.config_path.exists():
            return CodexConfig()

        with open(self.config_path, "rb") as f:
            data = tomllib.load(f)

        # Transform nested TOML tables into our model
        # TOML format: [mcp_servers.databricks] becomes key "mcp_servers.databricks"
        # or nested dict mcp_servers: {databricks: {...}}
        mcp_servers: Dict[str, MCPServerConfig] = {}

        # Handle both flat keys (mcp_servers.name) and nested dicts
        for key, value in data.items():
            if key.startswith("mcp_servers."):
                server_name = key.split(".", 1)[1]
                if isinstance(value, dict):
                    mcp_servers[server_name] = MCPServerConfig(**value)
            elif key == "mcp_servers" and isinstance(value, dict):
                for server_name, server_config in value.items():
                    if isinstance(server_config, dict):
                        mcp_servers[server_name] = MCPServerConfig(**server_config)

        return CodexConfig(mcp_servers=mcp_servers)

    def write(self, config: CodexConfig) -> None:
        """Write configuration to file atomically.

        Uses temp file + rename pattern to prevent corruption.

        Args:
            config: Configuration to write
        """
        if tomli_w is None:
            raise ImportError("tomli-w package required: pip install tomli-w")

        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to TOML-compatible dict with nested structure
        data: Dict[str, Any] = {}

        if config.mcp_servers:
            data["mcp_servers"] = {}
            for name, server in config.mcp_servers.items():
                server_dict = server.model_dump(exclude_none=True)
                # Remove empty collections
                if not server_dict.get("args"):
                    server_dict.pop("args", None)
                if not server_dict.get("env"):
                    server_dict.pop("env", None)
                data["mcp_servers"][name] = server_dict

        # Atomic write: temp file + rename
        fd, tmp_path = tempfile.mkstemp(
            dir=self.config_path.parent,
            prefix=".config-tmp-",
            suffix=".toml",
        )
        try:
            with os.fdopen(fd, "wb") as f:
                tomli_w.dump(data, f)
            os.replace(tmp_path, self.config_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def configure_databricks_mcp(
        self,
        profile: str = "DEFAULT",
        python_path: Optional[str] = None,
        mcp_entry: Optional[str] = None,
    ) -> None:
        """Configure Databricks MCP server in Codex config.

        Args:
            profile: Databricks config profile to use
            python_path: Path to Python executable (auto-detected if None)
            mcp_entry: Path to MCP entry script (auto-detected if None)
        """
        config = self.read()

        # Auto-detect paths if not provided
        if python_path is None:
            python_path = self._detect_venv_python()
        if mcp_entry is None:
            mcp_entry = self._detect_mcp_entry()

        env: Dict[str, str] = {}
        if profile != "DEFAULT":
            env["DATABRICKS_CONFIG_PROFILE"] = profile

        config.mcp_servers["databricks"] = MCPServerConfig(
            command=python_path,
            args=[mcp_entry] if mcp_entry else [],
            env=env,
        )

        self.write(config)

    def remove_databricks_mcp(self) -> bool:
        """Remove Databricks MCP server from configuration.

        Returns:
            True if removed, False if not found
        """
        config = self.read()
        if "databricks" in config.mcp_servers:
            del config.mcp_servers["databricks"]
            self.write(config)
            return True
        return False

    def _detect_venv_python(self) -> str:
        """Detect the ai-dev-kit venv Python path."""
        default_paths = [
            Path.home() / ".ai-dev-kit" / ".venv" / "bin" / "python",
            Path.home() / ".ai-dev-kit" / "venv" / "bin" / "python",
        ]
        for path in default_paths:
            if path.exists():
                return str(path)
        return sys.executable

    def _detect_mcp_entry(self) -> str:
        """Detect the MCP server entry point."""
        default_paths = [
            Path.home() / ".ai-dev-kit" / "repo" / "databricks-mcp-server" / "run_server.py",
            Path.home()
            / ".ai-dev-kit"
            / "databricks-mcp-server"
            / "databricks_mcp_server"
            / "__main__.py",
        ]
        for path in default_paths:
            if path.exists():
                return str(path)
        # Fallback to module invocation
        return "-m databricks_mcp_server"

    def has_databricks_mcp(self) -> bool:
        """Check if Databricks MCP server is configured.

        Returns:
            True if configured
        """
        config = self.read()
        return "databricks" in config.mcp_servers

    def get_databricks_mcp_config(self) -> Optional[MCPServerConfig]:
        """Get the Databricks MCP server configuration.

        Returns:
            MCPServerConfig if configured, None otherwise
        """
        config = self.read()
        return config.mcp_servers.get("databricks")
