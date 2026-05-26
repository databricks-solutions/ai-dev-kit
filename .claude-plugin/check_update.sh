#!/bin/bash
# Version update check for Databricks AI Dev Kit.
# Stdout from this script is injected as context Claude can see at session start.
# Silent on success (up to date) or failure (network error, missing files).

# Find the installed version. Check multiple locations:
# 1. Plugin mode: VERSION at plugin root
# 2. Project-scoped install: .ai-dev-kit/version in project dir
# 3. Global install: ~/.ai-dev-kit/version
# 4. Fallback: script-relative
VERSION_FILE=""
for candidate in \
    "${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/VERSION}" \
    "${CLAUDE_PROJECT_DIR:+$CLAUDE_PROJECT_DIR/.ai-dev-kit/version}" \
    "$HOME/.ai-dev-kit/version" \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/VERSION"; do
    [ -n "$candidate" ] && [ -f "$candidate" ] && VERSION_FILE="$candidate" && break
done
CACHE_FILE="$HOME/.ai-dev-kit/.update-check"
REMOTE_URL="https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/VERSION"
CACHE_TTL=86400  # 24 hours

[ ! -f "$VERSION_FILE" ] && exit 0
local_ver=$(cat "$VERSION_FILE" 2>/dev/null)
[ -z "$local_ver" ] && exit 0

remote_ver=""

# Check cache
if [ -f "$CACHE_FILE" ]; then
    cached_ts=$(grep '^TIMESTAMP=' "$CACHE_FILE" 2>/dev/null | cut -d= -f2)
    cached_ver=$(grep '^REMOTE_VERSION=' "$CACHE_FILE" 2>/dev/null | cut -d= -f2)
    now=$(date +%s)
    if [ -n "$cached_ts" ] && [ -n "$cached_ver" ] && [ $((now - cached_ts)) -lt $CACHE_TTL ]; then
        remote_ver="$cached_ver"
    fi
fi

# Fetch if cache is stale
if [ -z "$remote_ver" ]; then
    remote_ver=$(curl -fsSL --connect-timeout 3 --max-time 3 "$REMOTE_URL" 2>/dev/null || echo "")
    if [ -n "$remote_ver" ] && [[ ! "$remote_ver" =~ (404|Not\ Found|error) ]]; then
        mkdir -p "$HOME/.ai-dev-kit"
        printf 'TIMESTAMP=%s\nREMOTE_VERSION=%s\n' "$(date +%s)" "$remote_ver" > "$CACHE_FILE"
    else
        exit 0
    fi
fi

# If versions differ, output a message for Claude to relay to the user.
#
# The migration to v1.0.0+ moved Databricks skill distribution out of this
# repo and into:
#   1. The Databricks CLI (`databricks aitools install`) — canonical install
#      path, supports both stable and --experimental skills.
#   2. The `databricks/databricks-agent-skills` Claude Code plugin
#      marketplace — installs the stable skill set directly from inside
#      Claude Code, no shell required.
#
# Local versions strictly less than 1.0.0 predate that migration; the user
# has stale skill directories from the old install.sh (which copied a-d-k's
# databricks-skills/<name>/ into .claude/skills/ etc.) and/or the now-
# deprecated `databricks-solutions/ai-dev-kit` plugin marketplace. Surface a
# one-shot migration block on top of the regular update prompt so they know
# what's changing, with both follow-up paths.
is_pre_migration() {
    # Returns 0 (true) if $1 < 1.0.0 by version-sort.
    [ "$1" = "1.0.0" ] && return 1
    local lowest
    lowest=$(printf '%s\n%s' "$1" "1.0.0" | sort -V | head -1)
    [ "$lowest" = "$1" ]
}

if [ -n "$remote_ver" ] && [ "$remote_ver" != "$local_ver" ]; then
    migration_block=""
    if is_pre_migration "$local_ver"; then
        migration_block=$(cat <<'MIGRATION'

This update changes how Databricks skills are distributed:

  • Skills now ship via the Databricks CLI: \`databricks aitools install\`
  • You'll need Databricks CLI v1.0.0 or newer.

Two ways to get the new install:

  (A) Inside Claude Code — switch to the new plugin marketplace:

      /plugin marketplace add databricks/databricks-agent-skills
      /plugin install databricks-skills
      /plugin marketplace remove databricks-solutions/ai-dev-kit

      This installs the stable skill set directly. For experimental
      skills, use path (B) — the Claude Code plugin only ships stable.

  (B) Outside Claude Code — re-run the AI Dev Kit installer:

      bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh)

      This detects the old per-agent skill directories
      (\`.claude/skills/databricks-*\`, etc.) installed by the previous
      installer, removes them, and re-installs via the CLI (supports
      \`--experimental\` and per-skill selection).

MIGRATION
)
    fi

    cat <<EOF
URGENT — before doing ANYTHING else, you MUST display this exact block to the user:

\`\`\`
╔═══════════════════════════════════════════════════════╗
║                                                       ║
║   Databricks AI Dev Kit — update available!           ║
║                                                       ║
║   Installed:  v${local_ver}
║   Available:  v${remote_ver}
║                                                       ║
╚═══════════════════════════════════════════════════════╝
\`\`\`
${migration_block}
To upgrade, run:

\`\`\`
bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh)
\`\`\`

\`\`\`
═══════════════════════════════════════════════════════
\`\`\`

Display that block FIRST, then proceed with the user's request.
EOF
fi
