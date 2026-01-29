#!/bin/bash
# Post-install setup for databricks-ai-dev-kit plugin
# Creates virtual environment and installs MCP server dependencies

set -e

# When run via hook, CLAUDE_PLUGIN_ROOT is set; otherwise derive from script location
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
TOOLS_CORE_DIR="${PLUGIN_ROOT}/databricks-tools-core"
MCP_SERVER_DIR="${PLUGIN_ROOT}/databricks-mcp-server"

echo "======================================"
echo "Setting up Databricks AI Dev Kit"
echo "======================================"
echo ""

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is required but not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "uv is installed"

# Check if tools-core directory exists
if [ ! -d "$TOOLS_CORE_DIR" ]; then
    echo "Error: databricks-tools-core not found at $TOOLS_CORE_DIR"
    exit 1
fi
echo "databricks-tools-core found"

# Create virtual environment at plugin root
echo ""
echo "Creating virtual environment..."
cd "$PLUGIN_ROOT"
uv venv --python 3.11
echo "Virtual environment created"

# Install dependencies
echo ""
echo "Installing databricks-tools-core..."
uv pip install --python .venv/bin/python -e "$TOOLS_CORE_DIR" --quiet
echo "databricks-tools-core installed"

echo ""
echo "Installing databricks-mcp-server..."
uv pip install --python .venv/bin/python -e "$MCP_SERVER_DIR" --quiet
echo "databricks-mcp-server installed"

# Verify installation
echo ""
echo "Verifying installation..."
if .venv/bin/python -c "import databricks_mcp_server" 2>/dev/null; then
    echo "MCP server verified"
else
    echo "Warning: Could not verify MCP server import"
fi

echo ""
echo "======================================"
echo "Databricks AI Dev Kit setup complete!"
echo "======================================"
echo ""
echo "To enable the MCP server, add this to your project's .mcp.json:"
echo ""
cat <<'EOF'
{
  "mcpServers": {
    "databricks": {
      "command": "${CLAUDE_PLUGIN_ROOT}/.venv/bin/python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/databricks-mcp-server/run_server.py"],
      "defer_loading": true
    }
  }
}
EOF
echo ""
echo "Or run this command to add it via CLI:"
echo "  claude mcp add-json databricks '{\"command\":\"\${CLAUDE_PLUGIN_ROOT}/.venv/bin/python\",\"args\":[\"\${CLAUDE_PLUGIN_ROOT}/databricks-mcp-server/run_server.py\"],\"defer_loading\":true}'"
echo ""
