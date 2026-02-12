#!/bin/bash
#
# Databricks Skills Installer
#
# Installs Databricks skills for Claude Code into your project.
# These skills teach Claude how to work with Databricks using MCP tools.
#
# Usage:
#   # Install all skills (Databricks + MLflow)
#   curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash
#
#   # Install specific skills (can mix Databricks and MLflow skills)
#   curl -sSL https://raw.githubusercontent.com/databricks-solutions/ai-dev-kit/main/databricks-skills/install_skills.sh | bash -s -- asset-bundles agent-evaluation
#
#   # Or run locally
#   ./install_skills.sh                              # Install all skills
#   ./install_skills.sh asset-bundles agent-evaluation  # Install specific skills
#   ./install_skills.sh --mlflow-version v1.0.0      # Pin MLflow skills version
#   ./install_skills.sh --local                      # Install Databricks skills from local directory
#   ./install_skills.sh --list                       # List available skills
#   ./install_skills.sh --help                       # Show help
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

# MLflow skills configuration
MLFLOW_REPO_RAW_URL="https://raw.githubusercontent.com/mlflow/skills"
MLFLOW_REPO_REF="main"

# Databricks skills (hosted in this repo)
DATABRICKS_SKILLS="agent-bricks aibi-dashboards asset-bundles databricks-app-apx databricks-app-python databricks-config databricks-dbsql databricks-docs databricks-genie databricks-jobs databricks-python-sdk databricks-unity-catalog lakebase-autoscale lakebase-provisioned metric-views mlflow-evaluation model-serving spark-declarative-pipelines spark-structured-streaming synthetic-data-generation unstructured-pdf-generation vector-search"

# MLflow skills (fetched from mlflow/skills repo)
MLFLOW_SKILLS="agent-evaluation analyze-mlflow-chat-session analyze-mlflow-trace instrumenting-with-mlflow-tracing mlflow-onboarding querying-mlflow-metrics retrieving-mlflow-traces searching-mlflow-docs"

# All available skills
ALL_SKILLS="$DATABRICKS_SKILLS $MLFLOW_SKILLS"

# Get skill description
get_skill_description() {
    case "$1" in
        # Databricks skills
        "agent-bricks") echo "Knowledge Assistants, Genie Spaces, Multi-Agent Supervisors" ;;
        "aibi-dashboards") echo "AI/BI Dashboards - create and manage dashboards" ;;
        "asset-bundles") echo "Databricks Asset Bundles - deployment and configuration" ;;
        "databricks-app-apx") echo "Databricks Apps with React/Next.js (APX framework)" ;;
        "databricks-app-python") echo "Databricks Apps with Python (Dash, Streamlit)" ;;
        "databricks-config") echo "Profile authentication setup for Databricks" ;;
        "databricks-dbsql") echo "Databricks SQL - SQL scripting, MVs, geospatial, AI functions, federation" ;;
        "databricks-docs") echo "Documentation reference via llms.txt" ;;
        "databricks-genie") echo "Genie Spaces - create, curate, and query via Conversation API" ;;
        "databricks-jobs") echo "Databricks Lakeflow Jobs - workflow orchestration" ;;
        "databricks-python-sdk") echo "Databricks Python SDK, Connect, and REST API" ;;
        "databricks-unity-catalog") echo "System tables, volumes, and FGAC policy governance" ;;
        "lakebase-autoscale") echo "Lakebase Autoscale - managed PostgreSQL with autoscaling" ;;
        "lakebase-provisioned") echo "Lakebase Provisioned - data connections and reverse ETL" ;;
        "metric-views") echo "Unity Catalog Metric Views - governed business metrics in YAML" ;;
        "model-serving") echo "Model Serving - deploy MLflow models and AI agents" ;;
        "spark-declarative-pipelines") echo "Spark Declarative Pipelines (SDP/LDP/DLT)" ;;
        "spark-structured-streaming") echo "Spark Structured Streaming patterns and best practices" ;;
        "synthetic-data-generation") echo "Synthetic test data generation" ;;
        "unstructured-pdf-generation") echo "Generate synthetic PDFs for RAG" ;;
        "vector-search") echo "Vector Search - endpoints, indexes, and queries for RAG" ;;
        # MLflow skills (from mlflow/skills repo)
        "agent-evaluation") echo "End-to-end agent evaluation workflow" ;;
        "analyze-mlflow-chat-session") echo "Debug multi-turn conversations" ;;
        "analyze-mlflow-trace") echo "Debug traces, spans, and assessments" ;;
        "instrumenting-with-mlflow-tracing") echo "Add MLflow tracing to Python/TypeScript" ;;
        "mlflow-onboarding") echo "MLflow setup guide for new users" ;;
        "querying-mlflow-metrics") echo "Aggregated metrics and time-series analysis" ;;
        "retrieving-mlflow-traces") echo "Trace search and filtering" ;;
        "searching-mlflow-docs") echo "Search MLflow documentation" ;;
        *) echo "Unknown skill" ;;
    esac
}

# Get extra files for a Databricks skill (besides SKILL.md)
get_skill_extra_files() {
    case "$1" in
        "agent-bricks") echo "1-knowledge-assistants.md 3-multi-agent-supervisors.md" ;;
        "aibi-dashboards") echo "widget-reference.md sql-patterns.md" ;;
        "databricks-genie") echo "spaces.md conversation.md" ;;
        "asset-bundles") echo "alerts_guidance.md SDP_guidance.md" ;;
        "databricks-app-apx") echo "backend-patterns.md best-practices.md frontend-patterns.md" ;;
        "databricks-app-python") echo "dash.md streamlit.md README.md" ;;
        "databricks-jobs") echo "task-types.md triggers-schedules.md notifications-monitoring.md examples.md" ;;
        "databricks-python-sdk") echo "doc-index.md examples/1-authentication.py examples/2-clusters-and-jobs.py examples/3-sql-and-warehouses.py examples/4-unity-catalog.py examples/5-serving-and-vector-search.py" ;;
        "databricks-unity-catalog") echo "5-system-tables.md 6-volumes.md 7-fgac-overview.md 8-fgac-sql-generation.md 9-fgac-sdk-and-tools.md 10-uc-acls.md" ;;
        "lakebase-autoscale") echo "projects.md branches.md computes.md connection-patterns.md reverse-etl.md" ;;
        "lakebase-provisioned") echo "connection-patterns.md reverse-etl.md" ;;
        "metric-views") echo "yaml-reference.md patterns.md" ;;
        "mlflow-evaluation") echo "references/CRITICAL-interfaces.md references/GOTCHAS.md references/patterns-context-optimization.md references/patterns-datasets.md references/patterns-evaluation.md references/patterns-scorers.md references/patterns-trace-analysis.md references/user-journeys.md" ;;
        "model-serving") echo "1-classical-ml.md 2-custom-pyfunc.md 3-genai-agents.md 4-tools-integration.md 5-development-testing.md 6-logging-registration.md 7-deployment.md 8-querying-endpoints.md 9-package-requirements.md" ;;
        "spark-declarative-pipelines") echo "1-ingestion-patterns.md 2-streaming-patterns.md 3-scd-patterns.md 4-performance-tuning.md 5-python-api.md 6-dlt-migration.md 7-advanced-configuration.md 8-project-initialization.md" ;;
        "spark-structured-streaming") echo "checkpoint-best-practices.md kafka-streaming.md merge-operations.md multi-sink-writes.md stateful-operations.md stream-static-joins.md stream-stream-joins.md streaming-best-practices.md trigger-and-cost-optimization.md" ;;
        "vector-search") echo "index-types.md" ;;
        *) echo "" ;;
    esac
}

# Check if a skill is from MLflow repo
is_mlflow_skill() {
    local skill=$1
    for mlflow_skill in $MLFLOW_SKILLS; do
        if [ "$skill" = "$mlflow_skill" ]; then
            return 0
        fi
    done
    return 1
}

# Get extra files for an MLflow skill (besides SKILL.md)
get_mlflow_skill_extra_files() {
    case "$1" in
        "agent-evaluation") echo "references/dataset-preparation.md references/scorers-constraints.md references/scorers.md references/setup-guide.md references/tracing-integration.md references/troubleshooting.md scripts/analyze_results.py scripts/create_dataset_template.py scripts/list_datasets.py scripts/run_evaluation_template.py scripts/setup_mlflow.py scripts/validate_agent_tracing.py scripts/validate_auth.py scripts/validate_environment.py scripts/validate_tracing_runtime.py" ;;
        "analyze-mlflow-chat-session") echo "scripts/discover_schema.sh scripts/inspect_turn.sh" ;;
        "analyze-mlflow-trace") echo "references/trace-structure.md" ;;
        "instrumenting-with-mlflow-tracing") echo "references/advanced-patterns.md references/distributed-tracing.md references/feedback-collection.md references/production.md references/python.md references/typescript.md" ;;
        "mlflow-onboarding") echo "" ;;
        "querying-mlflow-metrics") echo "references/api_reference.md scripts/fetch_metrics.py" ;;
        "retrieving-mlflow-traces") echo "" ;;
        "searching-mlflow-docs") echo "" ;;
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
    echo "  --help, -h              Show this help message"
    echo "  --list, -l              List all available skills"
    echo "  --all, -a               Install all skills (default if no skills specified)"
    echo "  --local                 Install from local files instead of downloading"
    echo "  --mlflow-version <ref>  Pin MLflow skills to specific version/branch/tag (default: main)"
    echo ""
    echo "Examples:"
    echo "  ./install_skills.sh                          # Install all skills"
    echo "  ./install_skills.sh spark-declarative-pipelines  # Install specific Databricks skill"
    echo "  ./install_skills.sh agent-evaluation         # Install specific MLflow skill"
    echo "  ./install_skills.sh asset-bundles agent-evaluation  # Mix of both sources"
    echo "  ./install_skills.sh --mlflow-version v1.0.0  # Pin MLflow skills version"
    echo "  ./install_skills.sh --local                  # Install all from local directory"
    echo "  ./install_skills.sh --list                   # List available skills"
    echo ""
    echo -e "${GREEN}Databricks Skills:${NC}"
    for skill in $DATABRICKS_SKILLS; do
        echo "  - $skill: $(get_skill_description "$skill")"
    done
    echo ""
    echo -e "${GREEN}MLflow Skills (from github.com/mlflow/skills):${NC}"
    for skill in $MLFLOW_SKILLS; do
        echo "  - $skill: $(get_skill_description "$skill")"
    done
    echo ""
}

# List available skills
list_skills() {
    echo -e "${BLUE}Available Skills:${NC}"
    echo ""
    echo -e "${GREEN}Databricks Skills:${NC}"
    for skill in $DATABRICKS_SKILLS; do
        echo -e "  ${GREEN}$skill${NC}"
        echo -e "    $(get_skill_description "$skill")"
    done
    echo ""
    echo -e "${GREEN}MLflow Skills (from github.com/mlflow/skills):${NC}"
    for skill in $MLFLOW_SKILLS; do
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

# Function to download a Databricks skill
download_databricks_skill() {
    local skill_name=$1
    local skill_dir="$SKILLS_DIR/$skill_name"

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
        echo -e "  Downloading from Databricks repo..."

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

    return 0
}

# Function to download an MLflow skill
download_mlflow_skill() {
    local skill_name=$1
    local skill_dir="$SKILLS_DIR/$skill_name"

    echo -e "  Downloading from MLflow repo (${MLFLOW_REPO_REF})..."

    # Download SKILL.md (required)
    if curl -sSL -f "${MLFLOW_REPO_RAW_URL}/${MLFLOW_REPO_REF}/${skill_name}/SKILL.md" -o "$skill_dir/SKILL.md" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Downloaded SKILL.md"
    else
        echo -e "  ${RED}✗${NC} Failed to download SKILL.md from MLflow repo"
        rm -rf "$skill_dir"
        return 1
    fi

    # Download skill-specific extra files
    local extra_files=$(get_mlflow_skill_extra_files "$skill_name")
    if [ -n "$extra_files" ]; then
        for extra_file in $extra_files; do
            # Create subdirectory if needed
            local extra_file_dir=$(dirname "$skill_dir/${extra_file}")
            mkdir -p "$extra_file_dir"
            if curl -sSL -f "${MLFLOW_REPO_RAW_URL}/${MLFLOW_REPO_REF}/${skill_name}/${extra_file}" -o "$skill_dir/${extra_file}" 2>/dev/null; then
                echo -e "  ${GREEN}✓${NC} Downloaded ${extra_file}"
            else
                echo -e "  ${YELLOW}○${NC} Optional file ${extra_file} not found"
            fi
        done
    fi

    return 0
}

# Function to download a skill (routes to appropriate download function)
download_skill() {
    local skill_name=$1
    local skill_dir="$SKILLS_DIR/$skill_name"

    echo -e "\n${BLUE}Processing skill: ${skill_name}${NC}"

    # Remove existing skill directory to ensure clean install
    if [ -d "$skill_dir" ]; then
        rm -rf "$skill_dir"
    fi

    # Create skill directory
    mkdir -p "$skill_dir"

    # Route to appropriate download function
    if is_mlflow_skill "$skill_name"; then
        if [ "$INSTALL_FROM_LOCAL" = true ]; then
            echo -e "  ${RED}✗${NC} MLflow skills cannot be installed from local (they are fetched from github.com/mlflow/skills)"
            rm -rf "$skill_dir"
            return 1
        fi
        download_mlflow_skill "$skill_name"
    else
        download_databricks_skill "$skill_name"
    fi

    local result=$?
    if [ $result -eq 0 ]; then
        echo -e "  ${GREEN}✓ Installed successfully${NC}"
    fi
    return $result
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
        --mlflow-version)
            if [ -z "$2" ] || [ "${2:0:1}" = "-" ]; then
                echo -e "${RED}Error: --mlflow-version requires a version/ref argument${NC}"
                exit 1
            fi
            MLFLOW_REPO_REF="$2"
            shift 2
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

