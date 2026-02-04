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

# ─── Configuration ──────────────────────────────────────────────
REPO_GIT_URL="https://github.com/databricks-solutions/ai-dev-kit.git"
REPO_RAW_URL="https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main"
AIDEVKIT_HOME="${AIDEVKIT_HOME:-$HOME/.ai-dev-kit}"
REPO_DIR="$AIDEVKIT_HOME/repo"
VENV_DIR="$AIDEVKIT_HOME/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
MCP_SERVER_ENTRY="$REPO_DIR/databricks-mcp-server/run_server.py"

# ─── Colors ─────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ─── Defaults ───────────────────────────────────────────────────
DATABRICKS_CONFIG_PROFILE="DEFAULT"
SCOPE="project"
INSTALL_MCP=true
INSTALL_SKILLS=true
FORCE=false
IS_UPDATE=false
NON_INTERACTIVE=false
DETECTED_TOOLS=""
USER_TOOLS=""
USER_MCP_PATH=""
PKG_MANAGER=""

# ─── All available skills ──────────────────────────────────────
ALL_SKILLS="agent-bricks aibi-dashboards asset-bundles databricks-app-apx databricks-app-python databricks-config databricks-docs databricks-genie databricks-jobs databricks-python-sdk databricks-unity-catalog mlflow-evaluation model-serving spark-declarative-pipelines synthetic-data-generation unstructured-pdf-generation"

# ─── Output helpers ─────────────────────────────────────────────
info()    { echo -e "  ${BLUE}$*${NC}"; }
success() { echo -e "  ${GREEN}✓${NC} $*"; }
warn()    { echo -e "  ${YELLOW}!${NC} $*"; }
err()     { echo -e "  ${RED}✗${NC} $*"; }
step()    { echo -e "\n${BOLD}$*${NC}"; }

# ─── Help ───────────────────────────────────────────────────────
show_help() {
    cat << 'EOF'
Databricks AI Dev Kit - Unified Installer

Installs skills, MCP server, and configuration for Claude Code, Cursor, and OpenAI Codex.

USAGE
  Install (auto-detects your tools):
    curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh | bash

  Update (same command, detects existing install):
    curl -sL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/install.sh | bash

OPTIONS
  --profile, -p      Databricks config profile to use for MCP server (default: DEFAULT)
  --global, -g       Install to user-level directories (available in all projects)
  --skills-only      Install skills only, skip MCP server setup
  --mcp-only         Install MCP server only, skip skills
  --tools LIST       Comma-separated list of tools: claude,cursor,codex
                     (default: interactive prompt with auto-detection)
  --mcp-path PATH    Path for MCP server runtime (default: ~/.ai-dev-kit)
  --non-interactive  Skip all prompts, use defaults and flags only
  --force, -f        Overwrite instruction files (CLAUDE.md, .cursorrules, AGENTS.md)
                     and re-install even if already up to date
  --help, -h         Show this help message

EXAMPLES
  # Install everything, auto-detect tools
  curl -sL .../install.sh | bash

  # Install globally (all projects get skills + MCP)
  curl -sL .../install.sh | bash -s -- --global

  # Cursor user, skills only
  curl -sL .../install.sh | bash -s -- --tools cursor --skills-only

  # Force update everything
  curl -sL .../install.sh | bash -s -- --force

WHAT GETS INSTALLED
  ~/.ai-dev-kit/           MCP server runtime (always)
  .claude/skills/          Skills for Claude Code + Cursor
  .cursor/skills/          Skills for Cursor (if Claude not detected)
  .agents/skills/          Skills for OpenAI Codex
  CLAUDE.md                Instructions for Claude Code
  .cursorrules             Instructions for Cursor
  AGENTS.md                Instructions for OpenAI Codex
  .mcp.json                MCP config for Claude Code
  .cursor/mcp.json         MCP config for Cursor
  .codex/config.toml       MCP config for OpenAI Codex

EOF
}

# ─── Argument parsing ───────────────────────────────────────────
while [ $# -gt 0 ]; do
    case $1 in
        --profile|-p)    DATABRICKS_CONFIG_PROFILE="$2"; shift 2 ;;
        --global|-g)     SCOPE="global"; shift ;;
        --skills-only)   INSTALL_MCP=false; shift ;;
        --mcp-only)      INSTALL_SKILLS=false; shift ;;
        --tools)         USER_TOOLS="$2"; shift 2 ;;
        --mcp-path)      USER_MCP_PATH="$2"; shift 2 ;;
        --non-interactive) NON_INTERACTIVE=true; shift ;;
        --force|-f)      FORCE=true; shift ;;
        --help|-h)       show_help; exit 0 ;;
        *)               err "Unknown option: $1"; echo "  Use --help for usage."; exit 1 ;;
    esac
done

# ─── Interactive helpers ────────────────────────────────────────
# Reads from /dev/tty so prompts work even when piped via curl | bash

# Simple text prompt with default value
prompt() {
    local prompt_text=$1
    local default_value=$2
    local result=""

    if [ "$NON_INTERACTIVE" = true ]; then
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
        DETECTED_TOOLS=$(echo "$USER_TOOLS" | tr ',' ' ')
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
    if [ "$NON_INTERACTIVE" = false ] && [ -e /dev/tty ]; then
        echo ""
        echo -e "  ${BOLD}Select tools to install for:${NC}"

        DETECTED_TOOLS=$(checkbox_select \
            "Claude Code|claude|${claude_state}|${claude_hint}" \
            "Cursor|cursor|${cursor_state}|${cursor_hint}" \
            "OpenAI Codex|codex|${codex_state}|${codex_hint}" \
        )
    else
        # Non-interactive: use detected defaults
        local tools=""
        [ "$has_claude" = true ] && tools="claude"
        [ "$has_cursor" = true ] && tools="${tools:+$tools }cursor"
        [ "$has_codex" = true ]  && tools="${tools:+$tools }codex"
        [ -z "$tools" ] && tools="claude"
        DETECTED_TOOLS="$tools"
    fi

    # Validate we have at least one
    if [ -z "$DETECTED_TOOLS" ]; then
        warn "No tools selected, defaulting to Claude Code"
        DETECTED_TOOLS="claude"
    fi
}

# ─── MCP path selection ────────────────────────────────────────
prompt_mcp_path() {
    # If provided via --mcp-path flag, skip prompt
    if [ -n "$USER_MCP_PATH" ]; then
        AIDEVKIT_HOME="$USER_MCP_PATH"
    elif [ "$NON_INTERACTIVE" = false ]; then
        echo ""
        echo -e "  ${BOLD}MCP server location${NC}"
        echo -e "  ${DIM}The MCP server runtime (Python venv + source) will be installed here.${NC}"
        echo -e "  ${DIM}Shared across all your projects — only the config files are per-project.${NC}"
        echo ""

        local selected
        selected=$(prompt "Install path" "$AIDEVKIT_HOME")

        # Expand ~ to $HOME
        AIDEVKIT_HOME="${selected/#\~/$HOME}"
    fi

    # Update derived paths
    REPO_DIR="$AIDEVKIT_HOME/repo"
    VENV_DIR="$AIDEVKIT_HOME/.venv"
    VENV_PYTHON="$VENV_DIR/bin/python"
    MCP_SERVER_ENTRY="$REPO_DIR/databricks-mcp-server/run_server.py"
}

# ─── Prerequisites ──────────────────────────────────────────────
check_prerequisites() {
    local ok=true

    if ! command -v git >/dev/null 2>&1; then
        err "git is required but not installed"
        ok=false
    else
        success "git"
    fi

    if command -v uv >/dev/null 2>&1; then
        PKG_MANAGER="uv"
        success "uv"
    elif command -v pip3 >/dev/null 2>&1; then
        PKG_MANAGER="pip3"
        success "pip3 (uv recommended for faster installs: https://docs.astral.sh/uv)"
    elif command -v pip >/dev/null 2>&1; then
        PKG_MANAGER="pip"
        success "pip (uv recommended for faster installs: https://docs.astral.sh/uv)"
    else
        if [ "$INSTALL_MCP" = true ]; then
            err "Python package manager required for MCP server"
            err "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
            ok=false
        fi
    fi

    if [ "$ok" = false ]; then
        exit 1
    fi
}

# ─── Version check ─────────────────────────────────────────────
check_version() {
    local local_version="none"

    # Check global version stamp
    if [ -f "$AIDEVKIT_HOME/version" ]; then
        local_version=$(cat "$AIDEVKIT_HOME/version")
        IS_UPDATE=true
    fi

    # Check project version stamp
    if [ "$SCOPE" = "project" ] && [ -f ".ai-dev-kit/version" ]; then
        local_version=$(cat ".ai-dev-kit/version")
        IS_UPDATE=true
    fi

    if [ "$IS_UPDATE" = true ]; then
        local remote_version
        remote_version=$(curl -sL "$REPO_RAW_URL/VERSION" 2>/dev/null || echo "unknown")

        if [ "$local_version" = "$remote_version" ] && [ "$FORCE" != true ]; then
            echo ""
            success "Already up to date (v${local_version})"
            echo ""
            echo -e "  ${DIM}Run with --force to re-install anyway${NC}"
            exit 0
        fi

        if [ "$remote_version" != "unknown" ]; then
            info "Updating v${local_version} → v${remote_version}"
        fi
    fi
}

# ─── MCP server setup ──────────────────────────────────────────
setup_mcp_server() {
    step "Setting up MCP server"

    # Clone or update the repo
    if [ -d "$REPO_DIR/.git" ]; then
        info "Updating repository..."
        git -C "$REPO_DIR" pull --quiet 2>/dev/null || {
            warn "git pull failed, re-cloning..."
            rm -rf "$REPO_DIR"
            git clone --depth 1 --quiet "$REPO_GIT_URL" "$REPO_DIR"
        }
        success "Repository updated"
    else
        info "Cloning repository..."
        mkdir -p "$AIDEVKIT_HOME"
        git clone --depth 1 --quiet "$REPO_GIT_URL" "$REPO_DIR"
        success "Repository cloned"
    fi

    # Create venv and install packages
    info "Installing Python dependencies..."

    if [ "$PKG_MANAGER" = "uv" ]; then
        if [ ! -d "$VENV_DIR" ]; then
            uv venv --python 3.11 "$VENV_DIR" --quiet 2>/dev/null || uv venv "$VENV_DIR" --quiet
        fi
        uv pip install --python "$VENV_PYTHON" \
            -e "$REPO_DIR/databricks-tools-core" \
            -e "$REPO_DIR/databricks-mcp-server" \
            --quiet
    else
        if [ ! -d "$VENV_DIR" ]; then
            python3 -m venv "$VENV_DIR"
        fi
        "$VENV_PYTHON" -m pip install \
            -e "$REPO_DIR/databricks-tools-core" \
            -e "$REPO_DIR/databricks-mcp-server" \
            --quiet
    fi

    # Verify
    if "$VENV_PYTHON" -c "import databricks_mcp_server" 2>/dev/null; then
        success "MCP server ready"
    else
        err "MCP server installation failed"
        err "Try manually: cd $REPO_DIR && $PKG_MANAGER pip install -e databricks-tools-core -e databricks-mcp-server"
        exit 1
    fi
}

# ─── Skills installation ───────────────────────────────────────
install_skill() {
    local skill_name=$1
    local target_dir=$2
    local skill_dir="$target_dir/$skill_name"
    local source_dir="$REPO_DIR/databricks-skills/$skill_name"

    if [ ! -d "$source_dir" ]; then
        warn "Skill source not found: $skill_name"
        return 1
    fi

    if [ ! -f "$source_dir/SKILL.md" ]; then
        warn "SKILL.md missing for: $skill_name"
        return 1
    fi

    # Create skill directory and copy all files
    rm -rf "$skill_dir"
    mkdir -p "$skill_dir"

    # Copy everything from source, preserving directory structure
    (cd "$source_dir" && find . -type f | while read -r file; do
        local dest_dir
        dest_dir=$(dirname "$skill_dir/$file")
        mkdir -p "$dest_dir"
        cp "$source_dir/$file" "$skill_dir/$file"
    done)

    return 0
}

install_skills() {
    step "Installing skills"

    local base_dir=$1
    local skill_dirs=""
    local has_claude=false
    local installed=0
    local total=0

    # Determine which directories to install to
    for tool in $DETECTED_TOOLS; do
        case $tool in
            claude)
                has_claude=true
                skill_dirs="$base_dir/.claude/skills"
                ;;
            cursor)
                # Cursor reads .claude/skills/ too, only use .cursor/skills/ if no Claude
                if [ "$has_claude" = false ] && ! echo "$DETECTED_TOOLS" | grep -q "claude"; then
                    skill_dirs="$skill_dirs $base_dir/.cursor/skills"
                fi
                ;;
            codex)
                skill_dirs="$skill_dirs $base_dir/.agents/skills"
                ;;
        esac
    done

    # Trim and deduplicate
    skill_dirs=$(echo "$skill_dirs" | xargs -n1 | sort -u | xargs)

    for target_dir in $skill_dirs; do
        info "Target: ${target_dir#$HOME/}"
        mkdir -p "$target_dir"

        for skill in $ALL_SKILLS; do
            total=$((total + 1))
            if install_skill "$skill" "$target_dir"; then
                installed=$((installed + 1))
            fi
        done
    done

    success "$installed skills installed"
}

# ─── Instruction files ─────────────────────────────────────────
generate_instruction_content() {
    cat << 'CONTENT'
# Databricks AI Dev Kit

You have access to Databricks tools and skills for data engineering, ML, and AI development.

## MCP Tools

Databricks MCP tools are available for direct operations: SQL execution, pipeline management,
job orchestration, Unity Catalog governance, and more.

## Skills

Load a skill for step-by-step guidance on specific topics:

| Skill | Description |
|-------|-------------|
| `agent-bricks` | Knowledge Assistants, Genie Spaces, Multi-Agent Supervisors |
| `aibi-dashboards` | AI/BI Dashboards |
| `asset-bundles` | Databricks Asset Bundles (DABs) |
| `databricks-app-apx` | Full-stack apps with APX (FastAPI + React) |
| `databricks-app-python` | Python apps with Dash, Streamlit, Flask |
| `databricks-config` | Profile authentication setup |
| `databricks-docs` | Documentation reference |
| `databricks-genie` | Genie Spaces via Conversation API |
| `databricks-jobs` | Lakeflow Jobs and workflow orchestration |
| `databricks-python-sdk` | Python SDK, Connect, CLI, and REST API |
| `databricks-unity-catalog` | Unity Catalog governance and system tables |
| `mlflow-evaluation` | MLflow evaluation, scoring, and trace analysis |
| `model-serving` | Model Serving deployment and endpoints |
| `spark-declarative-pipelines` | Spark Declarative Pipelines (SDP/LDP) |
| `synthetic-data-generation` | Realistic test data generation |
| `unstructured-pdf-generation` | Synthetic PDFs for RAG testing |

## Quick Start

1. Verify connection: "List my SQL warehouses"
2. Load a skill for guidance on a specific topic
3. Combine skills + MCP tools for complex workflows
CONTENT
}

generate_instructions() {
    step "Generating instruction files"

    local base_dir=$1

    for tool in $DETECTED_TOOLS; do
        local file_path=""
        local file_label=""

        case $tool in
            claude) file_path="$base_dir/CLAUDE.md";     file_label="CLAUDE.md" ;;
            cursor) file_path="$base_dir/.cursorrules";   file_label=".cursorrules" ;;
            codex)  file_path="$base_dir/AGENTS.md";      file_label="AGENTS.md" ;;
        esac

        if [ -z "$file_path" ]; then
            continue
        fi

        if [ -f "$file_path" ] && [ "$FORCE" != true ]; then
            warn "$file_label already exists (use --force to overwrite)"
        else
            generate_instruction_content > "$file_path"
            success "Created $file_label"
        fi
    done
}

# ─── MCP config generation ─────────────────────────────────────
write_mcp_json() {
    local file_path=$1
    local label=$2

    mkdir -p "$(dirname "$file_path")"

    if [ -f "$file_path" ]; then
        # File exists - check if we can safely merge using the venv python
        if [ -f "$VENV_PYTHON" ]; then
            local backup="${file_path}.bak"
            cp "$file_path" "$backup"

            if "$VENV_PYTHON" -c "
import json, sys
path = sys.argv[1]
cmd = sys.argv[2]
args = sys.argv[3]
try:
    with open(path) as f:
        config = json.load(f)
except (json.JSONDecodeError, ValueError):
    config = {}
config.setdefault('mcpServers', {})['databricks'] = {
    'command': cmd,
    'args': [args]
}
with open(path, 'w') as f:
    json.dump(config, f, indent=2)
    f.write('\n')
" "$file_path" "$VENV_PYTHON" "$MCP_SERVER_ENTRY" 2>/dev/null; then
                rm -f "$backup"
                success "Updated $label (merged databricks server)"
                return
            else
                # Merge failed, restore backup
                mv "$backup" "$file_path"
                warn "$label exists with other servers. Add manually:"
                echo -e "    ${DIM}\"databricks\": { \"command\": \"$VENV_PYTHON\", \"args\": [\"$MCP_SERVER_ENTRY\"] }${NC}"
                return
            fi
        else
            warn "$label already exists. Add the databricks server manually:"
            echo -e "    ${DIM}\"databricks\": { \"command\": \"$VENV_PYTHON\", \"args\": [\"$MCP_SERVER_ENTRY\"] }${NC}"
            return
        fi
    fi

    # File doesn't exist - create it
    cat > "$file_path" << EOF
{
  "mcpServers": {
    "databricks": {
      "command": "$VENV_PYTHON",
      "args": ["$MCP_SERVER_ENTRY"],
      "env": {
        "DATABRICKS_CONFIG_PROFILE": "$DATABRICKS_CONFIG_PROFILE"
      }
    }
  }
}
EOF
    success "Created $label"
}

write_mcp_toml() {
    local file_path=$1
    local label=$2

    mkdir -p "$(dirname "$file_path")"

    local toml_block="# Databricks MCP Server (ai-dev-kit)
[mcp_servers.databricks]
command = \"$VENV_PYTHON\"
args = [\"$MCP_SERVER_ENTRY\"]"

    if [ -f "$file_path" ]; then
        if grep -q "mcp_servers.databricks" "$file_path" 2>/dev/null; then
            # Already has a databricks entry - we could update it but safer to skip
            warn "$label already has a databricks MCP entry"
            return
        else
            # Append our section
            echo "" >> "$file_path"
            echo "$toml_block" >> "$file_path"
            success "Updated $label (appended databricks server)"
            return
        fi
    fi

    # File doesn't exist - create it
    echo "$toml_block" > "$file_path"
    success "Created $label"
}

generate_mcp_configs() {
    step "Configuring MCP"

    local base_dir=$1

    for tool in $DETECTED_TOOLS; do
        case $tool in
            claude)
                if [ "$SCOPE" = "global" ]; then
                    write_mcp_json "$HOME/.claude/mcp.json" "~/.claude/mcp.json"
                else
                    write_mcp_json "$base_dir/.mcp.json" ".mcp.json"
                fi
                ;;
            cursor)
                if [ "$SCOPE" = "global" ]; then
                    warn "Cursor: global MCP must be configured via Cursor Settings > MCP"
                    info "  Command: $VENV_PYTHON"
                    info "  Args:    $MCP_SERVER_ENTRY"
                else
                    write_mcp_json "$base_dir/.cursor/mcp.json" ".cursor/mcp.json"
                fi
                ;;
            codex)
                if [ "$SCOPE" = "global" ]; then
                    write_mcp_toml "$HOME/.codex/config.toml" "~/.codex/config.toml"
                else
                    write_mcp_toml "$base_dir/.codex/config.toml" ".codex/config.toml"
                fi
                ;;
        esac
    done
}

# ─── Version stamp ──────────────────────────────────────────────
write_version() {
    local version
    version=$(curl -sL "$REPO_RAW_URL/VERSION" 2>/dev/null || echo "dev")

    # Global stamp
    mkdir -p "$AIDEVKIT_HOME"
    echo "$version" > "$AIDEVKIT_HOME/version"

    # Project stamp
    if [ "$SCOPE" = "project" ]; then
        mkdir -p ".ai-dev-kit"
        echo "$version" > ".ai-dev-kit/version"
    fi
}

# ─── Summary ────────────────────────────────────────────────────
print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}Installation complete!${NC}"
    echo -e "────────────────────────────────────────"
    echo ""

    if [ "$INSTALL_MCP" = true ]; then
        echo -e "  MCP server  ${DIM}$AIDEVKIT_HOME${NC}"
    fi

    if [ "$SCOPE" = "project" ]; then
        echo -e "  Project     ${DIM}$(pwd)${NC}"
    else
        echo -e "  Scope       ${DIM}global (all projects)${NC}"
    fi

    echo -e "  Tools       ${GREEN}$(echo "$DETECTED_TOOLS" | tr ' ' ', ')${NC}"
    echo ""

    # Show what was installed per tool
    for tool in $DETECTED_TOOLS; do
        case $tool in
            claude)
                echo -e "  ${BOLD}Claude Code${NC}"
                [ "$INSTALL_SKILLS" = true ] && echo -e "    Skills  .claude/skills/"
                [ "$INSTALL_MCP" = true ] && {
                    [ "$SCOPE" = "global" ] && echo -e "    MCP     ~/.claude/mcp.json" || echo -e "    MCP     .mcp.json"
                }
                ;;
            cursor)
                echo -e "  ${BOLD}Cursor${NC}"
                if [ "$INSTALL_SKILLS" = true ]; then
                    if echo "$DETECTED_TOOLS" | grep -q "claude"; then
                        echo -e "    Skills  .claude/skills/ ${DIM}(shared with Claude)${NC}"
                    else
                        echo -e "    Skills  .cursor/skills/"
                    fi
                fi
                [ "$INSTALL_MCP" = true ] && {
                    [ "$SCOPE" = "global" ] && echo -e "    MCP     Configure in Cursor Settings > MCP" || echo -e "    MCP     .cursor/mcp.json"
                }
                ;;
            codex)
                echo -e "  ${BOLD}OpenAI Codex${NC}"
                [ "$INSTALL_SKILLS" = true ] && echo -e "    Skills  .agents/skills/"
                [ "$INSTALL_MCP" = true ] && {
                    [ "$SCOPE" = "global" ] && echo -e "    MCP     ~/.codex/config.toml" || echo -e "    MCP     .codex/config.toml"
                }
                ;;
        esac
    done

    echo ""
    echo -e "${BOLD}Next steps${NC}"
    echo "  1. Authenticate to selected profile $DATABRICKS_CONFIG_PROFILE or set environment variables DATABRICKS_HOST and DATABRICKS_TOKEN".
    echo "     Run: databricks auth login --profile $DATABRICKS_CONFIG_PROFILE"
    echo "  2. Open your project in your tool of choice"
    echo "  3. Try: \"List my SQL warehouses\""
    echo ""
    echo -e "  ${DIM}To update later, run the same install command again.${NC}"
    echo ""
}

# ─── Main ───────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BOLD}  Databricks AI Dev Kit${NC}"
    echo -e "  ────────────────────────────────────────"

    # ── Step 1: Prerequisites ──
    step "Checking prerequisites"
    check_prerequisites

    # ── Step 2: Interactive tool selection ──
    step "Selecting tools"
    detect_tools
    echo ""
    success "Selected: $(echo "$DETECTED_TOOLS" | tr ' ' ', ')"

    # ── Step 3: Interactive MCP path ──
    if [ "$INSTALL_MCP" = true ]; then
        prompt_mcp_path
        success "MCP path: $AIDEVKIT_HOME"
    fi

    # ── Step 4: Confirm before proceeding ──
    echo ""
    echo -e "  ${BOLD}Summary${NC}"
    echo -e "  ────────────────────────────────────"
    echo -e "  Tools:       ${GREEN}$(echo "$DETECTED_TOOLS" | tr ' ' ', ')${NC}"
    echo -e "  Scope:       ${GREEN}${SCOPE}${NC}"
    [ "$INSTALL_MCP" = true ]    && echo -e "  MCP server:  ${GREEN}${AIDEVKIT_HOME}${NC}"
    [ "$INSTALL_SKILLS" = true ] && echo -e "  Skills:      ${GREEN}yes${NC}"
    [ "$INSTALL_MCP" = true ]    && echo -e "  MCP config:  ${GREEN}yes${NC}"
    echo ""

    if [ "$NON_INTERACTIVE" = false ]; then
        local confirm
        confirm=$(prompt "Proceed with installation? ${DIM}(y/n)${NC}" "y")
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ] && [ "$confirm" != "yes" ]; then
            echo ""
            info "Installation cancelled."
            exit 0
        fi
    fi

    # ── Step 5: Version check (may exit early if up to date) ──
    check_version

    # ── Step 6: MCP server setup ──
    if [ "$INSTALL_MCP" = true ]; then
        setup_mcp_server
    elif [ ! -d "$REPO_DIR/databricks-skills" ]; then
        # Even for --skills-only, we need the repo for skill source files
        step "Downloading skill sources"
        mkdir -p "$AIDEVKIT_HOME"
        if [ -d "$REPO_DIR/.git" ]; then
            git -C "$REPO_DIR" pull --quiet 2>/dev/null || true
            success "Repository updated"
        else
            git clone --depth 1 --quiet "$REPO_GIT_URL" "$REPO_DIR"
            success "Repository cloned"
        fi
    fi

    # ── Step 7: Determine base directory ──
    local base_dir
    if [ "$SCOPE" = "global" ]; then
        base_dir="$HOME"
    else
        base_dir="$(pwd)"
    fi

    # ── Step 8: Install skills ──
    if [ "$INSTALL_SKILLS" = true ]; then
        install_skills "$base_dir"
    fi

    # ── Step 9: Generate instruction files (project-level only) ──
    if [ "$INSTALL_SKILLS" = true ] && [ "$SCOPE" = "project" ]; then
        generate_instructions "$base_dir"
    fi

    # ── Step 10: Generate MCP configs ──
    if [ "$INSTALL_MCP" = true ]; then
        generate_mcp_configs "$base_dir"
    fi

    # ── Step 11: Version stamp ──
    write_version

    # ── Done ──
    print_summary
}

main
