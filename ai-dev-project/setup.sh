#!/bin/bash
#
# Setup script for ai-dev-project
# Installs skills and configures the MCP server
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
SKILLS_DIR="$BASE_DIR/databricks-skills"
MCP_SERVER_DIR="$BASE_DIR/databricks-mcp-server"
TOOLS_CORE_DIR="$BASE_DIR/databricks-tools-core"

echo "=========================================="
echo "Setting up Databricks Claude Test Project"
echo "=========================================="
echo ""

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✓ uv is installed"

# Check if skills directory exists
if [ ! -d "$SKILLS_DIR" ]; then
    echo "Error: Skills directory not found at $SKILLS_DIR"
    echo "Make sure you're running from the ai-dev-kit repository."
    exit 1
fi
echo "✓ Skills directory found"

# Check if MCP server directory exists
if [ ! -d "$MCP_SERVER_DIR" ]; then
    echo "Error: MCP server directory not found at $MCP_SERVER_DIR"
    echo "Make sure you're running from the ai-dev-kit repository."
    exit 1
fi
echo "✓ MCP server directory found"

# Verify MCP server is set up
MCP_PYTHON="$BASE_DIR/.venv/bin/python"

echo ""
echo "Checking MCP server setup..."
if [ ! -f "$MCP_PYTHON" ]; then
# Run the install MCP server script
    echo ""
    echo "Setup Databricks MCP server..."
    cd "$BASE_DIR"
    "$MCP_SERVER_DIR/setup.sh" "$@"
    if [ ! -f "$MCP_PYTHON" ]; then 
        echo "Error: MCP server venv not found at $BASE_DIR/.venv"
        echo ""
        echo "Please debug MCP server setup first by running:"
        echo "  cd $BASE_DIR"
        echo "  ./databricks-mcp-server/setup.sh   # or: uv venv && uv pip install -e ../databricks-tools-core -e ."
        exit 1
    fi
fi

# Verify the server can be imported
if ! "$MCP_PYTHON" -c "import databricks_mcp_server" 2>/dev/null; then
    echo ""
    echo "Setup Databricks MCP server..."
    cd "$BASE_DIR"
    "$MCP_SERVER_DIR/setup.sh" "$@"
    if ! "$MCP_PYTHON" -c "import databricks_mcp_server" 2>/dev/null; then 
        echo "Error: MCP server packages not installed properly"
        echo ""
        echo "Please debug MCP server setup first by running:"
        echo "  cd $BASE_DIR"
        echo "  ./databricks-mcp-server/setup.sh   # or: uv venv && uv pip install -e ../databricks-tools-core -e ."
        exit 1
    fi
fi
echo "✓ MCP server is set up"

# Run the install skills script
echo ""
echo "Installing Databricks skills..."
cd "$SCRIPT_DIR"
"$SKILLS_DIR/install_skills.sh" "$@"

# Populate .mcp.json (for Claude Code) and .cursor/mcp.json (for Cursor) with the MCP server configuration
# Build development-purpose mcpServers configuration for direct python runner using this environment
MCP_DEV_CONFIG=$(cat <<EOF
{
  "mcpServers": {
    "databricks": {
      "command": "$BASE_DIR/.venv/bin/python",
      "args": ["$MCP_SERVER_DIR/run_server.py"]
    }
  }
}
EOF
)

echo ""
echo "Creating .mcp.json..."
echo "$MCP_DEV_CONFIG" > "$SCRIPT_DIR/.mcp.json"
echo "Created .mcp.json"

echo ""
echo "Creating .cursor/mcp.json..."
mkdir -p ${SCRIPT_DIR}/.cursor
echo "$MCP_DEV_CONFIG" > "$SCRIPT_DIR/.cursor/mcp.json"
echo "Created .cursor/mcp.json"

# Create/reset CLAUDE.md
echo ""
echo "Creating CLAUDE.md..."
cat > "$SCRIPT_DIR/CLAUDE.md" << 'EOF'
# Project Context

This is a test project for experimenting with Databricks MCP tools and Claude Code.

## Available Tools

You have access to Databricks MCP tools prefixed with `mcp__databricks__`. Use `/mcp` to see the list of available tools.

## Skills

Load skills for detailed guidance:
- `skill: "agent-bricks"` - Knowledge Assistants, Genie Spaces, Multi-Agent Supervisors
- `skill: "aibi-dashboards"` - AI/BI Dashboards
- `skill: "asset-bundles"` - Databricks Asset Bundles
- `skill: "databricks-app-apx"` - Full-stack apps with APX framework
- `skill: "databricks-app-python"` - Python apps with Dash, Streamlit, Flask
- `skill: "databricks-config"` - Profile authentication setup
- `skill: "databricks-docs"` - Documentation reference
- `skill: "databricks-jobs"` - Lakeflow Jobs and workflows
- `skill: "databricks-python-sdk"` - Python SDK patterns
- `skill: "databricks-unity-catalog"` - System tables for lineage, audit, billing, access controls, and FGAC policy governance.
- `skill: "mlflow-evaluation"` - MLflow evaluation and trace analysis
- `skill: "spark-declarative-pipelines"` - Spark Declarative Pipelines
- `skill: "synthetic-data-generation"` - Test data generation
- `skill: "unstructured-pdf-generation"` - Generate synthetic PDFs for RAG

## Testing Workflow

1. Start with simple queries to verify MCP connection works
2. Test individual tools before combining them
3. Use skills when building pipelines or complex workflows

## Notes

This is a sandbox for testing - feel free to create files, run queries, and experiment.
EOF
echo "Created CLAUDE.md"

echo ""
echo "========================================"
echo "Setup complete!"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Make sure DATABRICKS_HOST and DATABRICKS_TOKEN are set"
echo "  2. Run: claude (or open Cursor IDE)"
echo "  3. Test the MCP tools with commands like:"
echo "     - 'List my SQL warehouses'"
echo "     - 'Run a simple SQL query'"
echo ""
