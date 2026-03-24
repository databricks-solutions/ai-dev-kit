#!/usr/bin/env bash
# Install/sync skill-authoring skill to .claude/skills/
#
# The source of truth is .skill-authoring/ (this directory).
# This script copies files to .claude/skills/skill-authoring/ so Claude Code
# picks them up automatically when contributors clone the repo.
#
# Usage:
#   bash .skill-authoring/install_skill_authoring.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="$REPO_ROOT/.claude/skills/skill-authoring"

mkdir -p "$TARGET_DIR/references"

echo "Syncing skill-authoring to $TARGET_DIR ..."

cp "$SCRIPT_DIR/SKILL.md" "$TARGET_DIR/SKILL.md"
cp "$SCRIPT_DIR/references/skill-format.md" "$TARGET_DIR/references/skill-format.md"
cp "$SCRIPT_DIR/references/test-format.md" "$TARGET_DIR/references/test-format.md"

echo "Done. skill-authoring skill installed at $TARGET_DIR"
