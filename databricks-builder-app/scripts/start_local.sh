#!/bin/bash
# Unified local development script for Databricks Builder App
# One command: provisions Lakebase, installs deps, configures env, starts servers

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

MIN_CLI_VERSION="0.287.0"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$PROJECT_DIR")"

PROFILE="${PROFILE:-}"
SKIP_LAKEBASE="${SKIP_LAKEBASE:-false}"
FORCE_ENV="${FORCE_ENV:-false}"
FORCE_INSTALL="${FORCE_INSTALL:-false}"
LAKEBASE_PROJECT_ID="${LAKEBASE_PROJECT_ID:-builder-app-db}"

usage() {
  echo "Usage: $0 --profile <profile> [options]"
  echo ""
  echo "Start the Builder App locally. On first run, provisions Lakebase,"
  echo "installs dependencies, and generates .env.local automatically."
  echo ""
  echo "Options:"
  echo "  --profile PROFILE     Databricks CLI profile (required)"
  echo "  --skip-lakebase       Skip Lakebase provisioning"
  echo "  --force-env           Regenerate .env.local even if it exists"
  echo "  --force-install       Reinstall all dependencies"
  echo "  --lakebase-id ID      Lakebase project ID (default: builder-app-db)"
  echo "  -h, --help            Show this help message"
  echo ""
  echo "Example:"
  echo "  $0 --profile dbx_shared_demo"
  echo "  $0 --profile dbx_shared_demo --skip-lakebase --skip-skills"
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -h|--help) usage; exit 0 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --skip-lakebase) SKIP_LAKEBASE=true; shift ;;
    --force-env) FORCE_ENV=true; shift ;;
    --force-install) FORCE_INSTALL=true; shift ;;
    --lakebase-id) LAKEBASE_PROJECT_ID="$2"; shift 2 ;;
    -*) echo -e "${RED}Error: Unknown option $1${NC}"; usage; exit 1 ;;
    *) echo -e "${RED}Error: Unexpected argument $1${NC}"; usage; exit 1 ;;
  esac
done

if [ -z "$PROFILE" ]; then
  echo -e "${RED}Error: --profile is required${NC}"; echo ""; usage; exit 1
fi

LAKEBASE_ENDPOINT="projects/${LAKEBASE_PROJECT_ID}/branches/production/endpoints/primary"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Databricks Builder App — Local Dev                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Profile:           ${GREEN}${PROFILE}${NC}"
echo -e "  Lakebase ID:       ${LAKEBASE_PROJECT_ID}"
echo ""

TOTAL_STEPS=10

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Check prerequisites
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[1/${TOTAL_STEPS}] Checking prerequisites...${NC}"

if ! command -v uv &> /dev/null; then
  echo -e "${RED}Error: uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"; exit 1
fi
echo -e "  ${GREEN}✓${NC} uv"

if ! command -v node &> /dev/null; then
  echo -e "${RED}Error: Node.js not found. Install 18+ from https://nodejs.org/${NC}"; exit 1
fi
NODE_VERSION=$(node -v | sed 's/v//' | cut -d. -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
  echo -e "${RED}Error: Node.js 18+ required (found $(node -v))${NC}"; exit 1
fi
echo -e "  ${GREEN}✓${NC} Node.js $(node -v)"

if ! command -v npm &> /dev/null; then
  echo -e "${RED}Error: npm not found${NC}"; exit 1
fi
echo -e "  ${GREEN}✓${NC} npm"

if ! command -v databricks &> /dev/null; then
  echo -e "${RED}Error: Databricks CLI not found${NC}"; exit 1
fi
cli_version=$(databricks --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
if [ -n "$cli_version" ]; then
  if printf '%s\n%s' "$MIN_CLI_VERSION" "$cli_version" | sort -V -C; then
    echo -e "  ${GREEN}✓${NC} Databricks CLI v${cli_version}"
  else
    echo -e "${RED}Error: CLI v${cli_version} too old (need v${MIN_CLI_VERSION}+)${NC}"; exit 1
  fi
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Get credentials from profile
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[2/${TOTAL_STEPS}] Getting credentials from profile '${PROFILE}'...${NC}"

WORKSPACE_HOST=$(databricks auth describe --profile "$PROFILE" --output json 2>/dev/null | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(data.get('host', '') or data.get('details', {}).get('host', ''))
" 2>/dev/null || echo "")
if [ -z "$WORKSPACE_HOST" ]; then
  echo -e "${RED}Error: Could not determine workspace from profile '${PROFILE}'${NC}"; exit 1
fi

DATABRICKS_TOKEN=$(databricks auth token --profile "$PROFILE" 2>/dev/null | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(data.get('access_token', data.get('token', '')))
" 2>/dev/null || echo "")
if [ -z "$DATABRICKS_TOKEN" ]; then
  echo -e "${RED}Error: Could not get token from profile '${PROFILE}'. Run: databricks auth login --profile ${PROFILE}${NC}"; exit 1
fi

CURRENT_USER=$(databricks current-user me --profile "$PROFILE" --output json 2>/dev/null | python3 -c "
import sys, json; data = json.load(sys.stdin)
print(data.get('userName', data.get('user_name', '')))
" 2>/dev/null || echo "")
if [ -z "$CURRENT_USER" ]; then
  echo -e "${RED}Error: Could not determine current user${NC}"; exit 1
fi

echo -e "  Workspace: ${WORKSPACE_HOST}"
echo -e "  User:      ${CURRENT_USER}"
echo -e "  ${GREEN}✓${NC} Credentials obtained"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 3: Deploy Lakebase via DAB
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[3/${TOTAL_STEPS}] Provisioning Lakebase...${NC}"

if [ "$SKIP_LAKEBASE" = true ]; then
  echo -e "  ${GREEN}✓${NC} Skipped (--skip-lakebase)"
else
  cd "$PROJECT_DIR"
  databricks bundle deploy --profile "$PROFILE" --var "lakebase_project_id=${LAKEBASE_PROJECT_ID}" 2>&1
  echo -e "  ${GREEN}✓${NC} Lakebase project '${LAKEBASE_PROJECT_ID}' ready"
fi
cd "$PROJECT_DIR"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Generate .env.local
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[4/${TOTAL_STEPS}] Configuring .env.local...${NC}"

if [ -f "$PROJECT_DIR/.env.local" ] && [ "$FORCE_ENV" != true ]; then
  # Always refresh the token in existing .env.local
  # Always update host and token to match current profile
  sed -i '' "s|^DATABRICKS_HOST=.*|DATABRICKS_HOST=${WORKSPACE_HOST}|" "$PROJECT_DIR/.env.local"
  sed -i '' "s|^DATABRICKS_TOKEN=.*|DATABRICKS_TOKEN=${DATABRICKS_TOKEN}|" "$PROJECT_DIR/.env.local"
  sed -i '' "s|^LAKEBASE_ENDPOINT=.*|LAKEBASE_ENDPOINT=${LAKEBASE_ENDPOINT}|" "$PROJECT_DIR/.env.local"
  echo -e "  ${GREEN}✓${NC} Updated host, token, and endpoint from profile '${PROFILE}'"
else
  cat > "$PROJECT_DIR/.env.local" << ENVEOF
DATABRICKS_HOST=${WORKSPACE_HOST}
DATABRICKS_TOKEN=${DATABRICKS_TOKEN}
LAKEBASE_ENDPOINT=${LAKEBASE_ENDPOINT}
LAKEBASE_DATABASE_NAME=databricks_postgres
LLM_PROVIDER=DATABRICKS
DATABRICKS_MODEL=databricks-meta-llama-3-3-70b-instruct
DATABRICKS_MODEL_MINI=databricks-gemini-3-flash
ENABLED_SKILLS=
SKILLS_ONLY_MODE=false
ENV=development
PROJECTS_BASE_DIR=./projects
CLAUDE_CODE_STREAM_CLOSE_TIMEOUT=3600000
MLFLOW_TRACKING_URI=databricks
MLFLOW_EXPERIMENT_NAME=/Workspace/Users/${CURRENT_USER}/builder_app_local_traces
ENVEOF
  echo -e "  ${GREEN}✓${NC} Generated .env.local"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 5: Install backend dependencies
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[5/${TOTAL_STEPS}] Installing backend dependencies...${NC}"

cd "$PROJECT_DIR"
if [ -d ".venv" ] && [ "$FORCE_INSTALL" != true ]; then
  echo -e "  ${GREEN}✓${NC} Venv exists (use --force-install to reinstall)"
else
  uv sync --quiet
  echo -e "  ${GREEN}✓${NC} Backend dependencies installed"
fi

if [ -d "$REPO_ROOT/databricks-tools-core" ] && [ -d "$REPO_ROOT/databricks-mcp-server" ]; then
  uv pip install -e "$REPO_ROOT/databricks-tools-core" -e "$REPO_ROOT/databricks-mcp-server" --quiet 2>/dev/null
  echo -e "  ${GREEN}✓${NC} Sibling packages installed"
else
  echo -e "  ${YELLOW}⚠${NC} Sibling packages not found at repo root"
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 6: Install frontend dependencies
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[6/${TOTAL_STEPS}] Installing frontend dependencies...${NC}"

cd "$PROJECT_DIR/client"
if [ -d "node_modules" ] && [ "$FORCE_INSTALL" != true ]; then
  echo -e "  ${GREEN}✓${NC} node_modules exists (use --force-install to reinstall)"
else
  npm install --silent 2>/dev/null || npm install
  echo -e "  ${GREEN}✓${NC} Frontend dependencies installed"
fi
cd "$PROJECT_DIR"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 7: Install skills
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[7/${TOTAL_STEPS}] Installing skills...${NC}"

# Run install_skills.sh from the project dir — installs to .claude/skills/
INSTALL_SKILLS_SCRIPT="$REPO_ROOT/databricks-skills/install_skills.sh"

if [ ! -f "$INSTALL_SKILLS_SCRIPT" ]; then
  echo -e "  ${YELLOW}⚠${NC} install_skills.sh not found — using existing skills only"
else
  # Run from PROJECT_DIR so skills install to databricks-builder-app/.claude/skills/
  cd "$PROJECT_DIR"
  bash "$INSTALL_SKILLS_SCRIPT"
  cd "$PROJECT_DIR"
fi

# Scan skills from .claude/skills/ (where install_skills.sh puts them)
# and from ../databricks-skills/ (local repo skills) — union of both
SKILL_NAMES=""
SKILL_COUNT=0
for skills_root in "$PROJECT_DIR/.claude/skills" "$REPO_ROOT/databricks-skills"; do
  [ -d "$skills_root" ] || continue
  for skill_dir in "$skills_root"/*/; do
    [ -d "$skill_dir" ] || continue
    if [ -f "$skill_dir/SKILL.md" ]; then
      name=$(basename "$skill_dir")
      # Avoid duplicates
      if ! echo ",$SKILL_NAMES," | grep -q ",$name,"; then
        if [ -n "$SKILL_NAMES" ]; then SKILL_NAMES="${SKILL_NAMES},${name}"; else SKILL_NAMES="${name}"; fi
        SKILL_COUNT=$((SKILL_COUNT + 1))
      fi
    fi
  done
done
if [ -n "$SKILL_NAMES" ] && [ -f "$PROJECT_DIR/.env.local" ]; then
  sed -i '' "s|^ENABLED_SKILLS=.*|ENABLED_SKILLS=${SKILL_NAMES}|" "$PROJECT_DIR/.env.local"
fi
echo -e "  ${GREEN}✓${NC} ${SKILL_COUNT} skills available"
echo ""

# Step 8: Test Lakebase connection
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[8/${TOTAL_STEPS}] Testing Lakebase connection...${NC}"

PYTHON_CMD="$PROJECT_DIR/.venv/bin/python3"
if [ ! -f "$PYTHON_CMD" ]; then PYTHON_CMD="uv run python3"; fi

DB_TEST_OUTPUT=$(DATABRICKS_CONFIG_PROFILE="$PROFILE" $PYTHON_CMD -c "
import sys
from urllib.parse import quote
from databricks.sdk import WorkspaceClient
import psycopg

w = WorkspaceClient()
ep = w.postgres.get_endpoint(name=sys.argv[1])
cred = w.postgres.generate_database_credential(endpoint=sys.argv[1])
user = w.current_user.me().user_name

conn = psycopg.connect(f'postgresql://{quote(user, safe=str())}:{cred.token}@{ep.status.hosts.host}:5432/databricks_postgres?sslmode=require')
conn.autocommit = True
cur = conn.cursor()

# Test basic connectivity
cur.execute('SELECT 1')
print('CONNECTED')

# Test schema access
try:
    cur.execute('CREATE SCHEMA IF NOT EXISTS builder_app')
    cur.execute('SET search_path TO builder_app, public')
    cur.execute('SELECT 1')
    print('SCHEMA_OK')
except Exception as e:
    print(f'SCHEMA_DENIED:{e}')

cur.close()
conn.close()
" "$LAKEBASE_ENDPOINT" 2>&1) || true

if echo "$DB_TEST_OUTPUT" | grep -q "CONNECTED"; then
  echo -e "  ${GREEN}✓${NC} Connected to Lakebase"
else
  echo -e "  ${RED}✗${NC} Could not connect to Lakebase"
  echo "    $DB_TEST_OUTPUT"
  echo ""
  echo -e "  ${YELLOW}If compute is waking from scale-to-zero, wait 30s and retry.${NC}"
  exit 1
fi

if echo "$DB_TEST_OUTPUT" | grep -q "SCHEMA_OK"; then
  echo -e "  ${GREEN}✓${NC} Schema access verified"
else
  echo -e "  ${RED}✗${NC} Permission denied on builder_app schema"
  echo ""
  echo -e "  ${YELLOW}Ask the Lakebase project owner to run these grants:${NC}"
  echo ""
  echo "    GRANT CREATE ON DATABASE databricks_postgres TO \"${CURRENT_USER}\";"
  echo "    CREATE SCHEMA IF NOT EXISTS builder_app;"
  echo "    GRANT USAGE ON SCHEMA builder_app TO \"${CURRENT_USER}\";"
  echo "    GRANT ALL PRIVILEGES ON SCHEMA builder_app TO \"${CURRENT_USER}\";"
  echo "    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA builder_app TO \"${CURRENT_USER}\";"
  echo "    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA builder_app TO \"${CURRENT_USER}\";"
  echo "    ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app GRANT ALL ON TABLES TO \"${CURRENT_USER}\";"
  echo "    ALTER DEFAULT PRIVILEGES IN SCHEMA builder_app GRANT ALL ON SEQUENCES TO \"${CURRENT_USER}\";"
  echo ""
  exit 1
fi
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 9: Kill stale processes
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[9/${TOTAL_STEPS}] Checking for stale processes...${NC}"

for PORT in 8000 3000; do
  PID=$(lsof -ti:$PORT 2>/dev/null || true)
  if [ -n "$PID" ]; then
    PROC=$(ps -p $PID -o comm= 2>/dev/null || echo "unknown")
    echo -e "  ${YELLOW}Killing${NC} PID $PID ($PROC) on port $PORT"
    kill -9 $PID 2>/dev/null || true
  fi
done
sleep 1
echo -e "  ${GREEN}✓${NC} Ports 8000 and 3000 clear"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Step 10: Start servers
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${YELLOW}[10/${TOTAL_STEPS}] Starting servers...${NC}"

cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down servers...${NC}"
  kill $(jobs -p) 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM

cd "$PROJECT_DIR"
echo -e "  Starting backend on ${GREEN}http://localhost:8000${NC}..."
uv run uvicorn server.app:app --reload --port 8000 --reload-dir server &
sleep 2

echo -e "  Starting frontend on ${GREEN}http://localhost:3000${NC}..."
cd client
npm run dev &
cd "$PROJECT_DIR"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    App Running!                            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Frontend: ${GREEN}http://localhost:3000${NC}"
echo -e "  Backend:  ${GREEN}http://localhost:8000${NC}"
echo -e "  API Docs: ${GREEN}http://localhost:8000/docs${NC}"
echo ""
echo -e "  Press ${YELLOW}Ctrl+C${NC} to stop"
echo ""

wait
