#!/bin/bash
# Deploy script for Databricks MCP App
# Usage: ./deploy.sh <profile-name> [app-name]
#
# PREREQUISITE: Run ./databricks-skills/install_skills.sh first
#
# Deploys:
#   - MCP Server (databricks-mcp-server)
#   - Tools Core Library (databricks-tools-core)
#   - Skills Documentation (from .claude/skills/ - Databricks + MLflow)

set -e

PROFILE=${1:-"dbx_shared_demo"}
APP_NAME=${2:-"mcp-ai-dev-kit"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
LOCAL_SKILLS_DIR="$REPO_ROOT/.claude/skills"

echo "================================================"
echo "Deploying AI Dev Kit MCP Server to Databricks"
echo "================================================"
echo "Profile: $PROFILE"
echo "App Name: $APP_NAME"
echo ""

# Check if local skills are installed
if [ ! -d "$LOCAL_SKILLS_DIR" ] || [ -z "$(ls -A "$LOCAL_SKILLS_DIR" 2>/dev/null)" ]; then
    echo "Error: Local skills not found at $LOCAL_SKILLS_DIR"
    echo ""
    echo "Please run ./databricks-skills/install_skills.sh first."
    echo "This will install both Databricks and MLflow skills."
    echo ""
    echo "Example:"
    echo "  cd $REPO_ROOT/databricks-skills"
    echo "  ./install_skills.sh"
    echo "  cd $SCRIPT_DIR"
    echo "  ./deploy.sh $PROFILE"
    exit 1
fi
echo "Skills directory: $LOCAL_SKILLS_DIR"
echo ""

# Get current user email for workspace path
USER_EMAIL=$(databricks current-user me --profile "$PROFILE" --output json 2>/dev/null | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('userName', d.get('emails', [{}])[0].get('value', '')))" 2>/dev/null || echo "")
if [ -z "$USER_EMAIL" ]; then
    echo "Could not determine user email. Using generic path."
    USER_EMAIL="shared"
fi

WORKSPACE_PATH="/Workspace/Users/$USER_EMAIL/apps/$APP_NAME"

echo "Workspace Path: $WORKSPACE_PATH"
echo "Repo Root: $REPO_ROOT"
echo ""

# Step 1: Check if app exists, create if not
echo "Step 1: Checking if app exists..."
if databricks apps get "$APP_NAME" --profile "$PROFILE" &>/dev/null; then
    echo "  App '$APP_NAME' already exists"
else
    echo "  Creating app '$APP_NAME'..."
    databricks apps create "$APP_NAME" --profile "$PROFILE"
fi
echo ""

# Step 2: Create requirements.txt for deployment (uv handles dependencies via pyproject.toml)
echo "Step 2: Preparing deployment package..."

# Create a requirements file with just uv (uv handles the rest via pyproject.toml)
cat > "$SCRIPT_DIR/requirements_deploy.txt" << 'EOF'
uv
EOF

echo "  Created requirements_deploy.txt"
echo ""

# Step 3: Upload source code
echo "Step 3: Uploading source code to workspace..."
# Clean up existing files
databricks workspace delete "$WORKSPACE_PATH" --recursive --profile "$PROFILE" 2>/dev/null || true
databricks workspace mkdirs "$WORKSPACE_PATH" --profile "$PROFILE"

# Upload files
echo "  Uploading app.yaml..."
databricks workspace import "$WORKSPACE_PATH/app.yaml" --file "$SCRIPT_DIR/app.yaml" --profile "$PROFILE" --format AUTO --overwrite

echo "  Uploading requirements.txt..."
databricks workspace import "$WORKSPACE_PATH/requirements.txt" --file "$SCRIPT_DIR/requirements_deploy.txt" --profile "$PROFILE" --format AUTO --overwrite

echo "  Uploading pyproject.toml..."
databricks workspace import "$WORKSPACE_PATH/pyproject.toml" --file "$SCRIPT_DIR/pyproject.toml" --profile "$PROFILE" --format AUTO --overwrite

# Upload the server package
echo "  Uploading server package..."
databricks workspace mkdirs "$WORKSPACE_PATH/server" --profile "$PROFILE"
for f in "$SCRIPT_DIR/server/"*.py; do
    if [ -f "$f" ]; then
        fname=$(basename "$f")
        databricks workspace import "$WORKSPACE_PATH/server/$fname" --file "$f" --profile "$PROFILE" --format AUTO --overwrite
    fi
done

# Upload the MCP server package
echo "  Uploading databricks_mcp_server package..."
databricks workspace mkdirs "$WORKSPACE_PATH/databricks_mcp_server" --profile "$PROFILE"
for f in "$REPO_ROOT/databricks-mcp-server/databricks_mcp_server/"*.py; do
    if [ -f "$f" ]; then
        fname=$(basename "$f")
        databricks workspace import "$WORKSPACE_PATH/databricks_mcp_server/$fname" --file "$f" --profile "$PROFILE" --format AUTO --overwrite
    fi
done

# Upload tools subdirectory
databricks workspace mkdirs "$WORKSPACE_PATH/databricks_mcp_server/tools" --profile "$PROFILE"
for f in "$REPO_ROOT/databricks-mcp-server/databricks_mcp_server/tools/"*.py; do
    if [ -f "$f" ]; then
        fname=$(basename "$f")
        databricks workspace import "$WORKSPACE_PATH/databricks_mcp_server/tools/$fname" --file "$f" --profile "$PROFILE" --format AUTO --overwrite
    fi
done

# Upload the tools core package
echo "  Uploading databricks_tools_core package..."
databricks workspace mkdirs "$WORKSPACE_PATH/databricks_tools_core" --profile "$PROFILE"

# Upload all Python files recursively from databricks-tools-core
upload_dir() {
    local src_dir="$1"
    local dest_dir="$2"
    
    for item in "$src_dir"/*; do
        if [ -d "$item" ]; then
            local dirname=$(basename "$item")
            if [[ "$dirname" != "__pycache__" && "$dirname" != "*.egg-info" ]]; then
                databricks workspace mkdirs "$dest_dir/$dirname" --profile "$PROFILE" 2>/dev/null || true
                upload_dir "$item" "$dest_dir/$dirname"
            fi
        elif [ -f "$item" ]; then
            local fname=$(basename "$item")
            if [[ "$fname" == *.py || "$fname" == *.md || "$fname" == *.sql || "$fname" == *.txt ]]; then
                databricks workspace import "$dest_dir/$fname" --file "$item" --profile "$PROFILE" --format AUTO --overwrite 2>/dev/null || true
            fi
        fi
    done
}

upload_dir "$REPO_ROOT/databricks-tools-core/databricks_tools_core" "$WORKSPACE_PATH/databricks_tools_core"

# Upload the skills documentation
echo "  Uploading skills documentation..."
databricks workspace mkdirs "$WORKSPACE_PATH/skills" --profile "$PROFILE"

upload_skills() {
    local src_dir="$1"
    local dest_dir="$2"
    
    for item in "$src_dir"/*; do
        if [ -d "$item" ]; then
            local dirname=$(basename "$item")
            # Skip hidden directories and TEMPLATE
            if [[ "$dirname" != "."* && "$dirname" != "TEMPLATE" ]]; then
                databricks workspace mkdirs "$dest_dir/$dirname" --profile "$PROFILE" 2>/dev/null || true
                upload_skills "$item" "$dest_dir/$dirname"
            fi
        elif [ -f "$item" ]; then
            local fname=$(basename "$item")
            # Only upload markdown, yaml, and python files
            if [[ "$fname" == *.md || "$fname" == *.yaml || "$fname" == *.yml || "$fname" == *.py ]]; then
                databricks workspace import "$dest_dir/$fname" --file "$item" --profile "$PROFILE" --format AUTO --overwrite 2>/dev/null || true
            fi
        fi
    done
}

upload_skills "$LOCAL_SKILLS_DIR" "$WORKSPACE_PATH/skills"

echo ""

# Step 4: Deploy the app
echo "Step 4: Deploying app..."
databricks apps deploy "$APP_NAME" \
    --source-code-path "$WORKSPACE_PATH" \
    --profile "$PROFILE"

echo ""

# Step 5: Get app info
echo "Step 5: Getting app information..."
echo ""
databricks apps get "$APP_NAME" --profile "$PROFILE"

echo ""
echo "================================================"
echo "Deployment complete!"
echo ""
echo "MCP Server URL: https://<app-url>/mcp"
echo ""
echo "Deployed components:"
echo "  - MCP Server with 12 tool categories"
echo "  - Skills documentation ($(ls -d "$LOCAL_SKILLS_DIR"/*/ 2>/dev/null | wc -l | tr -d ' ') skills)"
echo ""
echo "To use in an agent:"
echo ""
echo "  from databricks_mcp import DatabricksMCPClient"
echo "  from databricks.sdk import WorkspaceClient"
echo ""
echo "  ws = WorkspaceClient(profile='$PROFILE')"
echo "  mcp = DatabricksMCPClient(server_url='<app-url>/mcp', workspace_client=ws)"
echo "  tools = mcp.list_tools()"
echo ""
echo "  # List available skills"
echo "  skills = mcp.call_tool('list_skills', {})"
echo ""
echo "  # Get skill documentation"
echo "  skill = mcp.call_tool('get_skill', {'skill_name': 'aibi-dashboards'})"
echo ""
echo "To view logs:"
echo "  databricks apps logs $APP_NAME --profile $PROFILE"
echo "================================================"
