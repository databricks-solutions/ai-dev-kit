---
name: databricks-config
description: "Manage Databricks workspace connections: check current workspace, switch profiles, list available workspaces, or authenticate to a new workspace. Use when the user mentions \"switch workspace\", \"which workspace\", \"current profile\", \"databrickscfg\", \"connect to workspace\", or \"databricks auth\"."
---

Use the `manage_workspace` MCP tool for all workspace operations. Do NOT edit `~/.databrickscfg`, use Bash, or use the Databricks CLI.

## Steps

1. Call `ToolSearch` with query `select:mcp__databricks__manage_workspace` to load the tool.

2. Map user intent to action:
   - status / which workspace / current → `action="status"`
   - list / available workspaces → `action="list"`
   - switch to X → call `list` first to find the profile name, then `action="switch", profile="<name>"` (or `host="<url>"` if a URL was given)
   - login / connect / authenticate → `action="login", host="<url>"`

3. Call `mcp__databricks__manage_workspace` with the action and any parameters.

4. Present the result. For `status`/`switch`/`login`: show host, profile, username. For `list`: formatted table with the active profile marked.

> **Note:** The switch is session-scoped — it resets on MCP server restart. For permanent profile setup, use `databricks auth login -p <profile>` and update `~/.databrickscfg` with `cluster_id` or `serverless_compute_id = auto`.
