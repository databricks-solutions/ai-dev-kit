#!/bin/bash
# Install/sync skill-test skill to .claude/skills/
#
# This script copies files from .test/ (source of truth) to
# .claude/skills/skill-test/ (installed skill location).
#
# Usage:
#   ./install_skill_test.sh           # Install from local .test/
#   ./install_skill_test.sh --force   # Overwrite existing (default)
#   ./install_skill_test.sh --dry-run # Show what would be copied

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$SCRIPT_DIR"
TARGET_DIR="$REPO_ROOT/.claude/skills/skill-test"

# Parse arguments
DRY_RUN=false
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            ;;
        --force)
            # Force is the default, kept for compatibility
            ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--force]"
            echo ""
            echo "Options:"
            echo "  --dry-run  Show what would be copied without making changes"
            echo "  --force    Overwrite existing files (default behavior)"
            echo ""
            echo "Syncs files from .test/ to .claude/skills/skill-test/"
            exit 0
            ;;
    esac
done

# Files to copy (source:destination)
FILES_TO_COPY=(
    "SKILL.md:SKILL.md"
    "references/yaml-schemas.md:references/yaml-schemas.md"
    "references/scorers.md:references/scorers.md"
    "scripts/mlflow_eval.py:scripts/mlflow_eval.py"
    "scripts/run_eval.py:scripts/run_eval.py"
    "scripts/baseline.py:scripts/baseline.py"
    "scripts/regression.py:scripts/regression.py"
    "scripts/init_skill.py:scripts/init_skill.py"
)

echo "Skill-test installer"
echo "===================="
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would perform the following actions:"
    echo ""
fi

# Create directories
DIRS_TO_CREATE=(
    "$TARGET_DIR"
    "$TARGET_DIR/references"
    "$TARGET_DIR/scripts"
)

for dir in "${DIRS_TO_CREATE[@]}"; do
    if [ ! -d "$dir" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "  mkdir -p $dir"
        else
            mkdir -p "$dir"
            echo "  Created directory: ${dir#$REPO_ROOT/}"
        fi
    fi
done

# Copy files
copied=0
skipped=0
missing=0

for mapping in "${FILES_TO_COPY[@]}"; do
    src="${mapping%%:*}"
    dst="${mapping##*:}"
    src_path="$SOURCE_DIR/$src"
    dst_path="$TARGET_DIR/$dst"

    if [ -f "$src_path" ]; then
        if [ "$DRY_RUN" = true ]; then
            echo "  cp $src -> $dst"
        else
            cp "$src_path" "$dst_path"
            echo "  Copied: $src"
        fi
        ((copied++))
    else
        echo "  WARNING: Source not found: $src"
        ((missing++))
    fi
done

echo ""
if [ "$DRY_RUN" = true ]; then
    echo "[DRY RUN] Would copy $copied files"
    if [ $missing -gt 0 ]; then
        echo "[DRY RUN] $missing files not found"
    fi
else
    echo "Done! Copied $copied files to $TARGET_DIR"
    if [ $missing -gt 0 ]; then
        echo "Warning: $missing source files not found"
    fi
fi
