#!/bin/bash
#
# Databricks Skills Installer
#
# Installs Databricks skills for Claude Code into your project.
# These skills teach Claude how to work with Databricks using MCP tools.
#
# Usage:
#   # Install all skills
#   curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash
#
#   # Install specific skills
#   curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- sdp asset-bundles
#
#   # Or run locally
#   ./install_skills.sh                    # Install all from URL
#   ./install_skills.sh sdp asset-bundles    # Install specific skills from URL
#   ./install_skills.sh --local            # Install all from local directory
#   ./install_skills.sh --local sdp        # Install specific skill from local directory
#   ./install_skills.sh --list             # List available skills
#   ./install_skills.sh --help             # Show help
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="https://github.com/databricks-solutions/ai-dev-kit"
REPO_RAW_URL="https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main"
SKILLS_DIR=".claude/skills"
INSTALL_FROM_LOCAL=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# All available skills
ALL_SKILLS="aibi-dashboards asset-bundles databricks-app-apx databricks-app-python databricks-jobs databricks-python-sdk mlflow-evaluation spark-declarative-pipelines synthetic-data-generation"

# Get skill description
get_skill_description() {
    case "$1" in
        "aibi-dashboards") echo "AI/BI Dashboards - create and manage dashboards" ;;
        "asset-bundles") echo "Databricks Asset Bundles - deployment and configuration" ;;
        "databricks-app-apx") echo "Databricks Apps with React/Next.js (APX framework)" ;;
        "databricks-app-python") echo "Databricks Apps with Python (Dash, Streamlit)" ;;
        "databricks-jobs") echo "Databricks Lakeflow Jobs - workflow orchestration" ;;
        "databricks-python-sdk") echo "Databricks Python SDK, Connect, and REST API" ;;
        "mlflow-evaluation") echo "MLflow evaluation, scoring, and trace analysis" ;;
        "spark-declarative-pipelines") echo "Spark Declarative Pipelines (SDP/LDP/DLT)" ;;
        "synthetic-data-generation") echo "Synthetic test data generation" ;;
        *) echo "Unknown skill" ;;
    esac
}

# Get extra files for a skill (besides SKILL.md)
get_skill_extra_files() {
    case "$1" in
        "aibi-dashboards") echo "widget-reference.md sql-patterns.md" ;;
        "databricks-app-apx") echo "backend-patterns.md best-practices.md frontend-patterns.md" ;;
        "databricks-app-python") echo "dash.md streamlit.md README.md" ;;
        "databricks-jobs") echo "task-types.md triggers-schedules.md notifications-monitoring.md examples.md" ;;
        "mlflow-evaluation") echo "references/CRITICAL-interfaces.md references/GOTCHAS.md references/patterns-context-optimization.md references/patterns-datasets.md references/patterns-evaluation.md references/patterns-scorers.md references/patterns-trace-analysis.md references/user-journeys.md" ;;
        "spark-declarative-pipelines") echo "1-ingestion-patterns.md 2-streaming-patterns.md 3-scd-patterns.md 4-performance-tuning.md 5-python-api.md 6-dlt-migration.md 7-advanced-configuration.md" ;;
        *) echo "" ;;
    esac
}

# Show usage
show_help() {
    echo -e "${BLUE}Databricks Skills Installer for Claude Code${NC}"
    echo ""
    echo "Usage:"
    echo "  ./install_skills.sh [options] [skill1 skill2 ...]"
    echo ""
    echo "Options:"
    echo "  --help, -h     Show this help message"
    echo "  --list, -l     List all available skills"
    echo "  --all, -a      Install all skills (default if no skills specified)"
    echo "  --local        Install from local files instead of downloading"
    echo ""
    echo "Examples:"
    echo "  ./install_skills.sh                    # Install all skills from URL"
    echo "  ./install_skills.sh sdp                # Install only SDP skill from URL"
    echo "  ./install_skills.sh sdp asset-bundles    # Install specific skills from URL"
    echo "  ./install_skills.sh --local            # Install all skills from local directory"
    echo "  ./install_skills.sh --local sdp        # Install SDP skill from local directory"
    echo "  ./install_skills.sh --list             # List available skills"
    echo ""
    echo "Available skills:"
    for skill in $ALL_SKILLS; do
        echo "  - $skill: $(get_skill_description "$skill")"
    done
    echo ""
}

# List available skills
list_skills() {
    echo -e "${BLUE}Available Databricks Skills:${NC}"
    echo ""
    for skill in $ALL_SKILLS; do
        echo -e "  ${GREEN}$skill${NC}"
        echo -e "    $(get_skill_description "$skill")"
    done
    echo ""
}

# Validate skill name
is_valid_skill() {
    local skill=$1
    for valid_skill in $ALL_SKILLS; do
        if [ "$skill" = "$valid_skill" ]; then
            return 0
        fi
    done
    return 1
}

# Function to download a skill
download_skill() {
    local skill_name=$1
    local skill_dir="$SKILLS_DIR/$skill_name"

    echo -e "\n${BLUE}Processing skill: ${skill_name}${NC}"

    # Check if skill already exists
    if [ -d "$skill_dir" ]; then
        echo -e "${YELLOW}  Skill '$skill_name' already exists.${NC}"
        read -p "  Overwrite? (y/N): " overwrite
        if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
            echo -e "  ${YELLOW}Skipped.${NC}"
            return 0
        fi
        rm -rf "$skill_dir"
    fi

    # Create skill directory
    mkdir -p "$skill_dir"

    if [ "$INSTALL_FROM_LOCAL" = true ]; then
        # Copy from local files
        echo -e "  Copying from local..."
        local source_dir="$SCRIPT_DIR/${skill_name}"

        # Check if source directory exists
        if [ ! -d "$source_dir" ]; then
            echo -e "  ${RED}✗${NC} Source directory not found: $source_dir"
            rm -rf "$skill_dir"
            return 1
        fi

        # Copy SKILL.md (required)
        if [ -f "$source_dir/SKILL.md" ]; then
            cp "$source_dir/SKILL.md" "$skill_dir/SKILL.md"
            echo -e "  ${GREEN}✓${NC} Copied SKILL.md"
        else
            echo -e "  ${RED}✗${NC} SKILL.md not found in $source_dir"
            rm -rf "$skill_dir"
            return 1
        fi

        # Copy skill-specific extra files
        local extra_files=$(get_skill_extra_files "$skill_name")
        if [ -n "$extra_files" ]; then
            for extra_file in $extra_files; do
                if [ -f "$source_dir/${extra_file}" ]; then
                    # Create subdirectory if needed
                    local extra_file_dir=$(dirname "$skill_dir/${extra_file}")
                    mkdir -p "$extra_file_dir"
                    cp "$source_dir/${extra_file}" "$skill_dir/${extra_file}"
                    echo -e "  ${GREEN}✓${NC} Copied ${extra_file}"
                else
                    echo -e "  ${YELLOW}○${NC} Optional file ${extra_file} not found"
                fi
            done
        fi
    else
        # Download from URL
        echo -e "  Downloading..."

        # Download SKILL.md (required)
        if curl -sSL -f "${REPO_RAW_URL}/databricks-skills/${skill_name}/SKILL.md" -o "$skill_dir/SKILL.md" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} Downloaded SKILL.md"
        else
            echo -e "  ${RED}✗${NC} Failed to download SKILL.md"
            rm -rf "$skill_dir"
            return 1
        fi

        # Download skill-specific extra files
        local extra_files=$(get_skill_extra_files "$skill_name")
        if [ -n "$extra_files" ]; then
            for extra_file in $extra_files; do
                # Create subdirectory if needed
                local extra_file_dir=$(dirname "$skill_dir/${extra_file}")
                mkdir -p "$extra_file_dir"
                if curl -sSL -f "${REPO_RAW_URL}/databricks-skills/${skill_name}/${extra_file}" -o "$skill_dir/${extra_file}" 2>/dev/null; then
                    echo -e "  ${GREEN}✓${NC} Downloaded ${extra_file}"
                else
                    echo -e "  ${YELLOW}○${NC} Optional file ${extra_file} not found"
                fi
            done
        fi
    fi

    echo -e "  ${GREEN}✓ Installed successfully${NC}"
    return 0
}

# Parse arguments
SKILLS_TO_INSTALL=""

while [ $# -gt 0 ]; do
    case $1 in
        --help|-h)
            show_help
            exit 0
            ;;
        --list|-l)
            list_skills
            exit 0
            ;;
        --all|-a)
            SKILLS_TO_INSTALL="$ALL_SKILLS"
            shift
            ;;
        --local)
            INSTALL_FROM_LOCAL=true
            shift
            ;;
        -*)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information."
            exit 1
            ;;
        *)
            # Validate skill name
            if is_valid_skill "$1"; then
                SKILLS_TO_INSTALL="$SKILLS_TO_INSTALL $1"
            else
                echo -e "${RED}Unknown skill: $1${NC}"
                echo ""
                echo "Available skills:"
                for skill in $ALL_SKILLS; do
                    echo "  - $skill"
                done
                echo ""
                echo "Use --list for more details."
                exit 1
            fi
            shift
            ;;
    esac
done

# If no skills specified, install all
if [ -z "$SKILLS_TO_INSTALL" ]; then
    SKILLS_TO_INSTALL="$ALL_SKILLS"
fi

# Header
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        Databricks Skills Installer for Claude Code         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if we're in a git repo or project directory
if [ ! -d ".git" ] && [ ! -f "pyproject.toml" ] && [ ! -f "package.json" ] && [ ! -f "databricks.yml" ]; then
    echo -e "${YELLOW}Warning: This doesn't look like a project root directory.${NC}"
    echo -e "Current directory: $(pwd)"
    read -p "Continue anyway? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 1
    fi
fi

# Create .claude/skills directory if it doesn't exist
if [ ! -d "$SKILLS_DIR" ]; then
    echo -e "${GREEN}Creating $SKILLS_DIR directory...${NC}"
    mkdir -p "$SKILLS_DIR"
fi

# Show what will be installed
echo -e "${GREEN}Skills to install:${NC}"
for skill in $SKILLS_TO_INSTALL; do
    echo -e "  - $skill"
done

if [ "$INSTALL_FROM_LOCAL" = true ]; then
    echo -e "\n${BLUE}Installing from local directory: ${SCRIPT_DIR}${NC}"
else
    echo -e "\n${BLUE}Installing from: ${REPO_URL}${NC}"
fi

# Download each skill
echo -e "\n${GREEN}Installing Databricks skills...${NC}"
installed=0
failed=0

for skill in $SKILLS_TO_INSTALL; do
    if download_skill "$skill"; then
        installed=$((installed + 1))
    else
        failed=$((failed + 1))
    fi
done

# Summary
echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Installation complete!${NC}"
echo -e "  Installed: ${installed} skills"
if [ $failed -gt 0 ]; then
    echo -e "  ${RED}Failed: ${failed} skills${NC}"
fi
echo ""
echo -e "${BLUE}Skills installed to: ${SKILLS_DIR}/${NC}"
echo ""
echo -e "Installed skills:"
for skill in $SKILLS_TO_INSTALL; do
    if [ -d "$SKILLS_DIR/$skill" ]; then
        echo -e "  ${GREEN}✓${NC} $skill"
    fi
done
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "  1. Configure the Databricks MCP server in .claude/mcp.json"
echo -e "  2. Start Claude Code in your project directory"
echo -e "  3. Ask Claude to help with Databricks tasks!"
echo ""
echo -e "For MCP server setup, see:"
echo -e "  ${BLUE}${REPO_URL}${NC}"
echo ""
