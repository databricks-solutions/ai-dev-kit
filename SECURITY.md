# Security Policy

## Reporting a Vulnerability

Please email bugbounty@databricks.com to report any security vulnerabilities. We will acknowledge receipt of your vulnerability and strive to send you regular updates about our progress. If you're curious about the status of your disclosure please feel free to email us again.

---

## Plugin Trust Model

This section describes what code executes when you install the Databricks AI Dev Kit as a Claude Code plugin.

### What Runs Automatically

When you install this plugin, the `SessionStart` hook executes `.claude-plugin/setup.sh`.

This script:
1. Checks if already installed (exits early if so)
2. Verifies `uv` package manager is available
3. Creates a Python 3.11 virtual environment at `.venv/`
4. Installs local packages: `databricks-tools-core` and `databricks-mcp-server`
5. Verifies the MCP server module can be imported

### What This Script Does NOT Do
- Make network requests (except to PyPI for Python dependencies)
- Modify files outside the plugin directory
- Run with elevated privileges

### Files Executed Automatically

| File | Trigger | Purpose |
|------|---------|---------|
| [.claude-plugin/setup.sh](.claude-plugin/setup.sh) | SessionStart hook | Install Python dependencies |

### Audit Before Installing
We encourage you to review these files before installation:

- [.claude-plugin/setup.sh](.claude-plugin/setup.sh) - Setup script (~50 lines)
- [hooks/hooks.json](hooks/hooks.json) - Hook definitions (~15 lines)
- [.mcp.json](.mcp.json) - MCP server configuration

### Dependency Sources

Python packages are installed from:

- **GitHub or Local (bundled):** `databricks-tools-core/` and `databricks-mcp-server/`
- **PyPI (transitive):** databricks-sdk, fastmcp, pydantic, and other dependencies
