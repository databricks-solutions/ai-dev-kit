#!/bin/bash
#
# Databricks AI Dev Kit - Unified Installer
#
# Installs skills, MCP server, and configuration for Claude Code, Cursor, OpenAI Codex, GitHub Copilot, Gemini CLI, Antigravity, Windsurf, OpenCode, and Kiro.
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
DRY_RUN="${DRY_RUN:-false}"
# Include experimental agent skills in profile/"all" selections (default: true).
# Pass --experimental false (or DEVKIT_EXPERIMENTAL=false) to install only stable
# skills. Explicit --skills requests are always honored as named.
INSTALL_EXPERIMENTAL="${DEVKIT_EXPERIMENTAL:-true}"

# Raw-fetch ref overrides (see resolve_ref). SKILLS_CHANNEL=dev flips unset
# refs to `main` for living-at-head testing.
SKILLS_CHANNEL="${SKILLS_CHANNEL:-stable}"
if [ "$SKILLS_CHANNEL" = "dev" ]; then
    APX_REF="${APX_REF:-main}"
else
    APX_REF="${APX_REF:-latest}"
fi
MLFLOW_REF="${MLFLOW_REF:-main}"  # mlflow/skills is tagless — main is intentional
INCLUDE_PRERELEASES="${INCLUDE_PRERELEASES:-0}"

# Convert string booleans from env vars to actual booleans
[ "$FORCE" = "true" ] || [ "$FORCE" = "1" ] && FORCE=true || FORCE=false
[ "$SILENT" = "true" ] || [ "$SILENT" = "1" ] && SILENT=true || SILENT=false
[ "$DRY_RUN" = "true" ] || [ "$DRY_RUN" = "1" ] && DRY_RUN=true || DRY_RUN=false
# Experimental defaults to true; only "false"/"0" turn it off
[ "$INSTALL_EXPERIMENTAL" = "false" ] || [ "$INSTALL_EXPERIMENTAL" = "0" ] && INSTALL_EXPERIMENTAL=false || INSTALL_EXPERIMENTAL=true

# Check if scope was explicitly set via env var
[ -n "${DEVKIT_SCOPE:-}" ] && SCOPE_EXPLICIT=true

OWNER="databricks-solutions"
REPO="ai-dev-kit"

# Branch/tag override. DEVKIT_BRANCH is canonical; AIDEVKIT_BRANCH is accepted
# as an alias so the bash and PowerShell installers honor the same env var.
if [ -n "${DEVKIT_BRANCH:-${AIDEVKIT_BRANCH:-}}" ]; then
  BRANCH="${DEVKIT_BRANCH:-$AIDEVKIT_BRANCH}"
else
  BRANCH="$(
    curl -s "https://api.github.com/repos/${OWNER}/${REPO}/releases/latest" \
    | grep '"tag_name"' \
    | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/'
  )"
  # Fallback to main if we couldn't fetch the latest release
  [ -z "$BRANCH" ] && BRANCH="main"
fi

# Installation mode defaults. The MCP server is deprecated/optional — skills
# now work directly via the Databricks CLI, so MCP defaults OFF and is opt-in
# (--mcp / --mcp-path / DEVKIT_INSTALL_MCP=true). When opted in, the venv build
# is delegated to databricks-mcp-server/setup.sh.
INSTALL_SKILLS=true
INSTALL_MCP="${DEVKIT_INSTALL_MCP:-false}"
[ "$INSTALL_MCP" = "true" ] || [ "$INSTALL_MCP" = "1" ] && INSTALL_MCP=true || INSTALL_MCP=false

# Minimum required versions
MIN_CLI_VERSION="0.278.0"
# (MCP server SDK minimum is enforced by databricks-mcp-server/setup.sh)
# Agent skills are delegated to `databricks aitools`, which ships with CLI v1.0.0+
MIN_AITOOLS_CLI_VERSION="1.0.0"

# Colors
G='\033[0;32m' Y='\033[1;33m' R='\033[0;31m' BL='\033[0;34m' B='\033[1m' D='\033[2m' N='\033[0m'

# Databricks skills bundled in this repo (everything else moved to databricks/databricks-agent-skills)
LOCAL_SKILLS="databricks-genie"

# MLflow skills (fetched from mlflow/skills repo; MLFLOW_REF defaults to main — the repo is tagless)
MLFLOW_SKILLS="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"
MLFLOW_BASE_URL="https://raw.githubusercontent.com/mlflow/skills"

# APX skills (fetched from databricks-solutions/apx repo @ latest stable tag, see resolve_ref / APX_REF)
APX_SKILLS="databricks-app-apx"
APX_BASE_URL="https://raw.githubusercontent.com/databricks-solutions/apx"

# Agent skills (from databricks/databricks-agent-skills, installed and managed by
# `databricks aitools`, which ships with the Databricks CLI v1.0.0+).
# The live inventory is discovered at runtime via `databricks aitools list -o json`
# (see fetch_agent_b_inventory); these lists are the fallback snapshot (v0.2.3).
AGENT_B_STABLE_FALLBACK="databricks-apps databricks-core databricks-dabs databricks-jobs databricks-lakebase databricks-model-serving databricks-pipelines databricks-serverless-migration databricks-vector-search"
AGENT_B_EXPERIMENTAL_FALLBACK="databricks-agent-bricks databricks-ai-functions databricks-aibi-dashboards databricks-apps-python databricks-dbsql databricks-docs databricks-execution-compute databricks-iceberg databricks-lakeflow-connect databricks-metric-views databricks-mlflow-evaluation databricks-python-sdk databricks-spark-structured-streaming databricks-synthetic-data-gen databricks-unity-catalog databricks-unstructured-pdf-generation databricks-zerobus-ingest spark-python-data-source"
# Skills never installed by default (excluded from "all" and profile selections;
# still installable via an explicit --skills request)
AGENT_B_EXCLUDED="databricks-execution-compute"
# Populated by fetch_agent_b_inventory (live or fallback)
AGENT_B_STABLE=""
AGENT_B_EXPERIMENTAL=""
AGENT_B_RELEASE=""

# Old skill names → new names (breaking rename when sourcing moved to
# databricks-agent-skills). Explicit requests for old names are migrated with a warning.
RENAMED_SKILLS="databricks-bundles:databricks-dabs databricks-spark-declarative-pipelines:databricks-pipelines databricks-config:databricks-core databricks:databricks-core databricks-lakebase-autoscale:databricks-lakebase databricks-lakebase-provisioned:databricks-lakebase"

# ─── Skill profiles ──────────────────────────────────────────
# Core skills always installed regardless of profile selection (all from databricks-agent-skills)
CORE_SKILLS="databricks-core databricks-docs databricks-python-sdk databricks-unity-catalog"

# Profile definitions (non-core skills only — core skills are always added).
# Names may come from any source; resolve_skills buckets them.
PROFILE_DATA_ENGINEER="databricks-pipelines databricks-spark-structured-streaming databricks-jobs databricks-dabs databricks-dbsql databricks-iceberg databricks-lakeflow-connect databricks-zerobus-ingest spark-python-data-source databricks-metric-views databricks-synthetic-data-gen"
PROFILE_ANALYST="databricks-aibi-dashboards databricks-dbsql databricks-genie databricks-metric-views"
PROFILE_AIML_ENGINEER="databricks-agent-bricks databricks-ai-functions databricks-vector-search databricks-model-serving databricks-genie databricks-unstructured-pdf-generation databricks-mlflow-evaluation databricks-synthetic-data-gen databricks-jobs"
PROFILE_AIML_MLFLOW="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"
PROFILE_APP_DEVELOPER="databricks-apps databricks-apps-python databricks-app-apx databricks-lakebase databricks-model-serving databricks-dbsql databricks-jobs databricks-dabs"

# Selected skills (populated during profile selection)
SELECTED_LOCAL_SKILLS=""
SELECTED_MLFLOW_SKILLS=""
SELECTED_APX_SKILLS=""
SELECTED_AGENT_B_SKILLS=""

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
        --mcp-only)       INSTALL_SKILLS=false; INSTALL_MCP=true; shift ;;
        --mcp)            INSTALL_MCP=true; shift ;;
        --mcp-path)       USER_MCP_PATH="$2"; INSTALL_MCP=true; shift 2 ;;
        --skills-profile) SKILLS_PROFILE="$2"; shift 2 ;;
        --skills)         USER_SKILLS="$2"; shift 2 ;;
        --list-skills)    LIST_SKILLS=true; shift ;;
        --experimental)
            case "$2" in
                false|0) INSTALL_EXPERIMENTAL=false; shift 2 ;;
                true|1)  INSTALL_EXPERIMENTAL=true; shift 2 ;;
                *)       INSTALL_EXPERIMENTAL=true; shift ;;
            esac ;;
        --silent)         SILENT=true; shift ;;
        --tools)          USER_TOOLS="$2"; shift 2 ;;
        --dry-run)        DRY_RUN=true; shift ;;
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
            echo "  --skills-only         Install skills only (default; MCP server is opt-in)"
            echo "  --mcp                 Install the deprecated MCP server (default: no)"
            echo "  --mcp-only            Install the MCP server only, skip skills"
            echo "  --mcp-path PATH       MCP server install path (implies --mcp; default: ~/.ai-dev-kit)"
            echo "  --silent              Silent mode (no output except errors)"
            echo "  --tools LIST          Comma-separated: claude,cursor,copilot,codex,gemini,antigravity,windsurf,opencode,kiro"
            echo "  --skills-profile LIST Comma-separated profiles: all,data-engineer,analyst,ai-ml-engineer,app-developer"
            echo "  --skills LIST         Comma-separated skill names to install (overrides profile)"
            echo "  --list-skills         List available skills and profiles, then exit"
            echo "  --experimental BOOL   Include experimental agent skills (default: true; 'false' = stable only)"
            echo "  --dry-run             Print what would be installed (resolved refs, aitools command) and exit"
            echo "  -f, --force           Force reinstall"
            echo "  -h, --help            Show this help"
            echo ""
            echo "Environment Variables (alternative to flags):"
            echo "  DEVKIT_PROFILE        Databricks config profile"
            echo "  DEVKIT_BRANCH         Git branch/tag to install (alias: AIDEVKIT_BRANCH; default: latest release)"
            echo "  DEVKIT_INSTALL_MCP    Set to 'true' to install the deprecated MCP server (default: false)"
            echo "  DEVKIT_SCOPE          'project' or 'global'"
            echo "  DEVKIT_TOOLS          Comma-separated list of tools"
            echo "  DEVKIT_FORCE          Set to 'true' to force reinstall"
            echo "  DEVKIT_MCP_PATH       Path to MCP server installation"
            echo "  DEVKIT_SKILLS_PROFILE Comma-separated skill profiles"
            echo "  DEVKIT_SKILLS         Comma-separated skill names"
            echo "  DEVKIT_SILENT         Set to 'true' for silent mode"
            echo "  DEVKIT_EXPERIMENTAL   'true' (default) or 'false' to skip experimental agent skills"
            echo "  AIDEVKIT_HOME         Installation directory (default: ~/.ai-dev-kit)"
            echo "  APX_REF               Ref for APX skill fetch: 'latest' (default), a tag/SHA, or 'main'"
            echo "  MLFLOW_REF            Ref for MLflow skills fetch (default: main)"
            echo "  SKILLS_CHANNEL        'stable' (default) or 'dev' (unset raw-fetch refs follow main)"
            echo "  INCLUDE_PRERELEASES   Set to '1' to allow -rc/-beta tags when resolving 'latest'"
            echo "  DRY_RUN               Set to '1' to print the install plan and exit"
            echo ""
            echo "Notes:"
            echo "  Most Databricks skills are installed via 'databricks aitools' (Databricks CLI v1.0.0+)"
            echo "  and are updated/uninstalled with 'databricks aitools update|uninstall', not this script."
            echo "  The MCP server is deprecated/optional — skills work without it. Opt in with --mcp."
            echo "  Renamed skills: databricks-bundles -> databricks-dabs,"
            echo "  databricks-spark-declarative-pipelines -> databricks-pipelines."
            echo "  Replaced skills: databricks-config -> databricks-core,"
            echo "  databricks-lakebase-autoscale/provisioned -> databricks-lakebase."
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
# (function — needs fetch_agent_b_inventory; invoked after function definitions below)
_count() { echo $#; }

# Number of skills the "all" profile installs (excluded agent skills omitted)
_count_all_skills() {
    local n skill
    n=$(_count $LOCAL_SKILLS $MLFLOW_SKILLS $APX_SKILLS $AGENT_B_STABLE $AGENT_B_EXPERIMENTAL)
    for skill in $AGENT_B_EXCLUDED; do
        _in_list "$skill" "$AGENT_B_STABLE $AGENT_B_EXPERIMENTAL" && n=$((n - 1))
    done
    echo "$n"
}

list_skills_and_exit() {
    fetch_agent_b_inventory

    local all_count de_count an_count ai_count ap_count
    all_count=$(_count_all_skills)
    de_count=$(_count $CORE_SKILLS $PROFILE_DATA_ENGINEER)
    an_count=$(_count $CORE_SKILLS $PROFILE_ANALYST)
    ai_count=$(_count $CORE_SKILLS $PROFILE_AIML_ENGINEER $PROFILE_AIML_MLFLOW)
    ap_count=$(_count $CORE_SKILLS $PROFILE_APP_DEVELOPER)

    echo ""
    echo -e "${B}Available Skill Profiles${N}"
    echo "────────────────────────────────"
    echo ""
    echo -e "  ${B}all${N}              All ${all_count} skills (default)"
    echo -e "  ${B}data-engineer${N}    Pipelines, Spark, Jobs, Streaming (${de_count} skills)"
    echo -e "  ${B}analyst${N}          Dashboards, SQL, Genie, Metrics (${an_count} skills)"
    echo -e "  ${B}ai-ml-engineer${N}   Agents, RAG, Vector Search, MLflow (${ai_count} skills)"
    echo -e "  ${B}app-developer${N}    Apps, Lakebase, Deployment (${ap_count} skills)"
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
    echo -e "${B}Bundled Skills${N} (from this repo)"
    echo "────────────────────────────────"
    for skill in $LOCAL_SKILLS; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}MLflow Skills${N} (from mlflow/skills repo @ ${MLFLOW_REF})"
    echo "────────────────────────────────"
    for skill in $MLFLOW_SKILLS; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}APX Skills${N} (from databricks-solutions/apx repo @ ${APX_REF})"
    echo "────────────────────────────────"
    for skill in $APX_SKILLS; do
        echo -e "    $skill"
    done
    echo ""
    echo -e "${B}Agent Skills${N} (from databricks/databricks-agent-skills${AGENT_B_RELEASE:+ @ $AGENT_B_RELEASE} — managed by ${B}databricks aitools${N})"
    echo "────────────────────────────────"
    for skill in $AGENT_B_STABLE; do
        echo -e "    $skill"
    done
    echo -e "  ${D}experimental:${N}"
    for skill in $AGENT_B_EXPERIMENTAL; do
        if echo "$AGENT_B_EXCLUDED" | tr ' ' '\n' | grep -Fxq "$skill"; then
            echo -e "    ${D}$skill (excluded by default — request explicitly via --skills)${N}"
        else
            echo -e "    $skill"
        fi
    done
    echo ""
    echo -e "${D}Usage: bash install.sh --skills-profile data-engineer,ai-ml-engineer${N}"
    echo -e "${D}       bash install.sh --skills databricks-jobs,databricks-dbsql${N}"
    echo ""
    exit 0
}

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

# True if we have an interactive tty we can read from.
# `[ -e /dev/tty ]` is not safe here — on macOS the device node always exists
# even when the process has no controlling terminal, so existence does not
# imply we can open it. We check stdin first (normal interactive runs) and
# fall back to attempting to open /dev/tty (needed for `curl … | bash` where
# stdin is piped but a controlling terminal is still available).
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
    # Hide cursor and disable line wrap (DECAWM). With wrap off the terminal
    # clips overlong lines to one row, so the cursor-up redraw can't desync.
    printf "\033[?25l\033[?7l" > /dev/tty

    # Restore cursor on exit (Ctrl+C safety)
    trap 'printf "\033[?25h\033[?7h" > /dev/tty 2>/dev/null' EXIT

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
    printf "\033[?25h\033[?7h" > /dev/tty
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
    # Hide cursor and disable line wrap (DECAWM). With wrap off the terminal
    # clips overlong lines to one row, so the cursor-up redraw can't desync.
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

    # Build checkbox items: "Label|value|on_or_off|hint"
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

    # Interactive or fallback
    if [ "$SILENT" = false ] && is_interactive; then
        [ "$SILENT" = false ] && echo ""
        [ "$SILENT" = false ] && echo -e "  ${B}Select tools to install for:${N}"

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
        # Silent: use detected defaults
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
    if [ "$SILENT" = true ] || ! is_interactive; then
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

    if [ ${#profiles[@]} -gt 0 ] && is_interactive; then
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

# ─── MCP server installation prompt (deprecated/optional) ──────
# Skills work via the Databricks CLI, so MCP is opt-in. Matches the radio-style
# prompt used on the experimental branch and defaults to "Do not install".
prompt_mcp_install() {
    # Already opted in via --mcp / --mcp-path / --mcp-only / env var
    [ "$INSTALL_MCP" = true ] && return
    # Silent or non-interactive runs leave MCP off
    if [ "$SILENT" = true ] || ! is_interactive; then
        return
    fi

    echo ""
    echo -e "  ${B}Deprecated MCP Server${N}"
    echo -e "  ${D}Skills now work via the Databricks CLI for better performance. The MCP"
    echo -e "  server is optional and only needed for backwards compatibility.${N}"

    local selected
    selected=$(radio_select \
        "Do not install|no|on|Recommended — skills work without MCP" \
        "Install MCP server|yes|off|Legacy — requires a Python venv (uv)" \
    )

    # Note: an `&& INSTALL_MCP=true` one-liner here would return 1 when the user
    # picks "no", and `set -e` would abort the installer. Use an if-block.
    if [ "$selected" = "yes" ]; then
        INSTALL_MCP=true
    fi
}

# ─── MCP path selection ────────────────────────────────────────
prompt_mcp_path() {
    # If provided via --mcp-path flag, skip prompt
    if [ -n "$USER_MCP_PATH" ]; then
        INSTALL_DIR="$USER_MCP_PATH"
    elif [ "$SILENT" = false ] && is_interactive; then
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
# Exact-match membership test: _in_list <name> <space-separated list>
# (`grep -w` is unsafe here — `-` is a word boundary, so `grep -w databricks`
# would match `databricks-jobs` etc.)
_in_list() { echo "$2" | tr ' ' '\n' | grep -Fxq "$1"; }

# Map an old skill name to its replacement (prints the new name, or fails)
migrate_renamed_skill() {
    local entry
    for entry in $RENAMED_SKILLS; do
        if [ "${entry%%:*}" = "$1" ]; then
            echo "${entry#*:}"
            return 0
        fi
    done
    return 1
}

# Resolve selected skills from profile names or explicit skill list,
# bucketing each name into its source (local repo / mlflow / apx / agent-skills).
resolve_skills() {
    fetch_agent_b_inventory

    local local_skills="" mlflow_skills="" apx_skills="" agent_b_skills=""

    # Bucket one skill name into its source list (fails for unknown names)
    _bucket() {
        if _in_list "$1" "$LOCAL_SKILLS"; then
            local_skills="${local_skills:+$local_skills }$1"
        elif _in_list "$1" "$MLFLOW_SKILLS"; then
            mlflow_skills="${mlflow_skills:+$mlflow_skills }$1"
        elif _in_list "$1" "$APX_SKILLS"; then
            apx_skills="${apx_skills:+$apx_skills }$1"
        elif _in_list "$1" "$AGENT_B_STABLE $AGENT_B_EXPERIMENTAL"; then
            agent_b_skills="${agent_b_skills:+$agent_b_skills }$1"
        else
            return 1
        fi
    }

    # Dedupe + normalize whitespace (empty input stays truly empty so `[ -n ]` works)
    _dedupe() { echo "$*" | tr ' ' '\n' | sed '/^$/d' | sort -u | tr '\n' ' ' | sed 's/[[:space:]]*$//'; }

    _store_selection() {
        SELECTED_LOCAL_SKILLS=$(_dedupe "$local_skills")
        SELECTED_MLFLOW_SKILLS=$(_dedupe "$mlflow_skills")
        SELECTED_APX_SKILLS=$(_dedupe "$apx_skills")
        SELECTED_AGENT_B_SKILLS=$(_dedupe "$agent_b_skills")
    }

    # Agent skills selected by default: everything except the excluded list (and
    # experimental skills when --experimental false)
    _default_agent_b() {
        local skill
        for skill in $AGENT_B_STABLE $AGENT_B_EXPERIMENTAL; do
            _in_list "$skill" "$AGENT_B_EXCLUDED" && continue
            [ "$INSTALL_EXPERIMENTAL" = false ] && _in_list "$skill" "$AGENT_B_EXPERIMENTAL" && continue
            agent_b_skills="${agent_b_skills:+$agent_b_skills }$skill"
        done
    }

    # Priority 1: Explicit --skills flag (comma-separated skill names)
    if [ -n "$USER_SKILLS" ]; then
        local skill new_name
        for skill in $(echo "$USER_SKILLS" | tr ',' ' '); do
            if _bucket "$skill"; then
                continue
            fi
            if new_name=$(migrate_renamed_skill "$skill"); then
                warn "Skill '$skill' was renamed/replaced by '$new_name' — installing '$new_name'"
                _bucket "$new_name" && continue
            fi
            die "Unknown skill: '$skill' (run with --list-skills to see available skills)"
        done
        _store_selection
        return
    fi

    # Priority 2: --skills-profile flag or interactive selection
    if [ -z "$SKILLS_PROFILE" ] || [ "$SKILLS_PROFILE" = "all" ]; then
        local_skills="$LOCAL_SKILLS"
        mlflow_skills="$MLFLOW_SKILLS"
        apx_skills="$APX_SKILLS"
        _default_agent_b
        _store_selection
        return
    fi

    # Build union of selected profiles (comma-separated)
    local names="$CORE_SKILLS"
    local profile
    for profile in $(echo "$SKILLS_PROFILE" | tr ',' ' '); do
        case $profile in
            all)
                local_skills="$LOCAL_SKILLS"
                mlflow_skills="$MLFLOW_SKILLS"
                apx_skills="$APX_SKILLS"
                agent_b_skills=""
                _default_agent_b
                _store_selection
                return
                ;;
            data-engineer)  names="$names $PROFILE_DATA_ENGINEER" ;;
            analyst)        names="$names $PROFILE_ANALYST" ;;
            ai-ml-engineer) names="$names $PROFILE_AIML_ENGINEER $PROFILE_AIML_MLFLOW" ;;
            app-developer)  names="$names $PROFILE_APP_DEVELOPER" ;;
            *)              warn "Unknown skill profile: $profile (ignored)" ;;
        esac
    done

    local skill
    for skill in $names; do
        # Drop experimental agent skills from profiles when --experimental false
        if [ "$INSTALL_EXPERIMENTAL" = false ] && _in_list "$skill" "$AGENT_B_EXPERIMENTAL"; then
            continue
        fi
        _bucket "$skill" || warn "Skill '$skill' not found in any source (skipped)"
    done
    _store_selection
}

# Interactive skill profile selection (multi-select)
prompt_skills_profile() {
    # If provided via --skills or --skills-profile, skip interactive prompt
    if [ -n "$USER_SKILLS" ] || [ -n "$SKILLS_PROFILE" ]; then
        return
    fi

    # Skip in silent mode or non-interactive
    if [ "$SILENT" = true ] || ! is_interactive; then
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
    local all_count de_count an_count ai_count ap_count
    all_count=$(_count_all_skills)
    de_count=$(_count $CORE_SKILLS $PROFILE_DATA_ENGINEER)
    an_count=$(_count $CORE_SKILLS $PROFILE_ANALYST)
    ai_count=$(_count $CORE_SKILLS $PROFILE_AIML_ENGINEER $PROFILE_AIML_MLFLOW)
    ap_count=$(_count $CORE_SKILLS $PROFILE_APP_DEVELOPER)
    local -a p_labels=("All Skills" "Data Engineer" "Business Analyst" "AI/ML Engineer" "App Developer" "Custom")
    local -a p_values=("all" "data-engineer" "analyst" "ai-ml-engineer" "app-developer" "custom")
    local -a p_hints=("Install everything (${all_count} skills)" "Pipelines, Spark, Jobs, Streaming (${de_count} skills)" "Dashboards, SQL, Genie, Metrics (${an_count} skills)" "Agents, RAG, Vector Search, MLflow (${ai_count} skills)" "Apps, Lakebase, Deployment (${ap_count} skills)" "Pick individual skills")
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
    # Hide cursor and disable line wrap (DECAWM). With wrap off the terminal
    # clips overlong lines to one row, so the cursor-up redraw can't desync.
    printf "\033[?25l\033[?7l" > /dev/tty
    trap 'printf "\033[?25h\033[?7h" > /dev/tty 2>/dev/null' EXIT

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

    printf "\033[?25h\033[?7h" > /dev/tty
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
# Display "Label|hint" for a skill name. Known skills get a friendly label and
# hint; unknown/new ones fall back to the bare name so they still show up in the
# picker as the upstream inventory grows. (case-based — no associative arrays,
# so this stays compatible with the bash 3.2 that ships on macOS.)
_skill_meta() {
    case "$1" in
        databricks-core)                       echo "Core|CLI auth, data exploration" ;;
        databricks-docs)                       echo "Docs|Databricks documentation" ;;
        databricks-python-sdk)                 echo "Python SDK|SDK, Connect, REST API" ;;
        databricks-unity-catalog)              echo "Unity Catalog|System tables, volumes" ;;
        databricks-pipelines)                  echo "Spark Pipelines|SDP/LDP, CDC, SCD Type 2" ;;
        databricks-spark-structured-streaming) echo "Structured Streaming|Real-time streaming" ;;
        databricks-jobs)                       echo "Jobs & Workflows|Multi-task orchestration" ;;
        databricks-dabs)                       echo "Asset Bundles|DABs deployment" ;;
        databricks-dbsql)                      echo "Databricks SQL|SQL warehouse queries" ;;
        databricks-iceberg)                    echo "Iceberg|Apache Iceberg tables" ;;
        databricks-lakeflow-connect)           echo "Lakeflow Connect|Managed ingestion connectors" ;;
        databricks-zerobus-ingest)             echo "Zerobus Ingest|Streaming ingestion" ;;
        spark-python-data-source)              echo "Python Data Source|Custom Spark data sources" ;;
        databricks-metric-views)               echo "Metric Views|Metric definitions" ;;
        databricks-aibi-dashboards)            echo "AI/BI Dashboards|Dashboard creation" ;;
        databricks-genie)                      echo "Genie|Natural language SQL" ;;
        databricks-agent-bricks)               echo "Agent Bricks|Build AI agents" ;;
        databricks-vector-search)              echo "Vector Search|Similarity search" ;;
        databricks-model-serving)              echo "Model Serving|Deploy models/agents" ;;
        databricks-mlflow-evaluation)          echo "MLflow Evaluation|Model evaluation" ;;
        databricks-ai-functions)               echo "AI Functions|AI Functions, document parsing & RAG" ;;
        databricks-unstructured-pdf-generation) echo "Unstructured PDF|Synthetic PDFs for RAG" ;;
        databricks-synthetic-data-gen)         echo "Synthetic Data|Generate test data" ;;
        databricks-lakebase)                   echo "Lakebase|Managed PostgreSQL (OLTP)" ;;
        databricks-serverless-migration)       echo "Serverless Migration|Migrate to serverless compute" ;;
        databricks-apps)                       echo "Apps|AppKit + all frameworks" ;;
        databricks-apps-python)                echo "App (AppKit + Python)|AppKit, Dash, Streamlit, Flask" ;;
        databricks-app-apx)                    echo "App APX|FastAPI + React" ;;
        mlflow-onboarding)                     echo "MLflow Onboarding|Getting started" ;;
        agent-evaluation)                      echo "Agent Evaluation|Evaluate AI agents" ;;
        instrumenting-with-mlflow-tracing)     echo "MLflow Tracing|Instrument with tracing" ;;
        analyze-mlflow-trace)                  echo "Analyze Traces|Analyze trace data" ;;
        retrieving-mlflow-traces)              echo "Retrieve Traces|Search & retrieve traces" ;;
        analyze-mlflow-chat-session)           echo "Analyze Chat Session|Chat session analysis" ;;
        querying-mlflow-metrics)               echo "Query Metrics|MLflow metrics queries" ;;
        searching-mlflow-docs)                 echo "Search MLflow Docs|MLflow documentation" ;;
        *)                                     echo "$1|" ;;
    esac
}

prompt_custom_skills() {
    local preselected_profiles="$1"

    # Build pre-selection set from any profiles that were also checked
    # (core skills start pre-selected — they are recommended for every profile)
    local preselected="$CORE_SKILLS"
    for profile in $preselected_profiles; do
        case $profile in
            data-engineer) preselected="$preselected $PROFILE_DATA_ENGINEER" ;;
            analyst)       preselected="$preselected $PROFILE_ANALYST" ;;
            ai-ml-engineer) preselected="$preselected $PROFILE_AIML_ENGINEER $PROFILE_AIML_MLFLOW" ;;
            app-developer) preselected="$preselected $PROFILE_APP_DEVELOPER" ;;
        esac
    done

    echo ""
    echo -e "  ${B}Select individual skills${N}"
    echo -e "  ${D}Core skills (core, docs, python-sdk, unity-catalog) are recommended for all profiles${N}"

    # Build the picker from the live inventory so new upstream skills appear
    # automatically. Order: agent skills (stable, then experimental), then
    # bundled, MLflow, and APX skills.
    local -a items=()
    local seen="" skill meta label hint state
    for skill in $AGENT_B_STABLE $AGENT_B_EXPERIMENTAL $LOCAL_SKILLS $MLFLOW_SKILLS $APX_SKILLS; do
        _in_list "$skill" "$seen" && continue
        seen="${seen:+$seen }$skill"
        meta=$(_skill_meta "$skill")
        label="${meta%%|*}"
        hint="${meta#*|}"
        state="off"; _in_list "$skill" "$preselected" && state="on"
        items+=("${label}|${skill}|${state}|${hint}")
    done

    local selected
    selected=$(checkbox_select "${items[@]}")

    # databricks-core is always required. This also guarantees a non-empty
    # selection — otherwise USER_SKILLS would be empty and resolve_skills would
    # fall back to installing ALL skills.
    _in_list "databricks-core" "$selected" || selected="databricks-core${selected:+ $selected}"

    # Warn if nothing beyond core was picked
    local rest
    rest=$(echo "$selected" | tr ' ' '\n' | sed '/^$/d' | grep -vx "databricks-core" || true)
    [ -z "$rest" ] && warn "Only databricks-core selected — installing it alone (no other skills)"

    # Use explicit skills list — set USER_SKILLS so resolve_skills handles it
    USER_SKILLS=$(echo "$selected" | tr ' ' ',' | sed 's/^,//;s/,$//')
}

# Compare semantic versions (returns 0 if $1 >= $2)
version_gte() {
    printf '%s\n%s' "$2" "$1" | sort -V -C
}

# ─── Agent skills (databricks/databricks-agent-skills via `databricks aitools`) ───

# Discover the live skill inventory from `databricks aitools list -o json`.
# Falls back to the hardcoded snapshot when the CLI is missing/old/offline.
# Idempotent — only fetches once.
fetch_agent_b_inventory() {
    [ -n "$AGENT_B_STABLE" ] && return

    local json=""
    if command -v databricks >/dev/null 2>&1; then
        json=$(databricks aitools list -o json 2>/dev/null) || json=""
    fi

    if [ -n "$json" ]; then
        AGENT_B_RELEASE=$(echo "$json" | grep -m1 '"release"' | sed -E 's/.*"release": *"([^"]*)".*/\1/')
        # Pair each "name" with the "experimental" flag that follows it
        local parsed
        parsed=$(echo "$json" | awk '
            /"name":/         { gsub(/[",]/, "", $2); name=$2 }
            /"experimental":/ { gsub(/[",]/, "", $2); if (name != "") { print $2, name; name="" } }')
        AGENT_B_STABLE=$(echo "$parsed" | awk '$1=="false"{print $2}' | tr '\n' ' ')
        AGENT_B_EXPERIMENTAL=$(echo "$parsed" | awk '$1=="true"{print $2}' | tr '\n' ' ')
    fi

    if [ -z "$AGENT_B_STABLE" ]; then
        AGENT_B_STABLE="$AGENT_B_STABLE_FALLBACK"
        AGENT_B_EXPERIMENTAL="$AGENT_B_EXPERIMENTAL_FALLBACK"
        AGENT_B_RELEASE=""
    fi
}

# Gate for `databricks aitools` (ships with the Databricks CLI v1.0.0+).
# Interactive: offers to run the upgrade and re-checks in a loop.
# Silent/non-interactive: dies with instructions.
# Returns 1 if the user chose to skip agent skills.
ensure_aitools_cli() {
    local attempts=0
    while true; do
        local cli_version=""
        if command -v databricks >/dev/null 2>&1; then
            cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        fi
        if [ -n "$cli_version" ] && version_gte "$cli_version" "$MIN_AITOOLS_CLI_VERSION"; then
            return 0
        fi

        local found_msg="Databricks CLI not found."
        [ -n "$cli_version" ] && found_msg="Databricks CLI v${cli_version} is too old."

        if [ "$SILENT" = true ] || ! is_interactive; then
            die "$found_msg Agent skills are installed via 'databricks aitools', which requires Databricks CLI v${MIN_AITOOLS_CLI_VERSION}+.
   Upgrade: ${B}curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh${N}
   Then re-run this installer. (Or pass --skills with only non-agent skills to skip this requirement.)"
        fi

        attempts=$((attempts + 1))
        if [ "$attempts" -gt 5 ]; then
            warn "Databricks CLI still not at v${MIN_AITOOLS_CLI_VERSION}+ after several attempts — skipping agent skills"
            return 1
        fi

        warn "$found_msg Agent skills are installed via ${B}databricks aitools${N}, which requires Databricks CLI v${MIN_AITOOLS_CLI_VERSION}+."
        msg "Upgrade command: ${B}curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh${N}"
        echo ""
        local choice
        choice=$(prompt "Upgrade the Databricks CLI now? ${D}(y = run upgrade, r = re-check, s = skip agent skills, a = abort)${N}" "y")
        case "$choice" in
            y|Y|yes)
                curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh || warn "CLI upgrade failed — you can retry or skip"
                hash -r 2>/dev/null || true
                ;;
            r|R) hash -r 2>/dev/null || true ;;
            s|S) return 1 ;;
            a|A) die "Installation aborted (Databricks CLI v${MIN_AITOOLS_CLI_VERSION}+ required for agent skills)" ;;
        esac
    done
}

# Map selected $TOOLS to `aitools --agents` tokens. Tools aitools doesn't
# install for are handled by deliver_agent_skills (which links every selected
# tool's dir from the canonical store).
AITOOLS_AGENTS=""
map_aitools_agents() {
    AITOOLS_AGENTS=""
    local tool
    for tool in $TOOLS; do
        case $tool in
            claude)      AITOOLS_AGENTS="${AITOOLS_AGENTS:+$AITOOLS_AGENTS,}claude-code" ;;
            cursor)      AITOOLS_AGENTS="${AITOOLS_AGENTS:+$AITOOLS_AGENTS,}cursor" ;;
            copilot)     AITOOLS_AGENTS="${AITOOLS_AGENTS:+$AITOOLS_AGENTS,}copilot" ;;
            codex)       AITOOLS_AGENTS="${AITOOLS_AGENTS:+$AITOOLS_AGENTS,}codex" ;;
            opencode)    AITOOLS_AGENTS="${AITOOLS_AGENTS:+$AITOOLS_AGENTS,}opencode" ;;
            antigravity) AITOOLS_AGENTS="${AITOOLS_AGENTS:+$AITOOLS_AGENTS,}antigravity" ;;
        esac
    done
}

# Skills dir for every selected tool (one per line, deduped). `aitools` only
# fans out to some agents (e.g. project scope: just Claude Code + Cursor), so we
# link the canonical store into every selected tool's dir ourselves.
agent_skill_target_dirs() {
    local base_dir=$1 tool
    for tool in $TOOLS; do
        case $tool in
            claude)   echo "$base_dir/.claude/skills" ;;
            cursor)   echo "$base_dir/.cursor/skills" ;;
            copilot)  echo "$base_dir/.github/skills" ;;
            codex)    echo "$base_dir/.agents/skills" ;;
            gemini)   echo "$base_dir/.gemini/skills" ;;
            antigravity) [ "$SCOPE" = "global" ] && echo "$HOME/.gemini/antigravity/skills" || echo "$base_dir/.agents/skills" ;;
            windsurf) [ "$SCOPE" = "global" ] && echo "$HOME/.codeium/windsurf/skills" || echo "$base_dir/.windsurf/skills" ;;
            opencode) [ "$SCOPE" = "global" ] && echo "$HOME/.config/opencode/skills" || echo "$base_dir/.opencode/skills" ;;
            kiro)     [ "$SCOPE" = "global" ] && echo "$HOME/.kiro/skills" || echo "$base_dir/.kiro/skills" ;;
        esac
    done | sort -u
}

# True if any selected agent skill is experimental
agent_b_needs_experimental() {
    local skill
    for skill in $SELECTED_AGENT_B_SKILLS; do
        _in_list "$skill" "$AGENT_B_EXPERIMENTAL" && return 0
    done
    return 1
}

# Install agent skills by delegating to `databricks aitools install`.
# aitools owns these skills afterwards (list/update/uninstall) — they are NOT
# tracked in this installer's manifest, except for the symlinks/copies created
# for tools aitools can't target.
install_agent_b_skills() {
    local base_dir=$1
    local prev_file="$STATE_DIR/.agent-b-skills"
    [ -z "$SELECTED_AGENT_B_SKILLS" ] && [ ! -f "$prev_file" ] && return

    step "Installing agent skills (via databricks aitools)"

    # Uninstall agent skills dropped since the previous run
    if [ -f "$prev_file" ]; then
        local dropped="" skill
        for skill in $(cat "$prev_file"); do
            _in_list "$skill" "$SELECTED_AGENT_B_SKILLS" || dropped="${dropped:+$dropped,}$skill"
        done
        if [ -n "$dropped" ] && command -v databricks >/dev/null 2>&1; then
            if databricks aitools uninstall --scope "$SCOPE" --skills "$dropped" >/dev/null 2>&1; then
                msg "${D}Removed deselected agent skills: ${dropped}${N}"
            else
                warn "Could not remove deselected agent skills — run: ${B}databricks aitools uninstall --skills $dropped${N}"
            fi
        fi
    fi

    if [ -z "$SELECTED_AGENT_B_SKILLS" ]; then
        rm -f "$prev_file"
        return
    fi

    if ! ensure_aitools_cli; then
        warn "Agent skills skipped — install later with: ${B}databricks aitools install${N}"
        return
    fi

    map_aitools_agents
    local skills_csv exp_flag=""
    skills_csv=$(echo "$SELECTED_AGENT_B_SKILLS" | tr -s ' ' ',' | sed 's/^,//;s/,$//')
    agent_b_needs_experimental && exp_flag="--experimental"
    local count
    count=$(_count $SELECTED_AGENT_B_SKILLS)

    if [ -n "$AITOOLS_AGENTS" ]; then
        msg "Delegating ${B}${count}${N} agent skills to ${B}databricks aitools${N} (agents: ${AITOOLS_AGENTS})"
        if [ "$SILENT" = true ]; then
            databricks aitools install --scope "$SCOPE" --agents "$AITOOLS_AGENTS" --skills "$skills_csv" $exp_flag -p "$PROFILE" >/dev/null 2>&1 \
                || die "databricks aitools install failed"
        else
            # Capture so we can drop aitools' "Skipped <agent>: does not support
            # project-scoped skills" notices — we deliver to those tools ourselves.
            local aitools_out aitools_rc
            aitools_out=$(databricks aitools install --scope "$SCOPE" --agents "$AITOOLS_AGENTS" --skills "$skills_csv" $exp_flag -p "$PROFILE" 2>&1) && aitools_rc=0 || aitools_rc=$?
            [ -n "$aitools_out" ] && echo "$aitools_out" | grep -v 'does not support project-scoped skills' || true
            if [ "$aitools_rc" -ne 0 ]; then
                warn "databricks aitools install failed — agent skills not installed"
                return
            fi
        fi
        ok "Agent skills ($count) installed — manage with ${B}databricks aitools list|update|uninstall${N}"
    fi

    # aitools only installs for some agents (project scope: just Claude Code +
    # Cursor). Link the canonical store into every other selected tool's dir.
    deliver_agent_skills "$base_dir" "$skills_csv" "$exp_flag"

    # Record the selection so a future profile change can uninstall dropped skills
    mkdir -p "$STATE_DIR"
    echo "$SELECTED_AGENT_B_SKILLS" | tr ' ' '\n' | sed '/^$/d' > "$prev_file"
}

# Link the agent skills into every selected tool's skills dir from the canonical
# store, so tools aitools doesn't install for (project scope: everything except
# Claude Code + Cursor; plus Gemini/Windsurf/Kiro, which aitools never targets)
# still get the skills. Entries aitools already created are left to aitools.
# If no aitools-supported agent was selected there is no persistent store, so we
# stage a throwaway install in a temp dir and copy real files from it.
deliver_agent_skills() {
    local base_dir=$1 skills_csv=$2 exp_flag=$3
    local manifest="$STATE_DIR/.installed-skills"

    local mode="link" store tmp_dir=""
    if [ "$SCOPE" = "global" ]; then
        store="$HOME/.databricks/aitools/skills"
    else
        store="$base_dir/.databricks/aitools/skills"
    fi

    if [ -z "$AITOOLS_AGENTS" ]; then
        mode="copy"
        tmp_dir=$(mktemp -d)
        if ! (cd "$tmp_dir" && databricks aitools install --scope project --agents claude-code --skills "$skills_csv" $exp_flag >/dev/null 2>&1); then
            rm -rf "$tmp_dir"
            warn "Could not stage agent skills for: $(echo "$TOOLS" | tr ' ' ',')"
            return
        fi
        store="$tmp_dir/.databricks/aitools/skills"
    fi

    local dir skill target made
    while IFS= read -r dir; do
        [ -z "$dir" ] && continue
        mkdir -p "$dir"
        made=0
        for skill in $SELECTED_AGENT_B_SKILLS; do
            if [ ! -d "$store/$skill" ]; then
                warn "Agent skill '$skill' missing from aitools store — skipped"
                continue
            fi
            # In link mode, leave anything aitools already placed (e.g. Claude
            # Code / Cursor) to aitools — it owns and updates those.
            if [ "$mode" = "link" ] && { [ -e "$dir/$skill" ] || [ -L "$dir/$skill" ]; }; then
                continue
            fi
            rm -rf "$dir/$skill"
            if [ "$mode" = "link" ]; then
                # Project-scope dirs are all <base>/.<tool>/skills (2 levels deep),
                # so a relative link survives moving the project directory.
                target="$store/$skill"
                [ "$SCOPE" = "project" ] && target="../../.databricks/aitools/skills/$skill"
                ln -s "$target" "$dir/$skill"
            else
                cp -R "$store/$skill" "$dir/$skill"
            fi
            echo "$dir|$skill" >> "$manifest"
            made=$((made + 1))
        done
        [ "$made" -gt 0 ] && ok "Agent skills ($made, $mode) → ${dir#$HOME/}"
    done < <(agent_skill_target_dirs "$base_dir")

    [ -n "$tmp_dir" ] && rm -rf "$tmp_dir"
    return 0
}

# ─── Raw-fetch ref resolution (apx, mlflow) ───────────────────

# resolve_ref <owner/repo> <requested>
#   ""/"latest" → highest stable semver tag (prereleases excluded unless
#                 INCLUDE_PRERELEASES=1; falls back to main if no tags).
#   main/master → passed through.
#   anything else → verified to exist as a tag/branch/SHA (fails loud).
# Uses `git ls-remote` (no API rate limits; git is a hard prerequisite) and
# `sort -V` (GNU coreutils; available in macOS bash environments).
resolve_ref() {
    local repo=$1 requested=$2
    local git_url="https://github.com/${repo}.git"
    case "$requested" in
        ""|latest)
            local tags pattern best
            tags=$(git ls-remote --tags --refs "$git_url" 2>/dev/null | sed 's|.*refs/tags/||')
            pattern='^v?[0-9]+\.[0-9]+\.[0-9]+$'
            [ "$INCLUDE_PRERELEASES" = "1" ] && pattern='^v?[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.]+)?$'
            best=$(echo "$tags" | grep -E "$pattern" | sort -V | tail -1)
            if [ -n "$best" ]; then
                echo "$best"
            else
                warn "Could not resolve latest tag for ${repo} — falling back to main" >&2
                echo "main"
            fi
            ;;
        main|master)
            echo "$requested"
            ;;
        *)
            if git ls-remote "$git_url" "refs/tags/${requested}" "refs/heads/${requested}" 2>/dev/null | grep -q .; then
                echo "$requested"
            elif curl -fsSL -o /dev/null "https://api.github.com/repos/${repo}/commits/${requested}" 2>/dev/null; then
                echo "$requested"  # bare commit SHA (not addressable via ls-remote)
            else
                die "Ref '${requested}' not found in ${repo}"
            fi
            ;;
    esac
}

# Resolve refs for all selected raw-fetch sources (records globals for the
# fetch URLs, summary, dry run, and lockfile)
MLFLOW_RESOLVED_REF=""
APX_RESOLVED_REF=""
resolve_fetch_refs() {
    [ -n "$SELECTED_MLFLOW_SKILLS" ] && MLFLOW_RESOLVED_REF=$(resolve_ref "mlflow/skills" "$MLFLOW_REF")
    [ -n "$SELECTED_APX_SKILLS" ] && APX_RESOLVED_REF=$(resolve_ref "databricks-solutions/apx" "$APX_REF")
    return 0
}

# Best-effort commit SHA for a ref (empty on failure). Prefers the peeled
# tag object (^{}) so annotated tags resolve to the commit they point at.
github_sha() {
    local out sha
    out=$(git ls-remote "https://github.com/$1.git" "refs/tags/$2^{}" "refs/tags/$2" "refs/heads/$2" 2>/dev/null)
    sha=$(echo "$out" | grep '\^{}' | head -1 | cut -f1)
    [ -z "$sha" ] && sha=$(echo "$out" | head -1 | cut -f1)
    if [ -z "$sha" ]; then
        sha=$(curl -fsSL "https://api.github.com/repos/$1/commits/$2" 2>/dev/null \
            | grep -m1 '"sha":' | sed -E 's/.*"sha": *"([^"]+)".*/\1/')
    fi
    echo "$sha"
}

# Record what was installed and from where (skills.lock in the scope-local state dir)
write_lockfile() {
    local lock="$STATE_DIR/skills.lock"
    mkdir -p "$STATE_DIR"
    local now entries="" sha kind
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    if [ -n "$SELECTED_MLFLOW_SKILLS" ]; then
        sha=$(github_sha "mlflow/skills" "$MLFLOW_RESOLVED_REF")
        entries="    \"mlflow/skills\": {\"requested_ref\": \"${MLFLOW_REF}\", \"resolved_kind\": \"branch\", \"resolved_ref\": \"${MLFLOW_RESOLVED_REF}\", \"resolved_sha\": \"${sha}\", \"fetched_at\": \"${now}\"}"
    fi
    if [ -n "$SELECTED_APX_SKILLS" ]; then
        kind="release_tag"
        case "$APX_RESOLVED_REF" in main|master) kind="branch" ;; esac
        sha=$(github_sha "databricks-solutions/apx" "$APX_RESOLVED_REF")
        entries="${entries:+$entries,
}    \"databricks-solutions/apx\": {\"requested_ref\": \"${APX_REF}\", \"resolved_kind\": \"${kind}\", \"resolved_ref\": \"${APX_RESOLVED_REF}\", \"resolved_sha\": \"${sha}\", \"fetched_at\": \"${now}\"}"
    fi
    if [ -n "$SELECTED_AGENT_B_SKILLS" ]; then
        local cli_version
        cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        entries="${entries:+$entries,
}    \"databricks/databricks-agent-skills\": {\"install_method\": \"databricks-aitools\", \"cli_version\": \"${cli_version}\", \"skills_release\": \"${AGENT_B_RELEASE}\", \"fetched_at\": \"${now}\"}"
    fi

    [ -z "$entries" ] && return 0
    printf '{\n  "sources": {\n%s\n  }\n}\n' "$entries" > "$lock"
}

# ─── Dry run ──────────────────────────────────────────────────
dry_run_report() {
    map_aitools_agents
    echo ""
    echo -e "${B}Dry run — nothing was installed${N}"
    echo "────────────────────────────────"
    msg "Bundled skills (this repo):  ${SELECTED_LOCAL_SKILLS:-<none>}"
    msg "MLflow skills @ ${MLFLOW_RESOLVED_REF:-n/a}: ${SELECTED_MLFLOW_SKILLS:-<none>}"
    msg "APX skills @ ${APX_RESOLVED_REF:-n/a}: ${SELECTED_APX_SKILLS:-<none>}"
    if [ -n "$SELECTED_AGENT_B_SKILLS" ]; then
        local skills_csv exp_flag=""
        skills_csv=$(echo "$SELECTED_AGENT_B_SKILLS" | tr -s ' ' ',' | sed 's/^,//;s/,$//')
        agent_b_needs_experimental && exp_flag=" --experimental"
        msg "Agent skills (databricks-agent-skills${AGENT_B_RELEASE:+ @ $AGENT_B_RELEASE}): ${SELECTED_AGENT_B_SKILLS}"
        if [ -n "$AITOOLS_AGENTS" ]; then
            msg "Would run: ${B}databricks aitools install --scope ${SCOPE} --agents ${AITOOLS_AGENTS} --skills ${skills_csv}${exp_flag} -p ${PROFILE}${N}"
        fi
        local mode="symlink from the aitools canonical store"
        [ -z "$AITOOLS_AGENTS" ] && mode="copy via a temp-dir aitools install"
        msg "Would deliver agent skills to every selected tool ($mode); entries aitools creates are left to aitools:"
        local dir base_dir
        [ "$SCOPE" = "global" ] && base_dir="$HOME" || base_dir="$(pwd)"
        while IFS= read -r dir; do
            [ -n "$dir" ] && msg "  → $dir"
        done < <(agent_skill_target_dirs "$base_dir")
    else
        msg "Agent skills: <none>"
    fi
    echo ""
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
            ok "$PKG ($(uv --version 2>/dev/null || echo 'unknown version'))"
        else
            die "uv is required but not found on your PATH.
   Install it with: ${B}curl -LsSf https://astral.sh/uv/install.sh | sh${N}
   Then re-run this installer."
        fi
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

# Clone or update the repo sources into $REPO_DIR (needed for bundled skills
# and the MCP server setup script). Idempotent.
clone_repo() {
    if [ -d "$REPO_DIR/.git" ]; then
        git -C "$REPO_DIR" fetch -q --depth 1 origin "$BRANCH" 2>/dev/null || true
        git -C "$REPO_DIR" reset --hard FETCH_HEAD 2>/dev/null || {
            rm -rf "$REPO_DIR"
            git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR" \
                || die "Could not clone branch '$BRANCH' from $REPO_URL — check your network and that the branch exists."
        }
    else
        mkdir -p "$INSTALL_DIR"
        git -c advice.detachedHead=false clone -q --depth 1 --branch "$BRANCH" "$REPO_URL" "$REPO_DIR" \
            || die "Could not clone branch '$BRANCH' from $REPO_URL — check your network and that the branch exists."
    fi
    ok "Repository cloned ($BRANCH)"
}

# Setup the (deprecated, opt-in) MCP server by delegating the venv build to
# databricks-mcp-server/setup.sh — that script is the single source of truth for
# the Python environment, so the installer doesn't duplicate venv/pip logic here.
setup_mcp() {
    step "Setting up MCP server"
    clone_repo

    local setup_script="$REPO_DIR/databricks-mcp-server/setup.sh"
    [ -f "$setup_script" ] || die "MCP setup script not found at $setup_script"

    msg "Building MCP server environment (databricks-mcp-server/setup.sh)..."
    local quiet_flag=""
    [ "$SILENT" = true ] && quiet_flag="--quiet"
    bash "$setup_script" --venv-dir "$VENV_DIR" $quiet_flag || die "MCP server setup failed"
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
            windsurf)
                if [ "$SCOPE" = "global" ]; then
                    dirs+=("$HOME/.codeium/windsurf/skills")
                else
                    dirs+=("$base_dir/.windsurf/skills")
                fi
                ;;
            opencode)
                if [ "$SCOPE" = "global" ]; then
                    dirs+=("$HOME/.config/opencode/skills")
                else
                    dirs+=("$base_dir/.opencode/skills")
                fi
                ;;
            kiro)
                if [ "$SCOPE" = "global" ]; then
                    dirs+=("$HOME/.kiro/skills")
                else
                    dirs+=("$base_dir/.kiro/skills")
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
    local local_count mlflow_count apx_count
    local_count=$(_count $SELECTED_LOCAL_SKILLS)
    mlflow_count=$(_count $SELECTED_MLFLOW_SKILLS)
    apx_count=$(_count $SELECTED_APX_SKILLS)
    local total_count=$((local_count + mlflow_count + apx_count))
    msg "Installing ${B}${total_count}${N} skills (agent skills are installed separately via databricks aitools)"

    # Skills this installer manages directly. Agent skills are deliberately NOT
    # in this set: any same-named entry from an older install is a stale real
    # copy that must be removed — `databricks aitools` will not overwrite an
    # existing real directory, so leaving it would shadow the new install.
    # (Symlinks for tools aitools can't target are re-created each run.)
    local all_new_skills="$SELECTED_LOCAL_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS"

    # Clean up previously installed skills that are no longer managed here
    # Check scope-local manifest first, fall back to global for upgrades from older versions
    local manifest="$STATE_DIR/.installed-skills"
    [ ! -f "$manifest" ] && [ "$SCOPE" = "project" ] && [ -f "$INSTALL_DIR/.installed-skills" ] && manifest="$INSTALL_DIR/.installed-skills"
    if [ -f "$manifest" ]; then
        while IFS='|' read -r prev_dir prev_skill; do
            [ -z "$prev_skill" ] && continue
            # Skip if this skill is still selected (exact match — see _in_list for why)
            if _in_list "$prev_skill" "$all_new_skills"; then
                continue
            fi
            # Remove real dirs and symlinks alike (rm -rf on a symlink removes the link)
            if [ -d "$prev_dir/$prev_skill" ] || [ -L "$prev_dir/$prev_skill" ]; then
                rm -rf "$prev_dir/$prev_skill"
                msg "${D}Removed previously installed skill: $prev_skill${N}"
            fi
        done < "$manifest"
    fi

    # Start fresh manifest (always write to scope-local state dir)
    manifest="$STATE_DIR/.installed-skills"
    mkdir -p "$STATE_DIR"
    : > "$manifest.tmp"

    local mlflow_raw_url="$MLFLOW_BASE_URL/${MLFLOW_RESOLVED_REF:-main}"
    local apx_raw_url="$APX_BASE_URL/${APX_RESOLVED_REF:-main}/skills/apx"

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
        # Install bundled Databricks skills from this repo
        for skill in $SELECTED_LOCAL_SKILLS; do
            local src="$REPO_DIR/databricks-skills/$skill"
            [ ! -d "$src" ] && continue
            rm -rf "$dir/$skill"
            cp -r "$src" "$dir/$skill"
            echo "$dir|$skill" >> "$manifest.tmp"
        done
        ok "Databricks skills ($local_count) → ${dir#$HOME/}"

        # Install MLflow skills from mlflow/skills repo
        if [ -n "$SELECTED_MLFLOW_SKILLS" ]; then
            for skill in $SELECTED_MLFLOW_SKILLS; do
                local dest_dir="$dir/$skill"
                mkdir -p "$dest_dir"
                local url="$mlflow_raw_url/$skill/SKILL.md"
                if curl -fsSL "$url" -o "$dest_dir/SKILL.md" 2>/dev/null; then
                    # Try to fetch optional reference files
                    for ref in reference.md examples.md api.md; do
                        curl -fsSL "$mlflow_raw_url/$skill/$ref" -o "$dest_dir/$ref" 2>/dev/null || true
                    done
                    echo "$dir|$skill" >> "$manifest.tmp"
                else
                    rm -rf "$dest_dir"
                fi
            done
            ok "MLflow skills ($mlflow_count, @ ${MLFLOW_RESOLVED_REF}) → ${dir#$HOME/}"
        fi

        # Install APX skills from databricks-solutions/apx repo
        if [ -n "$SELECTED_APX_SKILLS" ]; then
            for skill in $SELECTED_APX_SKILLS; do
                local dest_dir="$dir/$skill"
                mkdir -p "$dest_dir"
                local url="$apx_raw_url/SKILL.md"
                if curl -fsSL "$url" -o "$dest_dir/SKILL.md" 2>/dev/null; then
                    # Try to fetch optional reference files
                    for ref in backend-patterns.md frontend-patterns.md; do
                        curl -fsSL "$apx_raw_url/$ref" -o "$dest_dir/$ref" 2>/dev/null || true
                    done
                    echo "$dir|$skill" >> "$manifest.tmp"
                else
                    rmdir "$dest_dir" 2>/dev/null || warn "Could not install APX skill '$skill' — consider removing $dest_dir if it is no longer needed"
                fi
            done
            ok "APX skills ($apx_count, @ ${APX_RESOLVED_REF}) → ${dir#$HOME/}"
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
# Write/merge an MCP server entry into a JSON config.
#   $1 path        target config file
#   $2 root_key    top-level key: "mcpServers" (Claude/Cursor/Gemini/Windsurf/Kiro)
#                  or "servers" (Copilot)
#   $3 defer       "true" to include Claude's defer_loading hint, else "false"
# Replaces the old write_mcp_json / write_copilot_mcp_json / write_gemini_mcp_json
# trio, which differed only in those two parameters.
write_mcp_json_config() {
    local path=$1 root_key=$2 defer=$3
    mkdir -p "$(dirname "$path")"

    # Backup existing file before any modifications
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

write_opencode_json() {
    local path=$1
    mkdir -p "$(dirname "$path")"

    # Backup existing file before any modifications
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

    # Fallback: only safe for new files
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
                [ "$SCOPE" = "global" ] && write_mcp_json_config "$HOME/.claude.json" mcpServers true || write_mcp_json_config "$base_dir/.mcp.json" mcpServers true
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
        if [ -n "$SELECTED_AGENT_B_SKILLS" ]; then
            msg "Agent skills are managed by ${B}databricks aitools${N} — update with ${B}databricks aitools update${N}"
        fi
        echo ""
        msg "${B}Next steps:${N}"
        local step=1
        if [ "$INSTALL_MCP" = true ] && echo "$TOOLS" | grep -q cursor; then
            msg "${R}${step}. Enable MCP in Cursor: ${B}Cursor → Settings → Cursor Settings → Tools & MCP → Toggle 'databricks'${N}"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q copilot; then
            if [ "$INSTALL_MCP" = true ]; then
                msg "${step}. In Copilot Chat, click ${B}Configure Tools${N} (tool icon, bottom-right) and enable ${B}databricks${N}"
                step=$((step + 1))
            fi
            msg "${step}. Use Copilot in ${B}Agent mode${N} to access Databricks skills"
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
        if [ "$INSTALL_MCP" = true ] && echo "$TOOLS" | grep -q windsurf; then
            msg "${step}. Restart Windsurf to pick up the ${B}databricks${N} MCP server (Windsurf → Settings → Windsurf Settings → MCP)"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q opencode; then
            msg "${step}. Launch OpenCode in your project: ${B}opencode${N}"
            step=$((step + 1))
        fi
        if echo "$TOOLS" | grep -q kiro; then
            msg "${step}. Open your project in Kiro to use Databricks skills and MCP tools"
            step=$((step + 1))
        fi
        msg "${step}. Open your project in your tool of choice"
        step=$((step + 1))
        msg "${step}. Start prompting your AI assistant to interact with Databricks"
        echo ""
    fi
}

# Prompt for installation scope
prompt_scope() {
    if [ "$SILENT" = true ] || ! is_interactive; then
        return
    fi

    echo ""
    echo -e "  ${B}Select installation scope${N}"

    # Keep hints short — long ones wrap past the terminal width and break the
    # cursor-up redraw in radio_select (each arrow press would stack a copy).
    SCOPE=$(radio_select \
        "Project|project|on|Current directory (.claude/, etc.)" \
        "Global|global|off|Home directory (~/.claude/, etc.)" \
    )
}

# Prompt to run auth
prompt_auth() {
    if [ "$SILENT" = true ] || ! is_interactive; then
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
    # --list-skills exits early (uses the live aitools inventory when available)
    [ "${LIST_SKILLS:-false}" = true ] && list_skills_and_exit

    if [ "$SILENT" = false ]; then
        echo ""
        echo -e "${B}Databricks AI Dev Kit Installer${N}"
        echo "────────────────────────────────"
    fi

    # Check dependencies
    step "Checking prerequisites"
    check_deps

    # Discover the agent-skills inventory (live via `databricks aitools list`, or fallback)
    fetch_agent_b_inventory

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
        resolve_fetch_refs
        # Count for display
        local sk_count
        sk_count=$(_count $SELECTED_LOCAL_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS $SELECTED_AGENT_B_SKILLS)
        if [ -n "$USER_SKILLS" ]; then
            ok "Custom selection ($sk_count skills)"
        else
            ok "Profile: ${SKILLS_PROFILE:-all} ($sk_count skills)"
        fi
    fi

    # ── Step 4.5: MCP server opt-in (deprecated) ──
    prompt_mcp_install

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
                echo -e "  Skills:      ${G}custom selection${N} ${Y}(will be overwritten, backup your changes first)${N}"
            else
                local sk_total
                sk_total=$(_count $SELECTED_LOCAL_SKILLS $SELECTED_MLFLOW_SKILLS $SELECTED_APX_SKILLS $SELECTED_AGENT_B_SKILLS)
                echo -e "  Skills:      ${G}${SKILLS_PROFILE:-all} ($sk_total skills)${N} ${Y}(will be overwritten, backup your changes first)${N}"
            fi
            [ -n "$SELECTED_AGENT_B_SKILLS" ] && echo -e "  Agent skills: ${G}via databricks aitools${N} ${D}(requires Databricks CLI v${MIN_AITOOLS_CLI_VERSION}+)${N}"
            [ "$INSTALL_EXPERIMENTAL" = false ] && echo -e "  Experimental: ${Y}excluded${N} ${D}(--experimental false)${N}"
            [ -n "$SELECTED_APX_SKILLS" ] && [ -n "$APX_RESOLVED_REF" ] && echo -e "  APX ref:     ${G}${APX_RESOLVED_REF}${N}"
        fi
        [ "$INSTALL_MCP" = true ]    && echo -e "  MCP config:  ${G}yes${N}"
        echo ""
    fi

    # ── Dry run: report the plan and exit before any changes ──
    if [ "$DRY_RUN" = true ]; then
        dry_run_report
        exit 0
    fi

    if [ "$SILENT" = false ] && is_interactive; then
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
    
    # Setup MCP server (opt-in). Otherwise clone sources only if needed for bundled skills.
    if [ "$INSTALL_MCP" = true ]; then
        setup_mcp
    elif [ ! -d "$REPO_DIR" ] && [ -n "$SELECTED_LOCAL_SKILLS" ]; then
        step "Downloading sources"
        clone_repo
    fi
    
    # Install skills managed by this installer (bundled + mlflow + apx)
    [ "$INSTALL_SKILLS" = true ] && install_skills "$base_dir"

    # Install agent skills (delegated to `databricks aitools`)
    [ "$INSTALL_SKILLS" = true ] && install_agent_b_skills "$base_dir"

    # Record resolved sources
    [ "$INSTALL_SKILLS" = true ] && write_lockfile

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
