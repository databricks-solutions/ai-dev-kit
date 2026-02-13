#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SKILLS_SRC_DIR="${REPO_ROOT}/databricks-skills"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
CODEX_SKILLS_DIR="${CODEX_HOME}/skills"
PROJECT_CODEX_CONFIG="${REPO_ROOT}/.codex/config.toml"
PROFILE=""
INSTALL_ALL=true
SELECTED_SKILLS=()

usage() {
  cat <<EOF
Install Databricks skills for Codex and configure Databricks MCP for this project.

Usage:
  $(basename "$0") [options] [skill1 skill2 ...]

Options:
  --profile <name>   Databricks profile for MCP server env (default: first databricks-cli profile)
  --list             List installable skills and exit
  -h, --help         Show help

Examples:
  $(basename "$0")
  $(basename "$0") --profile my-profile
  $(basename "$0") databricks-dbsql databricks-genie
EOF
}

list_skills() {
  find "${SKILLS_SRC_DIR}" -mindepth 1 -maxdepth 1 -type d \
    ! -name "TEMPLATE" \
    -exec test -f "{}/SKILL.md" ';' -print \
    | xargs -n1 basename \
    | sort
}

detect_first_databricks_profile() {
  if ! command -v databricks >/dev/null 2>&1; then
    return 1
  fi

  local first_profile
  first_profile="$(
    databricks auth profiles --output json 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
    profiles = data.get("profiles") or []
    if profiles and isinstance(profiles[0], dict):
        name = profiles[0].get("name")
        if name:
            print(name)
except Exception:
    pass
'
  )"

  if [[ -n "${first_profile}" ]]; then
    printf "%s" "${first_profile}"
    return 0
  fi
  return 1
}

toml_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf "%s" "${s}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --list)
      list_skills
      exit 0
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      INSTALL_ALL=false
      SELECTED_SKILLS+=("$1")
      shift
      ;;
  esac
done

if [[ ! -d "${SKILLS_SRC_DIR}" ]]; then
  echo "Skills source not found: ${SKILLS_SRC_DIR}" >&2
  exit 1
fi

mkdir -p "${CODEX_SKILLS_DIR}"

if [[ "${INSTALL_ALL}" == "true" ]]; then
  mapfile -t SELECTED_SKILLS < <(list_skills)
fi

if [[ ${#SELECTED_SKILLS[@]} -eq 0 ]]; then
  echo "No skills selected." >&2
  exit 1
fi

if [[ -z "${PROFILE}" ]]; then
  if PROFILE="$(detect_first_databricks_profile)"; then
    echo "Using first Databricks CLI profile: ${PROFILE}"
  fi
fi

echo "Installing ${#SELECTED_SKILLS[@]} skill(s) into ${CODEX_SKILLS_DIR}"
for skill in "${SELECTED_SKILLS[@]}"; do
  src="${SKILLS_SRC_DIR}/${skill}"
  dst="${CODEX_SKILLS_DIR}/${skill}"
  if [[ ! -f "${src}/SKILL.md" ]]; then
    echo "Skipping '${skill}' (SKILL.md not found in ${src})" >&2
    continue
  fi
  rm -rf "${dst}"
  cp -R "${src}" "${dst}"
  echo "  - installed ${skill}"
done

mkdir -p "$(dirname "${PROJECT_CODEX_CONFIG}")"
touch "${PROJECT_CODEX_CONFIG}"

tmp_cfg="$(mktemp)"
awk '
BEGIN { skip = 0 }
{
  if ($0 ~ /^\[mcp_servers\.databricks\]$/ || $0 ~ /^\[mcp_servers\.databricks\.env\]$/) {
    skip = 1
    next
  }
  if (skip && $0 ~ /^\[/) {
    skip = 0
  }
  if (!skip) {
    print
  }
}
' "${PROJECT_CODEX_CONFIG}" > "${tmp_cfg}"

MCP_COMMAND="uv"
MCP_ARGS_1="run"
MCP_ARGS_2="--directory"
MCP_ARGS_3="${REPO_ROOT}/databricks-mcp-server"
MCP_ARGS_4="python"
MCP_ARGS_5="run_server.py"

if ! command -v uv >/dev/null 2>&1; then
  MCP_COMMAND="${PYTHON:-python3}"
  MCP_ARGS_1="${REPO_ROOT}/databricks-mcp-server/run_server.py"
  MCP_ARGS_2=""
  MCP_ARGS_3=""
  MCP_ARGS_4=""
  MCP_ARGS_5=""
fi

{
  echo ""
  echo "[mcp_servers.databricks]"
  echo "command = \"$(toml_escape "${MCP_COMMAND}")\""
  if [[ "${MCP_COMMAND}" == "uv" ]]; then
    echo "args = [\"$(toml_escape "${MCP_ARGS_1}")\", \"$(toml_escape "${MCP_ARGS_2}")\", \"$(toml_escape "${MCP_ARGS_3}")\", \"$(toml_escape "${MCP_ARGS_4}")\", \"$(toml_escape "${MCP_ARGS_5}")\"]"
  else
    echo "args = [\"$(toml_escape "${MCP_ARGS_1}")\"]"
  fi
  echo ""
  echo "[mcp_servers.databricks.env]"
  if [[ -n "${PROFILE}" ]]; then
    echo "DATABRICKS_CONFIG_PROFILE = \"$(toml_escape "${PROFILE}")\""
  fi
} >> "${tmp_cfg}"

mv "${tmp_cfg}" "${PROJECT_CODEX_CONFIG}"

echo ""
echo "Updated MCP config: ${PROJECT_CODEX_CONFIG}"
echo "Restart Codex to pick up newly installed skills and MCP config."
