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
  """Return the set of tool names currently registered with the vendored MCP server."""
  import asyncio
  import sys
  from pathlib import Path

  # Ensure vendored packages win over any sibling-repo installs on sys.path.
  packages_dir = Path(__file__).resolve().parents[1] / 'packages'
  packages_root = str(packages_dir)
  if packages_root not in sys.path:
    sys.path.insert(0, packages_root)

  from databricks_agent_tools.server import mcp
  from databricks_agent_tools.tools import (  # noqa: F401
    agent_bricks,
    aibi_dashboards,
    apps,
    compute,
    file,
    genie,
    jobs,
    lakebase,
    pipelines,
    serving,
    sql,
    unity_catalog,
    vector_search,
    volume_files,
    workspace,
  )

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


def test_normalize_skill_name_migrates_legacy_names():
  """Legacy skill names from older installs map to databricks-agent-skills names."""
  sm = _load_skills_manager()
  assert sm.normalize_skill_name('databricks-spark-declarative-pipelines') == 'databricks-pipelines'
  assert sm.normalize_skill_name('databricks-lakebase-autoscale') == 'databricks-lakebase'
  assert sm.normalize_skill_name('databricks-bundles') == 'databricks-dabs'


def test_get_allowed_mcp_tools_honors_legacy_skill_names():
  """Enabled skills saved under legacy names still gate the renamed skill's tools."""
  sm = _load_skills_manager()
  all_tools = [
    'mcp__databricks__manage_pipeline',
    'mcp__databricks__execute_sql',
  ]
  allowed = sm.get_allowed_mcp_tools(
    all_tools,
    enabled_skills=['databricks-spark-declarative-pipelines'],
  )
  assert 'mcp__databricks__manage_pipeline' in allowed
  assert 'mcp__databricks__execute_sql' in allowed
