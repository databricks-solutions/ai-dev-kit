#!/bin/bash
#
# Setup script for databricks-mcp-server.
#
# Creates the Python virtual environment and installs the MCP server (plus its
# databricks-tools-core dependency) in editable mode, then verifies the install.
#
# This is the single source of truth for building the MCP server runtime. The
# unified installers (install.sh / install.ps1) only write the editor config
# files that point at the venv — when the user opts into the (deprecated) MCP
# server, they delegate the actual environment build here so the logic lives
# next to the server it sets up.
#
# Usage:
#   bash databricks-mcp-server/setup.sh [OPTIONS]
#
# Options:
#   --venv-dir DIR   Location for the virtual environment (default: <this dir>/.venv)
#   --python VER     Python version to request from uv (default: 3.11)
#   --quiet          Suppress progress output (errors still print)
#   -h, --help       Show this help
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT_DIR="$(dirname "${SCRIPT_DIR}")"
TOOLS_CORE_DIR="${PARENT_DIR}/databricks-tools-core"

# Defaults
VENV_DIR="${SCRIPT_DIR}/.venv"
PYTHON_VERSION="3.11"
QUIET=false

# Minimum Databricks SDK version (kept in sync with the installers)
MIN_SDK_VERSION="0.85.0"

while [ $# -gt 0 ]; do
    case $1 in
        --venv-dir) VENV_DIR="$2"; shift 2 ;;
        --python)   PYTHON_VERSION="$2"; shift 2 ;;
        --quiet)    QUIET=true; shift ;;
        -h|--help)
            echo "Setup the Databricks MCP server runtime"
            echo ""
            echo "Usage: bash databricks-mcp-server/setup.sh [OPTIONS]"
            echo ""
            echo "  --venv-dir DIR   Virtual environment location (default: <script dir>/.venv)"
            echo "  --python VER     Python version for uv (default: 3.11)"
            echo "  --quiet          Suppress progress output"
            echo "  -h, --help       Show this help"
            exit 0 ;;
        *) echo "Unknown option: $1 (use -h for help)" >&2; exit 1 ;;
    esac
done

VENV_PYTHON="${VENV_DIR}/bin/python"

# Output helpers (respect --quiet; errors always print)
say() { [ "$QUIET" = true ] || echo "$@"; }
die() { echo "Error: $*" >&2; exit 1; }

# Compare semantic versions (returns 0 if $1 >= $2)
version_gte() { printf '%s\n%s' "$2" "$1" | sort -V -C; }

say "======================================"
say "Setting up Databricks MCP Server"
say "======================================"
say ""
say "MCP Server directory: $SCRIPT_DIR"
say "Tools Core directory: $TOOLS_CORE_DIR"
say "Virtual environment:  $VENV_DIR"
say ""

# Check for uv
command -v uv >/dev/null 2>&1 || die "'uv' is not installed.
   Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh
   Then re-run this script."
say "✓ uv is installed"

# Check tools-core is present
[ -d "$TOOLS_CORE_DIR" ] || die "databricks-tools-core not found at $TOOLS_CORE_DIR"
say "✓ databricks-tools-core found"

# Create virtual environment.
# On Apple Silicon under Rosetta, force arm64 to avoid an architecture mismatch
# with universal2 Python binaries (see issue #115).
arch_prefix=""
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && [ "$(uname -m)" = "x86_64" ]; then
    if arch -arm64 python3 -c "pass" 2>/dev/null; then
        arch_prefix="arch -arm64"
        say "! Rosetta detected on Apple Silicon — forcing arm64 for Python"
    fi
fi

say ""
say "Creating virtual environment..."
$arch_prefix uv venv --python "$PYTHON_VERSION" --allow-existing "$VENV_DIR" -q 2>/dev/null \
    || $arch_prefix uv venv --allow-existing "$VENV_DIR" -q
say "✓ Virtual environment ready"

say ""
say "Installing databricks-tools-core and databricks-mcp-server (editable)..."
$arch_prefix uv pip install --python "$VENV_PYTHON" -e "$TOOLS_CORE_DIR" -e "$SCRIPT_DIR" -q
say "✓ Packages installed"

# Verify
say ""
say "Verifying installation..."
"$VENV_PYTHON" -c "import databricks_mcp_server" 2>/dev/null \
    || die "Failed to import databricks_mcp_server"
say "✓ MCP server can be imported"

# Check Databricks SDK version
sdk_version=$("$VENV_PYTHON" -c "from databricks.sdk.version import __version__; print(__version__)" 2>/dev/null || true)
if [ -z "$sdk_version" ]; then
    say "! Could not determine Databricks SDK version"
elif version_gte "$sdk_version" "$MIN_SDK_VERSION"; then
    say "✓ Databricks SDK v${sdk_version}"
else
    say "! Databricks SDK v${sdk_version} is outdated (minimum: v${MIN_SDK_VERSION})"
    say "  Upgrade: $VENV_PYTHON -m pip install --upgrade databricks-sdk"
fi

if [ "$QUIET" = false ]; then
    echo ""
    echo "======================================"
    echo "Setup complete!"
    echo "======================================"
    echo ""
    echo "To run the MCP server:"
    echo "  $VENV_PYTHON $SCRIPT_DIR/run_server.py"
    echo ""
    echo "MCP config snippet (.mcp.json for Claude, .cursor/mcp.json for Cursor):"
    cat <<EOF
    {
      "mcpServers": {
        "databricks": {
          "command": "${VENV_PYTHON}",
          "args": ["${SCRIPT_DIR}/run_server.py"],
          "defer_loading": true
        }
      }
    }
EOF
    echo ""
fi
