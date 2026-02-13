#!/bin/bash
#
# Cleanup script for databricks-claude-test-project
# Removes generated files and resets to clean state
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================"
echo "Cleaning up Databricks Claude Test Project"
echo "============================================"
echo ""

# Remove MCP server registration
if command -v claude &> /dev/null; then
    echo "Removing MCP server registration..."
    claude mcp remove databricks 2>/dev/null || true
    echo "  Removed databricks MCP server"
fi

# Remove .claude directory (skills, sessions)
if [ -d "$SCRIPT_DIR/.claude" ]; then
    echo "Removing .claude/ directory..."
    rm -rf "$SCRIPT_DIR/.claude"
    echo "  Removed .claude/"
fi

# Remove any test output directories
for dir in test_output output tmp temp src; do
    if [ -d "$SCRIPT_DIR/$dir" ]; then
        echo "Removing $dir/ directory..."
        rm -rf "$SCRIPT_DIR/$dir"
        echo "  Removed $dir/"
    fi
done

# Remove generated files
echo "Removing generated files..."
find "$SCRIPT_DIR" -name "*.pyc" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.parquet" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.csv" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.log" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.tmp" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.py" ! -name "setup.py" -delete 2>/dev/null || true
find "$SCRIPT_DIR" -name "*.sql" -delete 2>/dev/null || true

# Reset CLAUDE.md to clean state
echo "Resetting CLAUDE.md..."
cat > "$SCRIPT_DIR/CLAUDE.md" << 'EOF'
# Project Context

This is a test project for experimenting with Databricks MCP tools and Claude Code.

## Available Tools

You have access to Databricks MCP tools prefixed with `mcp__databricks__`. Use `/mcp` to see the list of available tools.

## Skills

Load skills for detailed guidance:
- `skill: "asset-bundles"` - Databricks Asset Bundles
- `skill: "databricks-app-apx"` - Full-stack apps with APX framework
- `skill: "databricks-app-python"` - Python apps with Dash, Streamlit, Flask
- `skill: "databricks-python-sdk"` - Python SDK patterns
- `skill: "mlflow-evaluation"` - MLflow evaluation and trace analysis
- `skill: "spark-declarative-pipelines"` - Spark Declarative Pipelines
- `skill: "databricks-data-generation"` - Test data generation

## Testing Workflow

1. Start with simple queries to verify MCP connection works
2. Test individual tools before combining them
3. Use skills when building pipelines or complex workflows

## Notes

This is a sandbox for testing - feel free to create files, run queries, and experiment.
EOF
echo "  Reset CLAUDE.md"

echo ""
echo "========================================"
echo "Cleanup complete!"
echo "========================================"
echo ""
echo "Run ./setup.sh to set up the project again."
echo ""
