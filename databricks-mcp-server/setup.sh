#!/bin/bash
#
# ─── Noom governance guard ─────────────────────────────────────────────────────
# This repo is Noom's governed fork of databricks-solutions/ai-dev-kit.
# Do NOT use this setup script — it installs the unpatched upstream MCP server
# without Noom's SQL governance controls (SP execution, PAT rejection, query tagging).
#
# Use the Noom MCP server instead:
#   cd noom-mcp-server
#   cp .env.example .env   # fill in DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID
#   uv sync
#   uv run --env-file .env python run.py
#
# See noom-mcp-server/README.md for full setup instructions.
# ───────────────────────────────────────────────────────────────────────────────
echo "" >&2
echo "ERROR: Do not run this setup script at Noom." >&2
echo "" >&2
echo "This repo is Noom's governed fork. This script installs the unpatched" >&2
echo "upstream MCP server without SQL governance controls." >&2
echo "" >&2
echo "Use the Noom MCP server instead:" >&2
echo "  cd noom-mcp-server" >&2
echo "  cp .env.example .env  # fill in DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID" >&2
echo "  uv sync && uv run --env-file .env python run.py" >&2
echo "" >&2
echo "See noom-mcp-server/README.md for setup instructions." >&2
echo "" >&2
exit 1

#
# Setup script for databricks-mcp-server
# Creates virtual environment and installs dependencies
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"
TOOLS_CORE_DIR="${PARENT_DIR}/databricks-tools-core"
echo AI Dev Kit directory: $PARENT_DIR
echo MCP Server directory: $SCRIPT_DIR
echo Tools Core directory: $TOOLS_CORE_DIR


echo "======================================"
echo "Setting up Databricks MCP Server"
echo "======================================"
echo ""

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✓ uv is installed"

# Check if tools-core directory exists
if [ ! -d "$TOOLS_CORE_DIR" ]; then
    echo "Error: databricks-tools-core not found at $TOOLS_CORE_DIR"
    exit 1
fi
echo "✓ databricks-tools-core found"


# Create virtual environment
echo ""
echo "Creating virtual environment..."
uv venv --python 3.11
echo "✓ Virtual environment created"


# Install packages
echo ""
echo "Installing databricks-tools-core (editable)..."
uv pip install --python .venv/bin/python -e "$TOOLS_CORE_DIR" --quiet
echo "✓ databricks-tools-core installed"

echo ""
echo "Installing databricks-mcp-server (editable)..."

uv pip install --python .venv/bin/python -e "$SCRIPT_DIR" --quiet
echo "✓ databricks-mcp-server installed"

# Verify
echo ""
echo "Verifying installation..."
if .venv/bin/python -c "import databricks_mcp_server; print('✓ MCP server can be imported')"; then
    echo ""
    echo "======================================"
    echo "Setup complete!"
    echo "======================================"
    echo ""
    echo "To run the MCP server:"
    echo "  .venv/bin/python run_server.py"
    echo ""
    echo "To setup in the project, paste this into .mcp.json (Claude) or .cursor/mcp.json (Cursor):"
    cat <<EOF
    {
      "mcpServers": {
        "databricks": {
          "command": "${PARENT_DIR}/.venv/bin/python",
          "args": ["${SCRIPT_DIR}/run_server.py"]
        }
      }
    }
EOF
    echo ""
    echo "To setup with Claude Code CLI:"
    echo "  claude mcp add-json databricks '{\"command\":\"$PARENT_DIR/.venv/bin/python\",\"args\":[\"$SCRIPT_DIR/run_server.py\"]}'"
    echo ""
else
    echo "Error: Failed to import databricks_mcp_server"
    exit 1
fi
