#!/bin/bash
# Enhanced deploy script for Databricks Builder App
# Orchestrates: Lakebase (via DAB) → App creation → Lakebase permissions → App deploy

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

MIN_CLI_VERSION="0.287.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_DIR")"

APP_NAME="${APP_NAME:-}"
PROFILE="${PROFILE:-}"
STAGING_DIR=""
SKIP_BUILD="${SKIP_BUILD:-false}"
SKIP_LAKEBASE="${SKIP_LAKEBASE:-false}"
SKIP_SKILLS="${SKIP_SKILLS:-false}"
LAKEBASE_PROJECT_ID="${LAKEBASE_PROJECT_ID:-builder-app-db}"

usage() {
  echo "Usage: $0 <app-name> [options]"
  echo ""
  echo "Deploy the Databricks Builder App end-to-end:"
  echo "  1. Provision Lakebase (via Databricks Asset Bundle)"
  echo "  2. Build and stage the app"
  echo "  3. Create the app and configure Lakebase permissions"
  echo "  4. Deploy the app code"
  echo ""
  echo "Arguments:"
  echo "  app-name              Name of the Databricks App (required)"
  echo ""
  echo "Options:"
  echo "  --profile PROFILE     Databricks CLI profile to use"
  echo "  --skip-build          Skip frontend build (use existing build)"
  echo "  --skip-lakebase       Skip Lakebase provisioning (already exists)"
  echo "  --skip-skills        Skip skills installation (reuse cached skills)"
  echo "  --lakebase-id ID      Lakebase project ID (default: builder-app-db)"
  echo "  --staging-dir DIR     Custom staging directory"
  echo "  -h, --help            Show this help message"
  echo ""
  echo "Example:"
  echo "  $0 my-builder-app --profile dbx_shared_demo"
  echo "  $0 my-builder-app --skip-lakebase --skip-build"
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help) usage; exit 0 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    --skip-lakebase) SKIP_LAKEBASE=true; shift ;;
    --skip-skills) SKIP_SKILLS=true; shift ;;
    --lakebase-id) LAKEBASE_PROJECT_ID="$2"; shift 2 ;;
    --staging-dir) STAGING_DIR="$2"; shift 2 ;;
    -*) echo -e "${RED}Error: Unknown option $1${NC}"; usage; exit 1 ;;
    *)
      if [ -z "$APP_NAME" ]; then APP_NAME="$1"; else echo -e "${RED}Error: Unexpected argument $1${NC}"; usage; exit 1; fi
      shift ;;
  esac
done

if [ -z "$APP_NAME" ]; then
  echo -e "${RED}Error: App name is required${NC}"; echo ""; usage; exit 1
fi

CLI_ARGS=""
if [ -n "$PROFILE" ]; then CLI_ARGS="--profile $PROFILE"; fi

STAGING_DIR="${STAGING_DIR:-/tmp/${APP_NAME}-deploy}"
SKILLS_CACHE_DIR="/tmp/${APP_NAME}-skills-cache"
LAKEBASE_ENDPOINT="projects/${LAKEBASE_PROJECT_ID}/branches/production/endpoints/primary"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Databricks Builder App Deployment                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  App Name:          ${GREEN}${APP_NAME}${NC}"
echo -e "  Lakebase ID:       ${LAKEBASE_PROJECT_ID}"
echo -e "  Lakebase Endpoint: ${LAKEBASE_ENDPOINT}"
echo -e "  Profile:           ${PROFILE:-<default>}"
echo -e "  Skip Build:        ${SKIP_BUILD}"
echo -e "  Skip Lakebase:     ${SKIP_LAKEBASE}"
echo -e "  Skip Skills:       ${SKIP_SKILLS}"
echo ""

TOTAL_STEPS=8

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Check prerequisites
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[1/${TOTAL_STEPS}] Checking prerequisites...${NC}"

if ! command -v databricks &> /dev/null; then
  echo -e "${RED}Error: Databricks CLI not found.${NC}"; exit 1
fi

cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$cli_version" ]; then
  if printf '%s\n%s' "$MIN_CLI_VERSION" "$cli_version" | sort -V -C; then
    echo -e "  ${GREEN}✓${NC} Databricks CLI v${cli_version}"
  else
    echo -e "${RED}Error: CLI v${cli_version} too old (need v${MIN_CLI_VERSION}+)${NC}"; exit 1
  fi
fi

if ! databricks auth describe $CLI_ARGS &> /dev/null; then
  echo -e "${RED}Error: Not authenticated. Run: databricks auth login${NC}"; exit 1
fi

WORKSPACE_HOST=$(databricks auth describe $CLI_ARGS --output json 2>/dev/null | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(data.get('host', '') or data.get('details', {}).get('host', ''))
" 2>/dev/null || echo "")
if [ -z "$WORKSPACE_HOST" ]; then echo -e "${RED}Error: Could not determine workspace.${NC}"; exit 1; fi

CURRENT_USER=$(databricks current-user me $CLI_ARGS --output json 2>/dev/null | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(data.get('userName', data.get('user_name', '')))
" 2>/dev/null || echo "")
if [ -z "$CURRENT_USER" ]; then echo -e "${RED}Error: Could not determine current user.${NC}"; exit 1; fi

WORKSPACE_PATH="/Workspace/Users/${CURRENT_USER}/apps/${APP_NAME}"
echo -e "  Workspace:    ${WORKSPACE_HOST}"
echo -e "  User:         ${CURRENT_USER}"
echo -e "  Deploy Path:  ${WORKSPACE_PATH}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Deploy Lakebase via DAB
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[2/${TOTAL_STEPS}] Deploying Lakebase...${NC}"

if [ "$SKIP_LAKEBASE" = true ]; then
  echo -e "  ${GREEN}✓${NC} Skipped (--skip-lakebase)"
else
  cd "$PROJECT_DIR"
  BUNDLE_ARGS=""
  if [ -n "$PROFILE" ]; then BUNDLE_ARGS="--profile $PROFILE"; fi
  databricks bundle deploy $BUNDLE_ARGS --var "lakebase_project_id=${LAKEBASE_PROJECT_ID}" 2>&1
  echo -e "  ${GREEN}✓${NC} Lakebase project '${LAKEBASE_PROJECT_ID}' deployed"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Build frontend
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[3/${TOTAL_STEPS}] Building frontend...${NC}"
cd "$PROJECT_DIR/client"

if [ "$SKIP_BUILD" = true ]; then
  if [ ! -d "out" ]; then echo -e "${RED}Error: No build at client/out.${NC}"; exit 1; fi
  echo -e "  ${GREEN}✓${NC} Using existing build (--skip-build)"
else
  if [ ! -d "node_modules" ]; then echo "  Installing npm dependencies..."; npm install --silent; fi
  echo "  Building production bundle..."
  npm run build
  echo -e "  ${GREEN}✓${NC} Frontend built successfully"
fi
cd "$PROJECT_DIR"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Prepare deployment package
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[4/${TOTAL_STEPS}] Preparing deployment package...${NC}"

rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

echo "  Copying server code..."
cp -r server "$STAGING_DIR/"
cp requirements.txt "$STAGING_DIR/"

echo "  Copying Alembic migrations..."
cp alembic.ini "$STAGING_DIR/"
cp -r alembic "$STAGING_DIR/"

echo "  Copying frontend build..."
mkdir -p "$STAGING_DIR/client"
cp -r client/out "$STAGING_DIR/client/"

echo "  Copying Databricks packages..."
mkdir -p "$STAGING_DIR/packages/databricks_tools_core"
cp -r "$REPO_ROOT/databricks-tools-core/databricks_tools_core/"* "$STAGING_DIR/packages/databricks_tools_core/"
mkdir -p "$STAGING_DIR/packages/databricks_mcp_server"
cp -r "$REPO_ROOT/databricks-mcp-server/databricks_mcp_server/"* "$STAGING_DIR/packages/databricks_mcp_server/"

if [ "$SKIP_SKILLS" = true ] && [ -d "$SKILLS_CACHE_DIR" ] && [ "$(ls -A "$SKILLS_CACHE_DIR" 2>/dev/null)" ]; then
  mkdir -p "$STAGING_DIR/skills"
  echo -e "  ${GREEN}✓${NC} Reusing cached skills from ${SKILLS_CACHE_DIR} (--skip-skills)"
  cp -r "$SKILLS_CACHE_DIR"/* "$STAGING_DIR/skills/"
else
  echo "  Installing skills via install_skills.sh..."
INSTALL_SKILLS_SCRIPT="$REPO_ROOT/databricks-skills/install_skills.sh"
if [ ! -f "$INSTALL_SKILLS_SCRIPT" ]; then echo -e "${RED}Error: install_skills.sh not found${NC}"; exit 1; fi

SKILLS_TEMP_DIR=$(mktemp -d)
trap "rm -rf '$SKILLS_TEMP_DIR'" EXIT
touch "$SKILLS_TEMP_DIR/databricks.yml"
(cd "$SKILLS_TEMP_DIR" && bash "$INSTALL_SKILLS_SCRIPT")

mkdir -p "$STAGING_DIR/skills"
INSTALLED_SKILLS_DIR="$SKILLS_TEMP_DIR/.claude/skills"
if [ -d "$INSTALLED_SKILLS_DIR" ]; then
  for skill_dir in "$INSTALLED_SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_name=$(basename "$skill_dir")
    if [ -f "$skill_dir/SKILL.md" ]; then
      mkdir -p "$STAGING_DIR/skills/$skill_name"
      cp -r "$skill_dir"* "$STAGING_DIR/skills/$skill_name/"
    fi
  done
fi

  # Cache skills for --skip-skills on next run
  rm -rf "$SKILLS_CACHE_DIR"
  cp -r "$STAGING_DIR/skills" "$SKILLS_CACHE_DIR"
fi

# Build ENABLED_SKILLS list from installed skills
SKILL_NAMES=""
for skill_dir in "$STAGING_DIR/skills"/*/; do
  [ -d "$skill_dir" ] || continue
  if [ -f "$skill_dir/SKILL.md" ]; then
    name=$(basename "$skill_dir")
    if [ -n "$SKILL_NAMES" ]; then SKILL_NAMES="${SKILL_NAMES},${name}"; else SKILL_NAMES="${name}"; fi
  fi
done

# Generate a clean app.yaml (not patching the template — avoids regex/indentation issues)
echo "  Generating app.yaml..."
cat > "$STAGING_DIR/app.yaml" << APPYAML
command:
  - "uvicorn"
  - "server.app:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "\$DATABRICKS_APP_PORT"

env:
  - name: ENV
    value: "production"
  - name: PROJECTS_BASE_DIR
    value: "./projects"
  - name: PYTHONPATH
    value: "/app/python/source_code/packages"
  - name: LAKEBASE_ENDPOINT
    value: "${LAKEBASE_ENDPOINT}"
  - name: LAKEBASE_DATABASE_NAME
    value: "databricks_postgres"
  - name: ENABLED_SKILLS
    value: "${SKILL_NAMES}"
  - name: SKILLS_ONLY_MODE
    value: "false"
  - name: LLM_PROVIDER
    value: "DATABRICKS"
  - name: DATABRICKS_MODEL
    value: "databricks-meta-llama-3-3-70b-instruct"
  - name: DATABRICKS_MODEL_MINI
    value: "databricks-gemini-3-flash"
  - name: CLAUDE_CODE_STREAM_CLOSE_TIMEOUT
    value: "3600000"
  - name: MLFLOW_TRACKING_URI
    value: "databricks"
  - name: MLFLOW_EXPERIMENT_NAME
    value: "/Workspace/Shared/builder_app_ml_trace"
  - name: AUTO_GRANT_PERMISSIONS_TO
    value: "account users"
APPYAML
echo -e "  ${GREEN}✓${NC} app.yaml generated with LAKEBASE_ENDPOINT=${LAKEBASE_ENDPOINT}"

find "$STAGING_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$STAGING_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

echo -e "  ${GREEN}✓${NC} Deployment package prepared"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Create app (if it doesn't exist)
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[5/${TOTAL_STEPS}] Creating app (if needed)...${NC}"

if databricks apps get "$APP_NAME" $CLI_ARGS &> /dev/null; then
  echo -e "  ${GREEN}✓${NC} App '${APP_NAME}' already exists"
else
  echo "  Creating app '${APP_NAME}'..."
  databricks apps create "$APP_NAME" $CLI_ARGS 2>&1
  echo -e "  ${GREEN}✓${NC} App '${APP_NAME}' created"
fi

APP_INFO=$(databricks apps get "$APP_NAME" $CLI_ARGS --output json 2>/dev/null)
SP_CLIENT_ID=$(echo "$APP_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('service_principal_client_id', ''))" 2>/dev/null || echo "")

if [ -z "$SP_CLIENT_ID" ]; then
  echo -e "${RED}Error: Could not get SP client ID for app '${APP_NAME}'${NC}"; exit 1
fi
echo -e "  Service Principal: ${SP_CLIENT_ID}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Configure Lakebase permissions for the app's SP
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[6/${TOTAL_STEPS}] Configuring Lakebase permissions...${NC}"

BRANCH_PATH="projects/${LAKEBASE_PROJECT_ID}/branches/production"

# Create Lakebase OAuth role for the SP
echo "  Creating Lakebase OAuth role for SP..."
ROLE_JSON="{\"spec\": {\"postgres_role\": \"${SP_CLIENT_ID}\", \"auth_method\": \"LAKEBASE_OAUTH_V1\", \"identity_type\": \"SERVICE_PRINCIPAL\"}}"
ROLE_OUTPUT=$(databricks postgres create-role "$BRANCH_PATH" --json "$ROLE_JSON" --no-wait $CLI_ARGS 2>&1) || true
if echo "$ROLE_OUTPUT" | grep -qi "already exists"; then
  echo -e "  ${GREEN}✓${NC} Lakebase OAuth role already exists"
elif echo "$ROLE_OUTPUT" | grep -qi "error"; then
  echo -e "  ${YELLOW}⚠${NC} Role creation note: $ROLE_OUTPUT"
else
  echo -e "  ${GREEN}✓${NC} Lakebase OAuth role created"
fi

# Grant PostgreSQL permissions via Python (uses project venv — faster than uv run)
echo "  Granting PostgreSQL permissions..."
PROFILE_ENV=""
if [ -n "$PROFILE" ]; then PROFILE_ENV="DATABRICKS_CONFIG_PROFILE=$PROFILE"; fi

# Use existing venv if available, fall back to uv run
PYTHON_CMD="uv run python3"
if [ -f "$PROJECT_DIR/.venv/bin/python3" ]; then
  PYTHON_CMD="$PROJECT_DIR/.venv/bin/python3"
fi

GRANT_OUTPUT=$(env $PROFILE_ENV $PYTHON_CMD -c "
import sys
from urllib.parse import quote
from databricks.sdk import WorkspaceClient
import psycopg

w = WorkspaceClient()
ep = w.postgres.get_endpoint(name=sys.argv[1])
cred = w.postgres.generate_database_credential(endpoint=sys.argv[1])
user = w.current_user.me().user_name
sp = sys.argv[2]

conn = psycopg.connect(f'postgresql://{quote(user, safe=str())}:{cred.token}@{ep.status.hosts.host}:5432/databricks_postgres?sslmode=require')
conn.autocommit = True
cur = conn.cursor()
q = chr(34)
for sql in [
    f'GRANT CREATE ON DATABASE databricks_postgres TO {q}{sp}{q}',
    'CREATE SCHEMA IF NOT EXISTS builder_app',
    f'GRANT USAGE ON SCHEMA builder_app TO {q}{sp}{q}',
    f'GRANT ALL PRIVILEGES ON SCHEMA builder_app TO {q}{sp}{q}',
    f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA builder_app TO {q}{sp}{q}',
    f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA builder_app TO {q}{sp}{q}',
    f'ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app GRANT ALL ON TABLES TO {q}{sp}{q}',
    f'ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app GRANT ALL ON SEQUENCES TO {q}{sp}{q}',
]:
    cur.execute(sql)
cur.close()
conn.close()
print('OK')
" "$LAKEBASE_ENDPOINT" "$SP_CLIENT_ID" 2>&1) || true

if echo "$GRANT_OUTPUT" | grep -q "OK"; then
  echo -e "  ${GREEN}✓${NC} PostgreSQL permissions granted"
else
  echo -e "  ${YELLOW}⚠${NC} Grant issue: $GRANT_OUTPUT"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Upload to workspace
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[7/${TOTAL_STEPS}] Uploading to Databricks workspace...${NC}"
echo "  Target: ${WORKSPACE_PATH}"
databricks workspace import-dir "$STAGING_DIR" "$WORKSPACE_PATH" --overwrite $CLI_ARGS 2>&1 | tail -5
echo -e "  ${GREEN}✓${NC} Upload complete"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 8: Deploy the app
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[8/${TOTAL_STEPS}] Deploying app...${NC}"
DEPLOY_OUTPUT=$(databricks apps deploy "$APP_NAME" --source-code-path "$WORKSPACE_PATH" $CLI_ARGS 2>&1)
echo "$DEPLOY_OUTPUT"

if echo "$DEPLOY_OUTPUT" | grep -q '"state":"SUCCEEDED"'; then
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║                 Deployment Successful!                     ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
  echo ""

  APP_URL=$(echo "$APP_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', 'N/A'))" 2>/dev/null || echo "N/A")
  echo -e "  App URL:           ${GREEN}${APP_URL}${NC}"
  echo -e "  Lakebase Project:  ${LAKEBASE_PROJECT_ID}"
  echo -e "  Lakebase Endpoint: ${LAKEBASE_ENDPOINT}"
  echo -e "  Service Principal: ${SP_CLIENT_ID}"
  echo ""

  # Clean up old deployments
  CURRENT_DEPLOYMENT_ID=$(databricks apps get "$APP_NAME" $CLI_ARGS --output json 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin).get('active_deployment', {}).get('deployment_id', ''))" 2>/dev/null || echo "")
  if [ -n "$SP_CLIENT_ID" ] && [ -n "$CURRENT_DEPLOYMENT_ID" ]; then
    SP_SRC_PATH="/Workspace/Users/${SP_CLIENT_ID}/src"
    OLD_DIRS=$(databricks workspace list "$SP_SRC_PATH" $CLI_ARGS --output json 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
objects = data if isinstance(data, list) else data.get('objects', [])
current = '$CURRENT_DEPLOYMENT_ID'
for obj in objects:
    path = obj.get('path', '')
    name = path.rsplit('/', 1)[-1] if '/' in path else path
    if name != current and obj.get('object_type', '') == 'DIRECTORY':
        print(path)
" 2>/dev/null || echo "")
    if [ -n "$OLD_DIRS" ]; then
      CLEANED=0
      while IFS= read -r dir_path; do
        if databricks workspace delete "$dir_path" --recursive $CLI_ARGS 2>/dev/null; then CLEANED=$((CLEANED + 1)); fi
      done <<< "$OLD_DIRS"
      echo -e "  ${GREEN}✓${NC} Removed $CLEANED old deployment(s)"
    fi
  fi
  echo ""
else
  echo ""
  echo -e "${RED}Deployment may have issues. Check the output above.${NC}"
  echo -e "  Check logs with: databricks apps logs ${APP_NAME} ${CLI_ARGS}"
  exit 1
fi
