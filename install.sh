#!/bin/bash
#
# Databricks AI Dev Kit - Unified Installer
#
# Installs skills, MCP server, and configuration for Claude Code, Cursor, and OpenAI Codex.
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh | bash
#   curl -sL ... | bash -s -- --global
#   curl -sL ... | bash -s -- --skills-only
#   curl -sL ... | bash -s -- --mcp-only
#   curl -sL ... | bash -s -- --tools cursor,codex
#   curl -sL ... | bash -s -- --force
#

set -e

# Configuration
REPO_URL="https://github.com/databricks-solutions/ai-dev-kit.git"
RAW_URL="https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main"
INSTALL_DIR="${AIDEVKIT_HOME:-$HOME/.ai-dev-kit}"
REPO_DIR="$INSTALL_DIR/repo"
VENV_DIR="$INSTALL_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
MCP_ENTRY="$REPO_DIR/databricks-mcp-server/run_server.py"

# Colors
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' BL='\033[0;34m' B='\033[1m' D='\033[2m' N='\033[0m'

# Defaults
PROFILE="DEFAULT"
SCOPE="project"
INSTALL_MCP=true
INSTALL_SKILLS=true
FORCE=false
IS_UPDATE=false
SILENT=false
TOOLS=""
USER_TOOLS=""
USER_MCP_PATH=""

# Skills list
SKILLS="agent-bricks aibi-dashboards asset-bundles databricks-app-apx databricks-app-python databricks-config databricks-docs databricks-genie databricks-jobs databricks-python-sdk databricks-unity-catalog mlflow-evaluation model-serving spark-declarative-pipelines synthetic-data-generation unstructured-pdf-generation"

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
        -g|--global)      SCOPE="global"; shift ;;
        --skills-only)    INSTALL_MCP=false; shift ;;
        --mcp-only)       INSTALL_SKILLS=false; shift ;;
        --mcp-path)       USER_MCP_PATH="$2"; shift 2 ;;
        --silent)         SILENT=true; shift ;;
        --tools)          USER_TOOLS="$2"; shift 2 ;;
        -f|--force)       FORCE=true; shift ;;
        -h|--help)        
            echo "Databricks AI Dev Kit Installer"
            echo ""
            echo "Usage: curl -sL .../install.sh | bash [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -p, --profile NAME    Databricks profile (default: DEFAULT)"
            echo "  -g, --global          Install globally for all projects"
            echo "  --skills-only         Skip MCP server setup"
            echo "  --mcp-only            Skip skills installation"
            echo "  --mcp-path PATH       Path to MCP server installation (default: ~/.ai-dev-kit)"
            echo "  --silent              Silent mode (no output except errors)"
            echo "  --tools LIST          Comma-separated: claude,cursor,codex"
            echo "  -f, --force           Force reinstall"
            echo "  -h, --help            Show this help"
            exit 0 ;;
        *) die "Unknown option: $1 (use -h for help)" ;;
    esac
done

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

# ─── Tool detection & selection ─────────────────────────────────
detect_tools() {
    # If provided via --tools flag, skip detection and prompts
    if [ -n "$USER_TOOLS" ]; then
        TOOLS=$(echo "$USER_TOOLS" | tr ',' ' ')
        return
    fi

    # Auto-detect what's installed
    local has_claude=false
    local has_cursor=false
    local has_codex=false

    command -v claude >/dev/null 2>&1 && has_claude=true
    { [ -d "/Applications/Cursor.app" ] || command -v cursor >/dev/null 2>&1; } && has_cursor=true
    command -v codex >/dev/null 2>&1 && has_codex=true

    # Build checkbox items: "Label|value|on_or_off|hint"
    local claude_state="off" cursor_state="off" codex_state="off"
    local claude_hint="not found" cursor_hint="not found" codex_hint="not found"
    [ "$has_claude" = true ] && claude_state="on" && claude_hint="detected"
    [ "$has_cursor" = true ] && cursor_state="on" && cursor_hint="detected"
    [ "$has_codex" = true ]  && codex_state="on" && codex_hint="detected"

    # If nothing detected, pre-select claude as default
    if [ "$has_claude" = false ] && [ "$has_cursor" = false ] && [ "$has_codex" = false ]; then
        claude_state="on"
        claude_hint="default"
    fi

    # Interactive or fallback
    if [ "$SILENT" = false ] && [ -e /dev/tty ] && [ -t 0 ]; then
        [ "$SILENT" = false ] && echo ""
        [ "$SILENT" = false ] && echo -e "  ${B}Select tools to install for:${N}"

        TOOLS=$(checkbox_select \
            "Claude Code|claude|${claude_state}|${claude_hint}" \
            "Cursor|cursor|${cursor_state}|${cursor_hint}" \
            "OpenAI Codex|codex|${codex_state}|${codex_hint}" \
        )
    else
        # Silent: use detected defaults
        local tools=""
        [ "$has_claude" = true ] && tools="claude"
        [ "$has_cursor" = true ] && tools="${tools:+$tools }cursor"
        [ "$has_codex" = true ]  && tools="${tools:+$tools }codex"
        [ -z "$tools" ] && tools="claude"
        TOOLS="$tools"
    fi

    # Validate we have at least one
    if [ -z "$TOOLS" ]; then
        warn "No tools selected, defaulting to Claude Code"
        TOOLS="claude"
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

# Check prerequisites
check_deps() {
    command -v git >/dev/null 2>&1 || die "git required"
    ok "git"
    
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
        git -C "$REPO_DIR" pull -q 2>/dev/null || {
            rm -rf "$REPO_DIR"
            git clone -q --depth 1 "$REPO_URL" "$REPO_DIR"
        }
    else
        mkdir -p "$INSTALL_DIR"
        git clone -q --depth 1 "$REPO_URL" "$REPO_DIR"
    fi
    ok "Repository cloned"
    
    # Create venv and install
    msg "Installing Python dependencies..."
    if [ "$PKG" = "uv" ]; then
        [ ! -d "$VENV_DIR" ] && uv venv --python 3.11 "$VENV_DIR" -q 2>/dev/null || uv venv "$VENV_DIR" -q
        uv pip install --python "$VENV_PYTHON" -e "$REPO_DIR/databricks-tools-core" -e "$REPO_DIR/databricks-mcp-server" -q
    else
        [ ! -d "$VENV_DIR" ] && python3 -m venv "$VENV_DIR"
        "$VENV_PYTHON" -m pip install -q -e "$REPO_DIR/databricks-tools-core" -e "$REPO_DIR/databricks-mcp-server"
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
            codex) dirs="$dirs $base_dir/.agents/skills" ;;
        esac
    done
    
    dirs=$(echo "$dirs" | xargs -n1 | sort -u | xargs)
    
    for dir in $dirs; do
        mkdir -p "$dir"
        for skill in $SKILLS; do
            local src="$REPO_DIR/databricks-skills/$skill"
            [ ! -d "$src" ] && continue
            rm -rf "$dir/$skill"
            cp -r "$src" "$dir/$skill"
        done
        ok "Skills → ${dir#$HOME/}"
    done
}

# Generate instruction files
write_instructions() {
    [ "$SCOPE" = "global" ] && return
    
    local base_dir=$1
    local content='# Databricks AI Dev Kit

Databricks tools and skills for data engineering, ML, and AI development.

## MCP Tools
SQL execution, pipelines, jobs, Unity Catalog, and more.

## Skills
| Skill | Description |
|-------|-------------|
| `agent-bricks` | Knowledge Assistants, Multi-Agent Supervisors |
| `aibi-dashboards` | AI/BI Dashboards |
| `asset-bundles` | Databricks Asset Bundles (DABs) |
| `databricks-app-*` | Apps with APX, Dash, Streamlit |
| `databricks-genie` | Genie Spaces |
| `databricks-jobs` | Lakeflow Jobs |
| `databricks-python-sdk` | Python SDK, CLI, REST API |
| `databricks-unity-catalog` | Unity Catalog |
| `mlflow-evaluation` | MLflow evaluation |
| `model-serving` | Model Serving |
| `spark-declarative-pipelines` | SDP/LDP |

Quick start: "List my SQL warehouses"
'
    
    for tool in $TOOLS; do
        case $tool in
            claude) 
                [ -f "$base_dir/CLAUDE.md" ] && [ "$FORCE" != true ] || echo "$content" > "$base_dir/CLAUDE.md"
                ;;
            cursor) 
                [ -f "$base_dir/.cursorrules" ] && [ "$FORCE" != true ] || echo "$content" > "$base_dir/.cursorrules"
                ;;
            codex) 
                [ -f "$base_dir/AGENTS.md" ] && [ "$FORCE" != true ] || echo "$content" > "$base_dir/AGENTS.md"
                ;;
        esac
    done
    ok "Instructions created"
}

# Write MCP configs
write_mcp_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"
    
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

write_mcp_toml() {
    local path=$1
    mkdir -p "$(dirname "$path")"
    grep -q "mcp_servers.databricks" "$path" 2>/dev/null && return
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
        msg "1. Configure profile $PROFILE or set environment variables DATABRICKS_HOST and DATABRICKS_TOKEN".
        msg "   Authenticate: ${B}${BL}databricks auth login --profile $PROFILE${N}"
        msg "2. Open your project in your tool of choice"
        msg "3. Try: \"List my SQL warehouses\""
        echo ""
    fi
}

# Prompt to run auth
prompt_auth() {
    if [ "$SILENT" = false ] && [ -e /dev/tty ]; then
        local run_auth
        run_auth=$(prompt "Run authentication now? ${D}(y/n)${N}" "n")
        if [ "$run_auth" = "y" ] || [ "$run_auth" = "Y" ] || [ "$run_auth" = "yes" ]; then
            echo ""
            msg "Running: ${B}${BL}databricks auth login --profile $PROFILE${N}"
            echo ""
            databricks auth login --profile "$PROFILE"
        fi
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

    # ── Step 3: Interactive MCP path ──
    if [ "$INSTALL_MCP" = true ]; then
        prompt_mcp_path
        ok "MCP path: $INSTALL_DIR"
    fi

    # ── Step 4: Confirm before proceeding ──
    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "  ${B}Summary${N}"
        echo -e "  ────────────────────────────────────"
        echo -e "  Tools:       ${G}$(echo "$TOOLS" | tr ' ' ', ')${N}"
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

    # ── Step 5: Version check (may exit early if up to date) ──
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
        git clone -q --depth 1 "$REPO_URL" "$REPO_DIR"
        ok "Repository cloned"
    fi
    
    # Install skills
    [ "$INSTALL_SKILLS" = true ] && install_skills "$base_dir"
    
    # Write instructions
    [ "$INSTALL_SKILLS" = true ] && write_instructions "$base_dir"
    
    # Write MCP configs
    [ "$INSTALL_MCP" = true ] && write_mcp_configs "$base_dir"
    
    # Save version
    save_version
    
    # Done
    summary
    
    # Prompt to run auth
    prompt_auth
}

main "$@"
