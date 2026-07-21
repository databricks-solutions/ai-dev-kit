#!/bin/bash
# DEPRECATED: The databricks-ai-dev-kit Claude Code plugin is no longer published
# (see .claude-plugin/DEPRECATED.md). Install skills via install.sh or
# `databricks aitools install`. This script is kept for reference and still runs
# if invoked directly.
#
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

# Only nudge when the remote version is strictly newer than the local one.
# sort -V -C succeeds when its input is already in ascending version order, so
# this is true exactly when local_ver < remote_ver. Comparing on "!=" alone
# (as before) also fired when the local build was NEWER than main — e.g. someone
# on a pre-release/branch build (VERSION=0.1.14) got told to "update" to main's
# older 0.1.13 — a confusing backwards nudge.
remote_is_newer=false
if [ -n "$remote_ver" ] && [ "$remote_ver" != "$local_ver" ]; then
    printf '%s\n%s\n' "$local_ver" "$remote_ver" | sort -V -C 2>/dev/null && remote_is_newer=true
fi

# When a newer version exists, print an update notice for Claude to relay. The
# light "worth mentioning to the user" cue is deliberate: testing showed that
# with no assistant-directed wording at all, Claude treats the notice as
# background noise and stays silent, so the user never hears about the update.
# The line stays injection-safe by carrying no embedded install command —
# it points at the README instead of shipping a curl|bash one-liner.
if [ "$remote_is_newer" = true ]; then
    cat <<EOF
[ai-dev-kit] Update available: installed v${local_ver}, latest v${remote_ver}. Worth mentioning
to the user near the start of your reply. For how to update, refer them to the "Update" section
of the ai-dev-kit README: https://github.com/databricks-solutions/ai-dev-kit#update
EOF
fi
