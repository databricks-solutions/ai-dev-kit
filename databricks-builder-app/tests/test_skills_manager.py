"""Tests for ``server.services.skills_manager``.

The module is loaded directly from its file path so we do not trigger
``server.services.__init__`` (which pulls in heavier services whose relative
imports only resolve when the full app is running).
"""

import importlib.util
from pathlib import Path


def _load_skills_manager():
  """Load skills_manager.py without importing the server.services package."""
  module_path = Path(__file__).resolve().parents[1] / 'server' / 'services' / 'skills_manager.py'
  spec = importlib.util.spec_from_file_location('skills_manager_under_test', module_path)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


def _load_live_mcp_tool_names() -> set[str]:
  """Return the set of tool names currently registered with the MCP server.

  Uses the same import/enumeration pattern as ``databricks_tools.py`` so the
  test reflects the tools the running app actually exposes.
  """
  import asyncio

  from databricks_mcp_server.server import mcp
  from databricks_mcp_server.tools import (  # noqa: F401
    compute,
    file,
    pipelines,
    sql,
  )

  tool_manager = getattr(mcp, '_tool_manager', None)
  registered = getattr(tool_manager, '_tools', None)
  if registered:
    return set(registered.keys())

  tools_list = asyncio.run(mcp.list_tools())
  return {t.name for t in tools_list}


def test_skill_tool_mapping_matches_registered_mcp_tools():
  """Every tool name in SKILL_TOOL_MAPPING must exist in the MCP server.

  Without this guard, the MCP server can rename/consolidate a tool while
  SKILL_TOOL_MAPPING keeps referring to the dead name. ``get_allowed_mcp_tools``
  then silently lets the new (unmapped) tool through even when the owning skill
  is disabled — the per-skill filter becomes a no-op.
  """
  sm = _load_skills_manager()
  live = _load_live_mcp_tool_names()
  stale: dict[str, list[str]] = {}
  for skill, names in sm.SKILL_TOOL_MAPPING.items():
    missing = [n for n in names if n not in live]
    if missing:
      stale[skill] = missing

  assert not stale, (
    f'SKILL_TOOL_MAPPING references tools that do not exist in the MCP server: '
    f'{stale}. Update the mapping or rename the server tool.'
  )


def test_get_allowed_mcp_tools_blocks_disabled_skill():
  """Disabling a skill must actually remove its mapped tools from the allowed set.

  Regression test for the drift bug: when SKILL_TOOL_MAPPING referred to legacy
  tool names (``list_jobs``, ``create_or_update_dashboard``, …) that no longer
  existed, this filter became a no-op because the real ``manage_*`` tools were
  never listed.
  """
  sm = _load_skills_manager()
  all_tools = [
    'mcp__databricks__manage_jobs',
    'mcp__databricks__manage_job_runs',
    'mcp__databricks__manage_dashboard',
    'mcp__databricks__execute_sql',  # not mapped to any skill — always allowed
  ]

  allowed = sm.get_allowed_mcp_tools(all_tools, enabled_skills=['databricks-aibi-dashboards'])

  assert 'mcp__databricks__manage_jobs' not in allowed
  assert 'mcp__databricks__manage_job_runs' not in allowed
  assert 'mcp__databricks__manage_dashboard' in allowed
  assert 'mcp__databricks__execute_sql' in allowed
