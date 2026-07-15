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

# If versions differ, print a plain status line for Claude to see. No
# instructions directed at the assistant and no embedded install command —
# testing showed that combination still reads as a prompt injection even with
# calm wording, since it's the "here's how/when to tell the user" framing
# (not the tone) that trips the heuristic.
if [ -n "$remote_ver" ] && [ "$remote_ver" != "$local_ver" ]; then
    cat <<EOF
[ai-dev-kit] Note: installed version is v${local_ver}; v${remote_ver} is now available.
See the "Update" section of the ai-dev-kit README: https://github.com/databricks-solutions/ai-dev-kit#update
EOF
fi
