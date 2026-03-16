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
FULL_UPLOAD="${FULL_UPLOAD:-false}"
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-false}"
NO_WAIT="${NO_WAIT:-false}"

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
  echo "  --skip-migrations     Skip database migrations and SP grants"
  echo "  --no-wait             Don't wait for deployment to complete"
  echo "  --full-upload         Force full workspace import"
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
    --skip-migrations)
      SKIP_MIGRATIONS=true
      shift
      ;;
    --no-wait)
      NO_WAIT=true
      shift
      ;;
    --full-upload)
      FULL_UPLOAD=true
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
echo -e "  Skip Migrate: ${SKIP_MIGRATIONS}"
echo -e "  No Wait:      ${NO_WAIT}"
echo -e "  Full Upload:  ${FULL_UPLOAD}"
echo ""

# Check prerequisites (parallel API calls for speed)
echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

# Check Databricks CLI
if ! command -v databricks &> /dev/null; then
  echo -e "${RED}Error: Databricks CLI not found. Install with: curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh${NC}"
  exit 1
fi

cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$cli_version" ]; then
  if printf '%s\n%s' "$MIN_CLI_VERSION" "$cli_version" | sort -V -C; then
    echo -e "  ${GREEN}✓${NC} Databricks CLI v${cli_version}"
  else
    echo -e "  ${YELLOW}Warning: Databricks CLI v${cli_version} is outdated (minimum: v${MIN_CLI_VERSION})${NC}"
  fi
fi

# Run auth, user, and app-check API calls in parallel
_tmp_auth=$(mktemp)
_tmp_user=$(mktemp)
_tmp_app=$(mktemp)

databricks auth describe --output json > "$_tmp_auth" 2>/dev/null &
_pid_auth=$!
databricks current-user me --output json > "$_tmp_user" 2>/dev/null &
_pid_user=$!
databricks apps get "$APP_NAME" > "$_tmp_app" 2>/dev/null &
_pid_app=$!

wait $_pid_auth || { echo -e "${RED}Error: Not authenticated with Databricks. Run: databricks auth login${NC}"; exit 1; }
wait $_pid_user || { echo -e "${RED}Error: Could not determine current user.${NC}"; exit 1; }
wait $_pid_app || { echo -e "${RED}Error: App '${APP_NAME}' does not exist. Create with: databricks apps create ${APP_NAME}${NC}"; exit 1; }

WORKSPACE_HOST=$(python3 -c "
import sys, json
data = json.load(open('$_tmp_auth'))
host = data.get('host', '') or data.get('details', {}).get('host', '')
print(host)
" 2>/dev/null || echo "")

CURRENT_USER=$(python3 -c "
import sys, json
data = json.load(open('$_tmp_user'))
print(data.get('userName', data.get('user_name', '')))
" 2>/dev/null || echo "")

rm -f "$_tmp_auth" "$_tmp_user" "$_tmp_app"

if [ -z "$WORKSPACE_HOST" ] || [ -z "$CURRENT_USER" ]; then
  echo -e "${RED}Error: Could not determine workspace or user.${NC}"
  exit 1
fi

WORKSPACE_PATH="/Workspace/Users/${CURRENT_USER}/apps/${APP_NAME}"
echo -e "  ${GREEN}✓${NC} Workspace: ${WORKSPACE_HOST}"
echo -e "  ${GREEN}✓${NC} User: ${CURRENT_USER}"
echo -e "  ${GREEN}✓${NC} App '${APP_NAME}' exists"
echo ""

# Run database migrations synchronously (blocking) before packaging/deploy.
echo -e "${YELLOW}[3/7] Applying database migrations...${NC}"
cd "$PROJECT_DIR"

if [ "$SKIP_MIGRATIONS" = true ]; then
  echo -e "  ${GREEN}✓${NC} Skipped (--skip-migrations)"
  echo ""
elif true; then

# If LAKEBASE_* vars are not present in shell, derive from app.yaml.
if [ -z "${LAKEBASE_PG_URL:-}" ] && [ -z "${LAKEBASE_INSTANCE_NAME:-}" ]; then
  eval "$(python3 - <<'PY'
import re
from pathlib import Path

app_yaml = Path("app.yaml")
if not app_yaml.exists():
    raise SystemExit(0)

text = app_yaml.read_text(encoding="utf-8")

def get_env(name: str) -> str:
    pattern = re.compile(
        rf"-\s*name:\s*{re.escape(name)}\s*\n\s*value:\s*\"([^\"]*)\"",
        re.MULTILINE,
    )
    m = pattern.search(text)
    return m.group(1) if m else ""

instance = get_env("LAKEBASE_INSTANCE_NAME")
database = get_env("LAKEBASE_DATABASE_NAME")
schema = get_env("LAKEBASE_SCHEMA_NAME")

if instance:
    print(f'export LAKEBASE_INSTANCE_NAME="{instance}"')
if database:
    print(f'export LAKEBASE_DATABASE_NAME="{database}"')
if schema:
    print(f'export LAKEBASE_SCHEMA_NAME="{schema}"')
PY
)"
fi

# Prefer the project venv Python so databricks-sdk is importable.
VENV_PYTHON="${PROJECT_DIR}/.venv/bin/python3"
[ ! -x "$VENV_PYTHON" ] && VENV_PYTHON="python3"

# Build a temporary tokenized LAKEBASE_PG_URL when not explicitly provided.
# This makes local Alembic runs deterministic in CI/dev shells.
if [ -z "${LAKEBASE_PG_URL:-}" ] && [ -n "${LAKEBASE_INSTANCE_NAME:-}" ]; then
  eval "$($VENV_PYTHON - <<'PY'
import os
import urllib.parse

from databricks.sdk import WorkspaceClient

instance_name = os.environ.get("LAKEBASE_INSTANCE_NAME")
database_name = os.environ.get("LAKEBASE_DATABASE_NAME", "databricks_postgres")

if not instance_name:
    raise SystemExit(0)

w = WorkspaceClient()
instance = w.database.get_database_instance(name=instance_name)
cred = w.database.generate_database_credential(
    request_id="deploy-alembic",
    instance_names=[instance_name],
)
me = w.current_user.me()
user = me.user_name or ""
token = cred.token or ""

encoded_user = urllib.parse.quote(user, safe="")
encoded_token = urllib.parse.quote(token, safe="")
url = f"postgresql://{encoded_user}:{encoded_token}@{instance.read_write_dns}:5432/{database_name}?sslmode=require"

escaped = url.replace("'", "'\"'\"'")
print(f"export LAKEBASE_PG_URL='{escaped}'")
PY
)"
fi

# Ensure local Alembic environment can import databricks_tools_core in dynamic auth mode.
export PYTHONPATH="${REPO_ROOT}/databricks-tools-core:${PYTHONPATH:-}"

if [ -n "${LAKEBASE_PG_URL:-}" ] || [ -n "${LAKEBASE_INSTANCE_NAME:-}" ]; then
  if [ -x "$PROJECT_DIR/.venv/bin/alembic" ]; then
    "$PROJECT_DIR/.venv/bin/alembic" -c "$PROJECT_DIR/alembic.ini" upgrade head
  elif command -v alembic &> /dev/null; then
    alembic -c "$PROJECT_DIR/alembic.ini" upgrade head
  elif command -v uv &> /dev/null; then
    uv run alembic -c "$PROJECT_DIR/alembic.ini" upgrade head
  else
    echo -e "${RED}Error: Alembic not found (expected .venv/bin/alembic, alembic, or uv run alembic)${NC}"
    exit 1
  fi
  echo -e "  ${GREEN}✓${NC} Database migrations applied"

  # Grant the app's service principal permissions on all tables.
  # Migrations run as the deploying user who owns the tables, but the app
  # connects as its SP at runtime and needs explicit grants.
  if [ -n "${LAKEBASE_PG_URL:-}" ]; then
    export APP_NAME_FOR_GRANT="${APP_NAME}"
    export LAKEBASE_SCHEMA_FOR_GRANT="${LAKEBASE_SCHEMA_NAME:-builder_app}"
    $VENV_PYTHON - <<'GRANT_PY'
import os, psycopg

url = os.environ["LAKEBASE_PG_URL"]
app_name = os.environ["APP_NAME_FOR_GRANT"]
schema = os.environ.get("LAKEBASE_SCHEMA_FOR_GRANT", "builder_app")

try:
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient()
    app = w.apps.get(app_name)
    sp_role = app.service_principal_client_id
    if not sp_role:
        raise SystemExit(0)

    conn = psycopg.connect(url, autocommit=True)
    cur = conn.cursor()
    for s in (schema, "public"):
        cur.execute(f'GRANT USAGE ON SCHEMA {s} TO "{sp_role}"')
        cur.execute(f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {s} TO "{sp_role}"')
        cur.execute(f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {s} TO "{sp_role}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {s} GRANT ALL PRIVILEGES ON TABLES TO "{sp_role}"')
        cur.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {s} GRANT ALL PRIVILEGES ON SEQUENCES TO "{sp_role}"')
    cur.close()
    conn.close()
    print(f"  \033[0;32m✓\033[0m Granted SP ({sp_role[:8]}...) permissions on schemas: {schema}, public")
except Exception as e:
    print(f"  \033[1;33mWarning: Could not grant SP permissions: {e}\033[0m")
GRANT_PY
  fi
else
  echo -e "  ${YELLOW}Warning: No Lakebase configuration found in env or app.yaml; skipping migrations${NC}"
fi
echo ""

fi # end SKIP_MIGRATIONS guard

# Build frontend
echo -e "${YELLOW}[4/7] Building frontend...${NC}"
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
echo -e "${YELLOW}[5/7] Preparing deployment package...${NC}"

# Clean and create staging directory
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

# Copy server code + alembic
echo "  Copying server code..."
cp -r server "$STAGING_DIR/"
cp app.yaml "$STAGING_DIR/"
cp requirements.txt "$STAGING_DIR/"
cp alembic.ini "$STAGING_DIR/"
cp -r alembic "$STAGING_DIR/"

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

# Upload to workspace (incremental by default)
echo -e "${YELLOW}[6/7] Uploading to Databricks workspace...${NC}"
echo "  Target: ${WORKSPACE_PATH}"

MANIFEST_DIR="${PROJECT_DIR}/.deploy-manifests"
MANIFEST_FILE="${MANIFEST_DIR}/${APP_NAME}.manifest.tsv"
NEW_MANIFEST_FILE="$(mktemp)"

if [ "$FULL_UPLOAD" = true ] || [ ! -f "$MANIFEST_FILE" ]; then
  if [ "$FULL_UPLOAD" = true ]; then
    echo "  Full upload requested (--full-upload)"
  else
    echo "  No previous manifest found; performing initial full upload"
  fi

  databricks workspace import-dir "$STAGING_DIR" "$WORKSPACE_PATH" --overwrite 2>&1 | tail -5

  mkdir -p "$MANIFEST_DIR"
  FIND_LIST_FILE="$(mktemp)"
  find "$STAGING_DIR" -type f -print0 > "$FIND_LIST_FILE"
  while IFS= read -r -d '' local_file; do
    rel_path="${local_file#$STAGING_DIR/}"
    checksum="$(shasum -a 256 "$local_file" | awk '{print $1}')"
    printf "%s\t%s\n" "$checksum" "$rel_path" >> "$NEW_MANIFEST_FILE"
  done < "$FIND_LIST_FILE"
  rm -f "$FIND_LIST_FILE"
  mv "$NEW_MANIFEST_FILE" "$MANIFEST_FILE"
  echo -e "  ${GREEN}✓${NC} Upload complete (full)"
else
  echo "  Incremental upload using manifest"

  uploaded_count=0
  unchanged_count=0
  deleted_count=0

  # Build current manifest from staging
  FIND_LIST_FILE="$(mktemp)"
  find "$STAGING_DIR" -type f -print0 > "$FIND_LIST_FILE"
  while IFS= read -r -d '' local_file; do
    rel_path="${local_file#$STAGING_DIR/}"
    checksum="$(shasum -a 256 "$local_file" | awk '{print $1}')"
    printf "%s\t%s\n" "$checksum" "$rel_path" >> "$NEW_MANIFEST_FILE"
  done < "$FIND_LIST_FILE"
  rm -f "$FIND_LIST_FILE"

  CHANGED_LIST="$(mktemp)"
  DELETED_LIST="$(mktemp)"

  # Changed/new files: path missing in old manifest OR checksum changed
  awk -F $'\t' '
    NR==FNR { old[$2]=$1; next }
    { if (!(($2 in old) && old[$2]==$1)) print $2 }
  ' "$MANIFEST_FILE" "$NEW_MANIFEST_FILE" > "$CHANGED_LIST"

  while IFS= read -r rel_path; do
    if [ -n "$rel_path" ]; then
      local_file="$STAGING_DIR/$rel_path"
      remote_file="$WORKSPACE_PATH/$rel_path"
      remote_dir="$(dirname "$remote_file")"
      databricks workspace mkdirs "$remote_dir" >/dev/null
      databricks workspace import --file "$local_file" "$remote_file" --overwrite --format AUTO >/dev/null
      uploaded_count=$((uploaded_count + 1))
    fi
  done < "$CHANGED_LIST"

  # Deleted files: path existed before but is not in current manifest
  awk -F $'\t' '
    NR==FNR { new[$2]=1; next }
    { if (!($2 in new)) print $2 }
  ' "$NEW_MANIFEST_FILE" "$MANIFEST_FILE" > "$DELETED_LIST"

  while IFS= read -r rel_path; do
    if [ -n "$rel_path" ]; then
      databricks workspace delete "$WORKSPACE_PATH/$rel_path" >/dev/null 2>&1 || true
      deleted_count=$((deleted_count + 1))
    fi
  done < "$DELETED_LIST"

  total_files=$(wc -l < "$NEW_MANIFEST_FILE" | tr -d ' ')
  unchanged_count=$((total_files - uploaded_count))
  if [ "$unchanged_count" -lt 0 ]; then unchanged_count=0; fi

  mkdir -p "$MANIFEST_DIR"
  mv "$NEW_MANIFEST_FILE" "$MANIFEST_FILE"
  rm -f "$CHANGED_LIST" "$DELETED_LIST"
  echo -e "  ${GREEN}✓${NC} Upload complete (incremental)"
  echo "    Uploaded:  ${uploaded_count} changed file(s)"
  echo "    Unchanged: ${unchanged_count} file(s)"
  echo "    Deleted:   ${deleted_count} file(s)"
fi
echo ""

# Deploy the app
echo -e "${YELLOW}[7/7] Deploying app...${NC}"
DEPLOY_ARGS=("$APP_NAME" --source-code-path "$WORKSPACE_PATH")
if [ "$NO_WAIT" = true ]; then
  DEPLOY_ARGS+=(--no-wait)
fi
DEPLOY_OUTPUT=$(databricks apps deploy "${DEPLOY_ARGS[@]}" 2>&1)
echo "$DEPLOY_OUTPUT"

# Get app URL
APP_INFO=$(databricks apps get "$APP_NAME" --output json 2>/dev/null)
APP_URL=$(echo "$APP_INFO" | python3 -c "import sys, json; print(json.load(sys.stdin).get('url', 'N/A'))" 2>/dev/null || echo "N/A")

# Check deployment status
if [ "$NO_WAIT" = true ]; then
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║              Deployment Submitted (no-wait)               ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  App URL: ${GREEN}${APP_URL}${NC}"
  echo -e "  ${YELLOW}Check status:${NC} databricks apps get ${APP_NAME}"
  echo ""
elif echo "$DEPLOY_OUTPUT" | grep -q '"state":"SUCCEEDED"'; then
  echo ""
  echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
  echo -e "${GREEN}║                 Deployment Successful!                     ║${NC}"
  echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
  echo ""
  echo -e "  App URL: ${GREEN}${APP_URL}${NC}"
  echo ""
else
  echo ""
  echo -e "${RED}Deployment may have issues. Check the output above.${NC}"
  exit 1
fi
