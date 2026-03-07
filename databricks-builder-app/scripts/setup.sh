#!/bin/bash
#
# Setup script for Databricks Builder App
# Installs dependencies and prepares the environment for local development
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_DIR")"

cd "$PROJECT_DIR"

echo "=========================================="
echo "  Databricks Builder App Setup"
echo "=========================================="
echo ""

# ── Check prerequisites ──────────────────────────────────────────────────────

# Check for uv
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' is not installed."
    echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
echo "✓ uv is installed"

# Check for node
if ! command -v node &> /dev/null; then
    echo "Error: 'node' is not installed."
    echo "Install Node.js 18+ from: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Error: Node.js 18+ is required (found $(node -v))"
    exit 1
fi
echo "✓ Node.js $(node -v) is installed"

# Check for npm
if ! command -v npm &> /dev/null; then
    echo "Error: 'npm' is not installed."
    exit 1
fi
echo "✓ npm is installed"

# ── Environment file ─────────────────────────────────────────────────────────

echo ""
if [ ! -f "$PROJECT_DIR/.env.local" ]; then
    echo "Creating .env.local from .env.example..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env.local"
    echo "✓ Created .env.local"
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║  ACTION REQUIRED: Configure your .env.local file               ║"
    echo "╠══════════════════════════════════════════════════════════════════╣"
    echo "║                                                                ║"
    echo "║  Open databricks-builder-app/.env.local and fill in values:    ║"
    echo "║                                                                ║"
    echo "║  1. DATABRICKS_HOST  - Your workspace URL                      ║"
    echo "║  2. DATABRICKS_TOKEN - Your personal access token              ║"
    echo "║  3. LAKEBASE_PG_URL  - PostgreSQL connection string            ║"
    echo "║     (or LAKEBASE_INSTANCE_NAME for Databricks Apps)            ║"
    echo "║                                                                ║"
    echo "║  See .env.example for all available options.                   ║"
    echo "║                                                                ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    ENV_CREATED=true
else
    echo "✓ .env.local file already exists"
    ENV_CREATED=false
fi

# ── Install backend dependencies ─────────────────────────────────────────────

echo ""
echo "Installing backend dependencies..."
uv sync --quiet
echo "✓ Backend dependencies installed"

# ── Install sibling packages ─────────────────────────────────────────────────

echo ""
echo "Installing sibling packages (databricks-tools-core, databricks-mcp-server)..."
if [ -d "$REPO_ROOT/databricks-tools-core" ] && [ -d "$REPO_ROOT/databricks-mcp-server" ]; then
    uv pip install -e "$REPO_ROOT/databricks-tools-core" -e "$REPO_ROOT/databricks-mcp-server" --quiet
    echo "✓ Sibling packages installed"
else
    echo "⚠ Sibling packages not found at repo root. If you cloned just this"
    echo "  directory, install them manually:"
    echo "    pip install databricks-tools-core databricks-mcp-server"
fi

# ── Install frontend dependencies ────────────────────────────────────────────

echo ""
echo "Installing frontend dependencies..."
cd "$PROJECT_DIR/client"
npm install --silent 2>/dev/null || npm install
cd "$SCRIPT_DIR"
echo "✓ Frontend dependencies installed"

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""

if [ "$ENV_CREATED" = true ]; then
    echo "Next steps:"
    echo "  1. Edit .env.local with your Databricks credentials and database config"
    echo "  2. Run: ./scripts/start_dev.sh"
    echo ""
else
    echo "Next steps:"
    echo "  Run: ./scripts/start_dev.sh"
    echo ""
fi

echo "This will start:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo ""
