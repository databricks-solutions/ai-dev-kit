#!/usr/bin/env bash
# Run live Databricks integration tests for noom-mcp-server.
#
# Usage:
#   ./run_integration_tests.sh
#
# Required environment variables (export them before running, or add to .env):
#
#   DATABRICKS_HOST               Calling user's workspace URL
#   DATABRICKS_WAREHOUSE_ID       SQL warehouse to run test queries against
#   DATABRICKS_MCP_SQL_HOST       Workspace for SQL execution (usually prod)
#
#   Calling user auth — one of:
#     Browser OAuth (recommended): run 'databricks auth login' beforehand
#     OAuth M2M: set DATABRICKS_CLIENT_ID + DATABRICKS_CLIENT_SECRET
#
#   SQL SP credentials — one of:
#     DATABRICKS_MCP_SECRET_SCOPE             Databricks secret scope with SP creds
#     DATABRICKS_MCP_SQL_CLIENT_ID +          Direct env vars (dev/CI fallback)
#       DATABRICKS_MCP_SQL_CLIENT_SECRET

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Require .env — copy .env.example if you haven't already
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "ERROR: $SCRIPT_DIR/.env not found." >&2
  echo "  cp noom-mcp-server/.env.example noom-mcp-server/.env" >&2
  echo "  # then fill in any values and re-run" >&2
  exit 1
fi

echo "Loading $SCRIPT_DIR/.env"
set -a
# shellcheck disable=SC1090
source "$SCRIPT_DIR/.env"
set +a

# PAT auth is explicitly rejected by noom-mcp-server.
# Unset DATABRICKS_TOKEN if present so the SDK falls through to OAuth.
if [[ -n "${DATABRICKS_TOKEN:-}" ]]; then
  echo "WARNING: DATABRICKS_TOKEN is set — unsetting it to force OAuth auth."
  unset DATABRICKS_TOKEN
fi

# Validate required variables
missing=()
for var in DATABRICKS_HOST DATABRICKS_MCP_SQL_HOST; do
  [[ -z "${!var:-}" ]] && missing+=("$var")
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: Missing required environment variables:" >&2
  printf '  %s\n' "${missing[@]}" >&2
  exit 1
fi

# Locate the Python interpreter (prefer repo-root venv, fall back to system)
PYTHON="${SCRIPT_DIR}/../.venv/bin/python3"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

echo "Python: $PYTHON"
echo "Host:   $DATABRICKS_HOST"
echo "SQL:    $DATABRICKS_MCP_SQL_HOST"
echo "WH:     ${DATABRICKS_WAREHOUSE_ID:-<not set — tests will skip>}"
echo ""

"$PYTHON" -m pytest \
  "$SCRIPT_DIR/tests/integration/" \
  --integration \
  -v \
  "$@"
