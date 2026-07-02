#!/bin/bash
# One-command setup for AI Dev Kit integration example
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== AI Dev Kit Integration Setup ==="
echo ""

# Check for uv or pip
if command -v uv &> /dev/null; then
    PKG_MANAGER="uv"
    echo "Using uv package manager"
else
    PKG_MANAGER="pip"
    echo "Using pip (consider installing uv for faster installs)"
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ "$PKG_MANAGER" = "uv" ]; then
    uv venv .venv
else
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
if [ "$PKG_MANAGER" = "uv" ]; then
    uv pip install -r requirements.txt
else
    pip install -r requirements.txt
fi

# Install skills
echo ""
echo "Installing all skills..."
SKILLS_DIR="$SCRIPT_DIR/.claude/skills"
mkdir -p "$SKILLS_DIR"

# Copy all skills from the bundled skills snapshot (excluding non-skill dirs).
# The bundled skill copies moved under databricks-skills/deprecated/; prefer
# that snapshot and fall back to the legacy databricks-skills/ location.
SKILLS_SRC="$SCRIPT_DIR/../../../databricks-skills/deprecated"
if [ ! -d "$SKILLS_SRC" ]; then
    SKILLS_SRC="$SCRIPT_DIR/../../../databricks-skills"
fi
if [ -d "$SKILLS_SRC" ]; then
    # Find all directories containing SKILL.md (these are actual skills)
    for skill_dir in "$SKILLS_SRC"/*/; do
        skill_name=$(basename "$skill_dir")
        # Skip non-skill directories
        if [ "$skill_name" = "TEMPLATE" ]; then
            continue
        fi
        # Only copy if it has a SKILL.md (confirms it's a real skill)
        if [ -f "$skill_dir/SKILL.md" ]; then
            echo "  Installing: $skill_name"
            cp -r "$skill_dir" "$SKILLS_DIR/"
        fi
    done
    echo "Skills installed to $SKILLS_DIR"
else
    echo "Warning: databricks-skills not found at $SKILLS_SRC"
    echo "Skills will need to be installed manually"
fi

# Copy .env.example to .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Created .env - please edit with your credentials"
fi

# Create projects directory for agent working files
mkdir -p projects

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your Databricks and Claude credentials"
echo "  2. Activate the environment: source .venv/bin/activate"
echo "  3. Run the example: python example_integration.py"
echo ""
