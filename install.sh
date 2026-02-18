#!/bin/bash
#
# Databricks AI Dev Kit - Unified Installer
#
# Installs skills, MCP server, and configuration for Claude Code, Cursor, OpenAI Codex, and GitHub Copilot.
#
# Usage: bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) [OPTIONS]
#
# Examples:
#   # Basic installation (project scoped, prompts for inputs, uses latest release)
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh)
#
#   # Global installation with force reinstall
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --global --force
#
#   # Specify profile and force reinstall
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --profile DEFAULT --force
#
#   # Install for specific tools only
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --tools cursor,codex,copilot
#
#   # Skills only (skip MCP server)
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --skills-only
#
# Alternative: Use environment variables
#   DEVKIT_TOOLS=cursor curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh | bash
#   DEVKIT_FORCE=true DEVKIT_PROFILE=DEFAULT curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh | bash
#

set -e

# Defaults (can be overridden by environment variables or command-line arguments)
PROFILE="${DEVKIT_PROFILE:-DEFAULT}"
SCOPE="${DEVKIT_SCOPE:-project}"
SCOPE_EXPLICIT=false  # Track if --global was explicitly passed
FORCE="${DEVKIT_FORCE:-false}"
IS_UPDATE=false
SILENT="${DEVKIT_SILENT:-false}"
TOOLS="${DEVKIT_TOOLS:-}"
USER_TOOLS=""
USER_MCP_PATH="${DEVKIT_MCP_PATH:-}"

# Convert string booleans from env vars to actual booleans
[ "$FORCE" = "true" ] || [ "$FORCE" = "1" ] && FORCE=true || FORCE=false
[ "$SILENT" = "true" ] || [ "$SILENT" = "1" ] && SILENT=true || SILENT=false

# Check if scope was explicitly set via env var
[ -n "${DEVKIT_SCOPE:-}" ] && SCOPE_EXPLICIT=true

OWNER="databricks-solutions"
REPO="ai-dev-kit"

if [ -n "${DEVKIT_BRANCH:-}" ]; then
  BRANCH="$DEVKIT_BRANCH"
else
  BRANCH="$(
    curl -s "https://api.github.com/repos/${OWNER}/${REPO}/releases/latest" \
    | grep '"tag_name"' \
    | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/'
  )"
  # Fallback to main if we couldn't fetch the latest release
  [ -z "$BRANCH" ] && BRANCH="main"
fi

# Installation mode defaults
INSTALL_MCP=true
INSTALL_SKILLS=true

# Minimum required versions
MIN_CLI_VERSION="0.278.0"
MIN_SDK_VERSION="0.85.0"

# Colors
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' BL='\033[0;34m' B='\033[1m' D='\033[2m' N='\033[0m'

# Databricks skills (bundled in repo)
SKILLS="databricks-agent-bricks databricks-aibi-dashboards databricks-app-apx databricks-app-python databricks-asset-bundles databricks-config databricks-dbsql databricks-docs databricks-genie databricks-jobs databricks-metric-views databricks-model-serving databricks-python-sdk databricks-unity-catalog databricks-vector-search databricks-zerobus-ingest lakebase-autoscale lakebase-provisioned mlflow-evaluation spark-declarative-pipelines spark-python-data-source spark-structured-streaming synthetic-data-generation unstructured-pdf-generation"

# MLflow skills (fetched from mlflow/skills repo)
MLFLOW_SKILLS="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"
MLFLOW_RAW_URL="https://raw.githubusercontent.com/mlflow/skills/main"

# Output helpers
msg()  { [ "$SILENT" = false ] && echo -e "  $*"; }
ok()   { [ "$SILENT" = false ] && echo -e "  ${G}✓${N} $*"; }
warn() { [ "$SILENT" = false ] && echo -e "  ${Y}!${N} $*"; }
die()  { echo -e "  ${R}✗${N} $*" >&2; exit 1; }  # Always show errors
step() { [ "$SILENT" = false ] && echo -e "\n${B}$*${N}"; }

# Parse arguments
while [ $# -gt 0 ]; do
    case $1 in
        -p|--profile)     PROFILE="$2"; shift 2 ;;
        -g|--global)      SCOPE="global"; SCOPE_EXPLICIT=true; shift ;;
        -b|--branch)      BRANCH="$2"; shift 2 ;;
        --skills-only)    INSTALL_MCP=false; shift ;;
        --mcp-only)       INSTALL_SKILLS=false; shift ;;
        --mcp-path)       USER_MCP_PATH="$2"; shift 2 ;;
        --silent)         SILENT=true; shift ;;
        --tools)          USER_TOOLS="$2"; shift 2 ;;
        -f|--force)       FORCE=true; shift ;;
        -h|--help)        
            echo "Databricks AI Dev Kit Installer"
            echo ""
            echo "Usage: bash <(curl -sL .../install.sh) [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -p, --profile NAME    Databricks profile (default: DEFAULT)"
            echo "  -b, --branch NAME     Git branch/tag to install (default: latest release)"
            echo "  -g, --global          Install globally for all projects"
            echo "  --skills-only         Skip MCP server setup"
            echo "  --mcp-only            Skip skills installation"
            echo "  --mcp-path PATH       Path to MCP server installation (default: ~/.ai-dev-kit)"
            echo "  --silent              Silent mode (no output except errors)"
            echo "  --tools LIST          Comma-separated: claude,cursor,copilot,codex"
            echo "  -f, --force           Force reinstall"
            echo "  -h, --help            Show this help"
            echo ""
            echo "Environment Variables (alternative to flags):"
            echo "  DEVKIT_PROFILE        Databricks config profile"
            echo "  DEVKIT_BRANCH         Git branch/tag to install (default: latest release)"
            echo "  DEVKIT_SCOPE          'project' or 'global'"
            echo "  DEVKIT_TOOLS          Comma-separated list of tools"
            echo "  DEVKIT_FORCE          Set to 'true' to force reinstall"
            echo "  DEVKIT_MCP_PATH       Path to MCP server installation"
            echo "  DEVKIT_SILENT         Set to 'true' for silent mode"
            echo "  AIDEVKIT_HOME         Installation directory (default: ~/.ai-dev-kit)"
            echo ""
            echo "Examples:"
            echo "  # Using environment variables"
            echo "  DEVKIT_TOOLS=cursor curl -sL .../install.sh | bash"
            echo ""
            exit 0 ;;
        *) die "Unknown option: $1 (use -h for help)" ;;
    esac
done

# Set configuration URLs after parsing branch argument
REPO_URL="https://github.com/databricks-solutions/ai-dev-kit.git"
RAW_URL="https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/${BRANCH}"
INSTALL_DIR="${AIDEVKIT_HOME:-$HOME/.ai-dev-kit}"
REPO_DIR="$INSTALL_DIR/repo"
VENV_DIR="$INSTALL_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
MCP_ENTRY="$REPO_DIR/databricks-mcp-server/run_server.py"

# ─── Interactive helpers ────────────────────────────────────────
# Reads from /dev/tty so prompts work even when piped via curl | bash

# Simple text prompt with default value
prompt() {
    local prompt_text=$1
    local default_value=$2
    local result=""

    if [ "$SILENT" = true ]; then
        echo "$default_value"
        return
    fi

    if [ -e /dev/tty ]; then
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

# Interactive checkbox selector using arrow keys + space/enter + "Done" button
# Outputs space-separated selected values to stdout
# Args: "Label|value|on_or_off|hint" ...
checkbox_select() {
    # Parse items
    local -a labels=()
    local -a values=()
    local -a states=()
    local -a hints=()
    local count=0

    for item in "$@"; do
        IFS='|' read -r label value state hint <<< "$item"
        labels+=("$label")
        values+=("$value")
        hints+=("$hint")
        if [ "$state" = "on" ]; then
            states+=(1)
        else
            states+=(0)
        fi
        count=$((count + 1))
    done

    local cursor=0
    local total_rows=$((count + 2))  # items + blank line + Done button

    # Draw the checkbox list + Done button
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
        # Blank separator line
        printf "\033[2K\n" > /dev/tty
        # Done button
        if [ "$cursor" = "$count" ]; then
            printf "\033[2K  \033[0;34m❯\033[0m \033[1;32m[ Confirm ]\033[0m\n" > /dev/tty
        else
            printf "\033[2K    \033[2m[ Confirm ]\033[0m\n" > /dev/tty
        fi
    }

    # Print instructions
    printf "\n  \033[2m↑/↓ navigate · space/enter select · enter on Confirm to finish\033[0m\n\n" > /dev/tty

    # Hide cursor
    printf "\033[?25l" > /dev/tty

    # Restore cursor on exit (Ctrl+C safety)
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT

    # Initial draw
    _checkbox_draw

    # Input loop
    while true; do
        # Move back to top of drawn area and redraw
        printf "\033[%dA" "$total_rows" > /dev/tty
        _checkbox_draw

        # Read input
        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null

        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$cursor" -gt 0 ] && cursor=$((cursor - 1)) ;;  # Up
                    B) [ "$cursor" -lt "$count" ] && cursor=$((cursor + 1)) ;;  # Down (can go to Done)
                esac
            fi
        elif [ "$key" = " " ] || [ "$key" = "" ]; then
            # Space or Enter
            if [ "$cursor" -lt "$count" ]; then
                # On a checkbox item — toggle it
                if [ "${states[$cursor]}" = "1" ]; then
                    states[$cursor]=0
                else
                    states[$cursor]=1
                fi
            else
                # On the Confirm button — done
                printf "\033[%dA" "$total_rows" > /dev/tty
                _checkbox_draw
                break
            fi
        fi
    done

    # Show cursor again
    printf "\033[?25h" > /dev/tty
    trap - EXIT

    # Build result
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
    # Parse items
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
    local total_rows=$((count + 2))  # items + blank line + Confirm button

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
    printf "\033[?25l" > /dev/tty
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT

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
            # Enter — select current item and confirm immediately
            if [ "$cursor" -lt "$count" ]; then
                selected=$cursor
            fi
            printf "\033[%dA" "$total_rows" > /dev/tty
            _radio_draw
            break
        elif [ "$key" = " " ]; then
            # Space — select but keep browsing
            if [ "$cursor" -lt "$count" ]; then
                selected=$cursor
            fi
        fi
    done

    printf "\033[?25h" > /dev/tty
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
        # TOOLS env var already set, just normalize it
        TOOLS=$(echo "$TOOLS" | tr ',' ' ')
        return
    fi

    # Auto-detect what's installed
    local has_claude=false
    local has_cursor=false
    local has_codex=false
    local has_copilot=false

    command -v claude >/dev/null 2>&1 && has_claude=true
    { [ -d "/Applications/Cursor.app" ] || command -v cursor >/dev/null 2>&1; } && has_cursor=true
    command -v codex >/dev/null 2>&1 && has_codex=true
    { [ -d "/Applications/Visual Studio Code.app" ] || command -v code >/dev/null 2>&1; } && has_copilot=true

    # Build checkbox items: "Label|value|on_or_off|hint"
    local claude_state="off" cursor_state="off" codex_state="off" copilot_state="off"
    local claude_hint="not found" cursor_hint="not found" codex_hint="not found" copilot_hint="not found"
    [ "$has_claude" = true ]  && claude_state="on"  && claude_hint="detected"
    [ "$has_cursor" = true ]  && cursor_state="on"  && cursor_hint="detected"
    [ "$has_codex" = true ]   && codex_state="on"   && codex_hint="detected"
    [ "$has_copilot" = true ] && copilot_state="on"  && copilot_hint="detected"

    # If nothing detected, pre-select claude as default
    if [ "$has_claude" = false ] && [ "$has_cursor" = false ] && [ "$has_codex" = false ] && [ "$has_copilot" = false ]; then
        claude_state="on"
        claude_hint="default"
    fi

    # Interactive or fallback
    if [ "$SILENT" = false ] && [ -e /dev/tty ]; then
        [ "$SILENT" = false ] && echo ""
        [ "$SILENT" = false ] && echo -e "  ${B}Select tools to install for:${N}"

        TOOLS=$(checkbox_select \
            "Claude Code|claude|${claude_state}|${claude_hint}" \
            "Cursor|cursor|${cursor_state}|${cursor_hint}" \
            "GitHub Copilot|copilot|${copilot_state}|${copilot_hint}" \
            "OpenAI Codex|codex|${codex_state}|${codex_hint}" \
        )
    else
        # Silent: use detected defaults
        local tools=""
        [ "$has_claude" = true ]  && tools="claude"
        [ "$has_cursor" = true ]  && tools="${tools:+$tools }cursor"
        [ "$has_copilot" = true ] && tools="${tools:+$tools }copilot"
        [ "$has_codex" = true ]   && tools="${tools:+$tools }codex"
        [ -z "$tools" ] && tools="claude"
        TOOLS="$tools"
    fi

    # Validate we have at least one
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

    # Skip in silent mode or non-interactive
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        return
    fi

    # Detect existing profiles from ~/.databrickscfg
    local cfg_file="$HOME/.databrickscfg"
    local -a profiles=()

    if [ -f "$cfg_file" ]; then
        while IFS= read -r line; do
            # Match [PROFILE_NAME] sections
            if [[ "$line" =~ ^\[([a-zA-Z0-9_-]+)\]$ ]]; then
                profiles+=("${BASH_REMATCH[1]}")
            fi
        done < "$cfg_file"
    fi

    echo ""
    echo -e "  ${B}Select Databricks profile${N}"

    if [ ${#profiles[@]} -gt 0 ] && [ -e /dev/tty ]; then
        # Build radio items: "Label|value|on_or_off|hint"
        local -a items=()
        for p in "${profiles[@]}"; do
            local state="off"
            local hint=""
            [ "$p" = "DEFAULT" ] && state="on" && hint="default"
            items+=("${p}|${p}|${state}|${hint}")
        done
        
        # Add custom profile option at the end
        items+=("Custom profile name...|__CUSTOM__|off|Enter a custom profile name")

        # If no DEFAULT profile exists, pre-select the first one
        local has_default=false
        for p in "${profiles[@]}"; do
            [ "$p" = "DEFAULT" ] && has_default=true
        done
        if [ "$has_default" = false ]; then
            items[0]=$(echo "${items[0]}" | sed 's/|off|/|on|/')
        fi

        local selected_profile
        selected_profile=$(radio_select "${items[@]}")
        
        # If custom was selected, prompt for name
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

# ─── MCP path selection ────────────────────────────────────────
prompt_mcp_path() {
    # If provided via --mcp-path flag, skip prompt
    if [ -n "$USER_MCP_PATH" ]; then
        INSTALL_DIR="$USER_MCP_PATH"
    elif [ "$SILENT" = false ] && [ -e /dev/tty ]; then
        [ "$SILENT" = false ] && echo ""
        [ "$SILENT" = false ] && echo -e "  ${B}MCP server location${N}"
        [ "$SILENT" = false ] && echo -e "  ${D}The MCP server runtime (Python venv + source) will be installed here.${N}"
        [ "$SILENT" = false ] && echo -e "  ${D}Shared across all your projects — only the config files are per-project.${N}"
        [ "$SILENT" = false ] && echo ""

        local selected
        selected=$(prompt "Install path" "$INSTALL_DIR")

        # Expand ~ to $HOME
        INSTALL_DIR="${selected/#\~/$HOME}"
    fi

    # Update derived paths
    REPO_DIR="$INSTALL_DIR/repo"
    VENV_DIR="$INSTALL_DIR/.venv"
    VENV_PYTHON="$VENV_DIR/bin/python"
    MCP_ENTRY="$REPO_DIR/databricks-mcp-server/run_server.py"
}

# Compare semantic versions (returns 0 if $1 >= $2)
version_gte() {
    printf '%s\n%s' "$2" "$1" | sort -V -C
}

# Check Databricks CLI version meets minimum requirement
check_cli_version() {
    local cli_version
    cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)

    if [ -z "$cli_version" ]; then
        warn "Could not determine Databricks CLI version"
        return
    fi

    if version_gte "$cli_version" "$MIN_CLI_VERSION"; then
        ok "Databricks CLI v${cli_version}"
    else
        warn "Databricks CLI v${cli_version} is outdated (minimum: v${MIN_CLI_VERSION})"
        msg "  ${B}Upgrade:${N} curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"
    fi
}

# Check Databricks SDK version in the MCP venv
check_sdk_version() {
    local sdk_version
    sdk_version=$("$VENV_PYTHON" -c "from databricks.sdk.version import __version__; print(__version__)" 2>/dev/null)

    if [ -z "$sdk_version" ]; then
        warn "Could not determine Databricks SDK version"
        return
    fi

    if version_gte "$sdk_version" "$MIN_SDK_VERSION"; then
        ok "Databricks SDK v${sdk_version}"
    else
        warn "Databricks SDK v${sdk_version} is outdated (minimum: v${MIN_SDK_VERSION})"
        msg "  ${B}Upgrade:${N} $VENV_PYTHON -m pip install --upgrade databricks-sdk"
    fi
}

# Check prerequisites
check_deps() {
    command -v git >/dev/null 2>&1 || die "git required"
    ok "git"

    if command -v databricks >/dev/null 2>&1; then
        check_cli_version
    else
        warn "Databricks CLI not found. Install: ${B}curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh${N}"
        msg "${D}You can still install, but authentication will require the CLI later.${N}"
    fi

    if [ "$INSTALL_MCP" = true ]; then
        if command -v uv >/dev/null 2>&1; then
            PKG="uv"
        elif command -v pip3 >/dev/null 2>&1; then
            PKG="pip3"
        elif command -v pip >/dev/null 2>&1; then
            PKG="pip"
        else
            die "Python package manager required. Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
        fi
        ok "$PKG"
    fi
}

# Check if update needed
check_version() {
    local ver_file="$INSTALL_DIR/version"
    [ "$SCOPE" = "project" ] && ver_file=".ai-dev-kit/version"
    
    [ ! -f "$ver_file" ] && return
    [ "$FORCE" = true ] && return
    
    local local_ver=$(cat "$ver_file")
    # Use -f to fail on HTTP errors (like 404)
    local remote_ver=$(curl -fsSL "$RAW_URL/VERSION" 2>/dev/null || echo "")
    
    # Validate remote version format (should not contain "404" or other error text)
    if [ -n "$remote_ver" ] && [[ ! "$remote_ver" =~ (404|Not Found|error) ]]; then
        if [ "$local_ver" = "$remote_ver" ]; then
            ok "Already up to date (v${local_ver})"
            msg "${D}Use --force to reinstall${N}"
            exit 0
        fi
    fi
}

# Setup MCP server
setup_mcp() {
    step "Setting up MCP server"
    
    # Clone or update repo
    if [ -d "$REPO_DIR/.git" ]; then
        git -C "$REPO_DIR" fetch -q origin "$BRANCH" 2>/dev/null || true
        git -c advice.detachedHead=false -C "$REPO_DIR" checkout -q "$BRANCH" 2>/dev/null || true
        git -C "$REPO_DIR" pull -q 2>/dev/null || {
            rm -rf "$REPO_DIR"
            git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
        }
    else
        mkdir -p "$INSTALL_DIR"
        git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
    fi
    ok "Repository cloned ($BRANCH)"
    
    # Create venv and install
    # On Apple Silicon under Rosetta, force arm64 to avoid architecture mismatch
    # with universal2 Python binaries (see: github.com/databricks-solutions/ai-dev-kit/issues/115)
    local arch_prefix=""
    if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && [ "$(uname -m)" = "x86_64" ]; then
        if arch -arm64 python3 -c "pass" 2>/dev/null; then
            arch_prefix="arch -arm64"
            warn "Rosetta detected on Apple Silicon — forcing arm64 for Python"
        fi
    fi

    msg "Installing Python dependencies..."
    if [ "$PKG" = "uv" ]; then
        $arch_prefix uv venv --python 3.11 --allow-existing "$VENV_DIR" -q 2>/dev/null || $arch_prefix uv venv --allow-existing "$VENV_DIR" -q
        $arch_prefix uv pip install --python "$VENV_PYTHON" -e "$REPO_DIR/databricks-tools-core" -e "$REPO_DIR/databricks-mcp-server" -q
    else
        [ ! -d "$VENV_DIR" ] && $arch_prefix python3 -m venv "$VENV_DIR"
        $arch_prefix "$VENV_PYTHON" -m pip install -q -e "$REPO_DIR/databricks-tools-core" -e "$REPO_DIR/databricks-mcp-server"
    fi

    "$VENV_PYTHON" -c "import databricks_mcp_server" 2>/dev/null || die "MCP server install failed"
    ok "MCP server ready"
}

# Install skills
install_skills() {
    step "Installing skills"

    local base_dir=$1
    local dirs=""

    # Determine target directories
    for tool in $TOOLS; do
        case $tool in
            claude) dirs="$base_dir/.claude/skills" ;;
            cursor) echo "$TOOLS" | grep -q claude || dirs="$dirs $base_dir/.cursor/skills" ;;
            copilot) dirs="$dirs $base_dir/.github/skills" ;;
            codex) dirs="$dirs $base_dir/.agents/skills" ;;
        esac
    done

    dirs=$(echo "$dirs" | xargs -n1 | sort -u | xargs)

    for dir in $dirs; do
        mkdir -p "$dir"
        # Install Databricks skills from repo
        for skill in $SKILLS; do
            local src="$REPO_DIR/databricks-skills/$skill"
            [ ! -d "$src" ] && continue
            rm -rf "$dir/$skill"
            cp -r "$src" "$dir/$skill"
        done
        ok "Databricks skills → ${dir#$HOME/}"

        # Install MLflow skills from mlflow/skills repo
        for skill in $MLFLOW_SKILLS; do
            local dest_dir="$dir/$skill"
            mkdir -p "$dest_dir"
            local url="$MLFLOW_RAW_URL/$skill/SKILL.md"
            if curl -fsSL "$url" -o "$dest_dir/SKILL.md" 2>/dev/null; then
                # Try to fetch optional reference files
                for ref in reference.md examples.md api.md; do
                    curl -fsSL "$MLFLOW_RAW_URL/$skill/$ref" -o "$dest_dir/$ref" 2>/dev/null || true
                done
            else
                rm -rf "$dest_dir"
            fi
        done
        ok "MLflow skills → ${dir#$HOME/}"
    done
}

# Write MCP configs
write_mcp_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"

    # Backup existing file before any modifications
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}Backed up ${path##*/} → ${path##*/}.bak${N}"
    fi

    if [ -f "$path" ] && [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json, sys
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('mcpServers', {})['databricks'] = {'command': '$VENV_PYTHON', 'args': ['$MCP_ENTRY'], 'env': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'}}
with open('$path', 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    cat > "$path" << EOF
{
  "mcpServers": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_ENTRY"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$PROFILE"}
    }
  }
}
EOF
}

write_copilot_mcp_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"

    # Backup existing file before any modifications
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}Backed up ${path##*/} → ${path##*/}.bak${N}"
    fi

    if [ -f "$path" ] && [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json, sys
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('servers', {})['databricks'] = {'command': '$VENV_PYTHON', 'args': ['$MCP_ENTRY'], 'env': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'}}
with open('$path', 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    cat > "$path" << EOF
{
  "servers": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_ENTRY"],
      "env": {"DATABRICKS_CONFIG_PROFILE": "$PROFILE"}
    }
  }
}
EOF
}

write_mcp_toml() {
    local path=$1
    mkdir -p "$(dirname "$path")"
    grep -q "mcp_servers.databricks" "$path" 2>/dev/null && return
    if [ -f "$path" ]; then
        cp "$path" "${path}.bak"
        msg "${D}Backed up ${path##*/} → ${path##*/}.bak${N}"
    fi
    cat >> "$path" << EOF

[mcp_servers.databricks]
command = "$VENV_PYTHON"
args = ["$MCP_ENTRY"]
EOF
}

write_mcp_configs() {
    step "Configuring MCP"
    
    local base_dir=$1
    for tool in $TOOLS; do
        case $tool in
            claude)
                [ "$SCOPE" = "global" ] && write_mcp_json "$HOME/.claude/mcp.json" || write_mcp_json "$base_dir/.mcp.json"
                ok "Claude MCP config"
                ;;
            cursor)
                if [ "$SCOPE" = "global" ]; then
                    warn "Cursor global: configure in Settings > MCP"
                    msg "  Command: $VENV_PYTHON | Args: $MCP_ENTRY"
                else
                    write_mcp_json "$base_dir/.cursor/mcp.json"
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
                    write_copilot_mcp_json "$base_dir/.vscode/mcp.json"
                    ok "Copilot MCP config (.vscode/mcp.json)"
                fi
                warn "Copilot: MCP servers must be enabled manually."
                msg "  In Copilot Chat, click ${B}Configure Tools${N} (tool icon, bottom-right) and enable ${B}databricks${N}"
                ;;
            codex)
                [ "$SCOPE" = "global" ] && write_mcp_toml "$HOME/.codex/config.toml" || write_mcp_toml "$base_dir/.codex/config.toml"
                ok "Codex MCP config"
                ;;
        esac
    done
}

# Save version
save_version() {
    # Use -f to fail on HTTP errors (like 404)
    local ver=$(curl -fsSL "$RAW_URL/VERSION" 2>/dev/null || echo "dev")
    # Validate version format
    [[ "$ver" =~ (404|Not Found|error) ]] && ver="dev"
    echo "$ver" > "$INSTALL_DIR/version"
    [ "$SCOPE" = "project" ] && { mkdir -p ".ai-dev-kit"; echo "$ver" > ".ai-dev-kit/version"; }
}

# Print summary
summary() {
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "${G}${B}Installation complete!${N}"
        echo "────────────────────────────────"
        msg "Location: $INSTALL_DIR"
        msg "Scope:    $SCOPE"
        msg "Tools:    $(echo "$TOOLS" | tr ' ' ', ')"
        echo ""
        msg "${B}Next steps:${N}"
        local step=1
        if echo "$TOOLS" | grep -q cursor; then
            msg "${R}${step}. Enable MCP in Cursor: ${B}Cursor → Settings → Cursor Settings → Tools & MCP → Toggle 'databricks'${N}"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q copilot; then
            msg "${step}. In Copilot Chat, click ${B}Configure Tools${N} (tool icon, bottom-right) and enable ${B}databricks${N}"
            step=$((step + 1))
            msg "${step}. Use Copilot in ${B}Agent mode${N} to access Databricks skills and MCP tools"
            step=$((step + 1))
        fi
        msg "${step}. Open your project in your tool of choice"
        step=$((step + 1))
        msg "${step}. Try: \"List my SQL warehouses\""
        echo ""
    fi
}

# Prompt for installation scope
prompt_scope() {
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        return
    fi

    echo ""
    echo -e "  ${B}Select installation scope${N}"
    
    # Simple radio selector without Confirm button
    local -a labels=("Project" "Global")
    local -a values=("project" "global")
    local -a hints=("Install in current directory (.cursor/ and .claude/)" "Install in home directory (~/.cursor/ and ~/.claude/)")
    local count=2
    local selected=0
    local cursor=0
    
    _scope_draw() {
        for i in 0 1; do
            local dot="○"
            local dot_color="\033[2m"
            [ "$i" = "$selected" ] && dot="●" && dot_color="\033[0;32m"
            local arrow="  "
            [ "$i" = "$cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "$i" = "$selected" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b%b%b %-20s %b%s\033[0m\n" "$arrow" "$dot_color" "$dot" "${labels[$i]}" "$hint_style" "${hints[$i]}" > /dev/tty
        done
    }
    
    printf "\n  \033[2m↑/↓ navigate · enter select\033[0m\n\n" > /dev/tty
    printf "\033[?25l" > /dev/tty
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT
    
    _scope_draw
    
    while true; do
        printf "\033[%dA" "$count" > /dev/tty
        _scope_draw
        
        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null
        
        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$cursor" -gt 0 ] && cursor=$((cursor - 1)) ;;
                    B) [ "$cursor" -lt 1 ] && cursor=$((cursor + 1)) ;;
                esac
            fi
        elif [ "$key" = "" ]; then
            selected=$cursor
            printf "\033[%dA" "$count" > /dev/tty
            _scope_draw
            break
        elif [ "$key" = " " ]; then
            selected=$cursor
        fi
    done
    
    printf "\033[?25h" > /dev/tty
    trap - EXIT
    
    SCOPE="${values[$selected]}"
}

# Prompt to run auth
prompt_auth() {
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        return
    fi

    # Check if profile already has a token configured
    local cfg_file="$HOME/.databrickscfg"
    if [ -f "$cfg_file" ]; then
        # Read the token value under the selected profile section
        local in_profile=false
        while IFS= read -r line; do
            if [[ "$line" =~ ^\[([a-zA-Z0-9_-]+)\]$ ]]; then
                [ "${BASH_REMATCH[1]}" = "$PROFILE" ] && in_profile=true || in_profile=false
            elif [ "$in_profile" = true ] && [[ "$line" =~ ^token[[:space:]]*= ]]; then
                ok "Profile ${B}$PROFILE${N} already has a token configured — skipping auth"
                return
            fi
        done < "$cfg_file"
    fi

    # Also skip if env vars are set
    if [ -n "$DATABRICKS_TOKEN" ]; then
        ok "DATABRICKS_TOKEN is set — skipping auth"
        return
    fi

    # Databricks CLI is required for OAuth login
    if ! command -v databricks >/dev/null 2>&1; then
        warn "Databricks CLI not installed — cannot run OAuth login"
        msg "  Install it, then run: ${B}${BL}databricks auth login --profile $PROFILE${N}"
        return
    fi

    echo ""
    msg "${B}Authentication${N}"
    msg "This will run OAuth login for profile ${B}${BL}$PROFILE${N}"
    msg "${D}A browser window will open for you to authenticate with your Databricks workspace.${N}"
    echo ""
    local run_auth
    run_auth=$(prompt "Run ${B}databricks auth login --profile $PROFILE${N} now? ${D}(y/n)${N}" "y")
    if [ "$run_auth" = "y" ] || [ "$run_auth" = "Y" ] || [ "$run_auth" = "yes" ]; then
        echo ""
        databricks auth login --profile "$PROFILE"
    fi
}

# Main
main() {
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "${B}Databricks AI Dev Kit Installer${N}"
        echo "────────────────────────────────"
    fi
    
    # Check dependencies
    step "Checking prerequisites"
    check_deps

    # ── Step 2: Interactive tool selection ──
    step "Selecting tools"
    detect_tools
    ok "Selected: $(echo "$TOOLS" | tr ' ' ', ')"

    # ── Step 3: Interactive profile selection ──
    step "Databricks profile"
    prompt_profile
    ok "Profile: $PROFILE"

    # ── Step 3.5: Interactive scope selection ──
    if [ "$SCOPE_EXPLICIT" = false ]; then
        prompt_scope
        ok "Scope: $SCOPE"
    fi

    # ── Step 4: Interactive MCP path ──
    if [ "$INSTALL_MCP" = true ]; then
        prompt_mcp_path
        ok "MCP path: $INSTALL_DIR"
    fi

    # ── Step 5: Confirm before proceeding ──
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "  ${B}Summary${N}"
        echo -e "  ────────────────────────────────────"
        echo -e "  Tools:       ${G}$(echo "$TOOLS" | tr ' ' ', ')${N}"
        echo -e "  Profile:     ${G}${PROFILE}${N}"
        echo -e "  Scope:       ${G}${SCOPE}${N}"
        [ "$INSTALL_MCP" = true ]    && echo -e "  MCP server:  ${G}${INSTALL_DIR}${N}"
        [ "$INSTALL_SKILLS" = true ] && echo -e "  Skills:      ${G}yes${N}"
        [ "$INSTALL_MCP" = true ]    && echo -e "  MCP config:  ${G}yes${N}"
        echo ""
    fi

    if [ "$SILENT" = false ] && [ -e /dev/tty ]; then
        local confirm
        confirm=$(prompt "Proceed with installation? ${D}(y/n)${N}" "y")
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ] && [ "$confirm" != "yes" ]; then
            echo ""
            msg "Installation cancelled."
            exit 0
        fi
    fi

    # ── Step 6: Version check (may exit early if up to date) ──
    check_version
    
    # Determine base directory
    local base_dir
    [ "$SCOPE" = "global" ] && base_dir="$HOME" || base_dir="$(pwd)"
    
    # Setup MCP server
    if [ "$INSTALL_MCP" = true ]; then
        setup_mcp
    elif [ ! -d "$REPO_DIR" ]; then
        step "Downloading sources"
        mkdir -p "$INSTALL_DIR"
        git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR"
        ok "Repository cloned ($BRANCH)"
    fi
    
    # Install skills
    [ "$INSTALL_SKILLS" = true ] && install_skills "$base_dir"

    # Write MCP configs
    [ "$INSTALL_MCP" = true ] && write_mcp_configs "$base_dir"
    
    # Save version
    save_version
    
    # Prompt to run auth
    prompt_auth
    
    # Done
    summary
}

main "$@"
