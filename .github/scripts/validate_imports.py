"""Smoke test: verify all MCP tool modules can be imported without errors.

This catches broken imports, missing dependencies, and registration issues
that would prevent the MCP server from starting. Runs without a Databricks
workspace connection — only validates that the Python modules load cleanly.
"""

import importlib
import sys

TOOL_MODULES = [
    "databricks_mcp_server.tools.sql",
    "databricks_mcp_server.tools.compute",
    "databricks_mcp_server.tools.file",
    "databricks_mcp_server.tools.pipelines",
    "databricks_mcp_server.tools.jobs",
    "databricks_mcp_server.tools.agent_bricks",
    "databricks_mcp_server.tools.aibi_dashboards",
    "databricks_mcp_server.tools.serving",
    "databricks_mcp_server.tools.unity_catalog",
    "databricks_mcp_server.tools.volume_files",
    "databricks_mcp_server.tools.genie",
    "databricks_mcp_server.tools.manifest",
    "databricks_mcp_server.tools.vector_search",
    "databricks_mcp_server.tools.lakebase",
    "databricks_mcp_server.tools.user",
    "databricks_mcp_server.tools.apps",
    "databricks_mcp_server.tools.workspace",
]

CORE_MODULES = [
    "databricks_tools_core.auth",
    "databricks_tools_core.sql",
    "databricks_tools_core.agent_bricks",
    "databricks_tools_core.lakebase_autoscale",
]


def main():
    errors = []

    for module_name in CORE_MODULES + TOOL_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as e:
            errors.append((module_name, str(e)))

    if errors:
        print(f"FAILED: {len(errors)} module(s) failed to import:\n")
        for module_name, error in errors:
            print(f"  {module_name}: {error}")
        sys.exit(1)
    else:
        total = len(CORE_MODULES) + len(TOOL_MODULES)
        print(f"OK: All {total} modules imported successfully")


if __name__ == "__main__":
    main()
