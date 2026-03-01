#!/usr/bin/env bash
#
# Initialize project folder structure for PowerBI-to-Databricks conversion.
#
# Usage:
#   bash init_project.sh [project_dir] [FLAGS...]
#
# Flags:
#   --models  Create models/metric_views/ and models/mapping_documents/
#   --gold    Create notebooks/
#   --kpi     Create kpi/
#   --report  Create planreport/
#   --all     Create everything
#
# Without flags, creates the minimal base:
#   input/, reference/, temp/, .gitignore
#
# All user-provided files (PBI models, mappings, DDLs, configs, schema
# dumps, sample reports) go into a single flat input/ folder.
#
# Examples:
#   bash init_project.sh                          # minimal base in cwd
#   bash init_project.sh myproject                # minimal base in myproject/
#   bash init_project.sh myproject --models       # + metric view folders
#   bash init_project.sh myproject --kpi --report # + KPI and report folders
#   bash init_project.sh myproject --all          # everything

set -euo pipefail

# ---- Parse arguments --------------------------------------------------------
PROJECT_DIR="."
FLAGS=()

for arg in "$@"; do
    case "$arg" in
        --*) FLAGS+=("$arg") ;;
        *)
            if [ "$PROJECT_DIR" = "." ]; then
                PROJECT_DIR="$arg"
            fi
            ;;
    esac
done

want_all=false
want_models=false
want_gold=false
want_kpi=false
want_report=false

for flag in "${FLAGS[@]+"${FLAGS[@]}"}"; do
    case "$flag" in
        --all)    want_all=true ;;
        --models) want_models=true ;;
        --gold)   want_gold=true ;;
        --kpi)    want_kpi=true ;;
        --report) want_report=true ;;
        *)        echo "Unknown flag: $flag" >&2; exit 1 ;;
    esac
done

if $want_all; then
    want_models=true
    want_gold=true
    want_kpi=true
    want_report=true
fi

echo "Initializing PowerBI-to-Databricks project in: ${PROJECT_DIR}"

# ---- Always create base folders --------------------------------------------
mkdir -p "${PROJECT_DIR}/input"
mkdir -p "${PROJECT_DIR}/reference"
mkdir -p "${PROJECT_DIR}/temp"

echo "  Created: input/, reference/, temp/"

# ---- Conditional folders ----------------------------------------------------
if $want_models; then
    mkdir -p "${PROJECT_DIR}/models/metric_views"
    mkdir -p "${PROJECT_DIR}/models/mapping_documents"
    echo "  Created: models/metric_views/, models/mapping_documents/"
fi

if $want_gold; then
    mkdir -p "${PROJECT_DIR}/notebooks"
    echo "  Created: notebooks/"
fi

if $want_kpi; then
    mkdir -p "${PROJECT_DIR}/kpi"
    echo "  Created: kpi/"
fi

if $want_report; then
    mkdir -p "${PROJECT_DIR}/planreport"
    echo "  Created: planreport/"
fi

# ---- .gitignore -------------------------------------------------------------
GITIGNORE="${PROJECT_DIR}/.gitignore"
if [ ! -f "${GITIGNORE}" ]; then
    cat > "${GITIGNORE}" << 'EOF'
# Secrets
*.token
.env
input/databricks.yml

# Working files
temp/

# OS files
.DS_Store
Thumbs.db

# Python
__pycache__/
*.pyc
.venv/
EOF
    echo "  Created: ${GITIGNORE}"
fi

# ---- Summary ----------------------------------------------------------------
echo ""
echo "Project structure:"
echo ""
find "${PROJECT_DIR}" -type d | sort | while read -r d; do
    echo "  ${d}/"
done
echo ""
echo "Next steps:"
echo "  - Place ALL input files in input/ (PBI models, mappings, DDLs, configs, sample reports, etc.)"
echo "  - Run the skill workflow -- the agent will scan and classify every file"
if ! $want_models; then
    echo "  - To add metric view folders later: rerun with --models"
fi
if ! $want_gold; then
    echo "  - To add gold-layer folders later: rerun with --gold"
fi
if ! $want_kpi; then
    echo "  - To add KPI definitions folder later: rerun with --kpi"
fi
if ! $want_report; then
    echo "  - To add report planning folder later: rerun with --report"
fi
