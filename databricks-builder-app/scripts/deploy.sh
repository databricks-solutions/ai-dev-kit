#!/bin/bash
# Deploy script for Databricks Builder App
# Deploys the app to Databricks Apps platform

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Minimum required Databricks CLI version
MIN_CLI_VERSION="0.278.0"

# Script directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_DIR")"

# Default values
APP_NAME="${APP_NAME:-}"
WORKSPACE_PATH=""
STAGING_DIR=""
SKIP_BUILD="${SKIP_BUILD:-false}"

# Usage information
usage() {
  echo "Usage: $0 <app-name> [options]"
  echo ""
  echo "Deploy the Databricks Builder App to Databricks Apps platform."
  echo ""
  echo "Arguments:"
  echo "  app-name              Name of the Databricks App (required)"
  echo ""
  echo "Options:"
  echo "  --skip-build          Skip frontend build (use existing build)"
  echo "  --staging-dir DIR     Custom staging directory (default: /tmp/<app-name>-deploy)"
  echo "  -h, --help            Show this help message"
  echo ""
  echo "Prerequisites:"
  echo "  1. Databricks CLI configured (databricks auth login)"
  echo "  2. App created in Databricks (databricks apps create <app-name>)"
  echo "  3. Lakebase added as app resource (for database)"
  echo "  4. app.yaml configured with your settings"
  echo ""
  echo "Example:"
  echo "  $0 my-builder-app"
  echo "  APP_NAME=my-builder-app $0"
  echo "  $0 my-builder-app --skip-build"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help)
      usage
      exit 0
      ;;
    --skip-build)
      SKIP_BUILD=true
      shift
      ;;
    --staging-dir)
      STAGING_DIR="$2"
      shift 2
      ;;
    -*)
      echo -e "${RED}Error: Unknown option $1${NC}"
      usage
      exit 1
      ;;
    *)
      if [ -z "$APP_NAME" ]; then
        APP_NAME="$1"
      else
        echo -e "${RED}Error: Unexpected argument $1${NC}"
        usage
        exit 1
      fi
      shift
      ;;
  esac
done

# Validate app name
if [ -z "$APP_NAME" ]; then
  echo -e "${RED}Error: App name is required${NC}"
  echo ""
  usage
  exit 1
fi

# Set derived paths
STAGING_DIR="${STAGING_DIR:-/tmp/${APP_NAME}-deploy}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Databricks Builder App Deployment                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  App Name:     ${GREEN}${APP_NAME}${NC}"
echo -e "  Staging Dir:  ${STAGING_DIR}"
echo -e "  Skip Build:   ${SKIP_BUILD}"
echo ""

# Check prerequisites
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

# Check Databricks CLI
if ! command -v databricks &> /dev/null; then
  echo -e "${RED}Error: Databricks CLI not found. Install with: curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh${NC}"
  exit 1
fi

# Check Databricks CLI version
cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$cli_version" ]; then
  if printf '%s\n%s' "$MIN_CLI_VERSION" "$cli_version" | sort -V -C; then
    echo -e "  ${GREEN}✓${NC} Databricks CLI v${cli_version}"
  else
    echo -e "  ${YELLOW}Warning: Databricks CLI v${cli_version} is outdated (minimum: v${MIN_CLI_VERSION})${NC}"
    echo -e "  ${BOLD}Upgrade:${NC} curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh"
  fi
else
  echo -e "  ${YELLOW}Warning: Could not determine Databricks CLI version${NC}"
fi

# Check if authenticated
if ! databricks auth describe &> /dev/null; then
  echo -e "${RED}Error: Not authenticated with Databricks. Run: databricks auth login${NC}"
  exit 1
fi

# Get workspace info (handle both old and new Databricks CLI JSON formats)
WORKSPACE_HOST=$(databricks auth describe --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
# New CLI format has host under details.host, old format has it at root
host = data.get('host', '') or data.get('details', {}).get('host', '')
print(host)
" 2>/dev/null || echo "")
if [ -z "$WORKSPACE_HOST" ]; then
  echo -e "${RED}Error: Could not determine Databricks workspace. Check your authentication.${NC}"
  echo -e "${YELLOW}Tip: Try setting DATABRICKS_CONFIG_PROFILE=<profile-name> before running this script${NC}"
  echo -e "${YELLOW}     Run 'databricks auth profiles' to see available profiles${NC}"
  exit 1
fi

# Get current user for workspace path
CURRENT_USER=$(databricks current-user me --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
# Handle both formats
print(data.get('userName', data.get('user_name', '')))
" 2>/dev/null || echo "")
if [ -z "$CURRENT_USER" ]; then
  echo -e "${RED}Error: Could not determine current user.${NC}"
  exit 1
fi

WORKSPACE_PATH="/Workspace/Users/${CURRENT_USER}/apps/${APP_NAME}"
echo -e "  Workspace:    ${WORKSPACE_HOST}"
echo -e "  User:         ${CURRENT_USER}"
echo -e "  Deploy Path:  ${WORKSPACE_PATH}"
echo ""

# Check if app exists
echo -e "${YELLOW}[2/6] Verifying app exists...${NC}"
if ! databricks apps get "$APP_NAME" &> /dev/null; then
  echo -e "${RED}Error: App '${APP_NAME}' does not exist.${NC}"
  echo -e "Create it first with: ${GREEN}databricks apps create ${APP_NAME}${NC}"
  exit 1
fi
echo -e "  ${GREEN}✓${NC} App '${APP_NAME}' exists"
echo ""

# Build frontend
echo -e "${YELLOW}[3/6] Building frontend...${NC}"
cd "$PROJECT_DIR/client"

if [ "$SKIP_BUILD" = true ]; then
  if [ ! -d "out" ]; then
    echo -e "${RED}Error: No existing build found at client/out. Cannot skip build.${NC}"
    exit 1
  fi
  echo -e "  ${GREEN}✓${NC} Using existing build (--skip-build)"
else
  # Install dependencies if needed
  if [ ! -d "node_modules" ]; then
    echo "  Installing npm dependencies..."
    npm install --silent
  fi
  
  echo "  Building production bundle..."
  npm run build
  echo -e "  ${GREEN}✓${NC} Frontend built successfully"
fi
cd "$PROJECT_DIR"
echo ""

# Prepare staging directory
echo -e "${YELLOW}[4/6] Preparing deployment package...${NC}"

# Clean and create staging directory
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

# Copy server code
echo "  Copying server code..."
cp -r server "$STAGING_DIR/"
cp app.yaml "$STAGING_DIR/"
cp requirements.txt "$STAGING_DIR/"

# Copy frontend build (server expects it at client/out/)
echo "  Copying frontend build..."
mkdir -p "$STAGING_DIR/client"
cp -r client/out "$STAGING_DIR/client/"

# Copy packages (databricks-tools-core and databricks-mcp-server)
echo "  Copying Databricks packages..."
mkdir -p "$STAGING_DIR/packages"

# Copy databricks-tools-core (only Python source, no tests)
mkdir -p "$STAGING_DIR/packages/databricks_tools_core"
cp -r "$REPO_ROOT/databricks-tools-core/databricks_tools_core/"* "$STAGING_DIR/packages/databricks_tools_core/"

# Copy databricks-mcp-server (only Python source)
mkdir -p "$STAGING_DIR/packages/databricks_mcp_server"
cp -r "$REPO_ROOT/databricks-mcp-server/databricks_mcp_server/"* "$STAGING_DIR/packages/databricks_mcp_server/"

# Copy skills (preserve directory structure)
echo "  Copying skills..."
mkdir -p "$STAGING_DIR/skills"
SKILLS_DIR="$REPO_ROOT/databricks-skills"
if [ -d "$SKILLS_DIR" ]; then
  for skill_dir in "$SKILLS_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    # Skip template and non-skill directories
    if [ "$skill_name" != "TEMPLATE" ] && [ -f "$skill_dir/SKILL.md" ]; then
      # Create skill directory and copy contents (cp -r dir/ copies contents, not dir itself)
      mkdir -p "$STAGING_DIR/skills/$skill_name"
      cp -r "$skill_dir"* "$STAGING_DIR/skills/$skill_name/"
    fi
  done
fi

# Remove __pycache__ directories
find "$STAGING_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

echo -e "  ${GREEN}✓${NC} Deployment package prepared"
echo ""

# Upload to workspace
echo -e "${YELLOW}[5/6] Uploading to Databricks workspace...${NC}"
echo "  Target: ${WORKSPACE_PATH}"
databricks workspace import-dir "$STAGING_DIR" "$WORKSPACE_PATH" --overwrite 2>&1 | tail -5
echo -e "  ${GREEN}✓${NC} Upload complete"
echo ""

# Deploy the app
echo -e "${YELLOW}[6/6] Deploying app...${NC}"
DEPLOY_OUTPUT=$(databricks apps deploy "$APP_NAME" --source-code-path "$WORKSPACE_PATH" 2>&1)
echo "$DEPLOY_OUTPUT"

# Check deployment status
if echo "$DEPLOY_OUTPUT" | grep -q '"state":"SUCCEEDED"'; then
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║                 Deployment Successful!                     ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
  echo ""
  
  # Get app URL
  APP_INFO=$(databricks apps get "$APP_NAME" --output json 2>/dev/null)
  APP_URL=$(echo "$APP_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', 'N/A'))" 2>/dev/null || echo "N/A")
  
  echo -e "  App URL: ${GREEN}${APP_URL}${NC}"
  echo ""
  echo "  Next steps:"
  echo "    1. Open the app URL in your browser"
  echo "    2. If this is first deployment, add Lakebase as an app resource:"
  echo "       databricks apps add-resource $APP_NAME --resource-type database \\"
  echo "         --resource-name lakebase --database-instance <instance-name>"
  echo ""
else
  echo ""
  echo -e "${RED}Deployment may have issues. Check the output above.${NC}"
  exit 1
fi
