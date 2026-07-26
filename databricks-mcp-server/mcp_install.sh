#!/bin/bash
#
# Databricks MCP Server - Client Registration Installer
#
# Builds the MCP server runtime (by delegating to setup.sh) and registers the
# `databricks` MCP server with your AI coding tools: Claude Code, Cursor,
# GitHub Copilot, OpenAI Codex, Gemini CLI, Antigravity, Windsurf, OpenCode, and Kiro.
#
# The venv build is owned by databricks-mcp-server/setup.sh — this script never
# duplicates that logic; it calls setup.sh and then writes the editor config
# files that point at the resulting venv.
#
# Usage:
#   bash databricks-mcp-server/mcp_install.sh [OPTIONS]
#
# Options:
#   -p, --profile NAME   Databricks config profile to inject (default: DEFAULT)
#   -g, --global         Register globally (home dir) instead of per-project
#   --tools LIST         Comma-separated: claude,cursor,copilot,codex,gemini,antigravity,windsurf,opencode,kiro
#   --venv-dir DIR       Virtual environment location (default: <this dir>/.venv)
#   --skip-venv          Skip the setup.sh venv build (assume it already exists)
#   --silent             Silent mode (no output except errors)
#   --uninstall          Remove only the 'databricks' MCP entry from each client config
#   --dry-run            Print the plan (install or uninstall) and exit without changes
#   -y, --yes            With --uninstall: skip the confirmation prompt
#   -h, --help           Show this help
#
# Environment Variables (alternative to flags):
#   DEVKIT_PROFILE       Databricks config profile
#   DEVKIT_SCOPE         'project' or 'global'
#   DEVKIT_TOOLS         Comma-separated list of tools
#   DEVKIT_SILENT        Set to 'true' for silent mode
#

set -e

# ─── Paths (derived from this script's own location) ────────────
# The repo is already cloned when this standalone installer runs, so — unlike the
# unified installer's clone-to-~/.ai-dev-kit flow — paths derive from here, the
# same way setup.sh does.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_ENTRY="$SCRIPT_DIR/run_server.py"

# Defaults (can be overridden by environment variables or command-line arguments)
PROFILE="${DEVKIT_PROFILE:-DEFAULT}"
SCOPE="${DEVKIT_SCOPE:-project}"
SCOPE_EXPLICIT=false
SILENT="${DEVKIT_SILENT:-false}"
TOOLS="${DEVKIT_TOOLS:-}"
USER_TOOLS=""
VENV_DIR="$SCRIPT_DIR/.venv"
SKIP_VENV=false
UNINSTALL=false
DRY_RUN=false
ASSUME_YES=false

# Convert string booleans from env vars to actual booleans
if [ "$SILENT" = "true" ] || [ "$SILENT" = "1" ]; then SILENT=true; else SILENT=false; fi
# Guarded so a false test can't abort the script under `set -e` on older bash
# (e.g. macOS /bin/bash 3.2), where a bare `[ ... ] && VAR=...` at top level exits.
if [ -n "${DEVKIT_SCOPE:-}" ]; then SCOPE_EXPLICIT=true; fi

# Colors
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' B='\033[1m' D='\033[2m' N='\033[0m'

# Output helpers
msg()  { [ "$SILENT" = true ] || echo -e "  $*"; }
ok()   { [ "$SILENT" = true ] || echo -e "  ${G}✓${N} $*"; }
warn() { [ "$SILENT" = true ] || echo -e "  ${Y}!${N} $*"; }
die()  { echo -e "  ${R}✗${N} $*" >&2; exit 1; }  # Always show errors
step() { [ "$SILENT" = true ] || echo -e "\n${B}$*${N}"; }

# Parse arguments
while [ $# -gt 0 ]; do
    case $1 in
        -p|--profile)  PROFILE="$2"; shift 2 ;;
        -g|--global)   SCOPE="global"; SCOPE_EXPLICIT=true; shift ;;
        --tools)       USER_TOOLS="$2"; shift 2 ;;
        --venv-dir)    VENV_DIR="$2"; shift 2 ;;
        --skip-venv)   SKIP_VENV=true; shift ;;
        --silent)      SILENT=true; shift ;;
        --uninstall)   UNINSTALL=true; shift ;;
        --dry-run)     DRY_RUN=true; shift ;;
        -y|--yes)      ASSUME_YES=true; shift ;;
        -h|--help)
            echo "Databricks MCP Server - Client Registration Installer"
            echo ""
            echo "Usage: bash databricks-mcp-server/mcp_install.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -p, --profile NAME   Databricks config profile to inject (default: DEFAULT)"
            echo "  -g, --global         Register globally (home dir) instead of per-project"
            echo "  --tools LIST         Comma-separated: claude,cursor,copilot,codex,gemini,antigravity,windsurf,opencode,kiro"
            echo "  --venv-dir DIR       Virtual environment location (default: <this dir>/.venv)"
            echo "  --skip-venv          Skip the setup.sh venv build (assume it already exists)"
            echo "  --silent             Silent mode (no output except errors)"
            echo "  --uninstall          Remove only the 'databricks' MCP entry from each client config"
            echo "  --dry-run            Print the plan (install or uninstall) and exit without changes"
            echo "  -y, --yes            With --uninstall: skip the confirmation prompt"
            echo "  -h, --help           Show this help"
            echo ""
            echo "Environment Variables (alternative to flags):"
            echo "  DEVKIT_PROFILE       Databricks config profile"
            echo "  DEVKIT_SCOPE         'project' or 'global'"
            echo "  DEVKIT_TOOLS         Comma-separated list of tools"
            echo "  DEVKIT_SILENT        Set to 'true' for silent mode"
            echo ""
            echo "The venv build is delegated to databricks-mcp-server/setup.sh."
            echo ""
            exit 0 ;;
        *) die "Unknown option: $1 (use -h for help)" ;;
    esac
done

VENV_PYTHON="$VENV_DIR/bin/python"

# ─── Interactive helpers ────────────────────────────────────────
# Reads from /dev/tty so prompts work even when piped via curl | bash

# True if we have an interactive tty we can read from.
is_interactive() {
    [ -t 0 ] || ( : < /dev/tty ) 2>/dev/null
}

# Simple text prompt with default value
prompt() {
    local prompt_text=$1
    local default_value=$2
    local result=""

    if [ "$SILENT" = true ]; then
        echo "$default_value"
        return
    fi

    if ( : < /dev/tty ) 2>/dev/null; then
        printf "  %b [%s]: " "$prompt_text" "$default_value" > /dev/tty
        read -r result < /dev/tty
    elif [ -t 0 ]; then
        printf "  %b [%s]: " "$prompt_text" "$default_value"
        read -r result
    else
        echo "$default_value"
        return
    fi

    if [ -z "$result" ]; then
        echo "$default_value"
    else
        echo "$result"
    fi
}

# Interactive checkbox selector using arrow keys + space/enter + "Confirm" button
# Outputs space-separated selected values to stdout
# Args: "Label|value|on_or_off|hint[|lock]" ...
#   A 5th "lock" field marks the item as always-on and non-toggleable.
checkbox_select() {
    local -a labels=()
    local -a values=()
    local -a states=()
    local -a hints=()
    local -a locked=()
    local count=0

    for item in "$@"; do
        IFS='|' read -r label value state hint lock <<< "$item"
        labels+=("$label")
        values+=("$value")
        hints+=("$hint")
        if [ "$lock" = "lock" ]; then
            locked+=(1)
            states+=(1)
        else
            locked+=(0)
            [ "$state" = "on" ] && states+=(1) || states+=(0)
        fi
        count=$((count + 1))
    done

    local cursor=0
    local total_rows=$((count + 2))

    _checkbox_draw() {
        local i
        for i in $(seq 0 $((count - 1))); do
            local check=" "
            [ "${states[$i]}" = "1" ] && check="\033[0;32m✓\033[0m"
            local arrow="  "
            [ "$i" = "$cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "${states[$i]}" = "1" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b[%b] %-16s %b%s\033[0m\n" "$arrow" "$check" "${labels[$i]}" "$hint_style" "${hints[$i]}" > /dev/tty
        done
        printf "\033[2K\n" > /dev/tty
        if [ "$cursor" = "$count" ]; then
            printf "\033[2K  \033[0;34m❯\033[0m \033[1;32m[ Confirm ]\033[0m\n" > /dev/tty
        else
            printf "\033[2K    \033[2m[ Confirm ]\033[0m\n" > /dev/tty
        fi
    }

    printf "\n  \033[2m↑/↓ navigate · space/enter select · enter on Confirm to finish\033[0m\n\n" > /dev/tty

    # Hide cursor and disable line wrap (DECAWM). With wrap off the terminal
    # clips overlong lines to one row, so the cursor-up redraw can't desync.
    printf "\033[?25l\033[?7l" > /dev/tty
    trap 'printf "\033[?25h\033[?7h" > /dev/tty 2>/dev/null' EXIT

    _checkbox_draw

    while true; do
        printf "\033[%dA" "$total_rows" > /dev/tty
        _checkbox_draw

        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null

        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$cursor" -gt 0 ] && cursor=$((cursor - 1)) ;;
                    B) [ "$cursor" -lt "$count" ] && cursor=$((cursor + 1)) ;;
                esac
            fi
        elif [ "$key" = " " ] || [ "$key" = "" ]; then
            if [ "$cursor" -lt "$count" ]; then
                if [ "${locked[$cursor]}" = "1" ]; then
                    :
                elif [ "${states[$cursor]}" = "1" ]; then
                    states[$cursor]=0
                else
                    states[$cursor]=1
                fi
            else
                printf "\033[%dA" "$total_rows" > /dev/tty
                _checkbox_draw
                break
            fi
        fi
    done

    printf "\033[?25h\033[?7h" > /dev/tty
    trap - EXIT

    local selected=""
    for i in $(seq 0 $((count - 1))); do
        if [ "${states[$i]}" = "1" ]; then
            selected="${selected:+$selected }${values[$i]}"
        fi
    done

    echo "$selected"
}

# Interactive single-select using arrow keys + enter + "Confirm" button
# Outputs the selected value to stdout
# Args: "Label|value|selected|hint" ...  (exactly one should have selected=on)
radio_select() {
    local -a labels=()
    local -a values=()
    local -a hints=()
    local count=0
    local selected=0

    for item in "$@"; do
        IFS='|' read -r label value state hint <<< "$item"
        labels+=("$label")
        values+=("$value")
        hints+=("$hint")
        [ "$state" = "on" ] && selected=$count
        count=$((count + 1))
    done

    local cursor=0
    local total_rows=$((count + 2))

    _radio_draw() {
        local i
        for i in $(seq 0 $((count - 1))); do
            local dot="○"
            local dot_color="\033[2m"
            [ "$i" = "$selected" ] && dot="●" && dot_color="\033[0;32m"
            local arrow="  "
            [ "$i" = "$cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "$i" = "$selected" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b%b%b %-20s %b%s\033[0m\n" "$arrow" "$dot_color" "$dot" "${labels[$i]}" "$hint_style" "${hints[$i]}" > /dev/tty
        done
        printf "\033[2K\n" > /dev/tty
        if [ "$cursor" = "$count" ]; then
            printf "\033[2K  \033[0;34m❯\033[0m \033[1;32m[ Confirm ]\033[0m\n" > /dev/tty
        else
            printf "\033[2K    \033[2m[ Confirm ]\033[0m\n" > /dev/tty
        fi
    }

    printf "\n  \033[2m↑/↓ navigate · enter confirm · space preview\033[0m\n\n" > /dev/tty
    printf "\033[?25l\033[?7l" > /dev/tty
    trap 'printf "\033[?25h\033[?7h" > /dev/tty 2>/dev/null' EXIT

    _radio_draw

    while true; do
        printf "\033[%dA" "$total_rows" > /dev/tty
        _radio_draw

        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null

        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$cursor" -gt 0 ] && cursor=$((cursor - 1)) ;;
                    B) [ "$cursor" -lt "$count" ] && cursor=$((cursor + 1)) ;;
                esac
            fi
        elif [ "$key" = "" ]; then
            if [ "$cursor" -lt "$count" ]; then
                selected=$cursor
            fi
            printf "\033[%dA" "$total_rows" > /dev/tty
            _radio_draw
            break
        elif [ "$key" = " " ]; then
            if [ "$cursor" -lt "$count" ]; then
                selected=$cursor
            fi
        fi
    done

    printf "\033[?25h\033[?7h" > /dev/tty
    trap - EXIT

    echo "${values[$selected]}"
}

# ─── Tool detection & selection ─────────────────────────────────
detect_tools() {
    # If provided via --tools flag or TOOLS env var, skip detection and prompts
    if [ -n "$USER_TOOLS" ]; then
        TOOLS=$(echo "$USER_TOOLS" | tr ',' ' ')
        return
    elif [ -n "$TOOLS" ]; then
        TOOLS=$(echo "$TOOLS" | tr ',' ' ')
        return
    fi

    # Auto-detect what's installed
    local has_claude=false
    local has_cursor=false
    local has_codex=false
    local has_copilot=false
    local has_gemini=false
    local has_antigravity=false
    local has_windsurf=false
    local has_opencode=false
    local has_kiro=false

    command -v claude >/dev/null 2>&1 && has_claude=true
    { [ -d "/Applications/Cursor.app" ] || command -v cursor >/dev/null 2>&1; } && has_cursor=true
    command -v codex >/dev/null 2>&1 && has_codex=true
    { [ -d "/Applications/Visual Studio Code.app" ] || command -v code >/dev/null 2>&1; } && has_copilot=true
    { command -v gemini >/dev/null 2>&1 || [ -f "$HOME/.gemini/local/gemini" ]; } && has_gemini=true
    { [ -d "/Applications/Antigravity.app" ] || command -v antigravity >/dev/null 2>&1; } && has_antigravity=true
    { [ -d "/Applications/Windsurf.app" ] || command -v windsurf >/dev/null 2>&1; } && has_windsurf=true
    command -v opencode >/dev/null 2>&1 && has_opencode=true
    { [ -d "/Applications/Kiro.app" ] || command -v kiro >/dev/null 2>&1; } && has_kiro=true

    local claude_state="off" cursor_state="off" codex_state="off" copilot_state="off" gemini_state="off" antigravity_state="off" windsurf_state="off" opencode_state="off" kiro_state="off"
    local claude_hint="not found" cursor_hint="not found" codex_hint="not found" copilot_hint="not found" gemini_hint="not found" antigravity_hint="not found" windsurf_hint="not found" opencode_hint="not found" kiro_hint="not found"
    [ "$has_claude" = true ]        && claude_state="on"        && claude_hint="detected"
    [ "$has_cursor" = true ]        && cursor_state="on"        && cursor_hint="detected"
    [ "$has_codex" = true ]         && codex_state="on"         && codex_hint="detected"
    [ "$has_copilot" = true ]       && copilot_state="on"       && copilot_hint="detected"
    [ "$has_gemini" = true ]        && gemini_state="on"        && gemini_hint="detected"
    [ "$has_antigravity" = true ]   && antigravity_state="on"   && antigravity_hint="detected"
    [ "$has_windsurf" = true ]      && windsurf_state="on"      && windsurf_hint="detected"
    [ "$has_opencode" = true ]      && opencode_state="on"      && opencode_hint="detected"
    [ "$has_kiro" = true ]          && kiro_state="on"          && kiro_hint="detected"

    # If nothing detected, pre-select claude as default
    if [ "$has_claude" = false ] && [ "$has_cursor" = false ] && [ "$has_codex" = false ] && [ "$has_copilot" = false ] && [ "$has_gemini" = false ] && [ "$has_antigravity" = false ] && [ "$has_windsurf" = false ] && [ "$has_opencode" = false ] && [ "$has_kiro" = false ]; then
        claude_state="on"
        claude_hint="default"
    fi

    if [ "$SILENT" = false ] && is_interactive; then
        echo ""
        echo -e "  ${B}Select tools to register the databricks MCP server for:${N}"

        TOOLS=$(checkbox_select \
            "Claude Code|claude|${claude_state}|${claude_hint}" \
            "Cursor|cursor|${cursor_state}|${cursor_hint}" \
            "GitHub Copilot|copilot|${copilot_state}|${copilot_hint}" \
            "OpenAI Codex|codex|${codex_state}|${codex_hint}" \
            "Gemini CLI|gemini|${gemini_state}|${gemini_hint}" \
            "Antigravity|antigravity|${antigravity_state}|${antigravity_hint}" \
            "Windsurf|windsurf|${windsurf_state}|${windsurf_hint}" \
            "OpenCode|opencode|${opencode_state}|${opencode_hint}" \
            "Kiro|kiro|${kiro_state}|${kiro_hint}" \
        )
    else
        local tools=""
        [ "$has_claude" = true ]        && tools="claude"
        [ "$has_cursor" = true ]        && tools="${tools:+$tools }cursor"
        [ "$has_copilot" = true ]       && tools="${tools:+$tools }copilot"
        [ "$has_codex" = true ]         && tools="${tools:+$tools }codex"
        [ "$has_gemini" = true ]        && tools="${tools:+$tools }gemini"
        [ "$has_antigravity" = true ]   && tools="${tools:+$tools }antigravity"
        [ "$has_windsurf" = true ]      && tools="${tools:+$tools }windsurf"
        [ "$has_opencode" = true ]      && tools="${tools:+$tools }opencode"
        [ "$has_kiro" = true ]          && tools="${tools:+$tools }kiro"
        [ -z "$tools" ] && tools="claude"
        TOOLS="$tools"
    fi

    if [ -z "$TOOLS" ]; then
        warn "No tools selected, defaulting to Claude Code"
        TOOLS="claude"
    fi
}

# ─── Databricks profile selection ─────────────────────────────
prompt_profile() {
    # If provided via --profile flag (non-default), skip prompt
    if [ "$PROFILE" != "DEFAULT" ]; then
        return
    fi

    if [ "$SILENT" = true ] || ! is_interactive; then
        return
    fi

    local cfg_file="$HOME/.databrickscfg"
    local -a profiles=()

    if [ -f "$cfg_file" ]; then
        while IFS= read -r line; do
            if [[ "$line" =~ ^\[([a-zA-Z0-9_-]+)\]$ ]]; then
                profiles+=("${BASH_REMATCH[1]}")
            fi
        done < "$cfg_file"
    fi

    echo ""
    echo -e "  ${B}Select Databricks profile${N}"

    if [ ${#profiles[@]} -gt 0 ] && is_interactive; then
        local -a items=()
        for p in "${profiles[@]}"; do
            local state="off"
            local hint=""
            [ "$p" = "DEFAULT" ] && state="on" && hint="default"
            items+=("${p}|${p}|${state}|${hint}")
        done

        items+=("Custom profile name...|__CUSTOM__|off|Enter a custom profile name")

        local has_default=false
        for p in "${profiles[@]}"; do
            [ "$p" = "DEFAULT" ] && has_default=true
        done
        if [ "$has_default" = false ]; then
            items[0]=$(echo "${items[0]}" | sed 's/|off|/|on|/')
        fi

        local selected_profile
        selected_profile=$(radio_select "${items[@]}")

        if [ "$selected_profile" = "__CUSTOM__" ]; then
            echo ""
            local custom_name
            custom_name=$(prompt "Enter profile name" "DEFAULT")
            PROFILE="$custom_name"
        else
            PROFILE="$selected_profile"
        fi
    else
        echo -e "  ${D}No ~/.databrickscfg found. You can authenticate after install.${N}"
        echo ""
        local selected
        selected=$(prompt "Profile name" "DEFAULT")
        PROFILE="$selected"
    fi
}

# ─── Scope selection ────────────────────────────────────────────
prompt_scope() {
    if [ "$SILENT" = true ] || ! is_interactive; then
        return
    fi

    local title="${SCOPE_PROMPT_TITLE:-Select registration scope}"

    echo ""
    echo -e "  ${B}${title}${N}"

    SCOPE=$(radio_select \
        "Project|project|on|Current directory (.mcp.json, etc.)" \
        "Global|global|off|Home directory (~/.claude.json, etc.)" \
    )
}

# ─── MCP config writers ────────────────────────────────────────
# Write/merge an MCP server entry into a JSON config.
#   $1 path        target config file
#   $2 root_key    top-level key: "mcpServers" (Claude/Cursor/Gemini/Windsurf/Kiro)
#                  or "servers" (Copilot)
#   $3 defer       "true" to include Claude's defer_loading hint, else "false"
# Merges into any existing config with Python, preserving other servers, and
# backs up the original to <file>.bak first.
write_mcp_json_config() {
    local path=$1 root_key=$2 defer=$3
    mkdir -p "$(dirname "$path")"

    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}Backed up ${path##*/} → ${path##*/}.bak${N}"
    fi

    local defer_py="" defer_json=""
    if [ "$defer" = "true" ]; then
        defer_py="'defer_loading': True, "
        defer_json='
      "defer_loading": true,'
    fi

    if [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('$root_key', {})['databricks'] = {'command': '$VENV_PYTHON', 'args': ['$MCP_ENTRY'], ${defer_py}'env': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'}}
with open('$path', 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    # Fallback: only safe for new files — refuse to overwrite existing files
    # that may contain other settings (e.g. ~/.claude.json)
    if [ -f "$path" ]; then
        warn "Cannot merge MCP config into $path without Python. Add manually."
        return
    fi

    cat > "$path" << EOF
{
  "$root_key": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_ENTRY"],${defer_json}
      "env": {"DATABRICKS_CONFIG_PROFILE": "$PROFILE"}
    }
  }
}
EOF
}

# Write/merge the Codex TOML config. Unlike the historical unified installer,
# this includes the profile env block ([mcp_servers.databricks.env]) so Codex
# picks up the same DATABRICKS_CONFIG_PROFILE as every other client.
write_mcp_toml() {
    local path=$1
    mkdir -p "$(dirname "$path")"
    # Anchor to the table header so a match in a comment/value can't be mistaken
    # for an existing registration (matches the removal awk's anchor).
    grep -qE '^\[mcp_servers\.databricks' "$path" 2>/dev/null && return
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}Backed up ${path##*/} → ${path##*/}.bak${N}"
    fi
    cat >> "$path" << EOF

[mcp_servers.databricks]
command = "$VENV_PYTHON"
args = ["$MCP_ENTRY"]

[mcp_servers.databricks.env]
DATABRICKS_CONFIG_PROFILE = "$PROFILE"
EOF
}

# Write/merge the OpenCode config (root key 'mcp', type 'local', command-as-array).
write_opencode_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"

    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}Backed up ${path##*/} → ${path##*/}.bak${N}"
    fi

    if [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('\$schema', 'https://opencode.ai/config.json')
cfg.setdefault('mcp', {})['databricks'] = {
    'type': 'local',
    'command': ['$VENV_PYTHON', '$MCP_ENTRY'],
    'environment': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'},
    'enabled': True
}
with open('$path', 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    if [ -f "$path" ]; then
        warn "Cannot merge MCP config into $path without Python. Add manually."
        return
    fi

    cat > "$path" << EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "mcp": {
    "databricks": {
      "type": "local",
      "command": ["$VENV_PYTHON", "$MCP_ENTRY"],
      "environment": {"DATABRICKS_CONFIG_PROFILE": "$PROFILE"},
      "enabled": true
    }
  }
}
EOF
}

write_mcp_configs() {
    step "Registering the databricks MCP server"

    local base_dir=$1
    for tool in $TOOLS; do
        case $tool in
            claude)
                [ "$SCOPE" = "global" ] && write_mcp_json_config "$HOME/.claude.json" mcpServers true || write_mcp_json_config "$base_dir/.mcp.json" mcpServers true
                ok "Claude MCP config"
                ;;
            cursor)
                if [ "$SCOPE" = "global" ]; then
                    warn "Cursor global: manual MCP configuration required"
                    msg "  1. Open ${B}Cursor → Settings → Cursor Settings → Tools & MCP${N}"
                    msg "  2. Click ${B}New MCP Server${N}"
                    msg "  3. Add the following JSON config:"
                    msg "     {"
                    msg "       \"mcpServers\": {"
                    msg "         \"databricks\": {"
                    msg "           \"command\": \"$VENV_PYTHON\","
                    msg "           \"args\": [\"$MCP_ENTRY\"],"
                    msg "           \"env\": {\"DATABRICKS_CONFIG_PROFILE\": \"$PROFILE\"}"
                    msg "         }"
                    msg "       }"
                    msg "     }"
                else
                    write_mcp_json_config "$base_dir/.cursor/mcp.json" mcpServers true
                    ok "Cursor MCP config"
                fi
                warn "Cursor: MCP servers are disabled by default."
                msg "  Enable in: ${B}Cursor → Settings → Cursor Settings → Tools & MCP → Toggle 'databricks'${N}"
                ;;
            copilot)
                if [ "$SCOPE" = "global" ]; then
                    warn "Copilot global: configure MCP in VS Code settings (Ctrl+Shift+P → 'MCP: Open User Configuration')"
                    msg "  Command: $VENV_PYTHON | Args: $MCP_ENTRY"
                else
                    write_mcp_json_config "$base_dir/.vscode/mcp.json" servers false
                    ok "Copilot MCP config (.vscode/mcp.json)"
                fi
                warn "Copilot: MCP servers must be enabled manually."
                msg "  In Copilot Chat, click ${B}Configure Tools${N} (tool icon, bottom-right) and enable ${B}databricks${N}"
                ;;
            codex)
                [ "$SCOPE" = "global" ] && write_mcp_toml "$HOME/.codex/config.toml" || write_mcp_toml "$base_dir/.codex/config.toml"
                ok "Codex MCP config"
                ;;
            gemini)
                if [ "$SCOPE" = "global" ]; then
                    write_mcp_json_config "$HOME/.gemini/settings.json" mcpServers false
                else
                    write_mcp_json_config "$base_dir/.gemini/settings.json" mcpServers false
                fi
                ok "Gemini CLI MCP config"
                ;;
            antigravity)
                if [ "$SCOPE" = "project" ]; then
                    warn "Antigravity only supports global MCP configuration."
                    msg "  Config written to ${B}~/.gemini/antigravity/mcp_config.json${N}"
                fi
                write_mcp_json_config "$HOME/.gemini/antigravity/mcp_config.json" mcpServers false
                ok "Antigravity MCP config"
                ;;
            windsurf)
                if [ "$SCOPE" = "project" ]; then
                    warn "Windsurf only supports global MCP configuration."
                    msg "  Config written to ${B}~/.codeium/windsurf/mcp_config.json${N}"
                fi
                write_mcp_json_config "$HOME/.codeium/windsurf/mcp_config.json" mcpServers true
                ok "Windsurf MCP config"
                ;;
            opencode)
                if [ "$SCOPE" = "global" ]; then
                    write_opencode_json "$HOME/.config/opencode/opencode.json"
                else
                    write_opencode_json "$base_dir/opencode.json"
                fi
                ok "OpenCode MCP config"
                ;;
            kiro)
                if [ "$SCOPE" = "global" ]; then
                    mkdir -p "$HOME/.kiro/settings"
                    write_mcp_json_config "$HOME/.kiro/settings/mcp.json" mcpServers true
                else
                    mkdir -p "$base_dir/.kiro/settings"
                    write_mcp_json_config "$base_dir/.kiro/settings/mcp.json" mcpServers true
                fi
                ok "Kiro MCP config"
                ;;
            *)
                warn "Unknown tool '$tool' — skipping"
                ;;
        esac
    done
}

# ─── Uninstall (deregistration) ────────────────────────────────
# Remove the 'databricks' MCP server entry from a JSON config, preserving all
# other servers and settings. $2 is the top-level key ('mcpServers' or 'servers').
uninstall_remove_json_key() {
    local path=$1 top=$2
    [ -f "$path" ] || return 1
    grep -qF '"databricks"' "$path" 2>/dev/null || return 1
    if [ "$DRY_RUN" = true ]; then echo "$path"; return 0; fi
    local py=""
    command -v python3 >/dev/null 2>&1 && py=python3
    [ -z "$py" ] && [ -f "$VENV_PYTHON" ] && py="$VENV_PYTHON"
    if [ -z "$py" ]; then warn "No Python to edit $path — remove the 'databricks' entry manually."; return 1; fi
    cp "$path" "${path}.bak"
    if "$py" - "$path" "$top" <<'PYEOF'
import json, sys
path, top = sys.argv[1], sys.argv[2]
try:
    with open(path) as f: cfg = json.load(f)
except Exception: sys.exit(2)
if not (isinstance(cfg.get(top), dict) and 'databricks' in cfg[top]):
    sys.exit(1)  # nothing to remove
cfg[top].pop('databricks', None)
if not cfg[top]: cfg.pop(top, None)
with open(path, 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
sys.exit(0)
PYEOF
    then
        return 0
    else
        rm -f "${path}.bak"   # nothing changed — don't leave a spurious backup
        return 1
    fi
}

# Remove the [mcp_servers.databricks] block (and its dotted subtables, e.g.
# [mcp_servers.databricks.env]) from a Codex TOML config.
uninstall_remove_toml_block() {
    local path=$1
    [ -f "$path" ] || return 1
    grep -qE '^\[mcp_servers\.databricks' "$path" 2>/dev/null || return 1
    if [ "$DRY_RUN" = true ]; then echo "$path"; return 0; fi
    cp "$path" "${path}.bak"
    awk '
        /^\[mcp_servers\.databricks(\.|\])/ { skip=1; next }
        /^\[/ { skip=0 }
        !skip { print }
    ' "${path}.bak" > "$path"
    return 0
}

# Same top-level key check used by removal, so the plan matches what removal does.
mcp_json_has_databricks() {
    local path=$1 top=$2 py=""
    [ -f "$path" ] || return 1
    command -v python3 >/dev/null 2>&1 && py=python3
    [ -z "$py" ] && [ -f "$VENV_PYTHON" ] && py="$VENV_PYTHON"
    [ -z "$py" ] && { grep -qF '"databricks"' "$path" 2>/dev/null; return; }
    "$py" - "$path" "$top" <<'PYEOF'
import json, sys
try:
    cfg = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
top = cfg.get(sys.argv[2])
sys.exit(0 if (isinstance(top, dict) and "databricks" in top) else 1)
PYEOF
}

# Build the list of per-scope client config targets ("path|kind").
mcp_targets_for_scope() {
    local base_dir=$1
    if [ "$SCOPE" = "global" ]; then
        cat <<EOF
$HOME/.claude.json|json:mcpServers
$HOME/.codex/config.toml|toml
$HOME/.gemini/settings.json|json:mcpServers
$HOME/.gemini/antigravity/mcp_config.json|json:mcpServers
$HOME/.codeium/windsurf/mcp_config.json|json:mcpServers
$HOME/.config/opencode/opencode.json|json:mcp
$HOME/.kiro/settings/mcp.json|json:mcpServers
EOF
    else
        cat <<EOF
$base_dir/.mcp.json|json:mcpServers
$base_dir/.cursor/mcp.json|json:mcpServers
$base_dir/.vscode/mcp.json|json:servers
$base_dir/.codex/config.toml|toml
$base_dir/.gemini/settings.json|json:mcpServers
$base_dir/opencode.json|json:mcp
$base_dir/.kiro/settings/mcp.json|json:mcpServers
EOF
    fi
}

run_uninstall() {
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "${B}Databricks MCP Server — Deregister${N}"
        echo "────────────────────────────────"
    fi

    # Mirror install: if scope wasn't set explicitly, ask (interactive, non --yes).
    if [ "$SCOPE_EXPLICIT" = false ] && [ "$ASSUME_YES" != true ]; then
        SCOPE_PROMPT_TITLE="Select deregistration scope" prompt_scope
    fi
    local base_dir
    [ "$SCOPE" = "global" ] && base_dir="$HOME" || base_dir="$(pwd)"

    # Build the plan (only targets that actually contain our 'databricks' entry)
    local -a plan_mcp=()
    local entry path kind
    while IFS= read -r entry; do
        [ -n "$entry" ] || continue
        path="${entry%%|*}"; kind="${entry#*|}"
        case "$kind" in
            json:*) mcp_json_has_databricks "$path" "${kind#json:}" && plan_mcp+=("$entry") ;;
            toml)   [ -f "$path" ] && grep -qE '^\[mcp_servers\.databricks' "$path" 2>/dev/null && plan_mcp+=("$entry") ;;
        esac
    done < <(mcp_targets_for_scope "$base_dir")

    if [ ${#plan_mcp[@]} -eq 0 ]; then
        ok "Nothing to deregister for ${B}$SCOPE${N} scope at ${D}${base_dir}${N} — no 'databricks' MCP entry found."
        [ "$SCOPE" = "project" ] && msg "${D}Tip: pass --global to remove a global registration.${N}"
        exit 0
    fi

    step "Deregister plan (${SCOPE} scope)"
    echo -e "  ${B}MCP config — remove 'databricks' entry (${#plan_mcp[@]}):${N}"
    for entry in "${plan_mcp[@]}"; do echo "    ${entry%%|*}" | sed "s#$HOME#~#"; done
    echo ""
    msg "${D}Config files are backed up to <file>.bak before editing.${N}"

    if [ "$DRY_RUN" = true ]; then
        ok "Dry run — nothing was changed. Re-run without --dry-run to apply."
        exit 0
    fi

    if [ "$ASSUME_YES" != true ]; then
        local reply=""
        if { exec 3</dev/tty; } 2>/dev/null; then
            printf "  ${Y}Remove these %d item(s)?${N} [y/N] " "${#plan_mcp[@]}"
            read -r reply <&3 || reply=""
            exec 3<&-
        else
            die "No terminal to confirm on. Re-run with -y/--yes to proceed non-interactively (or --dry-run to preview)."
        fi
        case "$reply" in [yY]|[yY][eE][sS]) ;; *) die "Aborted — nothing removed." ;; esac
    fi

    step "Removing"
    for entry in "${plan_mcp[@]}"; do
        path="${entry%%|*}"; kind="${entry#*|}"
        case "$kind" in
            json:*) uninstall_remove_json_key "$path" "${kind#json:}" && msg "cleaned ${path/#$HOME/~}" ;;
            toml)   uninstall_remove_toml_block "$path" && msg "cleaned ${path/#$HOME/~}" ;;
        esac
    done

    echo ""
    ok "databricks MCP server deregistered (${SCOPE} scope)."
    msg "${D}Per-editor .bak backups were left untouched.${N}"
    exit 0
}

# ─── Build the venv by delegating to setup.sh (single source of truth) ──
setup_mcp() {
    step "Setting up MCP server"

    local setup_script="$SCRIPT_DIR/setup.sh"
    [ -f "$setup_script" ] || die "MCP setup script not found at $setup_script"

    msg "Building MCP server environment (databricks-mcp-server/setup.sh)..."
    local quiet_flag=""
    [ "$SILENT" = true ] && quiet_flag="--quiet"
    bash "$setup_script" --venv-dir "$VENV_DIR" $quiet_flag || die "MCP server setup failed"
    ok "MCP server ready"
}

# ─── Summary / post-hints ──────────────────────────────────────
summary() {
    [ "$SILENT" = true ] && return
    echo ""
    echo -e "${G}${B}MCP registration complete!${N}"
    echo "────────────────────────────────"
    msg "Server:  $MCP_ENTRY"
    msg "Python:  $VENV_PYTHON"
    msg "Profile: $PROFILE"
    msg "Scope:   $SCOPE"
    msg "Tools:   $(echo "$TOOLS" | tr ' ' ', ')"
    echo ""
    msg "${B}Next steps:${N}"
    local step=1
    if echo "$TOOLS" | grep -q cursor; then
        msg "${step}. Enable MCP in Cursor: ${B}Cursor → Settings → Cursor Settings → Tools & MCP → Toggle 'databricks'${N}"
        step=$((step + 1))
    fi
    if echo "$TOOLS" | grep -q copilot; then
        msg "${step}. In Copilot Chat, click ${B}Configure Tools${N} (tool icon, bottom-right) and enable ${B}databricks${N}"
        step=$((step + 1))
    fi
    if echo "$TOOLS" | grep -q windsurf; then
        msg "${step}. Restart Windsurf to pick up the ${B}databricks${N} MCP server (Windsurf → Settings → Windsurf Settings → MCP)"
        step=$((step + 1))
    fi
    if echo "$TOOLS" | grep -q antigravity; then
        msg "${step}. Open your project in Antigravity to use the ${B}databricks${N} MCP tools"
        step=$((step + 1))
    fi
    msg "${step}. Open your project in your tool of choice and start prompting"
    echo ""
}

# ─── Main ──────────────────────────────────────────────────────
main() {
    if [ "$UNINSTALL" = true ]; then
        run_uninstall
    fi

    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "${B}Databricks MCP Server — Client Registration${N}"
        echo "────────────────────────────────"
    fi

    # uv is required by setup.sh; check early with a helpful message.
    if [ "$SKIP_VENV" = false ] && ! command -v uv >/dev/null 2>&1; then
        die "uv is required but not found on your PATH.
   Install it with: ${B}curl -LsSf https://astral.sh/uv/install.sh | sh${N}
   Then re-run this installer."
    fi

    # ── Tool selection ──
    step "Selecting tools"
    detect_tools
    ok "Selected: $(echo "$TOOLS" | tr ' ' ', ')"

    # ── Profile selection ──
    step "Databricks profile"
    prompt_profile
    ok "Profile: $PROFILE"

    # ── Scope selection ──
    if [ "$SCOPE_EXPLICIT" = false ]; then
        prompt_scope
        ok "Scope: $SCOPE"
    fi

    # ── Confirm ──
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "  ${B}Summary${N}"
        echo -e "  ────────────────────────────────────"
        echo -e "  Tools:    ${G}$(echo "$TOOLS" | tr ' ' ', ')${N}"
        echo -e "  Profile:  ${G}${PROFILE}${N}"
        echo -e "  Scope:    ${G}${SCOPE}${N}"
        echo -e "  Venv:     ${G}${VENV_DIR}${N}"
        echo ""
    fi

    if [ "$DRY_RUN" = true ]; then
        ok "Dry run — nothing was changed. Re-run without --dry-run to apply."
        exit 0
    fi

    if [ "$SILENT" = false ] && is_interactive; then
        local confirm
        confirm=$(prompt "Proceed with MCP registration? ${D}(y/n)${N}" "y")
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ] && [ "$confirm" != "yes" ]; then
            echo ""
            msg "Registration cancelled."
            exit 0
        fi
    fi

    # ── Build the venv (delegated to setup.sh) ──
    if [ "$SKIP_VENV" = false ]; then
        setup_mcp
    fi
    [ -f "$VENV_PYTHON" ] || warn "venv python not found at $VENV_PYTHON — configs will still be written, but build the venv with setup.sh before use."

    # ── Write client configs ──
    local base_dir
    [ "$SCOPE" = "global" ] && base_dir="$HOME" || base_dir="$(pwd)"
    write_mcp_configs "$base_dir"

    summary
}

main "$@"
