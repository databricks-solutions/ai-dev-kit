#!/bin/bash
# Deploy skills to Databricks Assistant skills folder
# This enables the built-in Assistant in Agent mode to use all skills
#
# PREREQUISITE: Run ./install_skills.sh first to install skills locally
#
# Usage: ./install_to_dbx_assistant.sh <profile-name>

set -e

PROFILE=${1:-"DEFAULT"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOCAL_SKILLS_DIR="$PROJECT_ROOT/.claude/skills"

echo "================================================"
echo "Deploying Skills to Databricks Assistant"
echo "================================================"
echo "Profile: $PROFILE"
echo ""

# Check if local skills are installed
if [ ! -d "$LOCAL_SKILLS_DIR" ] || [ -z "$(ls -A "$LOCAL_SKILLS_DIR" 2>/dev/null)" ]; then
    echo "Error: Local skills not found at $LOCAL_SKILLS_DIR"
    echo ""
    echo "Please run ./install_skills.sh first to install skills locally."
    echo "This will install both Databricks and MLflow skills."
    echo ""
    echo "Example:"
    echo "  cd databricks-skills"
    echo "  ./install_skills.sh"
    echo "  ./install_to_dbx_assistant.sh $PROFILE"
    exit 1
fi

# Get current user email
USER_EMAIL=$(databricks current-user me --profile "$PROFILE" --output json 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('userName', ''))" 2>/dev/null || echo "")
if [ -z "$USER_EMAIL" ]; then
    echo "Error: Could not determine user email."
    exit 1
fi

# Skills destination in workspace
SKILLS_PATH="/Users/$USER_EMAIL/.assistant/skills"

echo "User: $USER_EMAIL"
echo "Skills Path: $SKILLS_PATH"
echo ""

# Create the skills directory
echo "Step 1: Creating skills directory..."
databricks workspace mkdirs "$SKILLS_PATH" --profile "$PROFILE" 2>/dev/null || true
echo ""

# Function to upload a skill directory
upload_skill() {
    local skill_dir="$1"
    # Remove trailing slash if present
    skill_dir="${skill_dir%/}"
    local skill_name=$(basename "$skill_dir")
    
    # Skip hidden dirs, TEMPLATE, and non-skill directories
    if [[ "$skill_name" == "."* ]] || [[ "$skill_name" == "TEMPLATE" ]] || [[ ! -d "$skill_dir" ]]; then
        return
    fi
    
    # Check if it has a SKILL.md
    if [[ ! -f "$skill_dir/SKILL.md" ]]; then
        return
    fi
    
    echo "  Uploading skill: $skill_name"
    
    # Create skill directory in workspace
    databricks workspace mkdirs "$SKILLS_PATH/$skill_name" --profile "$PROFILE" 2>/dev/null || true
    
    # Upload all markdown, python, and yaml files in the skill directory
    find "$skill_dir" -type f \( -name "*.md" -o -name "*.py" -o -name "*.yaml" -o -name "*.yml" -o -name "*.sh" \) | while read -r file; do
        # Get the relative path within the skill directory
        rel_path="${file#$skill_dir/}"
        dest_path="$SKILLS_PATH/$skill_name/$rel_path"
        
        # Create parent directories if needed (for subdirs like scripts/)
        parent_dir=$(dirname "$dest_path")
        if [[ "$parent_dir" != "$SKILLS_PATH/$skill_name" ]]; then
            databricks workspace mkdirs "$parent_dir" --profile "$PROFILE" 2>/dev/null || true
        fi
        
        # Upload file
        databricks workspace import "$dest_path" --file "$file" --profile "$PROFILE" --format AUTO --overwrite 2>/dev/null || true
    done
}

# Upload all skills from local .claude/skills directory
echo "Step 2: Uploading skills from $LOCAL_SKILLS_DIR..."
for skill_dir in "$LOCAL_SKILLS_DIR"/*/; do
    upload_skill "$skill_dir"
done
echo ""

# List uploaded skills
echo "Step 3: Verifying deployment..."
echo ""
databricks workspace list "$SKILLS_PATH" --profile "$PROFILE" 2>/dev/null || echo "  (Could not list skills)"
echo ""

echo "================================================"
echo "Deployment complete!"
echo ""
echo "Your Databricks Assistant in Agent mode now has access to:"
echo ""
skills_count=$(find "$LOCAL_SKILLS_DIR" -maxdepth 1 -type d -exec test -f {}/SKILL.md \; -print 2>/dev/null | wc -l | tr -d ' ')
echo "  $skills_count skills deployed to: $SKILLS_PATH"
echo ""
echo "To use:"
echo "  1. Open a Databricks notebook"
echo "  2. Open the Assistant panel"
echo "  3. Switch to 'Agent' mode"
echo "  4. Ask: 'Create a dashboard for my sales data'"
echo ""
echo "The Assistant will automatically load relevant skills!"
echo "================================================"
