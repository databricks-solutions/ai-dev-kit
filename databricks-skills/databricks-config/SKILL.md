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
| **Switch doesn't persist after restart** | This is expected — switches are session-scoped. For permanent changes, edit `~/.databrickscfg` or set `DATABRICKS_HOST` / `DATABRICKS_TOKEN` env vars |
| **Wrong workspace after MCP server restart** | The server defaults to the first valid profile or env vars. Use `action="status"` to verify, then `action="switch"` to change |
| **Multiple profiles with same host** | Profile names must be unique. Use descriptive names like `dev-workspace` and `prod-workspace` |
| **Token expired / 401 errors** | Re-authenticate: `databricks auth login -p <profile>`. OAuth tokens expire; PATs may have been revoked |
| **`serverless_compute_id = auto` not working** | Ensure your workspace has serverless enabled. This setting tells the SDK to use serverless compute for `databricks-connect` sessions |
