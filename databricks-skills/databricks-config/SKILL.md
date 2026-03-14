---
name: databricks-config
description: "Manage Databricks workspace connections: check which workspace you're connected to, switch workspaces, list available workspaces, or authenticate to a new workspace."
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

## Common Issues

| Issue | Solution |
|-------|----------|
| **`manage_workspace` returns "no profiles found"** | Run `databricks auth login --host https://your-workspace.cloud.databricks.com` to create a profile in `~/.databrickscfg` |
| **Switch doesn't persist after restart** | Expected — switches are session-scoped. For permanent changes, set `DATABRICKS_HOST` / `DATABRICKS_TOKEN` env vars |
| **"Token expired" errors** | Re-authenticate with `databricks auth login`. OAuth tokens from `databricks auth login` auto-refresh; PATs do not |
| **Wrong workspace after switching** | Use `action="status"` to verify which workspace is active. The MCP server may have restarted, resetting the switch |
| **Multiple profiles for same host** | Use distinct profile names. The CLI picks the first matching host if no profile is specified |
| **`DATABRICKS_CONFIG_PROFILE` not respected** | Env vars override `~/.databrickscfg` defaults. Unset conflicting env vars: `DATABRICKS_HOST`, `DATABRICKS_TOKEN` |
