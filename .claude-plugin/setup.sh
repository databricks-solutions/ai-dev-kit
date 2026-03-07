#!/bin/bash
# Post-install setup for databricks-ai-dev-kit plugin
# Creates virtual environment and installs MCP server dependencies
# ============================================================
# SECURITY NOTE: This script runs automatically on plugin load
#
# What it does:
#   1. Creates .venv/ with Python 3.11 (if not present)
#   2. Installs databricks-tools-core (local package)
#   3. Installs databricks-mcp-server (local package)
#   4. Verifies MCP server import works
#
# What it does NOT do:
#   - Collect or transmit credentials
#   - Modify files outside the plugin directory
#   - Run with elevated privileges
#   - Access your Databricks workspace (until you authenticate)
#
# Source: https://github.com/databricks-solutions/ai-dev-kit
# ============================================================

set -e

# When run via hook, CLAUDE_PLUGIN_ROOT is set; otherwise derive from script location
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TOOLS_CORE_DIR="${PLUGIN_ROOT}/databricks-tools-core"
MCP_SERVER_DIR="${PLUGIN_ROOT}/databricks-mcp-server"

# Idempotency check: skip if already set up and working
if [ -f "${PLUGIN_ROOT}/.venv/bin/python" ] && \
   "${PLUGIN_ROOT}/.venv/bin/python" -c "import databricks_mcp_server" 2>/dev/null; then
    echo "Databricks AI Dev Kit already set up."
    exit 0
fi

echo "Setting up Databricks AI Dev Kit..." >&2

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is required but not installed." >&2
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

# Check if tools-core directory exists
if [ ! -d "$TOOLS_CORE_DIR" ]; then
    echo "Error: databricks-tools-core not found at $TOOLS_CORE_DIR" >&2
    exit 1
fi

# Create virtual environment at plugin root
cd "$PLUGIN_ROOT"
uv venv --python 3.11 >&2

# Install dependencies
uv pip install --python .venv/bin/python -e "$TOOLS_CORE_DIR" --quiet >&2
uv pip install --python .venv/bin/python -e "$MCP_SERVER_DIR" --quiet >&2

# Verify installation
if .venv/bin/python -c "import databricks_mcp_server" 2>/dev/null; then
    touch "${PLUGIN_ROOT}/.venv/.setup-complete"
    echo "Databricks AI Dev Kit setup complete."
else
    echo "Error: Could not verify MCP server import after install." >&2
    exit 1
fi
