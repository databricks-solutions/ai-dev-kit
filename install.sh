#!/bin/bash
#
# Databricks AI Dev Kit - Unified Installer
#
# Installs skills, MCP server, and configuration for Claude Code, Cursor, OpenAI Codex, GitHub Copilot, Gemini CLI, and Antigravity.
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
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --tools cursor,codex,copilot,gemini
#
#   # Skills only (skip MCP server)
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --skills-only
#
#   # Install skills for a specific profile
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --skills-profile data-engineer
#
#   # Install multiple profiles
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --skills-profile data-engineer,ai-ml-engineer
#
#   # Install specific skills only
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --skills databricks-jobs,databricks-dbsql
#
#   # List available skills and profiles
#   bash <(curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh) --list-skills
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
SKILLS_PROFILE="${DEVKIT_SKILLS_PROFILE:-}"
USER_SKILLS="${DEVKIT_SKILLS:-}"

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
SKILLS="databricks-agent-bricks databricks-ai-functions databricks-aibi-dashboards databricks-app-python databricks-bundles databricks-config databricks-dbsql databricks-docs databricks-genie databricks-iceberg databricks-jobs databricks-lakebase-autoscale databricks-lakebase-provisioned databricks-metric-views databricks-mlflow-evaluation databricks-model-serving databricks-python-sdk databricks-spark-declarative-pipelines databricks-spark-structured-streaming databricks-synthetic-data-gen databricks-unity-catalog databricks-unstructured-pdf-generation databricks-vector-search databricks-zerobus-ingest spark-python-data-source"

# MLflow skills (fetched from mlflow/skills repo)
MLFLOW_SKILLS="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"
MLFLOW_RAW_URL="https://raw.githubusercontent.com/mlflow/skills/main"

# APX skills (fetched from databricks-solutions/apx repo)
APX_SKILLS="databricks-app-apx"
APX_RAW_URL="https://raw.githubusercontent.com/databricks-solutions/apx/main/skills/apx"

# ─── Skill profiles ──────────────────────────────────────────
# Core skills always installed regardless of profile selection
CORE_SKILLS="databricks-config databricks-docs databricks-python-sdk databricks-unity-catalog"

# Profile definitions (non-core skills only — core skills are always added)
PROFILE_DATA_ENGINEER="databricks-spark-declarative-pipelines databricks-spark-structured-streaming databricks-jobs databricks-bundles databricks-dbsql databricks-iceberg databricks-zerobus-ingest spark-python-data-source databricks-metric-views databricks-synthetic-data-gen"
PROFILE_ANALYST="databricks-aibi-dashboards databricks-dbsql databricks-genie databricks-metric-views"
PROFILE_AIML_ENGINEER="databricks-agent-bricks databricks-ai-functions databricks-vector-search databricks-model-serving databricks-genie databricks-unstructured-pdf-generation databricks-mlflow-evaluation databricks-synthetic-data-gen databricks-jobs"
PROFILE_AIML_MLFLOW="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"
PROFILE_APP_DEVELOPER="databricks-app-python databricks-app-apx databricks-lakebase-autoscale databricks-lakebase-provisioned databricks-model-serving databricks-dbsql databricks-jobs databricks-bundles"

# Selected skills (populated during profile selection)
SELECTED_SKILLS=""
SELECTED_MLFLOW_SKILLS=""
SELECTED_APX_SKILLS=""

# Output helpers
msg()  { [ "$SILENT" = true ] || echo -e "  $*"; }
ok()   { [ "$SILENT" = true ] || echo -e "  ${G}✓${N} $*"; }
warn() { [ "$SILENT" = true ] || echo -e "  ${Y}!${N} $*"; }
die()  { echo -e "  ${R}✗${N} $*" >&2; exit 1; }  # Always show errors
step() { [ "$SILENT" = true ] || echo -e "\n${B}$*${N}"; }

# Parse arguments
while [ $# -gt 0 ]; do
    case $1 in
        -p|--profile)     PROFILE="$2"; shift 2 ;;
        -g|--global)      SCOPE="global"; SCOPE_EXPLICIT=true; shift ;;
        -b|--branch)      BRANCH="$2"; shift 2 ;;
        --skills-only)    INSTALL_MCP=false; shift ;;
        --mcp-only)       INSTALL_SKILLS=false; shift ;;
        --mcp-path)       USER_MCP_PATH="$2"; shift 2 ;;
        --skills-profile) SKILLS_PROFILE="$2"; shift 2 ;;
        --skills)         USER_SKILLS="$2"; shift 2 ;;
        --list-skills)    LIST_SKILLS=true; shift ;;
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
            echo "  --tools LIST          Comma-separated: claude,cursor,copilot,codex,gemini,antigravity"
            echo "  --skills-profile LIST Comma-separated profiles: all,data-engineer,analyst,ai-ml-engineer,app-developer"
            echo "  --skills LIST         Comma-separated skill names to install (overrides profile)"
            echo "  --list-skills         List available skills and profiles, then exit"
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
            echo "  DEVKIT_SKILLS_PROFILE Comma-separated skill profiles"
            echo "  DEVKIT_SKILLS         Comma-separated skill names"
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

# ─── --list-skills handler ─────────────────────────────────────
if [ "${LIST_SKILLS:-false}" = true ]; then
    echo ""
    echo -e "${B}Available Skill Profiles${N}"
    echo "────────────────────────────────"
    echo ""
    echo -e "  ${B}all${N}              All 34 skills (default)"
    echo -e "  ${B}data-engineer${N}    Pipelines, Spark, Jobs, Streaming (14 skills)"
    echo -e "  ${B}analyst${N}          Dashboards, SQL, Genie, Metrics (8 skills)"
    echo -e "  ${B}ai-ml-engineer${N}   Agents, RAG, Vector Search, MLflow (17 skills)"
    echo -e "  ${B}app-developer${N}    Apps, Lakebase, Deployment (10 skills)"
    echo ""
    echo -e "${B}Core Skills${N} (always installed)"
    echo "────────────────────────────────"
    for skill in $CORE_SKILLS; do
        echo -e "  ${G}✓${N} $skill"
    done
    echo ""
    echo -e "${B}Data Engineer${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_DATA_ENGINEER; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}Business Analyst${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_ANALYST; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}AI/ML Engineer${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_AIML_ENGINEER; do
        echo -e "    $skill"
    done
    echo -e "  ${D}+ MLflow skills:${N}"
    for skill in $PROFILE_AIML_MLFLOW; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}App Developer${N}"
    echo "────────────────────────────────"
    for skill in $PROFILE_APP_DEVELOPER; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}MLflow Skills${N} (from mlflow/skills repo)"
    echo "────────────────────────────────"
    for skill in $MLFLOW_SKILLS; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}APX Skills${N} (from databricks-solutions/apx repo)"
    echo "────────────────────────────────"
    for skill in $APX_SKILLS; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${D}Usage: bash install.sh --skills-profile data-engineer,ai-ml-engineer${N}"
    echo -e "${D}       bash install.sh --skills databricks-jobs,databricks-dbsql${N}"
    echo ""
    exit 0
fi

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
    local has_gemini=false
    local has_antigravity=false

    command -v claude >/dev/null 2>&1 && has_claude=true
    { [ -d "/Applications/Cursor.app" ] || command -v cursor >/dev/null 2>&1; } && has_cursor=true
    command -v codex >/dev/null 2>&1 && has_codex=true
    { [ -d "/Applications/Visual Studio Code.app" ] || command -v code >/dev/null 2>&1; } && has_copilot=true
    { command -v gemini >/dev/null 2>&1 || [ -f "$HOME/.gemini/local/gemini" ]; } && has_gemini=true
    { [ -d "/Applications/Antigravity.app" ] || command -v antigravity >/dev/null 2>&1; } && has_antigravity=true

    # Build checkbox items: "Label|value|on_or_off|hint"
    local claude_state="off" cursor_state="off" codex_state="off" copilot_state="off" gemini_state="off" antigravity_state="off"
    local claude_hint="not found" cursor_hint="not found" codex_hint="not found" copilot_hint="not found" gemini_hint="not found" antigravity_hint="not found"
    [ "$has_claude" = true ]        && claude_state="on"        && claude_hint="detected"
    [ "$has_cursor" = true ]        && cursor_state="on"        && cursor_hint="detected"
    [ "$has_codex" = true ]         && codex_state="on"         && codex_hint="detected"
    [ "$has_copilot" = true ]       && copilot_state="on"       && copilot_hint="detected"
    [ "$has_gemini" = true ]        && gemini_state="on"        && gemini_hint="detected"
    [ "$has_antigravity" = true ]   && antigravity_state="on"   && antigravity_hint="detected"

    # If nothing detected, pre-select claude as default
    if [ "$has_claude" = false ] && [ "$has_cursor" = false ] && [ "$has_codex" = false ] && [ "$has_copilot" = false ] && [ "$has_gemini" = false ] && [ "$has_antigravity" = false ]; then
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
            "Gemini CLI|gemini|${gemini_state}|${gemini_hint}" \
            "Antigravity|antigravity|${antigravity_state}|${antigravity_hint}" \
        )
    else
        # Silent: use detected defaults
        local tools=""
        [ "$has_claude" = true ]        && tools="claude"
        [ "$has_cursor" = true ]        && tools="${tools:+$tools }cursor"
        [ "$has_copilot" = true ]       && tools="${tools:+$tools }copilot"
        [ "$has_codex" = true ]         && tools="${tools:+$tools }codex"
        [ "$has_gemini" = true ]        && tools="${tools:+$tools }gemini"
        [ "$has_antigravity" = true ]   && tools="${tools:+$tools }antigravity"
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

# ─── Skill profile selection ──────────────────────────────────
# Resolve selected skills from profile names or explicit skill list
resolve_skills() {
    local db_skills="" mlflow_skills="" apx_skills=""

    # Priority 1: Explicit --skills flag (comma-separated skill names)
    if [ -n "$USER_SKILLS" ]; then
        local user_list
        user_list=$(echo "$USER_SKILLS" | tr ',' ' ')
        # Separate into DB, MLflow, and APX buckets, always include core
        db_skills="$CORE_SKILLS"
        for skill in $user_list; do
            if echo "$MLFLOW_SKILLS" | grep -qw "$skill"; then
                mlflow_skills="${mlflow_skills:+$mlflow_skills }$skill"
            elif echo "$APX_SKILLS" | grep -qw "$skill"; then
                apx_skills="${apx_skills:+$apx_skills }$skill"
            else
                db_skills="${db_skills:+$db_skills }$skill"
            fi
        done
        # Deduplicate
        SELECTED_SKILLS=$(echo "$db_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
        SELECTED_MLFLOW_SKILLS=$(echo "$mlflow_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
        SELECTED_APX_SKILLS=$(echo "$apx_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
        return
    fi

    # Priority 2: --skills-profile flag or interactive selection
    if [ -z "$SKILLS_PROFILE" ] || [ "$SKILLS_PROFILE" = "all" ]; then
        SELECTED_SKILLS="$SKILLS"
        SELECTED_MLFLOW_SKILLS="$MLFLOW_SKILLS"
        SELECTED_APX_SKILLS="$APX_SKILLS"
        return
    fi

    # Build union of selected profiles (comma-separated)
    db_skills="$CORE_SKILLS"
    mlflow_skills=""
    apx_skills=""

    local profiles
    profiles=$(echo "$SKILLS_PROFILE" | tr ',' ' ')
    for profile in $profiles; do
        case $profile in
            all)
                SELECTED_SKILLS="$SKILLS"
                SELECTED_MLFLOW_SKILLS="$MLFLOW_SKILLS"
                SELECTED_APX_SKILLS="$APX_SKILLS"
                return
                ;;
            data-engineer)
                db_skills="$db_skills $PROFILE_DATA_ENGINEER"
                ;;
            analyst)
                db_skills="$db_skills $PROFILE_ANALYST"
                ;;
            ai-ml-engineer)
                db_skills="$db_skills $PROFILE_AIML_ENGINEER"
                mlflow_skills="$mlflow_skills $PROFILE_AIML_MLFLOW"
                ;;
            app-developer)
                db_skills="$db_skills $PROFILE_APP_DEVELOPER"
                apx_skills="$apx_skills $APX_SKILLS"
                ;;
            *)
                warn "Unknown skill profile: $profile (ignored)"
                ;;
        esac
    done

    # Deduplicate
    SELECTED_SKILLS=$(echo "$db_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
    SELECTED_MLFLOW_SKILLS=$(echo "$mlflow_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
    SELECTED_APX_SKILLS=$(echo "$apx_skills" | tr ' ' '\n' | sort -u | tr '\n' ' ')
}

# Interactive skill profile selection (multi-select)
prompt_skills_profile() {
    # If provided via --skills or --skills-profile, skip interactive prompt
    if [ -n "$USER_SKILLS" ] || [ -n "$SKILLS_PROFILE" ]; then
        return
    fi

    # Skip in silent mode or non-interactive
    if [ "$SILENT" = true ] || [ ! -e /dev/tty ]; then
        SKILLS_PROFILE="all"
        return
    fi

    # Check for previous selection (scope-local first, then global fallback for upgrades)
    local profile_file="$STATE_DIR/.skills-profile"
    [ ! -f "$profile_file" ] && [ "$SCOPE" = "project" ] && profile_file="$INSTALL_DIR/.skills-profile"
    if [ -f "$profile_file" ]; then
        local prev_profile
        prev_profile=$(cat "$profile_file")
        if [ "$FORCE" != true ]; then
            echo ""
            local display_profile
            display_profile=$(echo "$prev_profile" | tr ',' ', ')
            local keep
            keep=$(prompt "Previous skill profile: ${B}${display_profile}${N}. Keep? ${D}(Y/n)${N}" "y")
            if [ "$keep" = "y" ] || [ "$keep" = "Y" ] || [ "$keep" = "yes" ] || [ -z "$keep" ]; then
                SKILLS_PROFILE="$prev_profile"
                return
            fi
        fi
    fi

    echo ""
    echo -e "  ${B}Select skill profile(s)${N}"

    # Custom checkbox with mutual exclusion: "All" deselects others, others deselect "All"
    local -a p_labels=("All Skills" "Data Engineer" "Business Analyst" "AI/ML Engineer" "App Developer" "Custom")
    local -a p_values=("all" "data-engineer" "analyst" "ai-ml-engineer" "app-developer" "custom")
    local -a p_hints=("Install everything (34 skills)" "Pipelines, Spark, Jobs, Streaming (14 skills)" "Dashboards, SQL, Genie, Metrics (8 skills)" "Agents, RAG, Vector Search, MLflow (17 skills)" "Apps, Lakebase, Deployment (10 skills)" "Pick individual skills")
    local -a p_states=(1 0 0 0 0 0)  # "All" selected by default
    local p_count=6
    local p_cursor=0
    local p_total_rows=$((p_count + 2))

    _profile_draw() {
        local i
        for i in $(seq 0 $((p_count - 1))); do
            local check=" "
            [ "${p_states[$i]}" = "1" ] && check="\033[0;32m✓\033[0m"
            local arrow="  "
            [ "$i" = "$p_cursor" ] && arrow="\033[0;34m❯\033[0m "
            local hint_style="\033[2m"
            [ "${p_states[$i]}" = "1" ] && hint_style="\033[0;32m"
            printf "\033[2K  %b[%b] %-20s %b%s\033[0m\n" "$arrow" "$check" "${p_labels[$i]}" "$hint_style" "${p_hints[$i]}" > /dev/tty
        done
        printf "\033[2K\n" > /dev/tty
        if [ "$p_cursor" = "$p_count" ]; then
            printf "\033[2K  \033[0;34m❯\033[0m \033[1;32m[ Confirm ]\033[0m\n" > /dev/tty
        else
            printf "\033[2K    \033[2m[ Confirm ]\033[0m\n" > /dev/tty
        fi
    }

    printf "\n  \033[2m↑/↓ navigate · space/enter select · enter on Confirm to finish\033[0m\n\n" > /dev/tty
    printf "\033[?25l" > /dev/tty
    trap 'printf "\033[?25h" > /dev/tty 2>/dev/null' EXIT

    _profile_draw

    while true; do
        printf "\033[%dA" "$p_total_rows" > /dev/tty
        _profile_draw

        local key=""
        IFS= read -rsn1 key < /dev/tty 2>/dev/null

        if [ "$key" = $'\x1b' ]; then
            local s1="" s2=""
            read -rsn1 s1 < /dev/tty 2>/dev/null
            read -rsn1 s2 < /dev/tty 2>/dev/null
            if [ "$s1" = "[" ]; then
                case "$s2" in
                    A) [ "$p_cursor" -gt 0 ] && p_cursor=$((p_cursor - 1)) ;;
                    B) [ "$p_cursor" -lt "$p_count" ] && p_cursor=$((p_cursor + 1)) ;;
                esac
            fi
        elif [ "$key" = " " ] || [ "$key" = "" ]; then
            if [ "$p_cursor" -lt "$p_count" ]; then
                # Toggle the current item
                if [ "${p_states[$p_cursor]}" = "1" ]; then
                    p_states[$p_cursor]=0
                else
                    p_states[$p_cursor]=1
                    # Mutual exclusion: "All" (index 0) vs individual profiles (1-5)
                    if [ "$p_cursor" = "0" ]; then
                        # Selected "All" → deselect all others
                        for j in $(seq 1 $((p_count - 1))); do p_states[$j]=0; done
                    else
                        # Selected an individual profile → deselect "All"
                        p_states[0]=0
                    fi
                fi
            else
                # On Confirm — done
                printf "\033[%dA" "$p_total_rows" > /dev/tty
                _profile_draw
                break
            fi
        fi
    done

    printf "\033[?25h" > /dev/tty
    trap - EXIT

    # Build result
    local selected=""
    for i in $(seq 0 $((p_count - 1))); do
        if [ "${p_states[$i]}" = "1" ]; then
            selected="${selected:+$selected }${p_values[$i]}"
        fi
    done

    # Handle empty selection — default to all
    if [ -z "$selected" ]; then
        SKILLS_PROFILE="all"
        return
    fi

    # Check if "all" is selected
    if echo "$selected" | grep -qw "all"; then
        SKILLS_PROFILE="all"
        return
    fi

    # Check if "custom" is selected — show individual skill picker
    if echo "$selected" | grep -qw "custom"; then
        prompt_custom_skills "$selected"
        return
    fi

    # Store comma-separated profile names
    SKILLS_PROFILE=$(echo "$selected" | tr ' ' ',')
}

# Custom individual skill picker
prompt_custom_skills() {
    local preselected_profiles="$1"

    # Build pre-selection set from any profiles that were also checked
    local preselected=""
    for profile in $preselected_profiles; do
        case $profile in
            data-engineer) preselected="$preselected $PROFILE_DATA_ENGINEER" ;;
            analyst)       preselected="$preselected $PROFILE_ANALYST" ;;
            ai-ml-engineer) preselected="$preselected $PROFILE_AIML_ENGINEER $PROFILE_AIML_MLFLOW" ;;
            app-developer) preselected="$preselected $PROFILE_APP_DEVELOPER $APX_SKILLS" ;;
        esac
    done

    _is_preselected() {
        echo "$preselected" | grep -qw "$1" && echo "on" || echo "off"
    }

    echo ""
    echo -e "  ${B}Select individual skills${N}"
    echo -e "  ${D}Core skills (config, docs, python-sdk, unity-catalog) are always installed${N}"

    local selected
    selected=$(checkbox_select \
        "Spark Pipelines|databricks-spark-declarative-pipelines|$(_is_preselected databricks-spark-declarative-pipelines)|SDP/LDP, CDC, SCD Type 2" \
        "Structured Streaming|databricks-spark-structured-streaming|$(_is_preselected databricks-spark-structured-streaming)|Real-time streaming" \
        "Jobs & Workflows|databricks-jobs|$(_is_preselected databricks-jobs)|Multi-task orchestration" \
        "Asset Bundles|databricks-bundles|$(_is_preselected databricks-bundles)|DABs deployment" \
        "Databricks SQL|databricks-dbsql|$(_is_preselected databricks-dbsql)|SQL warehouse queries" \
        "Iceberg|databricks-iceberg|$(_is_preselected databricks-iceberg)|Apache Iceberg tables" \
        "Zerobus Ingest|databricks-zerobus-ingest|$(_is_preselected databricks-zerobus-ingest)|Streaming ingestion" \
        "Python Data Source|spark-python-data-source|$(_is_preselected spark-python-data-source)|Custom Spark data sources" \
        "Metric Views|databricks-metric-views|$(_is_preselected databricks-metric-views)|Metric definitions" \
        "AI/BI Dashboards|databricks-aibi-dashboards|$(_is_preselected databricks-aibi-dashboards)|Dashboard creation" \
        "Genie|databricks-genie|$(_is_preselected databricks-genie)|Natural language SQL" \
        "Agent Bricks|databricks-agent-bricks|$(_is_preselected databricks-agent-bricks)|Build AI agents" \
        "Vector Search|databricks-vector-search|$(_is_preselected databricks-vector-search)|Similarity search" \
        "Model Serving|databricks-model-serving|$(_is_preselected databricks-model-serving)|Deploy models/agents" \
        "MLflow Evaluation|databricks-mlflow-evaluation|$(_is_preselected databricks-mlflow-evaluation)|Model evaluation" \
        "AI Functions|databricks-ai-functions|$(_is_preselected databricks-ai-functions)|AI Functions, document parsing & RAG" \
        "Unstructured PDF|databricks-unstructured-pdf-generation|$(_is_preselected databricks-unstructured-pdf-generation)|Synthetic PDFs for RAG" \
        "Synthetic Data|databricks-synthetic-data-gen|$(_is_preselected databricks-synthetic-data-gen)|Generate test data" \
        "Lakebase Autoscale|databricks-lakebase-autoscale|$(_is_preselected databricks-lakebase-autoscale)|Managed PostgreSQL" \
        "Lakebase Provisioned|databricks-lakebase-provisioned|$(_is_preselected databricks-lakebase-provisioned)|Provisioned PostgreSQL" \
        "App Python|databricks-app-python|$(_is_preselected databricks-app-python)|Dash, Streamlit, Flask" \
        "App APX|databricks-app-apx|$(_is_preselected databricks-app-apx)|FastAPI + React" \
        "MLflow Onboarding|mlflow-onboarding|$(_is_preselected mlflow-onboarding)|Getting started" \
        "Agent Evaluation|agent-evaluation|$(_is_preselected agent-evaluation)|Evaluate AI agents" \
        "MLflow Tracing|instrumenting-with-mlflow-tracing|$(_is_preselected instrumenting-with-mlflow-tracing)|Instrument with tracing" \
        "Analyze Traces|analyze-mlflow-trace|$(_is_preselected analyze-mlflow-trace)|Analyze trace data" \
        "Retrieve Traces|retrieving-mlflow-traces|$(_is_preselected retrieving-mlflow-traces)|Search & retrieve traces" \
        "Analyze Chat Session|analyze-mlflow-chat-session|$(_is_preselected analyze-mlflow-chat-session)|Chat session analysis" \
        "Query Metrics|querying-mlflow-metrics|$(_is_preselected querying-mlflow-metrics)|MLflow metrics queries" \
        "Search MLflow Docs|searching-mlflow-docs|$(_is_preselected searching-mlflow-docs)|MLflow documentation" \
    )

    # Use explicit skills list — set USER_SKILLS so resolve_skills handles it
    USER_SKILLS=$(echo "$selected" | tr ' ' ',')
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

    # Skip version gate if user explicitly wants a different skill profile
    if [ -n "$SKILLS_PROFILE" ] || [ -n "$USER_SKILLS" ]; then
        local saved_profile_file="$STATE_DIR/.skills-profile"
        [ ! -f "$saved_profile_file" ] && [ "$SCOPE" = "project" ] && saved_profile_file="$INSTALL_DIR/.skills-profile"
        if [ -f "$saved_profile_file" ]; then
            local saved_profile
            saved_profile=$(cat "$saved_profile_file")
            local requested="${USER_SKILLS:+custom:$USER_SKILLS}"
            [ -z "$requested" ] && requested="$SKILLS_PROFILE"
            [ "$saved_profile" != "$requested" ] && return
        fi
    fi

    local local_ver=$(cat "$ver_file")
    # Use -f to fail on HTTP errors (like 404)
    local remote_ver=$(curl -fsSL "$RAW_URL/VERSION" 2>/dev/null || echo "")

    # Validate remote version format (should not contain "404" or other error text)
    if [ -n "$remote_ver" ] && [[ ! "$remote_ver" =~ (404|Not Found|error) ]]; then
        if [ "$local_ver" = "$remote_ver" ]; then
            ok "Already up to date (v${local_ver})"
            msg "${D}Use --force to reinstall or --skills-profile to change profiles${N}"
            exit 0
        fi
    fi
}

# Setup MCP server
setup_mcp() {
    step "Setting up MCP server"
    
    # Clone or update repo
    if [ -d "$REPO_DIR/.git" ]; then
        git -C "$REPO_DIR" fetch -q --depth 1 origin "$BRANCH" 2>/dev/null || true
        git -C "$REPO_DIR" reset --hard FETCH_HEAD 2>/dev/null || {
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
    local dirs=()

    # Determine target directories (array so paths with spaces work)
    for tool in $TOOLS; do
        case $tool in
            claude) dirs+=("$base_dir/.claude/skills") ;;
            cursor) echo "$TOOLS" | grep -q claude || dirs+=("$base_dir/.cursor/skills") ;;
            copilot) dirs+=("$base_dir/.github/skills") ;;
            codex) dirs+=("$base_dir/.agents/skills") ;;
            gemini) dirs+=("$base_dir/.gemini/skills") ;;
            antigravity)
                if [ "$SCOPE" = "global" ]; then
                    dirs+=("$HOME/.gemini/antigravity/skills")
                else
                    dirs+=("$base_dir/.agents/skills")
                fi
                ;;
        esac
    done

    # Dedupe: one element per line, sort -u, read back into array
    local unique=()
    while IFS= read -r d; do
        unique+=("$d")
    done < <(printf '%s\n' "${dirs[@]}" | sort -u)
    dirs=("${unique[@]}")

    # Count selected skills for display
    local db_count=0 mlflow_count=0 apx_count=0
    for _ in $SELECTED_SKILLS; do db_count=$((db_count + 1)); done
    for _ in $SELECTED_MLFLOW_SKILLS; do mlflow_count=$((mlflow_count + 1)); done
    for _ in $SELECTED_APX_SKILLS; do apx_count=$((apx_count + 1)); done
    local total_count=$((db_count + mlflow_count + apx_count))
    msg "Installing ${B}${total_count}${N} skills"

    # Build set of all skills being installed now
    local all_new_skills="$SELECTED_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS"

    # Clean up previously installed skills that are no longer selected
    # Check scope-local manifest first, fall back to global for upgrades from older versions
    local manifest="$STATE_DIR/.installed-skills"
    [ ! -f "$manifest" ] && [ "$SCOPE" = "project" ] && [ -f "$INSTALL_DIR/.installed-skills" ] && manifest="$INSTALL_DIR/.installed-skills"
    if [ -f "$manifest" ]; then
        while IFS='|' read -r prev_dir prev_skill; do
            [ -z "$prev_skill" ] && continue
            # Skip if this skill is still selected
            if echo " $all_new_skills " | grep -qw "$prev_skill"; then
                continue
            fi
            # Only remove if the directory exists
            if [ -d "$prev_dir/$prev_skill" ]; then
                rm -rf "$prev_dir/$prev_skill"
                msg "${D}Removed deselected skill: $prev_skill${N}"
            fi
        done < "$manifest"
    fi

    # Start fresh manifest (always write to scope-local state dir)
    manifest="$STATE_DIR/.installed-skills"
    mkdir -p "$STATE_DIR"
    : > "$manifest.tmp"

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
        # Install Databricks skills from repo
        for skill in $SELECTED_SKILLS; do
            local src="$REPO_DIR/databricks-skills/$skill"
            [ ! -d "$src" ] && continue
            rm -rf "$dir/$skill"
            cp -r "$src" "$dir/$skill"
            echo "$dir|$skill" >> "$manifest.tmp"
        done
        ok "Databricks skills ($db_count) → ${dir#$HOME/}"

        # Install MLflow skills from mlflow/skills repo
        if [ -n "$SELECTED_MLFLOW_SKILLS" ]; then
            for skill in $SELECTED_MLFLOW_SKILLS; do
                local dest_dir="$dir/$skill"
                mkdir -p "$dest_dir"
                local url="$MLFLOW_RAW_URL/$skill/SKILL.md"
                if curl -fsSL "$url" -o "$dest_dir/SKILL.md" 2>/dev/null; then
                    # Try to fetch optional reference files
                    for ref in reference.md examples.md api.md; do
                        curl -fsSL "$MLFLOW_RAW_URL/$skill/$ref" -o "$dest_dir/$ref" 2>/dev/null || true
                    done
                    echo "$dir|$skill" >> "$manifest.tmp"
                else
                    rm -rf "$dest_dir"
                fi
            done
            ok "MLflow skills ($mlflow_count) → ${dir#$HOME/}"
        fi

        # Install APX skills from databricks-solutions/apx repo
        if [ -n "$SELECTED_APX_SKILLS" ]; then
            for skill in $SELECTED_APX_SKILLS; do
                local dest_dir="$dir/$skill"
                mkdir -p "$dest_dir"
                local url="$APX_RAW_URL/SKILL.md"
                if curl -fsSL "$url" -o "$dest_dir/SKILL.md" 2>/dev/null; then
                    # Try to fetch optional reference files
                    for ref in backend-patterns.md frontend-patterns.md; do
                        curl -fsSL "$APX_RAW_URL/$ref" -o "$dest_dir/$ref" 2>/dev/null || true
                    done
                    echo "$dir|$skill" >> "$manifest.tmp"
                else
                    rmdir "$dest_dir" 2>/dev/null || warn "Could not install APX skill '$skill' — consider removing $dest_dir if it is no longer needed"
                fi
            done
            ok "APX skills ($apx_count) → ${dir#$HOME/}"
        fi
    done

    # Save manifest of installed skills (for cleanup on profile change)
    mv "$manifest.tmp" "$manifest"

    # Save selected profile for future reinstalls (scope-local)
    if [ -n "$USER_SKILLS" ]; then
        echo "custom:$USER_SKILLS" > "$STATE_DIR/.skills-profile"
    else
        echo "${SKILLS_PROFILE:-all}" > "$STATE_DIR/.skills-profile"
    fi
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

    if [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json, sys
try:
    with open('$path') as f: cfg = json.load(f)
except: cfg = {}
cfg.setdefault('mcpServers', {})['databricks'] = {'command': '$VENV_PYTHON', 'args': ['$MCP_ENTRY'], 'defer_loading': True, 'env': {'DATABRICKS_CONFIG_PROFILE': '$PROFILE'}}
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
  "mcpServers": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_ENTRY"],
      "defer_loading": true,
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

write_gemini_mcp_json() {
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

write_gemini_md() {
    local path=$1
    [ -f "$path" ] && return  # Don't overwrite existing file
    cat > "$path" << 'GEMINIEOF'
# Databricks AI Dev Kit

You have access to Databricks skills and MCP tools installed by the Databricks AI Dev Kit.

## Available MCP Tools

The `databricks` MCP server provides 50+ tools for interacting with Databricks, including:
- SQL execution and warehouse management
- Unity Catalog operations (tables, volumes, schemas)
- Jobs and workflow management
- Model serving endpoints
- Genie spaces and AI/BI dashboards
- Databricks Apps deployment

## Available Skills

Skills are installed in `.gemini/skills/` and provide patterns and best practices for:
- Spark Declarative Pipelines, Structured Streaming
- Databricks Jobs, Asset Bundles
- Unity Catalog, SQL, Genie
- MLflow evaluation and tracing
- Model Serving, Vector Search
- Databricks Apps (Python and APX)
- And more

## Getting Started

Try asking: "List my SQL warehouses" or "Show my Unity Catalog schemas"
GEMINIEOF
    ok "GEMINI.md"
}

write_claude_hook() {
    local path=$1
    local script=$2
    mkdir -p "$(dirname "$path")"

    # Merge into existing settings.json if present, using Python for safe JSON handling
    if [ -f "$path" ] && [ -f "$VENV_PYTHON" ]; then
        "$VENV_PYTHON" -c "
import json
path = '$path'
script = '$script'
hook_entry = {'type': 'command', 'command': 'bash ' + script, 'timeout': 5}
try:
    with open(path) as f: cfg = json.load(f)
except: cfg = {}
hooks = cfg.setdefault('hooks', {})
session_hooks = hooks.setdefault('SessionStart', [])
# Check if hook already exists
for group in session_hooks:
    for h in group.get('hooks', []):
        if 'check_update.sh' in h.get('command', ''):
            exit(0)  # Already configured
# Append new hook group
session_hooks.append({'hooks': [hook_entry]})
with open(path, 'w') as f: json.dump(cfg, f, indent=2); f.write('\n')
" 2>/dev/null && return
    fi

    # Fallback: write new file (only if no existing file)
    [ -f "$path" ] && return  # Don't overwrite existing settings without Python
    cat > "$path" << EOF
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash $script",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
EOF
}

write_mcp_configs() {
    step "Configuring MCP"
    
    local base_dir=$1
    for tool in $TOOLS; do
        case $tool in
            claude)
                [ "$SCOPE" = "global" ] && write_mcp_json "$HOME/.claude.json" || write_mcp_json "$base_dir/.mcp.json"
                ok "Claude MCP config"
                # Add version check hook to Claude settings
                local check_script="$REPO_DIR/.claude-plugin/check_update.sh"
                if [ "$SCOPE" = "global" ]; then
                    write_claude_hook "$HOME/.claude/settings.json" "$check_script"
                else
                    write_claude_hook "$base_dir/.claude/settings.json" "$check_script"
                fi
                ok "Claude update check hook"
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
            gemini)
                if [ "$SCOPE" = "global" ]; then
                    write_gemini_mcp_json "$HOME/.gemini/settings.json"
                else
                    write_gemini_mcp_json "$base_dir/.gemini/settings.json"
                fi
                ok "Gemini CLI MCP config"
                ;;
            antigravity)
                write_gemini_mcp_json "$HOME/.gemini/antigravity/mcp_config.json"
                ok "Antigravity MCP config"
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
    if [ "$SCOPE" = "project" ]; then
        mkdir -p ".ai-dev-kit"
        echo "$ver" > ".ai-dev-kit/version"
    fi
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
        if echo "$TOOLS" | grep -q gemini; then
            msg "${step}. Launch Gemini CLI in your project: ${B}gemini${N}"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q antigravity; then
            msg "${step}. Open your project in Antigravity to use Databricks skills and MCP tools"
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
    local -a hints=("Install in current directory (.cursor/, .claude/, .gemini/)" "Install in home directory (~/.cursor/, ~/.claude/, ~/.gemini/)")
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

    # Set state directory based on scope (for profile/manifest storage)
    if [ "$SCOPE" = "global" ]; then
        STATE_DIR="$INSTALL_DIR"
    else
        STATE_DIR="$(pwd)/.ai-dev-kit"
    fi

    # ── Step 4: Skill profile selection ──
    if [ "$INSTALL_SKILLS" = true ]; then
        step "Skill profiles"
        prompt_skills_profile
        resolve_skills
        # Count for display
        local sk_count=0
        for _ in $SELECTED_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS; do sk_count=$((sk_count + 1)); done
        if [ -n "$USER_SKILLS" ]; then
            ok "Custom selection ($sk_count skills)"
        else
            ok "Profile: ${SKILLS_PROFILE:-all} ($sk_count skills)"
        fi
    fi

    # ── Step 5: Interactive MCP path ──
    if [ "$INSTALL_MCP" = true ]; then
        prompt_mcp_path
        ok "MCP path: $INSTALL_DIR"
    fi

    # ── Step 6: Confirm before proceeding ──
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "  ${B}Summary${N}"
        echo -e "  ────────────────────────────────────"
        echo -e "  Tools:       ${G}$(echo "$TOOLS" | tr ' ' ', ')${N}"
        echo -e "  Profile:     ${G}${PROFILE}${N}"
        echo -e "  Scope:       ${G}${SCOPE}${N}"
        [ "$INSTALL_MCP" = true ]    && echo -e "  MCP server:  ${G}${INSTALL_DIR}${N}"
        if [ "$INSTALL_SKILLS" = true ]; then
            if [ -n "$USER_SKILLS" ]; then
                echo -e "  Skills:      ${G}custom selection${N}"
            else
                local sk_total=0
                for _ in $SELECTED_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS; do sk_total=$((sk_total + 1)); done
                echo -e "  Skills:      ${G}${SKILLS_PROFILE:-all} ($sk_total skills)${N}"
            fi
        fi
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

    # ── Step 7: Version check (may exit early if up to date) ──
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

    # Write GEMINI.md if gemini is selected
    if echo "$TOOLS" | grep -q gemini; then
        if [ "$SCOPE" = "global" ]; then
            write_gemini_md "$HOME/GEMINI.md"
        else
            write_gemini_md "$base_dir/GEMINI.md"
        fi
    fi

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
